"""Net 4 dataset — reads cached keypoint .npz files + builds per-frame features.

Per-frame feature vector (default config):
    coords (98)     49 keypoints * (x, y), normalised
    vis    (49)     visibility flags
    lag1   (98)     coords[t] - coords[t-1]
    lag2   (98)     coords[t] - coords[t-2]
                   ───────
    total  343 dims

Normalisation: anchor at the centroid of visible Net 1 face+body keypoints,
scale by the shoulder span (or fallback to half the frame width when the
body keypoints are absent). This makes the per-frame features
translation/scale-invariant — required for the classifier to ignore the
signer's position and zoom level.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from src.stage1.data import schema as S


FACE_BODY_INDICES = S.FACE_INDICES + S.BODY_INDICES  # nose/chin/forehead + 4 body


def _normalise_frame(kpts: np.ndarray, vis: np.ndarray,
                     W: int, H: int) -> np.ndarray:
    """Per-part normalization: body-scale for face/body, hand-scale for hands.

    Face/body keypoints are anchored on their centroid and divided by their
    bounding span (gross position, body-scale). The two hands are then
    RE-NORMALIZED by their OWN size: each hand's wrist is kept at its
    body-normalized location (so sign *location* is preserved) while the
    finger offsets are divided by that hand's own span (so *handshape* spans
    the feature range instead of being ~1% of shoulder width).

    This recovers the hand-relative scale that the detect→crop→landmark
    cascade produces and that `extract_keypoints.py` discards when it
    unprojects Net 3's crop coords back to frame space. No keypoint is used
    as a global anchor; hands self-scale, body keeps body-scale.

    kpts: (49, 2), vis: (49,)  →  (49, 2).
    """
    fb_vis = vis[FACE_BODY_INDICES] > 0.5
    if fb_vis.sum() >= 1:
        face_body_pts = kpts[FACE_BODY_INDICES][fb_vis]
    else:
        face_body_pts = kpts[vis > 0.5]
    if face_body_pts.shape[0] >= 1:
        centre = face_body_pts.mean(axis=0)
    else:
        centre = np.array([W * 0.5, H * 0.5], dtype=np.float32)
    if face_body_pts.shape[0] >= 2:
        span = float(np.linalg.norm(face_body_pts.max(axis=0)
                                    - face_body_pts.min(axis=0)))
    else:
        span = max(W, H) * 0.5
    if span < 1e-3:
        span = max(W, H) * 0.5
    out = (kpts - centre) / max(span, 1.0)

    # Per-hand scale recovery. For each hand: keep the wrist at its
    # body-normalized position, but rescale the finger offsets by the hand's
    # own span so handshape detail is not crushed by the shoulder-scale span.
    for hstart in (S.RIGHT_HAND_START, S.LEFT_HAND_START):
        sl = slice(hstart, hstart + 21)
        hvis = vis[sl] > 0.5
        if hvis.sum() < 3:
            continue
        hand = kpts[sl]
        hand_vis_pts = hand[hvis]
        hand_span = float(np.linalg.norm(hand_vis_pts.max(axis=0)
                                         - hand_vis_pts.min(axis=0)))
        if hand_span < 1e-3:
            continue
        wrist = hand[0]                              # kp0 = wrist (frame coords)
        body_norm_wrist = (wrist - centre) / max(span, 1.0)
        out[sl] = body_norm_wrist + (hand - wrist) / hand_span

    # Zero-out invisibles so they don't contribute through lag deltas.
    mask = (vis > 0.5).astype(np.float32)[:, None]
    return (out * mask).astype(np.float32)


def _build_per_frame_features(kpts: np.ndarray, vis: np.ndarray,
                              W: int, H: int,
                              include_visibility: bool = True,
                              include_lag1: bool = True,
                              include_lag2: bool = True) -> np.ndarray:
    """Per-frame feature: normalised coords + visibility + lag deltas.

    Returns (T, C) feature tensor.
    """
    T = kpts.shape[0]
    norm = np.stack([_normalise_frame(kpts[t], vis[t], W, H)
                     for t in range(T)])  # (T, 49, 2)
    parts = [norm.reshape(T, -1)]  # (T, 98)
    if include_visibility:
        parts.append(vis.astype(np.float32))  # (T, 49)
    if include_lag1:
        lag1 = np.zeros_like(norm)
        lag1[1:] = norm[1:] - norm[:-1]
        parts.append(lag1.reshape(T, -1))
    if include_lag2:
        lag2 = np.zeros_like(norm)
        lag2[2:] = norm[2:] - norm[:-2]
        parts.append(lag2.reshape(T, -1))
    return np.concatenate(parts, axis=1).astype(np.float32)


class SignSequenceDataset(Dataset):
    """Per-clip dataset that yields (features, label, length).

    Args:
        manifest_path: JSONL with {clip_id, gloss, split, kpt_path?}.
        kpt_dir: directory containing .npz files keyed by clip_id.
        gloss_to_idx: stable label mapping (built once, reused at eval time).
        split: filter to "train" / "val" / "test".
        max_frames: pad/truncate to T frames.
        augment: enable time/spatial augmentation for the training split.
    """

    def __init__(self, manifest_path: str | Path, kpt_dir: str | Path,
                 gloss_to_idx: dict[str, int], split: str = "train",
                 max_frames: int = 64, augment: bool = False,
                 include_visibility: bool = True,
                 include_lag1: bool = True, include_lag2: bool = True):
        super().__init__()
        self.kpt_dir = Path(kpt_dir)
        self.max_frames = int(max_frames)
        self.augment = bool(augment)
        self.gloss_to_idx = gloss_to_idx
        self.include_visibility = include_visibility
        self.include_lag1 = include_lag1
        self.include_lag2 = include_lag2

        self.items: list[dict] = []
        with open(manifest_path) as f:
            for line in f:
                e = json.loads(line)
                if e.get("split", "train") != split:
                    continue
                if e["gloss"] not in gloss_to_idx:
                    continue
                kpt_path = (Path(e["kpt_path"]) if "kpt_path" in e
                            else self.kpt_dir / f"{e['clip_id']}.npz")
                if not kpt_path.exists():
                    continue
                self.items.append({
                    "kpt_path": kpt_path,
                    "gloss": e["gloss"],
                    "label": gloss_to_idx[e["gloss"]],
                })

    def __len__(self) -> int:
        return len(self.items)

    def _pad_or_trim(self, feat: np.ndarray) -> tuple[np.ndarray, int]:
        T = feat.shape[0]
        if T >= self.max_frames:
            if self.augment and T > self.max_frames:
                start = random.randint(0, T - self.max_frames)
                return feat[start:start + self.max_frames], self.max_frames
            idxs = np.linspace(0, T - 1, self.max_frames).astype(int)
            return feat[idxs], self.max_frames
        out = np.zeros((self.max_frames, feat.shape[1]), dtype=np.float32)
        out[:T] = feat
        return out, T

    def __getitem__(self, idx: int) -> dict:
        e = self.items[idx]
        with np.load(e["kpt_path"]) as data:
            kpts = data["keypoints"].astype(np.float32)
            vis = data["visibility"].astype(np.float32)
            W = int(data["width"])
            H = int(data["height"])

        if self.augment:
            # Light spatial jitter: small global scale + shift in normalised
            # space (applied via fake "centre" perturbation on coords).
            scale = 1.0 + (random.random() - 0.5) * 0.2
            shift = np.array([(random.random() - 0.5) * 0.05 * W,
                              (random.random() - 0.5) * 0.05 * H],
                             dtype=np.float32)
            kpts = (kpts - shift) * scale + shift

        feat = _build_per_frame_features(
            kpts, vis, W, H,
            include_visibility=self.include_visibility,
            include_lag1=self.include_lag1,
            include_lag2=self.include_lag2,
        )
        feat, valid_T = self._pad_or_trim(feat)
        mask = np.ones(self.max_frames, dtype=bool)
        mask[:valid_T] = False  # True = padded

        return {
            "features": torch.from_numpy(feat),
            "key_padding_mask": torch.from_numpy(mask),
            "label": torch.tensor(e["label"], dtype=torch.long),
            "gloss": e["gloss"],
        }


def build_gloss_to_idx(sign_list_json: str | Path) -> dict[str, int]:
    """Stable label mapping in catalog order, written to disk for reuse."""
    with open(sign_list_json) as f:
        data = json.load(f)
    glosses: Sequence[str] = (data["glosses_flat"] if isinstance(data, dict)
                              and "glosses_flat" in data else list(data))
    return {g: i for i, g in enumerate(glosses)}


def feature_dim(include_visibility: bool = True, include_lag1: bool = True,
                include_lag2: bool = True) -> int:
    base = S.NUM_KEYPOINTS * 2  # coords (x, y)
    if include_visibility:
        base += S.NUM_KEYPOINTS
    if include_lag1:
        base += S.NUM_KEYPOINTS * 2
    if include_lag2:
        base += S.NUM_KEYPOINTS * 2
    return base
