"""Modal app: train Net 3 (hand landmark specialist) — P1 + P2.

Run after Net 1 + Net 2 are done:
    modal run --detach modal_apps/train_net3.py::train_phase1
    # When phase 1 completes:
    modal run --detach modal_apps/train_net3.py::train_phase2

Or run the full sequence:
    modal run --detach modal_apps/train_net3.py::train_both_phases

Volume `asl-net3-vol` layout:
  /vol/data/FreiHAND_pub_v2/      — 5 GB
  /vol/data/interhand/            — ~85 GB images + ~5 GB annotations
  /vol/checkpoints/landmark_p1/   — Phase 1 checkpoints
  /vol/checkpoints/landmark_p2/   — Phase 2 checkpoints
  /vol/cache/net2_predictions.json — Net 2 bbox preds for P2 mix
  /vol/logs/                      — Training logs
"""
from __future__ import annotations

import modal
from pathlib import Path


app = modal.App("asl-net3-retrain")

# Image: PyTorch + DALI for GPU JPEG decode + numba + cv2
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("unzip", "wget", "curl", "git", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch==2.6.0",
        "torchvision",
        "numpy",
        "opencv-python-headless",
        "pillow",
        "tqdm",
        "pyyaml",
        "kaggle",
        "gdown",
        "albumentations",
        "kornia",
        "numba",
        "nvidia-dali-cuda120",
    )
    .add_local_dir("src", remote_path="/workspace/src")
    .add_local_dir("scripts", remote_path="/workspace/scripts")
    .add_local_dir("configs", remote_path="/workspace/configs")
    .add_local_file("requirements.txt", remote_path="/workspace/requirements.txt")
    # Ship Net 2's best.pt for phase-2 bbox prediction
    .add_local_file("results/v3/net2/best.pt", remote_path="/workspace/results/v3/net2/best.pt")
)

volume = modal.Volume.from_name("asl-net3-vol", create_if_missing=True)


def _setup_workspace():
    """Common bootstrap: set up symlinks + kaggle creds. Runs inside the container."""
    import os
    os.chdir("/workspace")
    os.makedirs("/vol/data", exist_ok=True)
    os.makedirs("/vol/checkpoints/landmark_p1", exist_ok=True)
    os.makedirs("/vol/checkpoints/landmark_p2", exist_ok=True)
    os.makedirs("/vol/logs", exist_ok=True)
    os.makedirs("/vol/cache", exist_ok=True)
    for src, link in (
        ("/vol/data", "/workspace/data"),
        ("/vol/checkpoints", "/workspace/checkpoints"),
        ("/vol/logs", "/workspace/logs"),
    ):
        if not os.path.islink(link) and not os.path.exists(link):
            os.symlink(src, link)
    # Kaggle
    os.makedirs("/root/.kaggle", exist_ok=True)
    with open("/root/.kaggle/kaggle.json", "w") as f:
        f.write(f'{{"username":"{os.environ["KAGGLE_USERNAME"]}","key":"{os.environ["KAGGLE_KEY"]}"}}')
    os.chmod("/root/.kaggle/kaggle.json", 0o600)


