"""Constrained-target eval of Net 4 the way the app actually uses it.

The pilot never asks Net 4 "what sign is this?" (open-vocab top-1). In a
lesson it asks "did the learner produce THIS target sign?" — constrained
verification against one known target. This script measures that:

  ACCEPT RATE (recall)  — correct-target trials that reach `verified`.
  FALSE-ACCEPT RATE     — wrong-target trials that wrongly reach `verified`.
  OOD REJECTION = 1-FAR — the ml-handoff.md v2 gate wants >=90%.

It drives the SAME `SignVerifier` (UNMODIFIED) the demo wires up, with the
SAME injected `classify` callable as the demo's `_net4_classify` (pad/
subsample to the trained window via `window_to_model_input`, softmax). The
test split is recreated deterministically by running the manifest builder
(`build_manifest_popsign`, seed 42, val/test 0.1/0.1) over the local kpt
cache and keeping only `split == "test"`.

PopSign clips here are 32 frames; the verifier's window_len is 30 with a
stride of 2, so each clip yields very few sliding windows (and the persistence
vote needs `min_gated_windows`). We therefore ALSO report a per-clip
constrained metric (target's rank when the whole clip is scored as one
window) as a robust fallback, exactly as the task requests.

Run (CPU):
    python3 scripts/eval_net4_verifier.py
"""
from __future__ import annotations

import json
import random
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
from src.stage2.sign_verifier import SignVerifier  # noqa: E402

NET4_CKPT = REPO_ROOT / "results/v3/net4_popsign_baseline40/best.pt"
KPT_DIR = REPO_ROOT / "results/v3/net4_kpt_40word/popsign_kpt_cache"
VOCAB = REPO_ROOT / "configs/popsign_vocab.json"
SEED = 42
OPEN_VOCAB_TOP1 = 0.567  # current headline, for context
OPEN_VOCAB_TOP3 = 0.783


