"""v3 inference pipeline: v2 (face/body) + Net 2 (palm bbox) + Net 3 (hand kpts).

The single public entry point is `V3Pipeline.detect(frame)`. It runs:
  1. v2 model on the full frame → reuses slots 42-48 (face/body)
  2. PalmDetector at 192x192 → up to 2 palm bboxes
  3. HandLandmarkNet at 224x224 on each cropped palm → 21 hand kpts
  4. Assemble into a single 49-keypoint output
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

from src.stage1.data import schema as S
from src.stage1.data.hand_crops import crop_hand, unproject_kpts
from src.stage1.data.palm_boxes import HandBBox
from src.stage1.models.anchors import (
    decode_box, get_anchors, nms, xywh_to_xyxy,
)
from src.stage1.models.detector import KeypointDetector, soft_argmax_2d
from src.stage1.models.landmark_net import HandLandmarkNet
from src.stage1.models.palm_detector import PalmDetector


def _letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = image.shape[:2]
    scale = size / max(h, w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size, 3), dtype=image.dtype)
    dy = (size - new_h) // 2
    dx = (size - new_w) // 2
    out[dy:dy + new_h, dx:dx + new_w] = resized
    return out, scale, dx, dy


class V3Pipeline:
    """End-to-end three-network inference."""

    def __init__(self,
                 v2_ckpt: str | Path,
                 palm_ckpt: str | Path,
                 landmark_ckpt: str | Path,
                 device: str | None = None,
                 detector_input: int = 192,
                 landmark_input: int = 224,
                 v2_input: int = 256,
                 v2_heatmap: int = 64,
                 nms_iou: float = 0.3,
                 score_threshold: float = 0.5,
                 max_hands: int = 2):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.detector_input = detector_input
        self.landmark_input = landmark_input
        self.v2_input = v2_input
        self.v2_heatmap = v2_heatmap
        self.nms_iou = nms_iou
        self.score_threshold = score_threshold
        self.max_hands = max_hands

        # Load v2 (for face/body slot only).
        self.v2 = KeypointDetector(num_keypoints=S.NUM_KEYPOINTS).to(self.device)
        v2_state = torch.load(v2_ckpt, map_location=self.device, weights_only=False)
        self.v2.load_state_dict(v2_state.get("model", v2_state))
        self.v2.eval()

        # Net 2.
        self.palm = PalmDetector().to(self.device)
        palm_state = torch.load(palm_ckpt, map_location=self.device, weights_only=False)
        self.palm.load_state_dict(palm_state.get("model", palm_state))
        self.palm.eval()

        # Net 3.
        self.landmark = HandLandmarkNet().to(self.device)
        land_state = torch.load(landmark_ckpt, map_location=self.device,
                                weights_only=False)
        self.landmark.load_state_dict(land_state.get("model", land_state))
        self.landmark.eval()

        self.anchors_xywh_np = get_anchors(detector_input)
        self.anchors_xywh = torch.from_numpy(self.anchors_xywh_np).to(self.device)

    @torch.no_grad()
    def detect(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Run all three nets and return (49-kpt array, visibility flags)."""
        H, W = frame.shape[:2]
        kps = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)

        # --- v2 for face/body slot (42-48) ---
        v2_inp, v2_scale, v2_dx, v2_dy = _letterbox(frame, self.v2_input)
        v2_tensor = self._to_tensor(v2_inp)
        v2_hm = self.v2(v2_tensor)
        v2_coords_hm = soft_argmax_2d(v2_hm)[0].cpu().numpy()
        v2_to_img = self.v2_input / self.v2_heatmap
        v2_coords_full = v2_coords_hm * v2_to_img
        v2_coords_full[:, 0] = (v2_coords_full[:, 0] - v2_dx) / v2_scale
        v2_coords_full[:, 1] = (v2_coords_full[:, 1] - v2_dy) / v2_scale
        for k in (S.NOSE, S.CHIN, S.FOREHEAD, S.CHEST_CENTER,
                  S.LEFT_SHOULDER, S.RIGHT_SHOULDER, S.NECK):
            x, y = float(v2_coords_full[k, 0]), float(v2_coords_full[k, 1])
            if 0 <= x < W and 0 <= y < H:
                kps[k] = (x, y)
                visible[k] = 1

        # --- Net 2: palm detector ---
        det_inp, det_scale, det_dx, det_dy = _letterbox(frame, self.detector_input)
        det_tensor = self._to_tensor(det_inp)
        det_out = self.palm(det_tensor)
        cls_logits = det_out["cls"].squeeze(0)
        box_deltas = det_out["box"].squeeze(0)
        scores = torch.sigmoid(cls_logits)
        kept = scores > self.score_threshold
        if kept.sum() == 0:
            return kps, visible
        kept_scores = scores[kept]
        kept_deltas = box_deltas[kept]
        kept_anchors = self.anchors_xywh[kept]
        decoded = decode_box(kept_deltas, kept_anchors)  # (M, 4) cx,cy,w,h in det_input coords
        # cx,cy,w,h → xyxy for NMS
        decoded_xyxy = torch.stack([
            decoded[:, 0] - decoded[:, 2] / 2,
            decoded[:, 1] - decoded[:, 3] / 2,
            decoded[:, 0] + decoded[:, 2] / 2,
            decoded[:, 1] + decoded[:, 3] / 2,
        ], dim=-1)
        keep_idx = nms(decoded_xyxy, kept_scores, iou_threshold=self.nms_iou,
                       top_k=self.max_hands)
        if keep_idx.numel() == 0:
            return kps, visible

        # --- Net 3: landmark on each surviving bbox ---
        for i, ki in enumerate(keep_idx[:self.max_hands]):
            box_xywh = decoded[ki].cpu().numpy()
            # Unletterbox bbox coords to original frame.
            cx = (box_xywh[0] - det_dx) / det_scale
            cy = (box_xywh[1] - det_dy) / det_scale
            w = box_xywh[2] / det_scale
            h = box_xywh[3] / det_scale
            box = HandBBox(cx - w / 2, cy - h / 2, w, h, side="unknown")
            crop, M = crop_hand(frame, box, out_size=self.landmark_input, rotation_deg=0)
            crop_tensor = self._to_tensor(crop)
            heatmaps = self.landmark(crop_tensor)
            crop_kpts_hm = soft_argmax_2d(heatmaps)[0].cpu().numpy()
            crop_kpts = crop_kpts_hm * (self.landmark_input / 56)  # 56 = output stride
            frame_kpts = unproject_kpts(crop_kpts, M)
            # Decide right vs left by which slot is currently emptier.
            r_empty = not visible[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21].any()
            l_empty = not visible[S.LEFT_HAND_START:S.LEFT_HAND_START + 21].any()
            slot = (slice(S.RIGHT_HAND_START, S.RIGHT_HAND_START + 21) if r_empty
                    else slice(S.LEFT_HAND_START, S.LEFT_HAND_START + 21)
                    if l_empty else None)
            if slot is None:
                continue
            kps[slot] = frame_kpts
            visible[slot] = 1

        return kps, visible

    def _to_tensor(self, image: np.ndarray) -> torch.Tensor:
        t = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        t = (t - 0.5) / 0.5
        return t.unsqueeze(0).to(self.device)
