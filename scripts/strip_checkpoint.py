"""Strip optimizer/scheduler state from a training checkpoint for export.

Training checkpoints carry Adam moment buffers (roughly 2x the weight size)
that never ship to the browser or inference. This keeps only the keys the
inference loaders read (model weights plus light metadata) and writes a
`*_export.pt` next to the source.

  python3 scripts/strip_checkpoint.py results/v3/net1_v3_1/best.pt [more.pt ...]

Pass --inplace to overwrite the source instead of writing a sibling export.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

KEEP_KEYS = ("model", "epoch", "metrics", "config", "gloss_to_idx", "classes",
             "num_classes", "head_type")


def strip_one(src: Path, inplace: bool) -> tuple[float, float, Path]:
    ckpt = torch.load(src, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict) or "model" not in ckpt:
        raise SystemExit(f"{src}: not a dict checkpoint with a 'model' key")
    lean = {k: ckpt[k] for k in KEEP_KEYS if k in ckpt}
    dst = src if inplace else src.with_name(f"{src.stem}_export{src.suffix}")
    torch.save(lean, dst)
    src_mb = src.stat().st_size / 1e6
    dst_mb = dst.stat().st_size / 1e6
    return src_mb, dst_mb, dst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoints", nargs="+", type=Path)
    ap.add_argument("--inplace", action="store_true")
    args = ap.parse_args()
    for src in args.checkpoints:
        if not src.exists():
            print(f"[skip] {src} does not exist", file=sys.stderr)
            continue
        src_mb, dst_mb, dst = strip_one(src, args.inplace)
        print(f"[strip] {src.name}: {src_mb:.1f}MB -> {dst_mb:.1f}MB  ({dst})")


if __name__ == "__main__":
    main()
