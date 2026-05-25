"""Grab one reference demonstration clip per sign for the lesson UI.

Streams each PopSign per-sign tar and extracts ONLY the first .mp4 (the clip
sits at the start of the tar), so we download ~one clip (~5 MB), not the whole
1-3 GB tar. Saves to data/lesson_videos/<gloss>.mp4. License: PopSign is
CC BY 4.0 -- attribute "PopSign (Georgia Tech)" wherever these are shown.

  python3 scripts/grab_lesson_videos.py [--vocab configs/popsign_vocab.json] \
      [--out data/lesson_videos] [--limit N]

Tolerant: skips signs whose tar is missing/unreachable with a warning.
"""
from __future__ import annotations

import argparse
import json
import tarfile
import urllib.request
from pathlib import Path

BASE = "https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train"


def flatten_vocab(vocab_path: Path) -> list[str]:
    d = json.loads(vocab_path.read_text())
    aliases = d.get("popsign_tar_aliases", {})
    seen: set[str] = set()
    out: list[str] = []
    for signs in d["categories"].values():
        for s in signs:
            tar = aliases.get(s, s)
            if tar not in seen:
                seen.add(tar)
                out.append(tar)
    return out


def grab_one(sign: str, out_dir: Path) -> bool:
    dst = out_dir / f"{sign}.mp4"
    if dst.exists() and dst.stat().st_size > 1000:
        return True
    url = f"{BASE}/{sign}.tar"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Streaming mode 'r|' reads sequentially; we break after the first
            # .mp4 so only ~one clip's bytes are pulled off the socket.
            with tarfile.open(fileobj=resp, mode="r|") as tf:
                for m in tf:
                    if m.isfile() and m.name.lower().endswith(".mp4"):
                        src = tf.extractfile(m)
                        if src is None:
                            continue
                        dst.write_bytes(src.read())
                        return dst.stat().st_size > 1000
    except Exception as exc:  # noqa: BLE001
        print(f"[grab] WARN {sign}: {exc}")
        return False
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", default="configs/popsign_vocab.json")
    ap.add_argument("--out", default="data/lesson_videos")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    signs = flatten_vocab(Path(args.vocab))
    if args.limit:
        signs = signs[: args.limit]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = miss = 0
    for i, sign in enumerate(signs, 1):
        if grab_one(sign, out_dir):
            ok += 1
        else:
            miss += 1
        if i % 10 == 0 or i == len(signs):
            mb = sum(f.stat().st_size for f in out_dir.glob("*.mp4")) / 1e6
            print(f"[grab] {i}/{len(signs)} ok={ok} miss={miss} total={mb:.0f}MB",
                  flush=True)
    print(f"[grab] DONE ok={ok} miss={miss} -> {out_dir}")


if __name__ == "__main__":
    main()
