"""Measure the accuracy cost of Net1 frame-striding (the PoC speed knob).

The browser PoC runs Net1 (face/body, the 94% WebGPU cost) only every Nth
frame and HOLDS the body/face keypoints (global slots 42..48) from the nearest
computed frame; hands (slots 0..41, from Net2/Net3) run every frame. This script
SIMULATES that on the cached test-split keypoints and re-runs Net4, so we see
the open-vocab top-1/top-3 hit per stride without touching the browser.

Faithful to the PoC `net1Batched`: sel = [0, stride, 2*stride, ...] + last frame;
non-selected frames copy slots 42..48 from the nearest selected frame.

Run (CPU):  python3 scripts/eval_net1_stride.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.stage2.data.sign_dataset import (  # noqa: E402
    _build_per_frame_features, window_to_model_input,
)
from src.stage2.predict_clip import load_net4  # noqa: E402

NET4_CKPT = REPO_ROOT / "results/v3/net4_popsign_125word/best.pt"
KPT_DIR = REPO_ROOT / "results/v3/net4_kpt_125word/popsign_kpt_cache"
VOCAB = REPO_ROOT / "configs/popsign_vocab.json"
SEED = 42
STRIDES = [1, 2, 4, 8, 16, 32]
BODY_FACE = slice(42, 49)  # Net1 slots (RIGHT/LEFT hands occupy 0..41)


def build_test_split() -> list[dict]:
    tmp = Path(tempfile.mkdtemp(prefix="net1stride_"))
    manifest = tmp / "m.jsonl"
    cmd = [
        sys.executable, "-m", "src.stage2.data.build_manifest_popsign",
        "--vocab", str(VOCAB), "--kpt-dir", str(KPT_DIR),
        "--sign-list-out", str(tmp / "signs.json"),
        "--manifest-out", str(manifest),
        "--val-frac", "0.1", "--test-frac", "0.1", "--seed", str(SEED),
    ]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True, capture_output=True)
    rows = []
    with open(manifest) as f:
        for line in f:
            e = json.loads(line)
            if e.get("split") == "test":
                rows.append(e)
    return rows


def apply_net1_stride(kpts: np.ndarray, stride: int) -> np.ndarray:
    """Hold body/face slots (42..48) from the nearest strided frame."""
    if stride <= 1:
        return kpts
    T = kpts.shape[0]
    out = kpts.copy()
    sel = list(range(0, T, stride))
    if sel[-1] != T - 1:
        sel.append(T - 1)
    sel_arr = np.array(sel)
    sel_set = set(sel)
    for f in range(T):
        if f in sel_set:
            continue
        nf = int(sel_arr[np.argmin(np.abs(sel_arr - f))])
        out[f, BODY_FACE, :] = out[nf, BODY_FACE, :]
    return out


def main() -> None:
    device = "cpu"
    net4, gloss_to_idx, data_cfg = load_net4(str(NET4_CKPT), device)
    window = int(data_cfg.get("max_frames", 64))
    print(f"[init] {len(gloss_to_idx)} classes, window={window}", flush=True)

    rows = build_test_split()
    print(f"[init] test clips: {len(rows)}", flush=True)

    def classify(feat: np.ndarray) -> np.ndarray:
        f32, mask = window_to_model_input(feat.astype(np.float32), window)
        x = torch.from_numpy(f32).unsqueeze(0)
        m = torch.from_numpy(mask).unsqueeze(0)
        with torch.no_grad():
            logits = net4(x, key_padding_mask=m)
            return torch.softmax(logits[0].float(), -1).numpy()

    tally = {s: {"top1": 0, "top3": 0} for s in STRIDES}
    n = 0
    for e in rows:
        gloss = e["gloss"]
        if gloss not in gloss_to_idx:
            continue
        with np.load(e["kpt_path"]) as d:
            kpts = d["keypoints"].astype(np.float32)
            vis = d["visibility"].astype(np.float32)
            W, H = int(d["width"]), int(d["height"])
        tidx = gloss_to_idx[gloss]
        n += 1
        for s in STRIDES:
            k = apply_net1_stride(kpts, s)
            feat = _build_per_frame_features(
                k, vis, W, H,
                include_visibility=data_cfg["include_visibility"],
                include_lag1=data_cfg["include_lag1"],
                include_lag2=data_cfg["include_lag2"],
            )
            probs = classify(feat)
            order = np.argsort(-probs)
            rank = int(np.where(order == tidx)[0][0])
            if rank == 0:
                tally[s]["top1"] += 1
            if rank < 3:
                tally[s]["top3"] += 1

    print("\n" + "=" * 56)
    print(f"Net1-stride accuracy on the 125/word test split (n={n})")
    print("constrained whole-clip top-k; body/face held, hands every frame")
    print("=" * 56)
    print(f"{'stride':>6} | {'top-1':>7} | {'top-3':>7} | {'d-top1':>7}")
    print("-" * 40)
    base1 = tally[1]["top1"] / n
    for s in STRIDES:
        t1 = tally[s]["top1"] / n
        t3 = tally[s]["top3"] / n
        print(f"{s:>6} | {t1*100:6.1f}% | {t3*100:6.1f}% | {(t1-base1)*100:+6.1f}")
    print("=" * 56, flush=True)


if __name__ == "__main__":
    main()