def _download_datasets():
    """Download FreiHAND + InterHand2.6M (5fps split) — idempotent."""
    import os, subprocess
    from pathlib import Path

    if not Path("/vol/data/FreiHAND_pub_v2").exists():
        print("[modal] downloading FreiHAND...", flush=True)
        subprocess.run(
            "cd /vol/data && kaggle datasets download danieldelro/freihand --unzip",
            shell=True, check=True,
        )

    interhand_ok = (Path("/vol/data/interhand/annotations/train").exists() and
                    any(Path("/vol/data/interhand/annotations/train").glob("*.json")))
    if not interhand_ok:
        print("[modal] downloading InterHand2.6M (~85 GB images + 5 GB annotations)...", flush=True)
        env = os.environ.copy()
        env["DATA_DIR"] = "/vol/data"
        subprocess.run(
            ["bash", "-c", """
set -euo pipefail
DATA_DIR=/vol/data
INTERHAND_BASE="https://fb-baas-f32eacb9-8abb-11eb-b2b8-4857dd089e15.s3.amazonaws.com/InterHand2.6M/InterHand2.6M.images.5.fps.v1.0"
mkdir -p "$DATA_DIR/interhand"
( cd "$DATA_DIR/interhand" \
    && curl -sSL "${INTERHAND_BASE}/index.html" \
         | grep -oE 'InterHand2\\.6M\\.images\\.5\\.fps\\.v1\\.0\\.tar\\.part[a-z]+' \
         | sort -u > chunks.txt \
    && echo "  chunks: $(wc -l < chunks.txt)" \
    && xargs -n 1 -P 4 -I {} wget -q -c "${INTERHAND_BASE}/{}" < chunks.txt \
    && (
        for part in $(ls InterHand2.6M.images.5.fps.v1.0.tar.part* | sort); do
            cat "$part" || exit 1
            rm "$part" || exit 1
        done
    ) | tar -xf - \
    && rm -f chunks.txt )

# Annotations from gdrive folder
INTERHAND_ANN_GDRIVE_FOLDER="${INTERHAND_ANN_GDRIVE_FOLDER:-12RNG9slv9i_TsXSoZ6pQAq-Fa98eGLoy}"
cd "$DATA_DIR/interhand"
mkdir -p annotations_raw annotations/train annotations/val annotations/test
gdown --folder "$INTERHAND_ANN_GDRIVE_FOLDER" -O annotations_raw
find annotations_raw -type f \\( -name '*.tar.gz' -o -name '*.tgz' \\) | while read -r tb; do
    tar -xzf "$tb" -C "$(dirname "$tb")"
    rm "$tb"
done
find annotations_raw -type f -name 'InterHand2.6M_train_*.json' -exec cp -t annotations/train {} +
find annotations_raw -type f -name 'InterHand2.6M_val_*.json'   -exec cp -t annotations/val {} +
find annotations_raw -type f -name 'InterHand2.6M_test_*.json'  -exec cp -t annotations/test {} +
rm -rf annotations_raw
"""],
            env=env, check=True,
        )


@app.function(
    image=image, gpu="A10G", timeout=86400,
    volumes={"/vol": volume},
    secrets=[modal.Secret.from_name("asl-kaggle", required_keys=["KAGGLE_USERNAME", "KAGGLE_KEY"])],
)
def train_phase1():
    """Net 3 Phase 1: 70 epochs on GT bboxes + augmentation."""
    import os, subprocess
    import sys
    _setup_workspace()
    _download_datasets()
    volume.commit()

    sys.path.insert(0, "/workspace")
    resume_arg = []
    last = Path("/vol/checkpoints/landmark_p1/last.pt")
    if last.exists():
        # train_v3_landmark doesn't currently expose --resume-from, so just rely
        # on `best.pt` (it'll start from scratch; phase 1 has no warm-start).
        pass

    print("[modal] starting Net 3 Phase 1 (DALI, BF16, A10G, 70 epochs)...", flush=True)
    # Override checkpoint dir to land in the volume
    cfg_path = "/tmp/p1_config.yaml"
    subprocess.run(
        ["bash", "-c",
         f"sed 's|checkpoints/stage1_v3_landmark|/vol/checkpoints/landmark_p1|' "
         f"configs/stage1_v3_landmark_phase1.yaml > {cfg_path}"],
        check=True,
    )

    import threading, time
    proc = subprocess.Popen(
        ["python", "-u", "-m", "src.stage1.train_v3_landmark",
         "--config", cfg_path, "--use-dali"],
        cwd="/workspace",
    )

    def _periodic_commit():
        while proc.poll() is None:
            time.sleep(900)  # 15 min commits
            try:
                volume.commit()
                print(f"[modal] periodic commit @ {time.strftime('%H:%M:%S')}", flush=True)
            except Exception as e:
                print(f"[modal] commit error: {e}", flush=True)

    t = threading.Thread(target=_periodic_commit, daemon=True)
    t.start()
    rc = proc.wait()
    volume.commit()
    print(f"[modal] Net 3 P1 done rc={rc}", flush=True)
    return rc


