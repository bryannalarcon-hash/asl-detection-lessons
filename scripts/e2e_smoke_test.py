"""End-to-end smoke test for the full Stage 1 + Stage 2 pipeline.

Picks N test-split clips from the manifest at random, runs the full
4-net pipeline on each, and reports per-clip top-3 + a confusion summary.
Exits non-zero if top-3 accuracy drops below `--min-top3`.

Usage:
    python -m scripts.e2e_smoke_test \\
        --manifest data/signs/manifest.jsonl \\
        --net1 results/v3/net1_v3_1/best.pt \\
        --net2 results/v3/net2_v3_1/best.pt \\
        --net3 results/v3/net3_v1/best.pt \\
        --net4 results/v4/best.pt \\
        --num-clips 30 \\
        --min-top3 0.6 \\
        --device cuda
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.stage2.predict_clip import (
    load_net1, load_net2, load_net3, load_net4, predict,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--net1", required=True)
    p.add_argument("--net2", required=True)
    p.add_argument("--net3", required=True)
    p.add_argument("--net4", required=True)
    p.add_argument("--num-clips", type=int, default=30)
    p.add_argument("--split", default="test")
    p.add_argument("--min-top3", type=float, default=0.5,
                   help="Minimum top-3 accuracy required to pass.")
    p.add_argument("--device", default=None)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    import torch
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}", flush=True)

    entries = []
    with open(args.manifest) as f:
        for line in f:
            e = json.loads(line)
            if e.get("split") == args.split:
                entries.append(e)
    random.seed(args.seed)
    random.shuffle(entries)
    entries = entries[: args.num_clips]
    print(f"[init] sampling {len(entries)} clips from split={args.split}",
          flush=True)

    net1, net1_k, net1_kslice = load_net1(args.net1, device)
    net2, net2_meta = load_net2(args.net2, device)
    net3 = load_net3(args.net3, device)
    net4, gloss_to_idx, net4_data_cfg = load_net4(args.net4, device)

    top1_hits = top3_hits = 0
    miss_pairs: list[tuple[str, str]] = []
    per_clip: list[dict] = []
    for i, e in enumerate(entries):
        result = predict(Path(e["clip_path"]), net1, net1_k, net1_kslice,
                         net2, net2_meta, net3, net4, gloss_to_idx,
                         net4_data_cfg, device, topk=3)
        if "error" in result:
            per_clip.append({**result, "gt": e["gloss"]})
            continue
        gt = e["gloss"]
        topk_glosses = [t["gloss"] for t in result["topk"]]
        top1 = topk_glosses[0] == gt
        top3 = gt in topk_glosses
        if top1:
            top1_hits += 1
        else:
            miss_pairs.append((gt, topk_glosses[0]))
        if top3:
            top3_hits += 1
        per_clip.append({
            "clip_id": e["clip_id"],
            "gt": gt,
            "topk": topk_glosses,
            "probs": [round(t["prob"], 3) for t in result["topk"]],
            "top1": top1, "top3": top3,
            "timing_ms": result["timing_ms"],
        })
        if (i + 1) % 5 == 0 or i == len(entries) - 1:
            print(f"  {i+1}/{len(entries)} top1={top1_hits} top3={top3_hits}",
                  flush=True)

    n = len(entries)
    top1_acc = top1_hits / max(n, 1)
    top3_acc = top3_hits / max(n, 1)
    print(f"\n=== E2E SMOKE RESULT ===")
    print(f"  N clips      : {n}")
    print(f"  Top-1 accuracy: {top1_acc:.3f}  ({top1_hits}/{n})")
    print(f"  Top-3 accuracy: {top3_acc:.3f}  ({top3_hits}/{n})")
    if miss_pairs:
        from collections import Counter
        c = Counter(miss_pairs).most_common(10)
        print(f"  Top misses (gt -> pred):")
        for (gt, pred), n_ in c:
            print(f"    {gt!s:>22s} -> {pred!s:<22s} {n_}x")

    out = {
        "n": n,
        "top1": top1_acc,
        "top3": top3_acc,
        "miss_pairs_top10": [(gt, pr, c_) for (gt, pr), c_ in
                              (__import__("collections").Counter(miss_pairs)
                               .most_common(10))],
        "per_clip": per_clip,
    }
    out_path = REPO_ROOT / "results" / "v4" / "e2e_smoke_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved -> {out_path}")
    if top3_acc < args.min_top3:
        print(f"\n[FAIL] Top-3 {top3_acc:.3f} < required {args.min_top3:.3f}")
        sys.exit(1)
    print(f"\n[PASS] Top-3 {top3_acc:.3f} >= required {args.min_top3:.3f}")


if __name__ == "__main__":
    main()
