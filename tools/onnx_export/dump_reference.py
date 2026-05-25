"""Dump parity ground-truth fixtures for the WebGPU port (workstream A).

Two kinds of JSON fixtures land in frontend/tests/cv/fixtures/:

  per-net IO (net{1,2,3,4}_io.json)
    Fixed-seed input + the PyTorch forward output, using the SAME seeds and
    interface as tools/onnx_export/export_all.py. The verifier (V1) feeds the
    input through ORT Web and asserts the output matches within 1e-3. This
    catches export drift independent of the TS pre/post-processing.

  full pipeline (pipeline_<clip>.json)
    The complete predict_clip output on data/lesson_videos/{mom,red}.mp4 with
    the v3 stack: the per-frame 49-keypoint sequence + visibility (Stage 1
    ground truth for B's parity), and the final top-3 glosses+probs (Stage 2
    ground truth for C/V2). gloss_to_idx ordering is embedded so TS maps
    indices the same way.

Floats are JSON numbers (full precision); arrays are stored flat with an
explicit shape so the TS side can reshape deterministically.

Run from repo root (CPU box):
    python3 tools/onnx_export/dump_reference.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for export_all

from src.stage2.data.extract_keypoints import (  # noqa: E402
    extract_one_clip, load_net1, load_net2, load_net3,
)
from src.stage2.data.sign_dataset import (  # noqa: E402
    _build_per_frame_features, window_to_model_input,
)
from src.stage2.predict_clip import load_net4, predict  # noqa: E402
from export_all import (  # noqa: E402
    Net2Adapter, Net3Adapter, Net4Adapter,
    NET1_CKPT, NET2_CKPT, NET3_CKPT, NET4_CKPT,
    NET1_INPUT, NET2_INPUT, NET3_CROP, NET4_C, NET4_T,
)

FIX_DIR = REPO_ROOT / "frontend" / "tests" / "cv" / "fixtures"
CLIPS = {
    "mom": REPO_ROOT / "data" / "lesson_videos" / "mom.mp4",
    "red": REPO_ROOT / "data" / "lesson_videos" / "red.mp4",
}
DEVICE = "cpu"


def _arr(a: np.ndarray) -> dict:
    """Serialise an ndarray as {shape, data(flat, row-major)}."""
    a = np.ascontiguousarray(a)
    return {"shape": list(a.shape), "data": a.ravel().tolist()}


def _write(name: str, payload: dict) -> None:
    path = FIX_DIR / name
    path.write_text(json.dumps(payload))
    size_kb = path.stat().st_size / 1024
    print(f"  wrote {path.relative_to(REPO_ROOT)}  ({size_kb:.1f} KB)")


# --------------------------------------------------------------------------
# Per-net IO fixtures (same seeds as export_all.py).
# --------------------------------------------------------------------------
def dump_net1_io() -> None:
    model, k, kslice = load_net1(str(NET1_CKPT), DEVICE)
    rng = np.random.default_rng(1)
    x = rng.standard_normal((1, 3, NET1_INPUT, NET1_INPUT)).astype(np.float32)
    with torch.no_grad():
        y = model(torch.from_numpy(x)).cpu().numpy()
    _write("net1_io.json", {
        "net": "net1", "seed": 1, "k": int(k), "keypoint_slice": kslice,
        "inputs": {"input": _arr(x)},
        "outputs": {"heatmaps": _arr(y)},
    })


def dump_net2_io() -> None:
    model, meta = load_net2(str(NET2_CKPT), DEVICE)
    adapter = Net2Adapter(model).eval()
    rng = np.random.default_rng(2)
    x = rng.standard_normal((1, 3, NET2_INPUT, NET2_INPUT)).astype(np.float32)
    with torch.no_grad():
        cls, box = adapter(torch.from_numpy(x))
    _write("net2_io.json", {
        "net": "net2", "seed": 2, "n_kpts": int(meta["n_kpts"]),
        "n_anchors": int(cls.shape[1]),
        "anchors_xywh": _arr(meta["anchors_xywh"].cpu().numpy()),
        "inputs": {"input": _arr(x)},
        "outputs": {"cls": _arr(cls.cpu().numpy()),
                    "box": _arr(box.cpu().numpy())},
    })


def dump_net3_io() -> None:
    model, head_type = load_net3(str(NET3_CKPT), DEVICE)
    adapter = Net3Adapter(model).eval()
    rng = np.random.default_rng(3)
    x = rng.standard_normal((1, 3, NET3_CROP, NET3_CROP)).astype(np.float32)
    with torch.no_grad():
        coords = adapter(torch.from_numpy(x)).cpu().numpy()
    _write("net3_io.json", {
        "net": "net3", "seed": 3, "head_type": head_type,
        "inputs": {"input": _arr(x)},
        "outputs": {"coords": _arr(coords)},
    })


def dump_net4_io() -> None:
    model, gloss_to_idx, _ = load_net4(str(NET4_CKPT), DEVICE)
    adapter = Net4Adapter(model).eval()
    rng = np.random.default_rng(4)
    feats = rng.standard_normal((1, NET4_T, NET4_C)).astype(np.float32)
    mask = np.ones((1, NET4_T), dtype=np.float32)
    mask[0, :40] = 0.0
    with torch.no_grad():
        logits = adapter(torch.from_numpy(feats),
                         torch.from_numpy(mask)).cpu().numpy()
    _write("net4_io.json", {
        "net": "net4", "seed": 4, "num_classes": len(gloss_to_idx),
        "inputs": {"features": _arr(feats), "key_padding_mask": _arr(mask)},
        "outputs": {"logits": _arr(logits)},
    })


# --------------------------------------------------------------------------
# Full predict_clip pipeline fixtures.
# --------------------------------------------------------------------------
def dump_pipeline(nets) -> None:
    (net1, net1_k, net1_kslice, net2, net2_meta, net3, net3_head,
     net4, gloss_to_idx, net4_cfg) = nets
    idx_to_gloss = [None] * len(gloss_to_idx)
    for g, i in gloss_to_idx.items():
        idx_to_gloss[i] = g

    for tag, clip in CLIPS.items():
        if not clip.exists():
            print(f"  [skip] {clip} missing")
            continue
        # Stage 1 ground truth: the per-frame 49-kpt sequence.
        result = extract_one_clip(net1, net1_k, net1_kslice, net2, net2_meta,
                                  net3, net3_head, clip, DEVICE,
                                  max_frames=net4_cfg["max_frames"])
        if result is None:
            print(f"  [fail] extraction failed for {clip}")
            continue
        kpts, vis, W, H = result

        # Intermediate feature tensor + window (lets C parity-test the feature
        # build + window without re-deriving from kpts).
        feat = _build_per_frame_features(
            kpts, vis, W, H,
            include_visibility=net4_cfg["include_visibility"],
            include_lag1=net4_cfg["include_lag1"],
            include_lag2=net4_cfg["include_lag2"])
        feat_win, mask = window_to_model_input(feat, net4_cfg["max_frames"])

        # Stage 2 ground truth: the final top-3 prediction (full predict path).
        pred = predict(clip, net1, net1_k, net1_kslice, net2, net2_meta,
                       net3, net3_head, net4, gloss_to_idx, net4_cfg,
                       DEVICE, topk=3)

        _write(f"pipeline_{tag}.json", {
            "clip": clip.name,
            "width": int(W), "height": int(H),
            "n_frames": int(kpts.shape[0]),
            "keypoints": _arr(kpts.astype(np.float32)),     # (T, 49, 2)
            "visibility": _arr(vis.astype(np.float32)),     # (T, 49)
            "features": _arr(feat.astype(np.float32)),      # (T, 343)
            "features_windowed": _arr(feat_win),            # (64, 343)
            "key_padding_mask": _arr(mask.astype(np.float32)),  # (64,)
            "topk": pred["topk"],
            "data_cfg": {
                "max_frames": net4_cfg["max_frames"],
                "include_visibility": net4_cfg["include_visibility"],
                "include_lag1": net4_cfg["include_lag1"],
                "include_lag2": net4_cfg["include_lag2"],
            },
        })


def main() -> None:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    print(f"dumping fixtures to {FIX_DIR.relative_to(REPO_ROOT)}\n")

    print("per-net IO fixtures:")
    dump_net1_io()
    dump_net2_io()
    dump_net3_io()
    dump_net4_io()

    print("\nloading the full v3 stack for pipeline fixtures...")
    net1, net1_k, net1_kslice = load_net1(str(NET1_CKPT), DEVICE)
    net2, net2_meta = load_net2(str(NET2_CKPT), DEVICE)
    net3, net3_head = load_net3(str(NET3_CKPT), DEVICE)
    net4, gloss_to_idx, net4_cfg = load_net4(str(NET4_CKPT), DEVICE)

    # gloss_to_idx ordering (the 96-class label map) — TS maps indices via this.
    _write("gloss_to_idx.json", {"gloss_to_idx": gloss_to_idx,
                                  "num_classes": len(gloss_to_idx)})

    print("\nfull pipeline fixtures (predict_clip on lesson clips):")
    dump_pipeline((net1, net1_k, net1_kslice, net2, net2_meta, net3,
                   net3_head, net4, gloss_to_idx, net4_cfg))
    print("\nDONE")


if __name__ == "__main__":
    main()
