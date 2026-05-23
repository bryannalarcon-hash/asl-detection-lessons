"""Modal app: Net 1 v3.1 finetune (face+body K=7) on A100-40GB.

Run:
    modal run --detach modal_apps/train_net1_v3_1.py::train

v3.1 changes vs train_net1.py:
- Config: stage1_v2_facebody_v3_1.yaml (60 ep finetune, coco 70 / mpii 30 mix).
- Starts from existing /vol/checkpoints/stage1_v2_facebody/best.pt (the v3
  Net 1 result, PCK 0.71). Saves into /vol/checkpoints/stage1_v2_facebody_v3_1/
  so the v3 baseline is preserved.
- Adds MPII Human Pose download step.
- A100-40GB instead of 80GB (~36% cheaper; finetune fits easily in 40 GB).
- Volume: asl-net1-vol (shared with the v3 run; COCO + FreiHAND already there).
"""
from __future__ import annotations

import modal
from pathlib import Path


app = modal.App("asl-net1-v3-1")

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
        "scipy",
    )
    .add_local_dir("src", remote_path="/workspace/src")
    .add_local_dir("scripts", remote_path="/workspace/scripts")
    .add_local_dir("configs", remote_path="/workspace/configs")
    .add_local_file("requirements.txt", remote_path="/workspace/requirements.txt")
)

volume = modal.Volume.from_name("asl-net1-vol", create_if_missing=True)


@app.function(
    image=image,
    gpu="A100-40GB",
    timeout=10800,
    volumes={"/vol": volume},
    secrets=[
        modal.Secret.from_name("asl-kaggle", required_keys=["KAGGLE_USERNAME", "KAGGLE_KEY"]),
    ],
)
def train():
    import os
    import subprocess
    import sys
    import threading
    import time

    os.chdir("/workspace")
    sys.path.insert(0, "/workspace")

    os.makedirs("/vol/data", exist_ok=True)
    os.makedirs("/vol/cache/stage1", exist_ok=True)
    os.makedirs("/vol/checkpoints/stage1_v2_facebody_v3_1", exist_ok=True)
    os.makedirs("/vol/logs", exist_ok=True)

    for src, link in (
        ("/vol/data", "/workspace/data"),
        ("/vol/checkpoints", "/workspace/checkpoints"),
        ("/vol/logs", "/workspace/logs"),
    ):
        if not os.path.islink(link) and not os.path.exists(link):
            os.symlink(src, link)

    os.makedirs("/root/.kaggle", exist_ok=True)
    with open("/root/.kaggle/kaggle.json", "w") as f:
        f.write(f'{{"username":"{os.environ["KAGGLE_USERNAME"]}","key":"{os.environ["KAGGLE_KEY"]}"}}')
    os.chmod("/root/.kaggle/kaggle.json", 0o600)

    mpii_ready = Path("/vol/data/mpii/images").exists() and \
        any(Path("/vol/data/mpii/images").iterdir()) and \
        Path("/vol/data/mpii/annotations").exists()
    if not mpii_ready:
        print("[modal] downloading MPII Human Pose...", flush=True)
        env = os.environ.copy()
        env["DATA_DIR"] = "/vol/data"
        subprocess.run(["bash", "scripts/download_mpii.sh"], env=env, check=True)
        volume.commit()

    cache_root = Path("/vol/cache/stage1")
    coco_cache_ok = (cache_root / "coco_train" / "meta.json").exists()
    if not coco_cache_ok:
        print("[modal] re-priming COCO cache via preprocess_cache.py...", flush=True)
        subprocess.run(
            ["python", "scripts/preprocess_cache.py",
             "--config", "configs/stage1_v2_facebody_v3_1.yaml",
             "--out", str(cache_root),
             "--cache-size", "256"],
            check=True,
        )
        volume.commit()

    mpii_cache_ok = (cache_root / "mpii_train" / "meta.json").exists()
    if not mpii_cache_ok:
        print("[modal] building MPII preprocess cache...", flush=True)
        subprocess.run(
            ["python", "scripts/preprocess_cache.py",
             "--config", "configs/stage1_v2_facebody_v3_1.yaml",
             "--sources", "mpii",
             "--out", str(cache_root),
             "--cache-size", "256"],
            check=True,
        )
        volume.commit()

    starting_ckpt = Path("/vol/checkpoints/stage1_v2_facebody/best.pt")
    if not starting_ckpt.exists():
        raise SystemExit(f"v3 Net 1 best.pt missing at {starting_ckpt} — run train_net1.py first")
    last_v31 = Path("/vol/checkpoints/stage1_v2_facebody_v3_1/last.pt")
    resume_path = str(last_v31) if last_v31.exists() else str(starting_ckpt)
    print(f"[modal] starting Net 1 v3.1 from {resume_path}", flush=True)

    proc = subprocess.Popen(
        ["python", "-u", "-m", "src.stage1.train_v2_facebody",
         "--config", "configs/stage1_v2_facebody_v3_1.yaml",
         "--cache-root", "/vol/cache/stage1",
         "--resume-from", resume_path],
        cwd="/workspace",
    )

    def _periodic_commit():
        while proc.poll() is None:
            time.sleep(300)
            try:
                volume.commit()
                print(f"[modal] periodic commit @ {time.strftime('%H:%M:%S')}", flush=True)
            except Exception as e:
                print(f"[modal] commit error: {e}", flush=True)

    t = threading.Thread(target=_periodic_commit, daemon=True)
    t.start()

    rc = proc.wait()
    print(f"[modal] training exit code: {rc}", flush=True)
    volume.commit()
    if rc != 0:
        raise SystemExit(f"training failed with exit code {rc}")


if __name__ == "__main__":
    pass