def build_test_split() -> list[dict]:
    """Recreate the deterministic split and return the TEST-split rows."""
    tmpdir = Path(tempfile.mkdtemp(prefix="net4_eval_"))
    manifest = tmpdir / "manifest.jsonl"
    sign_list = tmpdir / "sign_list.json"
    cmd = [
        sys.executable, "-m", "src.stage2.data.build_manifest_popsign",
        "--vocab", str(VOCAB),
        "--kpt-dir", str(KPT_DIR),
        "--sign-list-out", str(sign_list),
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


def make_classify(net4, data_cfg: dict, device: str):
    """Mirror the demo's `_net4_classify`: pad/subsample window, softmax."""
    window = int(data_cfg.get("max_frames", 64))

    def classify(feat: np.ndarray) -> np.ndarray:
        feat32 = np.asarray(feat, dtype=np.float32)
        feat32, mask = window_to_model_input(feat32, window)
        x = torch.from_numpy(feat32).unsqueeze(0).to(device)
        m = torch.from_numpy(mask).unsqueeze(0).to(device)
        with torch.no_grad():
            logits = net4(x, key_padding_mask=m)
            probs = torch.softmax(logits[0].float(), dim=-1).cpu().numpy()
        return probs

    return classify


def whole_clip_probs(classify, kpts: np.ndarray, vis: np.ndarray,
                     W: int, H: int, data_cfg: dict) -> np.ndarray:
    """Score the entire clip as ONE window (the per-clip fallback metric).

    Builds features exactly like the verifier/predict_clip do, then runs the
    same injected classify. Returns the class-probability vector.
    """
    feat = _build_per_frame_features(
        kpts, vis, W, H,
        include_visibility=data_cfg["include_visibility"],
        include_lag1=data_cfg["include_lag1"],
        include_lag2=data_cfg["include_lag2"],
    )
    return classify(feat)


def run_clip_through_verifier(classify, gloss_to_idx, target: str,
                              kpts: np.ndarray, vis: np.ndarray) -> dict:
    """Feed one clip frame-by-frame into a FRESH verifier; return final verify.

    `present` per frame = at least one keypoint visible that frame (the same
    signal live detection provides). The verifier derives its own visibility
    and builds features with Net 4's helper internally.
    """
    verifier = SignVerifier(classify=classify, gloss_to_idx=gloss_to_idx)
    T = kpts.shape[0]
    for t in range(T):
        present = bool((vis[t] > 0.5).any())
        verifier.push_frame(kpts[t], present)
    return verifier.verify(target)


def main() -> None:
    device = "cpu"
    print(f"[init] device={device}", flush=True)

    net4, gloss_to_idx, data_cfg = load_net4(str(NET4_CKPT), device)
    idx_to_gloss = {v: k for k, v in gloss_to_idx.items()}
    classify = make_classify(net4, data_cfg, device)
    print(f"[init] Net 4 loaded — {len(gloss_to_idx)} classes; "
          f"window={data_cfg.get('max_frames')}", flush=True)

    test_rows = build_test_split()
    print(f"[init] test split: {len(test_rows)} clips", flush=True)

    # Glosses that exist BOTH in the model and the test set (for wrong-target).
    model_glosses = sorted(gloss_to_idx.keys())

    rng = random.Random(SEED)

    # Counters.
    n = 0
    n_skipped_unknown = 0
    accept_hits = 0          # correct-target verified
    false_accepts = 0        # wrong-target verified
    any_window = 0           # clips where verifier recorded >=1 window
    any_gated = 0            # clips where verifier classified >=1 window
    top1 = 0
    top3 = 0
    clip_lengths = []

    for e in test_rows:
        gloss = e["gloss"]
        if gloss not in gloss_to_idx:
            n_skipped_unknown += 1
            continue
        with np.load(e["kpt_path"]) as d:
            kpts = d["keypoints"].astype(np.float32)
            vis = d["visibility"].astype(np.float32)
            W = int(d["width"])
            H = int(d["height"])
        clip_lengths.append(kpts.shape[0])
        n += 1

        # Correct-target trial.
        res = run_clip_through_verifier(classify, gloss_to_idx, gloss,
                                        kpts, vis)
        if res["verified"]:
            accept_hits += 1
        if res["n_windows"] > 0:
            any_window += 1
        if (res["n_windows"] - res["gated_out"]) > 0:
            any_gated += 1

        # Wrong-target trial (fixed-seed pick of a DIFFERENT gloss).
        others = [g for g in model_glosses if g != gloss]
        wrong = rng.choice(others)
        res_w = run_clip_through_verifier(classify, gloss_to_idx, wrong,
                                          kpts, vis)
        if res_w["verified"]:
            false_accepts += 1

        # Per-clip constrained fallback: whole clip as one window.
        probs = whole_clip_probs(classify, kpts, vis, W, H, data_cfg)
        order = np.argsort(-probs)
        tidx = gloss_to_idx[gloss]
        rank = int(np.where(order == tidx)[0][0])
        if rank == 0:
            top1 += 1
        if rank < 3:
            top3 += 1

    if n == 0:
        print("[error] no usable test clips", flush=True)
        return

    accept_rate = accept_hits / n
    far = false_accepts / n
    ood_reject = 1.0 - far
    top1_rate = top1 / n
    top3_rate = top3 / n
    cl = np.array(clip_lengths)

    verifier_fired = any_gated > 0

    print("\n" + "=" * 64)
    print("Net 4 CONSTRAINED-TARGET eval (SignVerifier, as deployed)")
    print("=" * 64)
    print(f"checkpoint     : {NET4_CKPT.relative_to(REPO_ROOT)}")
    print(f"test clips     : {n}  (split=test, seed={SEED}; "
          f"{n_skipped_unknown} unknown-gloss skipped)")
    print(f"clip frames    : min={cl.min()} max={cl.max()} "
          f"mean={cl.mean():.1f}  (verifier window_len=30, stride=2)")
    print(f"classes        : {len(gloss_to_idx)} (baseline 40/word model)")
    print("-" * 64)
    print("VERIFIER (the deployed metric)")
    print(f"  windows recorded in >=1 clip : {any_window}/{n}")
    print(f"  windows classified (gated)   : {any_gated}/{n}")
    if not verifier_fired:
        print("  WARNING: 32-frame clips are too short for the verifier to "
              "vote\n           (window_len 30 + min_gated_windows). The "
              "accept/FAR\n           numbers below reflect that limit — see "
              "the per-clip\n           fallback for the usable signal.")
    print(f"  target ACCEPT RATE (recall)  : {accept_rate*100:5.1f}%  "
          f"({accept_hits}/{n})")
    print(f"  FALSE-ACCEPT RATE (wrong tgt): {far*100:5.1f}%  "
          f"({false_accepts}/{n})")
    print(f"  OOD REJECTION = 1-FAR        : {ood_reject*100:5.1f}%  "
          f"(ml-handoff gate >=90%)")
    print("-" * 64)
    print("PER-CLIP CONSTRAINED (whole clip = one window; fallback signal)")
    print(f"  constrained top-1            : {top1_rate*100:5.1f}%  "
          f"({top1}/{n})")
    print(f"  constrained top-3            : {top3_rate*100:5.1f}%  "
          f"({top3}/{n})")
    print("-" * 64)
    print("FOR CONTEXT (current open-vocab headline)")
    print(f"  open-vocab top-1             : {OPEN_VOCAB_TOP1*100:5.1f}%")
    print(f"  open-vocab top-3             : {OPEN_VOCAB_TOP3*100:5.1f}%")
    print("=" * 64, flush=True)


if __name__ == "__main__":
    main()
