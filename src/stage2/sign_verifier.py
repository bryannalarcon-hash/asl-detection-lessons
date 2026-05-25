"""Live sign VERIFICATION for the lesson practice loop (reference impl).

In a lesson the app shows ONE target sign and must confirm the user is
producing *that* sign from a live webcam stream. This is verification with a
known target — not open-set recognition — so it is far more robust: we only
ever ask "is the target class confident, consistently, while the hand moves?"

Net 4 (the sign classifier) is trained on pre-segmented ~30-frame clips and
has NO neutral / "no-sign" class. We therefore never ask it "what sign is
this?" on a still or absent hand. Instead we run a sliding window of
`window_len` frames (~one sign's duration), every `stride` frames, and gate
each window by motion + hand presence. A window only "counts" toward the vote
when the hand is actually signing. Verification fires when a fraction
(`vote_frac`) of the motion-gated windows in the last `span_sec` seconds put
the TARGET class above `conf_thresh`.

The classifier is INJECTED as a callable so this module never imports torch /
Net 4 — it stays pure-numpy, portable, and unit-testable, and serves as the
reference for the eventual TS/browser port (see HANDOFF_FRONTEND.md).

Per-frame features are built with the SAME helper Net 4's dataset uses
(`sign_dataset._build_per_frame_features`) so live features match training
exactly. That helper normalises coords (translation/scale invariant), so the
motion gate is computed on the RAW pixel keypoints, which retain real
velocity magnitude.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional

import numpy as np

from src.stage2.data.sign_dataset import _build_per_frame_features

# Type of the injected classifier: (window (T, feat_dim)) -> probs (num_classes,)
ClassifyFn = Callable[[np.ndarray], np.ndarray]


class SignVerifier:
    """Sliding-window + persistence-vote verifier for a single target sign.

    Feed live keypoints via :meth:`push_frame`; poll :meth:`verify` with the
    current lesson's target gloss to get a verification decision.
    """

    def __init__(
        self,
        classify: ClassifyFn,
        gloss_to_idx: dict[str, int],
        *,
        window_len: int = 30,
        stride: int = 2,
        span_sec: float = 2.0,
        fps: int = 30,
        conf_thresh: float = 0.5,
        vote_frac: float = 0.8,
        motion_min_speed: float = 1.5,
        presence_min: float = 0.6,
        min_gated_windows: int = 2,
        hold_sec: float = 0.75,
        include_visibility: bool = True,
        include_lag1: bool = True,
        include_lag2: bool = True,
        frame_wh: tuple[int, int] = (640, 480),
    ) -> None:
        if window_len < 2:
            raise ValueError("window_len must be >= 2")
        if stride < 1:
            raise ValueError("stride must be >= 1")
        self.classify = classify
        self.gloss_to_idx = dict(gloss_to_idx)
        self.window_len = int(window_len)
        self.stride = int(stride)
        self.span_sec = float(span_sec)
        self.fps = int(fps)
        self.conf_thresh = float(conf_thresh)
        self.vote_frac = float(vote_frac)
        self.motion_min_speed = float(motion_min_speed)
        self.presence_min = float(presence_min)
        self.min_gated_windows = int(min_gated_windows)
        self.hold_sec = float(hold_sec)
        self.include_visibility = bool(include_visibility)
        self.include_lag1 = bool(include_lag1)
        self.include_lag2 = bool(include_lag2)
        self.frame_w, self.frame_h = int(frame_wh[0]), int(frame_wh[1])

        # How many classifier windows fall inside the persistence span.
        self.windows_per_span = max(1, int(round(self.span_sec * self.fps
                                                  / self.stride)))

        # Rolling raw buffers, long enough to always reconstruct a window.
        buf = self.window_len + 2  # +2 for lag2 deltas at the window head
        self._kpts: deque[np.ndarray] = deque(maxlen=buf)
        self._vis: deque[np.ndarray] = deque(maxlen=buf)
        self._present: deque[bool] = deque(maxlen=buf)

        # Per-window records, capped at one span's worth. `_gate_pass[i]` is
        # whether window i passed the motion/presence gate; `_probs[i]` is the
        # classifier output for that window, or None when it was gated out
        # (we never run the classifier on a still/absent hand).
        self._gate_pass: deque[bool] = deque(maxlen=self.windows_per_span)
        self._probs: deque[Optional[np.ndarray]] = deque(
            maxlen=self.windows_per_span)

        self._frame_count = 0
        # Hysteresis: frames remaining to stay "verified" after a pass.
        self._hold_frames_left = 0
        self._hold_frames = max(1, int(round(self.hold_sec * self.fps)))

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Clear all buffers and votes (call when the target sign changes)."""
        self._kpts.clear()
        self._vis.clear()
        self._present.clear()
        self._gate_pass.clear()
        self._probs.clear()
        self._frame_count = 0
        self._hold_frames_left = 0

    # ------------------------------------------------------------------ #
    def push_frame(self, keypoints: np.ndarray, present: bool) -> None:
        """Append one frame of keypoints; run the classifier every `stride`.

        Args:
            keypoints: (49, 2) pixel coords in the source frame's space.
            present:   True if a hand was detected this frame.

        Visibility is derived from the keypoints (a row of NaN/zeros => not
        visible) so callers only need to pass coords + a presence flag.
        """
        kpts = np.asarray(keypoints, dtype=np.float32).reshape(49, 2)
        vis = self._derive_visibility(kpts, present)
        # Replace any NaNs so they never poison the feature math.
        kpts = np.nan_to_num(kpts, nan=0.0)

        self._kpts.append(kpts)
        self._vis.append(vis)
        self._present.append(bool(present))
        self._frame_count += 1
        if self._hold_frames_left > 0:
            self._hold_frames_left -= 1

        if len(self._kpts) >= self.window_len \
                and self._frame_count % self.stride == 0:
            self._evaluate_window()

    @staticmethod
    def _derive_visibility(kpts: np.ndarray, present: bool) -> np.ndarray:
        if not present:
            return np.zeros(49, dtype=np.float32)
        finite = np.isfinite(kpts).all(axis=1)
        nonzero = (np.abs(kpts) > 1e-6).any(axis=1)
        return (finite & nonzero).astype(np.float32)

    # ------------------------------------------------------------------ #
    def _evaluate_window(self) -> None:
        """Build the trailing window, gate it, classify, record the vote."""
        kpts = np.stack(list(self._kpts)[-self.window_len:])  # (T, 49, 2)
        vis = np.stack(list(self._vis)[-self.window_len:])    # (T, 49)
        present = list(self._present)[-self.window_len:]

        gate_pass = self._motion_presence_gate(kpts, vis, present)

        # Only spend the classifier when the window is actually signing.
        if gate_pass:
            feat = _build_per_frame_features(
                kpts, vis, self.frame_w, self.frame_h,
                include_visibility=self.include_visibility,
                include_lag1=self.include_lag1,
                include_lag2=self.include_lag2,
            )
            probs = np.asarray(self.classify(feat), dtype=np.float64).ravel()
        else:
            probs = None

        self._gate_pass.append(gate_pass)
        self._probs.append(probs)

    def _motion_presence_gate(self, kpts: np.ndarray, vis: np.ndarray,
                              present: list[bool]) -> bool:
        """True if the window shows enough motion AND hand presence.

        Motion = mean per-frame keypoint velocity over visible keypoints,
        measured on RAW pixel coords (features are normalised, so they lose
        absolute magnitude). Presence = fraction of frames with a hand.
        """
        presence_frac = float(np.mean(present)) if present else 0.0
        if presence_frac < self.presence_min:
            return False
        # Frame-to-frame displacement, averaged over keypoints visible in both
        # frames, then averaged over the window.
        speeds: list[float] = []
        for t in range(1, kpts.shape[0]):
            both = (vis[t] > 0.5) & (vis[t - 1] > 0.5)
            if not both.any():
                continue
            disp = np.linalg.norm(kpts[t][both] - kpts[t - 1][both], axis=1)
            speeds.append(float(disp.mean()))
        mean_speed = float(np.mean(speeds)) if speeds else 0.0
        return mean_speed >= self.motion_min_speed

    # ------------------------------------------------------------------ #
    def verify(self, target_gloss: str) -> dict:
        """Decide whether the user is producing `target_gloss` right now.

        Returns a dict with the decision plus diagnostics:
            verified         bool   final decision (with hysteresis)
            target_conf_mean float  mean TARGET prob over gated windows
            pass_fraction    float  gated windows above conf_thresh / gated
            n_windows        int    windows recorded in the span
            gated_out        int    windows that failed the motion/presence gate
        """
        if target_gloss not in self.gloss_to_idx:
            raise KeyError(f"unknown target gloss: {target_gloss!r}")
        tidx = self.gloss_to_idx[target_gloss]

        gate = list(self._gate_pass)
        n_windows = len(gate)
        gated_out = sum(1 for g in gate if not g)

        # Target-class probability for every gated window in the span. We use
        # the TARGET prob (not top-1) so a consistent close-#2 still verifies.
        confs = [float(p[tidx]) for p in self._probs if p is not None]
        n_gated = len(confs)

        if n_gated == 0:
            target_conf_mean = 0.0
            pass_fraction = 0.0
            raw_pass = False
        else:
            target_conf_mean = float(np.mean(confs))
            n_pass = int(np.sum(np.asarray(confs) >= self.conf_thresh))
            pass_fraction = n_pass / n_gated
            raw_pass = (pass_fraction >= self.vote_frac
                        and n_gated >= self.min_gated_windows)

        if raw_pass:
            self._hold_frames_left = self._hold_frames
        verified = raw_pass or self._hold_frames_left > 0

        return {
            "verified": bool(verified),
            "target_conf_mean": float(target_conf_mean),
            "pass_fraction": float(pass_fraction),
            "n_windows": int(n_windows),
            "gated_out": int(gated_out),
        }