@app.function(
    image=image, gpu="A10G", timeout=86400,
    volumes={"/vol": volume},
    secrets=[modal.Secret.from_name("asl-kaggle", required_keys=["KAGGLE_USERNAME", "KAGGLE_KEY"])],
)
def train_phase2():
    """Net 3 Phase 2: fine-tune from P1 best with Net 2 bbox mix-in."""
    import os, subprocess, sys
    _setup_workspace()
    _download_datasets()
    volume.commit()
    sys.path.insert(0, "/workspace")

    # Generate Net 2 bbox predictions for P2 mix-in if not cached
    pred_path = Path("/vol/cache/net2_predictions.json")
    if not pred_path.exists():
        print("[modal] generating Net 2 bbox predictions for P2 mix...", flush=True)
        subprocess.run(
            ["python", "-u", "scripts/predict_bboxes_for_phase2.py",
             "--palm", "/workspace/results/v3/net2/best.pt",
             "--out", str(pred_path)],
            cwd="/workspace", check=True,
        )
        volume.commit()

    # Patch P2 config: phase2_bbox_cache + path remap + resume from P1 best
    p1_best = Path("/vol/checkpoints/landmark_p1/best.pt")
    if not p1_best.exists():
        raise SystemExit("P1 best.pt not found — run train_phase1 first.")

    cfg_path = "/tmp/p2_config.yaml"
    subprocess.run(
        ["bash", "-c", f"""
sed -e 's|checkpoints/stage1_v3_landmark|/vol/checkpoints/landmark_p2|' \\
    -e 's|phase2_bbox_cache: null|phase2_bbox_cache: /vol/cache/net2_predictions.json|' \\
    -e 's|phase2_mix_prob: 0.0|phase2_mix_prob: 0.3|' \\
    configs/stage1_v3_landmark_phase2.yaml > {cfg_path}
"""], check=True,
    )

    print("[modal] starting Net 3 Phase 2 fine-tune...", flush=True)
    import threading, time
    proc = subprocess.Popen(
        ["python", "-u", "-m", "src.stage1.train_v3_landmark",
         "--config", cfg_path, "--use-dali"],
        cwd="/workspace",
    )

    def _periodic_commit():
        while proc.poll() is None:
            time.sleep(900)
            try:
                volume.commit()
                print(f"[modal] periodic commit @ {time.strftime('%H:%M:%S')}", flush=True)
            except Exception as e:
                print(f"[modal] commit error: {e}", flush=True)

    t = threading.Thread(target=_periodic_commit, daemon=True)
    t.start()
    rc = proc.wait()
    volume.commit()
    print(f"[modal] Net 3 P2 done rc={rc}", flush=True)
    return rc


@app.function(image=image, gpu="A10G", timeout=86400,
              volumes={"/vol": volume},
              secrets=[modal.Secret.from_name("asl-kaggle", required_keys=["KAGGLE_USERNAME", "KAGGLE_KEY"])])
def train_both_phases():
    """Sequential P1 → P2 in a single function call."""
    train_phase1.local()
    train_phase2.local()


@app.function(image=image, volumes={"/vol": volume}, timeout=300)
def status():
    """Status: latest P1 + P2 metrics if present."""
    import json, os
    out = {}
    for phase in ("p1", "p2"):
        mp = f"/vol/checkpoints/landmark_{phase}/metrics.jsonl"
        if os.path.exists(mp):
            with open(mp) as f:
                lines = f.readlines()
            out[phase] = {"epochs": len(lines)}
            if lines:
                out[phase]["last"] = json.loads(lines[-1])
    return out


@app.local_entrypoint()
def main():
    train_phase1.remote()
