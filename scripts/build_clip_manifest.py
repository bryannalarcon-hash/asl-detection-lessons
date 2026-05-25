"""Build a clip manifest (clip_path, gloss, split) for extract_keypoints.

PopSign tars extract to ``<work>/<sign>/<participant>.<id>-<sign>-<ts>-<take>.mp4``.
This walks the extracted tree and emits one JSONL row per clip. The ``split``
field is a placeholder ("train") here — the real train/val/test assignment is
done later by build_manifest_popsign over the extracted .npz keypoints; this
manifest only needs clip_path + gloss for the keypoint extractor.

``--max-per-sign`` caps clips per sign (a 96-class temporal classifier needs
far fewer than PopSign's ~700/sign, and extraction is the round's long pole).
Clips are taken in sorted order so the cap is deterministic.

  python3 scripts/build_clip_manifest.py --work-dir work \
      --out clips_manifest.jsonl --max-per-sign 300 [--signs dog cat ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True,
                    help="Dir containing <sign>/ subdirs of clips.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-per-sign", type=int, default=300)
    ap.add_argument("--signs", nargs="*", default=None,
                    help="Restrict to these sign dirs (default: all subdirs).")
    args = ap.parse_args()

    work = Path(args.work_dir)
    if not work.is_dir():
        raise SystemExit(f"work dir not found: {work}")

    sign_dirs = sorted(d for d in work.iterdir() if d.is_dir())
    if args.signs:
        wanted = set(args.signs)
        sign_dirs = [d for d in sign_dirs if d.name in wanted]

    rows = 0
    per_sign: dict[str, int] = {}
    with open(args.out, "w") as f:
        for d in sign_dirs:
            clips = sorted(p for p in d.iterdir()
                           if p.suffix.lower() in VIDEO_EXTS)
            if args.max_per_sign > 0:
                clips = clips[: args.max_per_sign]
            for clip in clips:
                f.write(json.dumps({
                    "clip_path": str(clip),
                    "gloss": d.name,
                    "split": "train",
                }) + "\n")
            per_sign[d.name] = len(clips)
            rows += len(clips)

    print(f"[clip-manifest] {rows} clips across {len(per_sign)} signs -> {args.out}")
    short = {s: n for s, n in per_sign.items() if n < 50}
    if short:
        print(f"[clip-manifest] WARN signs with <50 clips: {short}")


if __name__ == "__main__":
    main()
