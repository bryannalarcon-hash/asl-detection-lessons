"""End-to-end sign prediction on a single video clip.

Pipeline:
    video.mp4 -> Net 1 + Net 2 + Net 3 (per-frame keypoints)
              -> per-frame feature vector (coords + visibility + lag deltas)
              -> Net 4 (sign classifier)
              -> softmax top-k

Used by the e2e smoke test and by the streamlit demo's offline scoring
path. Live webcam inference runs the same code on a frame buffer.

Usage:
    python -m src.stage2.predict_clip \\
        --clip data/signs/clips/test.mp4 \\
        --net1 results/v3/net1_v3_1/best.pt \\
        --net2 results/v3/net2_v3_1/best.pt \\
        --net3 results/v3/net3_v1/best.pt \\
        --net4 results/v4/best.pt \\
        --topk 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.stage2.data.extract_keypoints import (
    extract_one_clip, load_net1, load_net2, load_net3,
)
from src.stage2.data.sign_dataset import (
    _build_per_frame_features, feature_dim, window_to_model_input,
)
from src.stage2.models.sign_classifier import SignClassifier


def load_net4(ckpt_path: str, device: str
              ) -> tuple[SignClassifier, dict[str, int], dict]:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    cfg = ckpt.get("config", {}) or {}
    gloss_to_idx = ckpt.get("gloss_to_idx") or {}
    if not gloss_to_idx:
        raise ValueError("Net 4 checkpoint missing gloss_to_idx — re-save "
                         "with the current trainer to embed it.")
    model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    data_cfg = cfg.get("data", {}) if isinstance(cfg, dict) else {}
    inc_vis = bool(data_cfg.get("include_visibility", True))
    inc_lag1 = bool(data_cfg.get("include_lag1", True))
    inc_lag2 = bool(data_cfg.get("include_lag2", True))
    in_channels = feature_dim(include_visibility=inc_vis,
                              include_lag1=inc_lag1, include_lag2=inc_lag2)
    # gloss_to_idx is the ground truth for class count — the training config's
    # num_classes may have been stale (catalog grew from 75 to 90 mid-session).
    model = SignClassifier(
        in_channels=in_channels,
        num_classes=len(gloss_to_idx),
        dim=int(model_cfg.get("dim", 192)),
        kernel=int(model_cfg.get("kernel", 17)),
        drop_path=0.0,
        late_dropout_p=float(model_cfg.get("late_dropout_p", 0.8)),
        late_dropout_start_step=int(model_cfg.get("late_dropout_start_step", 0)),
    ).to(device).eval()
    model.load_state_dict(state, strict=False)
    return model, gloss_to_idx, {
        "include_visibility": inc_vis,
        "include_lag1": inc_lag1,
        "include_lag2": inc_lag2,
        "max_frames": int(data_cfg.get("max_frames", 64)),
    }


def predict(clip_path: Path, net1, net1_k, net1_kslice, net2, net2_meta,
            net3, net3_head_type, net4, gloss_to_idx, net4_data_cfg,
            device: str, topk: int = 3) -> dict:
    t_extract = time.time()
    result = extract_one_clip(net1, net1_k, net1_kslice, net2, net2_meta,
                              net3, net3_head_type, clip_path, device,
                              max_frames=net4_data_cfg["max_frames"])
    if result is None:
        return {"clip": str(clip_path), "error": "extraction failed"}
    kpts, vis, W, H = result
    t_feat = time.time()
    feat = _build_per_frame_features(
        kpts, vis, W, H,
        include_visibility=net4_data_cfg["include_visibility"],
        include_lag1=net4_data_cfg["include_lag1"],
        include_lag2=net4_data_cfg["include_lag2"],
    )
    T = feat.shape[0]
    feat, mask = window_to_model_input(feat, net4_data_cfg["max_frames"])
    x = torch.from_numpy(feat).unsqueeze(0).to(device)
    m = torch.from_numpy(mask).unsqueeze(0).to(device)
    t_classify = time.time()
    with torch.no_grad():
        logits = net4(x, key_padding_mask=m)
        probs = torch.softmax(logits[0].float(), dim=-1).cpu().numpy()
    t_end = time.time()

    idx_to_gloss = {v: k for k, v in gloss_to_idx.items()}
    top_idx = np.argsort(-probs)[:topk]
    return {
        "clip": str(clip_path),
        "topk": [
            {"rank": i + 1, "gloss": idx_to_gloss[int(j)],
             "prob": float(probs[int(j)])}
            for i, j in enumerate(top_idx)
        ],
        "kpts_visible_per_frame": float(vis.sum(axis=1).mean()),
        "n_frames_extracted": int(T),
        "timing_ms": {
            "extract": round((t_feat - t_extract) * 1000, 1),
            "features": round((t_classify - t_feat) * 1000, 1),
            "classify": round((t_end - t_classify) * 1000, 1),
            "total": round((t_end - t_extract) * 1000, 1),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clip", required=True)
    p.add_argument("--net1", required=True)
    p.add_argument("--net2", required=True)
    p.add_argument("--net3", required=True)
    p.add_argument("--net4", required=True)
    p.add_argument("--topk", type=int, default=3)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}", flush=True)

    net1, net1_k, net1_kslice = load_net1(args.net1, device)
    net2, net2_meta = load_net2(args.net2, device)
    net3, net3_head_type = load_net3(args.net3, device)
    net4, gloss_to_idx, net4_data_cfg = load_net4(args.net4, device)
    print(f"[init] all four nets loaded; {len(gloss_to_idx)} classes",
          flush=True)

    result = predict(Path(args.clip), net1, net1_k, net1_kslice, net2,
                     net2_meta, net3, net3_head_type, net4, gloss_to_idx,
                     net4_data_cfg, device, topk=args.topk)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
