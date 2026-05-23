"""Modal app: retrain Net 1 (v2 KeypointDetector, face+body only) on A100-80GB.

Run:
    modal run modal_apps/train_net1.py::train

Or deploy + invoke:
    modal deploy modal_apps/train_net1.py
    modal run --detach modal_apps/train_net1.py::train

The function uses a persistent Modal Volume `asl-net1-vol`:
  - /vol/data       — downloaded datasets (COCO + FreiHAND only)
  - /vol/cache      — preprocess_cache.py output (keypoint .npy + image .npy)
  - /vol/checkpoints — training checkpoints (best.pt, epoch_NNN.pt, last.pt)
  - /vol/logs       — training logs

Setup is idempotent: re-runs detect already-downloaded data + cache and skip.
Training resumes from checkpoints/stage1_v2_facebody/last.pt if present.
"""
from __future__ import annotations

import modal
from pathlib import Path


app = modal.App("asl-net1-retrain")

# Image: official PyTorch CUDA + project deps.
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
    )
    .add_local_dir("src", remote_path="/workspace/src")
    .add_local_dir("scripts", remote_path="/workspace/scripts")
    .add_local_dir("configs", remote_path="/workspace/configs")
    .add_local_file("requirements.txt", remote_path="/workspace/requirements.txt")
)

volume = modal.Volume.from_name("asl-net1-vol", create_if_missing=True)


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=86400,  # 24h
    volumes={"/vol": volume},
    secrets=[
        modal.Secret.from_name("asl-kaggle", required_keys=["KAGGLE_USERNAME", "KAGGLE_KEY"]),
    ],
    # Detached run will keep going if you disconnect.
)
def train():
    import os
    import subprocess
    import sys

    os.chdir("/workspace")
    sys.path.insert(0, "/workspace")

    os.makedirs("/vol/data", exist_ok=True)
    os.makedirs("/vol/cache", exist_ok=True)
    os.makedirs("/vol/checkpoints/stage1_v2_facebody", exist_ok=True)
    os.makedirs("/vol/logs", exist_ok=True)

    # Symlinks so the source tree paths resolve to the volume.
    for src, link in (
        ("/vol/data", "/workspace/data"),
        ("/vol/checkpoints", "/workspace/checkpoints"),
        ("/vol/logs", "/workspace/logs"),
    ):
        if not os.path.islink(link) and not os.path.exists(link):
            os.symlink(src, link)

    # Configure kaggle
    os.makedirs("/root/.kaggle", exist_ok=True)
    with open("/root/.kaggle/kaggle.json", "w") as f:
        f.write(f'{{"username":"{os.environ["KAGGLE_USERNAME"]}","key":"{os.environ["KAGGLE_KEY"]}"}}')
    os.chmod("/root/.kaggle/kaggle.json", 0o600)

    # 1) Download COCO + FreiHAND (skip HaGRID + InterHand — Net 1 doesn't need them)
    coco_ready = Path("/vol/data/coco/train2017").exists() and \
        any(Path("/vol/data/coco/train2017").iterdir())
    frei_ready = Path("/vol/data/FreiHAND_pub_v2").exists()
    if not (coco_ready and frei_ready):
        print("[modal] downloading datasets...", flush=True)
        env = os.environ.copy()
        env["DATA_DIR"] = "/vol/data"
        # download_v3_data.sh handles COCO + FreiHAND in its first two blocks;
        # we use --net2-only to skip InterHand. HaGRID is still downloaded but
        # not used; skip the HaGRID block by intercepting the script with a wrapper.
        subprocess.run(
            ["bash", "-c", """
set -euo pipefail
DATA_DIR=/vol/data
# COCO
if [ ! -f "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" ]; then
    mkdir -p "$DATA_DIR/coco/annotations" "$DATA_DIR/coco"
    cd "$DATA_DIR/coco/annotations" && gdown 1thErEToRbmM9uLNi1JXXfOsaS5VK2FXf -O coco_wholebody_train_v1.0.json
    cd /workspace
    python scripts/split_train_val.py \
        --in "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" \
        --train-out "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" \
        --val-out "$DATA_DIR/coco/annotations/coco_wholebody_val_v1.0.json"
fi
if [ ! -d "$DATA_DIR/coco/train2017" ] || [ -z "$(find "$DATA_DIR/coco/train2017" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ]; then
    cd "$DATA_DIR/coco"
    wget -q -c http://images.cocodataset.org/zips/train2017.zip
    unzip -q -o train2017.zip
    rm train2017.zip
    cd /workspace
fi
# FreiHAND via Kaggle
if [ ! -d "$DATA_DIR/FreiHAND_pub_v2" ]; then
    cd "$DATA_DIR"
    kaggle datasets download danieldelro/freihand --unzip
    cd /workspace
fi
echo "datasets ready"
"""],
            env=env,
            check=True,
        )
        volume.commit()

    # 2) Preprocess cache (image_size=256 to match config). Idempotent.
    cache_ready = Path("/vol/cache/stage1/coco_train/meta.json").exists() and \
                  Path("/vol/cache/stage1/freihand_train/meta.json").exists()
    if not cache_ready:
        print("[modal] building preprocess cache...", flush=True)
        subprocess.run(
            ["python", "scripts/preprocess_cache.py",
             "--config", "configs/stage1_v2_facebody.yaml",
             "--out", "/vol/cache/stage1",
             "--cache-size", "256"],
            check=True,
        )
        volume.commit()

    # 3) Train. Resume from last.pt if it exists.
    resume_arg = []
    last_pt = Path("/vol/checkpoints/stage1_v2_facebody/last.pt")
    if last_pt.exists():
        resume_arg = ["--resume-from", str(last_pt)]
        print(f"[modal] resuming from {last_pt}", flush=True)
    print("[modal] starting Net 1 face+body training (210 epochs, BF16, NHWC, fused AdamW)...", flush=True)
    proc = subprocess.Popen(
        ["python", "-u", "-m", "src.stage1.train_v2_facebody",
         "--config", "configs/stage1_v2_facebody.yaml",
         "--cache-root", "/vol/cache/stage1",
         *resume_arg],
        cwd="/workspace",
    )
    # Periodic commit of checkpoints to volume while training runs.
    import threading
    import time

    def _periodic_commit():
        while proc.poll() is None:
            time.sleep(600)  # commit every 10 min
            try:
                volume.commit()
                print(f"[modal] periodic commit @ {time.strftime('%H:%M:%S')}", flush=True)
            except Exception as e:
                print(f"[modal] commit error: {e}", flush=True)

    t = threading.Thread(target=_periodic_commit, daemon=True)
    t.start()

    rc = proc.wait()
    volume.commit()
    print(f"[modal] training done rc={rc}", flush=True)
    return rc


@app.function(image=image, volumes={"/vol": volume}, timeout=300)
def status():
    """Quick status check — last metrics line + latest checkpoint."""
    import json
    import os
    metrics_p = "/vol/checkpoints/stage1_v2_facebody/metrics.jsonl"
    out = {"metrics_path": metrics_p}
    if os.path.exists(metrics_p):
        with open(metrics_p) as f:
            lines = f.readlines()
        out["epochs_completed"] = len(lines)
        if lines:
            out["last"] = json.loads(lines[-1])
    ckpt_dir = "/vol/checkpoints/stage1_v2_facebody"
    if os.path.exists(ckpt_dir):
        out["checkpoints"] = sorted(os.listdir(ckpt_dir))
    return out


@app.local_entrypoint()
def main():
    """Default entrypoint — kicks off training."""
    train.remote()
