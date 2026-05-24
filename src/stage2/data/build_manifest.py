"""Build the Net 4 training manifest from ASL Citizen splits.

ASL Citizen ships per-split CSVs (train/val/test) inside the same zip as
the videos. Each row maps a video file to its gloss and signer. We:

1. Read all three split CSVs.
2. Filter to clips whose gloss is in our 75-sign catalog (case-insensitive,
   underscored variants accepted — e.g. "thank you" matches THANK_YOU).
3. Emit one JSONL row per clip: {clip_id, clip_path, gloss, split,
   participant_id}. Glosses are written in UPPER_SNAKE_CASE matching the
   catalog so downstream code keys on a stable identifier.
4. Print per-gloss counts so we can sanity-check coverage before training.

Usage:
    python -m src.stage2.data.build_manifest \\
        --citizen-root data/asl_citizen/ASL_Citizen \\
        --sign-list data/signs/sign_list.json \\
        --out data/signs/manifest.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def normalise_gloss(text: str) -> str:
    """Map an ASL Citizen gloss to our UPPER_SNAKE_CASE form.

    ASL Citizen labels are lowercase with spaces and occasional punctuation.
    Our catalog uses UPPER_SNAKE: "thank you" -> "THANK_YOU",
    "you're welcome" -> "YOU_WELCOME". Aliases handled below.
    """
    t = text.strip().lower()
    # Strip ASL Citizen suffixes like "1", "2" when used for sign variants:
    # "blue1" -> "blue". Keep numeric numerals ("one", "two") intact.
    t = re.sub(r"(\D)\d+$", r"\1", t)
    # Replace non-alnum with underscores.
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = t.strip("_")
    return t.upper()


# Curated alias map: ASL Citizen → our catalog UPPER_SNAKE form.
# Update as we discover divergences. Multi-word target glosses go here.
GLOSS_ALIASES: dict[str, str] = {
    # Direct ASL Citizen → our catalog token. Keys are values AFTER
    # normalise_gloss (UPPER_SNAKE, numeric variant suffixes stripped).
    "BYE": "GOODBYE",
    "THANKYOU": "THANK_YOU",
    "THANK_YOU": "THANK_YOU",
    "WELCOME": "YOU_WELCOME",
    "YOURE_WELCOME": "YOU_WELCOME",
    "YOU_RE_WELCOME": "YOU_WELCOME",
    "YOUREWELCOME": "YOU_WELCOME",
    "SHOP": "STORE",
    "AGAIN": "REPEAT",
    "NICETOMEETYOU": "NICE_TO_MEET_YOU",
    "NICE_TO_MEET_YOU": "NICE_TO_MEET_YOU",
}


def resolve_gloss(raw: str, catalog: set[str]) -> str | None:
    """Try a few normalisations to map raw label → catalog token."""
    direct = normalise_gloss(raw)
    if direct in catalog:
        return direct
    aliased = GLOSS_ALIASES.get(direct)
    if aliased and aliased in catalog:
        return aliased
    return None


def find_csv(candidates: list[Path]) -> Path | None:
    for c in candidates:
        if c.exists():
            return c
    return None


def detect_columns(row_keys: list[str]) -> dict[str, str]:
    """Pick (video, gloss, participant) column names from a CSV header.

    ASL Citizen sometimes uses 'Video file' / 'Gloss' / 'Participant ID';
    other re-hosts use lower-snake. Be liberal in what we accept.
    """
    keymap: dict[str, str] = {}
    lower = {k.lower().strip(): k for k in row_keys}
    for cand in ("video file", "video_file", "video", "file", "filename",
                 "video filename"):
        if cand in lower:
            keymap["video"] = lower[cand]
            break
    for cand in ("gloss", "label", "sign", "word"):
        if cand in lower:
            keymap["gloss"] = lower[cand]
            break
    for cand in ("participant id", "participant_id", "signer", "signer id",
                 "participant"):
        if cand in lower:
            keymap["participant"] = lower[cand]
            break
    return keymap


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--citizen-root", required=True,
                   help="Directory containing splits/{train,val,test}.csv "
                        "and videos/ (post-unzip).")
    p.add_argument("--sign-list", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--video-subdir", default="videos",
                   help="Subdir under --citizen-root holding the .mp4 files")
    p.add_argument("--splits-subdir", default="splits")
    p.add_argument("--require-files", action="store_true",
                   help="Skip rows whose video file is not on disk. Off by "
                        "default so the manifest can be built before "
                        "selective extraction.")
    args = p.parse_args()

    catalog = set(json.loads(Path(args.sign_list).read_text())["glosses_flat"])
    print(f"[init] {len(catalog)} target glosses", flush=True)

    citizen = Path(args.citizen_root)
    splits_dir = citizen / args.splits_subdir
    videos_dir = citizen / args.video_subdir
    if not splits_dir.is_dir():
        # Try common layout variants.
        for alt in ("splits", "metadata", ""):
            candidate = citizen / alt
            if (candidate / "train.csv").exists():
                splits_dir = candidate
                break
    print(f"[init] splits_dir={splits_dir}", flush=True)
    print(f"[init] videos_dir={videos_dir}", flush=True)

    counts_per_gloss: dict[str, int] = defaultdict(int)
    per_split_counts: Counter[str] = Counter()
    unmatched_raw: Counter[str] = Counter()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_fh = out_path.open("w")
    written = 0

    for split in ("train", "val", "test"):
        csv_path = find_csv([splits_dir / f"{split}.csv",
                             splits_dir / f"{split.upper()}.csv"])
        if csv_path is None:
            print(f"[warn] no {split}.csv at {splits_dir}", flush=True)
            continue
        print(f"[scan] {csv_path}", flush=True)
        with csv_path.open(newline="") as f:
            reader = csv.DictReader(f)
            keymap = detect_columns(reader.fieldnames or [])
            if "video" not in keymap or "gloss" not in keymap:
                print(f"[err] columns not detected in {csv_path}; "
                      f"got fieldnames={reader.fieldnames}", flush=True)
                continue
            for row in reader:
                raw_gloss = row.get(keymap["gloss"], "")
                resolved = resolve_gloss(raw_gloss, catalog)
                if resolved is None:
                    unmatched_raw[raw_gloss] += 1
                    continue
                video_name = row.get(keymap["video"], "").strip()
                if not video_name:
                    continue
                clip_path = videos_dir / video_name
                if args.require_files and not clip_path.exists():
                    matches = list(videos_dir.rglob(video_name))
                    if not matches:
                        continue
                    clip_path = matches[0]
                participant = (row.get(keymap.get("participant", ""), "")
                               if "participant" in keymap else "")
                clip_id = Path(video_name).stem
                entry = {
                    "clip_id": clip_id,
                    "clip_path": str(clip_path),
                    "gloss": resolved,
                    "split": split,
                    "participant_id": participant,
                }
                out_fh.write(json.dumps(entry) + "\n")
                counts_per_gloss[resolved] += 1
                per_split_counts[split] += 1
                written += 1
    out_fh.close()

    print(f"\n[done] wrote {written} entries to {out_path}")
    print(f"[done] per-split: {dict(per_split_counts)}")
    print("\n[coverage] per-gloss counts:")
    missing = [g for g in catalog if g not in counts_per_gloss]
    present = sorted(counts_per_gloss.items(), key=lambda kv: -kv[1])
    for g, c in present:
        print(f"  {g:<22s} {c}")
    if missing:
        print(f"\n[gap] {len(missing)} glosses missing from ASL Citizen:")
        for g in sorted(missing):
            print(f"  {g}")
    if unmatched_raw:
        print(f"\n[unmatched] top 20 raw labels we couldn't map:")
        for raw, c in unmatched_raw.most_common(20):
            print(f"  {raw!r:<30s} {c}")


if __name__ == "__main__":
    main()
