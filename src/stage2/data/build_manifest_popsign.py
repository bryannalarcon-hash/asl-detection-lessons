"""Build the Net 4 PopSign manifest + sign_list.json.

PopSign v1.0 (CC BY 4.0, ~803 clips/sign post manual-review) is the single
source for the ASL-1 core vocabulary. The vocabulary is drawn FROM PopSign's
250-word CDI set so every word clears the 500-real-clips bar with no
augmentation. The word list (PopSign sign-tar names, by category) lives at
``configs/popsign_vocab.json``.

This builder produces two artifacts:
  1. ``sign_list.json`` — catalog in PopSign-native UPPER_SNAKE form, with a
     ``glosses_flat`` list and per-category ``lessons`` (same shape the Net 4
     trainer + ``build_gloss_to_idx`` already consume). num_classes is derived
     from ``len(glosses_flat)`` so the trainer needs no hardcoded count.
  2. ``manifest.jsonl`` — one row per extracted clip:
     {clip_id, clip_path, gloss, split, source}. Built from a directory of
     extracted keypoint .npz files (``--kpt-dir``), one .npz per clip named
     ``<sign>_<...>.npz`` (PopSign tar entries keep the sign in the stem).
     Clips with no matching .npz on disk are skipped with a warning, so this
     can run incrementally as signs are extracted on the GPU box.

If ``--kpt-dir`` is missing or empty, the builder still writes
``sign_list.json`` and an EMPTY ``manifest.jsonl`` (degrades gracefully), and
prints the per-sign extraction plan instead of failing.

PopSign acquisition + extraction sequence (run on the rented GPU box,
200 GB disk; peak disk per sign ~5 GB — download, extract, keypoint, rm):

    SIGN=dog
    BASE=https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train
    curl -sI "$BASE/$SIGN.tar"                         # expect HTTP 200 + length
    curl -O  "$BASE/$SIGN.tar"
    mkdir -p work && tar -xf "$SIGN.tar" -C work/
    python3 -m src.stage2.data.extract_keypoints \\
        --manifest <per-sign clip list> \\
        --net1 results/v3/net1_v3_1/best.pt \\
        --net2 results/v3/net2_v3_1/best.pt \\
        --net3 results/v3/net3_v2/best.pt \\
        --out data/signs/popsign_kpt_cache/ --max-frames 64 --delete-after
    rm -rf "$SIGN.tar" work/*                           # free disk before next sign

Loop that over every sign in ``glosses_flat`` (use the
``popsign_tar_aliases`` map for semantic approximations such as
CITY->downtown, SCHOOL->playgroundschool). Then run THIS builder against
``--kpt-dir data/signs/popsign_kpt_cache`` to emit the manifest.

Usage:
    python3 -m src.stage2.data.build_manifest_popsign \\
        --vocab configs/popsign_vocab.json \\
        --kpt-dir data/signs/popsign_kpt_cache \\
        --sign-list-out data/signs/popsign_sign_list.json \\
        --manifest-out data/signs/popsign_manifest.jsonl \\
        --val-frac 0.1 --test-frac 0.1 --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def gloss_in_npz(npz_path: Path) -> str | None:
    """The PopSign sign token the extractor stored in the .npz at extraction
    time (authoritative; the clip filename carries the sign in the MIDDLE, not
    as a prefix, so filename matching alone misses it). Lowercased token."""
    try:
        with np.load(npz_path, allow_pickle=False) as d:
            if "gloss" in d:
                return str(d["gloss"]).strip().lower()
    except Exception:
        return None
    return None


def to_gloss(sign: str) -> str:
    """PopSign tar name -> our catalog UPPER_SNAKE token (e.g. icecream->ICECREAM)."""
    return re.sub(r"[^a-z0-9]+", "_", sign.strip().lower()).strip("_").upper()


def load_vocab(vocab_path: Path) -> tuple[list[str], dict[str, list[str]], dict[str, str]]:
    """Returns (flat_signs, categories, tar_aliases).

    flat_signs preserves category order; duplicates removed (first wins).
    """
    data = json.loads(vocab_path.read_text())
    categories: dict[str, list[str]] = data["categories"]
    tar_aliases: dict[str, str] = data.get("popsign_tar_aliases", {})
    flat: list[str] = []
    seen: set[str] = set()
    for signs in categories.values():
        for s in signs:
            if s not in seen:
                seen.add(s)
                flat.append(s)
    return flat, categories, tar_aliases


def write_sign_list(flat_signs: list[str], categories: dict[str, list[str]],
                    out_path: Path) -> list[str]:
    """Write sign_list.json (glosses_flat + lessons). Returns glosses_flat."""
    glosses_flat = [to_gloss(s) for s in flat_signs]
    lessons = []
    for i, (cat, signs) in enumerate(categories.items(), 1):
        lessons.append({
            "title": f"Lesson {i}: {cat}",
            "category": cat,
            "signs": [to_gloss(s) for s in signs],
        })
    out = {
        "total": len(glosses_flat),
        "source": "PopSign v1.0",
        "lessons": lessons,
        "glosses_flat": glosses_flat,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    return glosses_flat


def sign_for_clip(clip_id: str, gloss_for_token: dict[str, str]) -> str | None:
    """Map a clip-id stem to a catalog gloss by matching its sign prefix.

    PopSign clip stems carry the sign (e.g. ``dog_1234_signerA``). We match
    the longest catalog token that the stem starts with (so ``icecream``
    wins over a hypothetical ``ice``). Returns the catalog gloss or None.
    """
    stem = clip_id.lower()
    best: str | None = None
    best_len = -1
    for token, gloss in gloss_for_token.items():
        if (stem == token or stem.startswith(token + "_")
                or stem.startswith(token + "-")):
            if len(token) > best_len:
                best, best_len = gloss, len(token)
    return best


def assign_split(rng: random.Random, val_frac: float, test_frac: float) -> str:
    r = rng.random()
    if r < test_frac:
        return "test"
    if r < test_frac + val_frac:
        return "val"
    return "train"


def print_plan(flat_signs: list[str], tar_aliases: dict[str, str]) -> None:
    base = "https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train"
    print("\n[plan] per-sign download/extract sequence (run on GPU box):")
    print(f"[plan] {len(flat_signs)} signs; peak disk ~5GB each; rm after each.")
    for s in flat_signs:
        tar = tar_aliases.get(s, s)
        note = f"  (alias of {s})" if tar != s else ""
        print(f"  {base}/{tar}.tar -> extract -> keypoints -> rm{note}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--vocab", default="configs/popsign_vocab.json")
    p.add_argument("--kpt-dir", default="data/signs/popsign_kpt_cache",
                   help="Directory of extracted .npz files. Missing/empty is "
                        "tolerated — manifest is then empty and a plan prints.")
    p.add_argument("--sign-list-out", default="data/signs/popsign_sign_list.json")
    p.add_argument("--manifest-out", default="data/signs/popsign_manifest.jsonl")
    p.add_argument("--val-frac", type=float, default=0.1)
    p.add_argument("--test-frac", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    vocab_path = Path(args.vocab)
    if not vocab_path.exists():
        raise SystemExit(f"vocab not found: {vocab_path}")
    flat_signs, categories, tar_aliases = load_vocab(vocab_path)
    glosses_flat = write_sign_list(flat_signs, categories,
                                   Path(args.sign_list_out))
    print(f"[init] vocab={len(glosses_flat)} signs -> "
          f"sign_list={args.sign_list_out}", flush=True)

    # token (popsign tar/lowercase) -> catalog gloss. Include alias targets so
    # extracted files named by the PopSign tar (e.g. downtown) still map back
    # to the intended catalog gloss (e.g. CITY) when present.
    gloss_for_token: dict[str, str] = {}
    for s in flat_signs:
        gloss_for_token[s] = to_gloss(s)
        tar = tar_aliases.get(s)
        if tar:
            gloss_for_token[tar] = to_gloss(s)

    out_path = Path(args.manifest_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kpt_dir = Path(args.kpt_dir)
    npz_files = sorted(kpt_dir.glob("*.npz")) if kpt_dir.is_dir() else []

    if not npz_files:
        out_path.write_text("")  # empty manifest — degrade gracefully
        print(f"[warn] no .npz in {kpt_dir} — wrote EMPTY manifest "
              f"{out_path}. Extract clips first.", flush=True)
        print_plan(flat_signs, tar_aliases)
        return

    rng = random.Random(args.seed)
    counts: dict[str, int] = defaultdict(int)
    per_split: Counter[str] = Counter()
    n_skip = 0
    written = 0
    with out_path.open("w") as fh:
        for npz in npz_files:
            clip_id = npz.stem
            # Prefer the gloss token the extractor stored inside the .npz
            # (authoritative); fall back to parsing the filename stem.
            token = gloss_in_npz(npz)
            gloss = gloss_for_token.get(token) if token else None
            if gloss is None:
                gloss = sign_for_clip(clip_id, gloss_for_token)
            if gloss is None:
                n_skip += 1
                continue
            split = assign_split(rng, args.val_frac, args.test_frac)
            fh.write(json.dumps({
                "clip_id": clip_id,
                "clip_path": str(npz),
                "kpt_path": str(npz),
                "gloss": gloss,
                "split": split,
                "source": "popsign",
            }) + "\n")
            counts[gloss] += 1
            per_split[split] += 1
            written += 1

    print(f"\n[done] wrote {written} entries to {out_path} "
          f"({n_skip} unmapped .npz skipped)", flush=True)
    print(f"[done] per-split: {dict(per_split)}", flush=True)
    missing = [g for g in glosses_flat if counts[g] == 0]
    below500 = [(g, counts[g]) for g in glosses_flat
                if 0 < counts[g] < 500]
    if missing:
        print(f"[gap] {len(missing)} signs with NO clips: "
              f"{', '.join(missing)}", flush=True)
    if below500:
        print(f"[gap] {len(below500)} signs below 500 real clips "
              f"(drop or backfill per sourcing doc):", flush=True)
        for g, c in sorted(below500, key=lambda kv: kv[1]):
            print(f"  {g:<16s} {c}", flush=True)


if __name__ == "__main__":
    main()
