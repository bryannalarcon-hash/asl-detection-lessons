"""Unit tests for the live sign-verification module (reference impl).

Target: ``src.stage2.sign_verifier.SignVerifier`` — a sliding-window +
persistence-vote verifier that confirms a user is producing ONE known target
sign on a live webcam stream. The classifier is injected as a callable, so we
mock it here with closures returning controlled probability vectors and feed
synthetic (49, 2) keypoint sequences.

The real per-frame feature builder (``sign_dataset._build_per_frame_features``)
is exercised end-to-end: it pulls in ``torch`` at import, which IS installed on
this box (torch 2.12.0+cpu), so no stub is needed. The window the verifier
hands to ``classify`` has shape (<=window_len, feat_dim) with feat_dim == 343
(98 coords + 49 vis + 98 lag1 + 98 lag2).

Run (no pytest on this box):  python3 tests/test_sign_verifier.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.sign_verifier import SignVerifier  # noqa: E402

GLOSS_TO_IDX = {"DOG": 0, "CAT": 1, "MILK": 2, "HELLO": 3}
NUM_CLASSES = len(GLOSS_TO_IDX)
FEAT_DIM = 343  # 98 coords + 49 vis + 98 lag1 + 98 lag2 (verified empirically)


# --------------------------------------------------------------------------- #
# Synthetic keypoint helpers
# --------------------------------------------------------------------------- #
def _make_frame(t: int, moving: bool, present: bool) -> np.ndarray:
    """One (49, 2) frame. Right hand (idx 0..20) + body (45..48) populated.

    `moving` => hand translates ~6px/frame (well above motion_min_speed=1.5);
    `present` is only used by the caller for the presence flag, but when False
    we still return a plausible array (the verifier zeroes visibility itself).
    """
    kpts = np.zeros((49, 2), dtype=np.float32)
    drift = (t * 6.0) if moving else 0.0
    for j in range(21):  # right hand
        kpts[j] = (300.0 + j * 3.0 + drift, 200.0 + j * 2.0)
    for k, bi in enumerate((45, 46, 47, 48)):  # body anchors (static)
        kpts[bi] = (240.0 + 60.0 * k, 150.0)
    return kpts


def _probs(target_idx: int | None, target_p: float,
           top_other_idx: int | None = None,
           top_other_p: float | None = None) -> np.ndarray:
    """Build a length-NUM_CLASSES prob vector with a controlled target prob.

    Remaining mass is spread evenly over the untouched classes so the vector
    sums to ~1.0 (the verifier only reads p[target_idx], but realistic vectors
    keep the test honest).
    """
    p = np.zeros(NUM_CLASSES, dtype=np.float64)
    fixed = 0.0
    if target_idx is not None:
        p[target_idx] = target_p
        fixed += target_p
    if top_other_idx is not None and top_other_p is not None:
        p[top_other_idx] = top_other_p
        fixed += top_other_p
    free = [i for i in range(NUM_CLASSES)
            if p[i] == 0.0 and i not in (target_idx, top_other_idx)]
    if free:
        rest = max(0.0, 1.0 - fixed)
        for i in free:
            p[i] = rest / len(free)
    return p


def _feed(verifier: SignVerifier, n_frames: int, *, moving: bool,
          present: bool) -> None:
    for t in range(n_frames):
        verifier.push_frame(_make_frame(t, moving, present), present)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_happy_path_verified():
    """Target-dominant probs + moving present hand over ~60 frames.

    Expect: verified=True, pass_fraction ~1.0, n_windows>0, gated_out ~0.
    """
    classify = lambda w: _probs(GLOSS_TO_IDX["DOG"], 0.92)  # noqa: E731
    v = SignVerifier(classify, GLOSS_TO_IDX)
    _feed(v, 60, moving=True, present=True)
    r = v.verify("DOG")
    assert r["verified"] is True, r
    assert r["pass_fraction"] > 0.99, r
    assert r["n_windows"] > 0, r
    assert r["gated_out"] == 0, r
    assert r["target_conf_mean"] > 0.9, r


def test_wrong_sign_not_verified():
    """A DIFFERENT class is dominant; the target prob stays below thresh."""
    classify = lambda w: _probs(GLOSS_TO_IDX["CAT"], 0.9)  # noqa: E731
    v = SignVerifier(classify, GLOSS_TO_IDX)
    _feed(v, 60, moving=True, present=True)
    r = v.verify("DOG")  # asking about DOG while user "signs" CAT
    assert r["verified"] is False, r
    assert r["target_conf_mean"] < v.conf_thresh, r
    assert r["pass_fraction"] == 0.0, r


def test_no_hand_all_gated_out():
    """present=False every frame -> no window is ever classified."""
    classify = lambda w: _probs(GLOSS_TO_IDX["DOG"], 0.99)  # noqa: E731
    v = SignVerifier(classify, GLOSS_TO_IDX)
    _feed(v, 60, moving=True, present=False)
    r = v.verify("DOG")
    assert r["verified"] is False, r
    assert r["n_windows"] > 0, r
    assert r["gated_out"] == r["n_windows"], r  # every window gated out
    assert r["pass_fraction"] == 0.0, r


def test_still_hand_motion_gate():
    """present=True but the hand does not move -> motion gate rejects."""
    classify = lambda w: _probs(GLOSS_TO_IDX["DOG"], 0.99)  # noqa: E731
    v = SignVerifier(classify, GLOSS_TO_IDX)
    _feed(v, 60, moving=False, present=True)
    r = v.verify("DOG")
    assert r["verified"] is False, r
    assert r["gated_out"] > 0, r
    # A still hand should classify nothing -> conf mean stays at 0.
    assert r["target_conf_mean"] == 0.0, r


def test_persistence_transient_does_not_trigger():
    """Target spikes high in a FEW windows but is low in most.

    pass_fraction must fall below vote_frac so a transient blip never verifies.
    """
    call = {"n": 0}

    def classify(_w):
        call["n"] += 1
        # High only on the first 2 invocations, low afterwards.
        p = 0.95 if call["n"] <= 2 else 0.1
        return _probs(GLOSS_TO_IDX["DOG"], p)

    v = SignVerifier(classify, GLOSS_TO_IDX)
    _feed(v, 60, moving=True, present=True)
    r = v.verify("DOG")
    assert r["verified"] is False, r
    assert r["pass_fraction"] < v.vote_frac, r
    assert r["n_windows"] >= v.min_gated_windows, r


def test_target_consistent_runner_up_still_verifies():
    """Target is a CONSISTENT close #2 (top-1 is a different class).

    The verifier must score the TARGET prob, not top-1, so this verifies.

    A target that is BOTH above conf_thresh AND a genuine #2 is impossible if
    conf_thresh >= 0.5 (two classes can't both exceed 0.5). So we run with a
    lower conf_thresh (0.35): DOG (target) = 0.40 clears the bar but CAT = 0.50
    is the true top-1. This isolates the "scores target, not top-1" behaviour.
    """
    classify = lambda w: _probs(  # noqa: E731
        GLOSS_TO_IDX["DOG"], 0.40,
        top_other_idx=GLOSS_TO_IDX["CAT"], top_other_p=0.50)
    v = SignVerifier(classify, GLOSS_TO_IDX, conf_thresh=0.35)
    _feed(v, 60, moving=True, present=True)
    r = v.verify("DOG")
    # Confirm CAT really is top-1 while DOG still clears conf_thresh.
    sample = classify(None)
    assert int(np.argmax(sample)) == GLOSS_TO_IDX["CAT"], sample
    assert sample[GLOSS_TO_IDX["DOG"]] >= v.conf_thresh, sample
    assert sample[GLOSS_TO_IDX["DOG"]] < sample[GLOSS_TO_IDX["CAT"]], sample
    assert r["verified"] is True, r
    assert r["pass_fraction"] > 0.99, r


def test_knob_sanity_thresholds_flip_borderline():
    """A borderline case: target prob 0.45, default conf_thresh 0.5 fails;
    lowering conf_thresh below 0.45 flips it to verified. Likewise vote_frac.
    """
    classify = lambda w: _probs(GLOSS_TO_IDX["DOG"], 0.45)  # noqa: E731

    strict = SignVerifier(classify, GLOSS_TO_IDX)  # conf_thresh=0.5
    _feed(strict, 60, moving=True, present=True)
    rs = strict.verify("DOG")
    assert rs["verified"] is False, rs

    loose = SignVerifier(classify, GLOSS_TO_IDX, conf_thresh=0.4)
    _feed(loose, 60, moving=True, present=True)
    rl = loose.verify("DOG")
    assert rl["verified"] is True, rl

    # vote_frac knob: half the windows pass at conf 0.55, half at 0.45.
    call = {"n": 0}

    def alt(_w):
        call["n"] += 1
        return _probs(GLOSS_TO_IDX["DOG"], 0.55 if call["n"] % 2 == 0 else 0.45)

    high_vf = SignVerifier(alt, GLOSS_TO_IDX, vote_frac=0.8)
    _feed(high_vf, 60, moving=True, present=True)
    assert high_vf.verify("DOG")["verified"] is False  # ~50% pass < 0.8

    call["n"] = 0
    low_vf = SignVerifier(alt, GLOSS_TO_IDX, vote_frac=0.4,
                          min_gated_windows=2)
    _feed(low_vf, 60, moving=True, present=True)
    assert low_vf.verify("DOG")["verified"] is True  # ~50% pass >= 0.4


def test_gloss_index_and_window_shape_contract():
    """classify() receives a (<=window_len, FEAT_DIM) window and the verifier
    indexes the TARGET gloss correctly (a per-class one-hot probe proves it).
    """
    seen_shapes: list[tuple[int, int]] = []

    def classify(w):
        seen_shapes.append(tuple(w.shape))
        # One-hot on MILK so only verify("MILK") can ever pass.
        return _probs(GLOSS_TO_IDX["MILK"], 1.0)

    v = SignVerifier(classify, GLOSS_TO_IDX, window_len=30)
    _feed(v, 60, moving=True, present=True)

    assert seen_shapes, "classify was never called"
    for shp in seen_shapes:
        assert shp[0] <= v.window_len, shp          # T <= window_len
        assert shp[1] == FEAT_DIM, shp              # feat_dim == 343

    # Check NON-target indices FIRST: with a MILK one-hot classifier their
    # target prob is 0 -> not verified. (Doing this before MILK avoids the
    # hysteresis hold a successful MILK check would arm.)
    assert v.verify("DOG")["verified"] is False
    assert v.verify("CAT")["verified"] is False
    # Now the real target: same buffers, indexes MILK -> verified.
    assert v.verify("MILK")["verified"] is True

    # Unknown gloss raises (boundary contract).
    raised = False
    try:
        v.verify("NOT_A_SIGN")
    except KeyError:
        raised = True
    assert raised, "verify() must reject unknown glosses"


def test_hysteresis_holds_after_pass():
    """Once verified, a single dipping window within hold_sec stays verified.

    Strategy: feed enough strong windows to set raw_pass=True (which arms the
    hold counter), then push ONE more window whose prob is low. Because
    hold_frames_left > 0, verify() must still report verified=True.
    """
    state = {"low": False}

    def classify(_w):
        return _probs(GLOSS_TO_IDX["DOG"], 0.05 if state["low"] else 0.95)

    # Short span so the rolling window buffer can fully flush to "low" within a
    # few frames; large hold_sec (2s = 60 frames) so that flush stays inside
    # the hysteresis window.
    v = SignVerifier(classify, GLOSS_TO_IDX, span_sec=0.5, hold_sec=2.0)
    _feed(v, 60, moving=True, present=True)
    r1 = v.verify("DOG")            # arms hysteresis (raw_pass True)
    assert r1["verified"] is True, r1
    assert v._hold_frames_left > 0, v._hold_frames_left

    # Drive the whole span's worth of windows LOW (8 windows * stride 2 = 16
    # frames << 60-frame hold), so raw_pass is unambiguously False now.
    state["low"] = True
    _feed(v, v.windows_per_span * v.stride + 2, moving=True, present=True)
    r2 = v.verify("DOG")
    assert r2["pass_fraction"] < v.vote_frac, r2     # raw pass now fails
    assert v._hold_frames_left > 0, r2               # still inside hold window
    assert r2["verified"] is True, ("hysteresis should hold within hold_sec", r2)


def _run_standalone() -> int:
    """Run every test_* without pytest (mirrors test_pipeline_integration)."""
    import traceback

    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    n_pass = n_fail = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
            n_pass += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc!r}")
            traceback.print_exc()
            n_fail += 1
    print(f"\n{n_pass} passed, {n_fail} failed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
