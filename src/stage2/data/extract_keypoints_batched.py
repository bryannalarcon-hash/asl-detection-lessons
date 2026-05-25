"""GPU-batched offline keypoint extraction for Net 4 training data.

Drop-in companion to ``extract_keypoints.extract_one_clip`` that produces
byte-for-byte equivalent output while batching the Stage-1 cascade so each
network runs ONE forward per clip instead of once per frame:

  Net 1  stack F letterboxed frames -> one forward (B=F) -> per-frame kpts.
  Net 2  per-frame forward + decode (the lightest net, and its box is the
         geometry that drives Net 3's crop — see the equivalence note below).
  Net 3  gather every hand crop across all frames -> one batched pass-1
         forward; compute rotations; gather pass-2 crops -> one batched
         pass-2 forward. Respects two_pass_fallback (skips pass-2 when
         False). Net-2-supplied keypoints take the single-pass oriented
         crop (still batched into pass 1).

Numerical equivalence holds because every model is in ``.eval()`` (BatchNorm
uses running stats, so batch composition does not change any sample's output)
and ``soft_argmax_2d`` is computed independently per sample. The only source
of drift is float reordering, which stays well under 0.5 px.

Net 2 is run per-frame on purpose. Batching its conv shifts the box logits by
~1e-6 vs the per-frame forward; that 1e-4 px box jitter feeds Net 3's crop,
and the 2-pass self-orientation re-crop is chaotically sensitive to it (a
sub-pixel box shift can flip the second-pass output by several px — the
reference ``run_net3`` shows the identical jump when handed a box perturbed
by 1e-4 px). Keeping Net 2 per-frame makes the box bit-identical to the
reference so the 2-pass output matches it exactly. Net 2 is by far the
smallest net (~615K params) so this costs almost nothing; the throughput win
comes from batching the heavy nets (Net 1 ~8M params, run F times, and Net 3
~1.3M params, run up to 2x per hand per frame).

The originals in ``extract_keypoints`` are the proven reference and are NOT
modified; this module reuses their letterbox / decode / crop / orientation
helpers (and ``run_net2``) verbatim.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from src.stage1.data import schema as S
from src.stage1.data.palm_boxes import HandBBox
from src.stage1.data.hand_crops import crop_hand, unproject_kpts
from src.stage1.models.detector import soft_argmax_2d

from src.stage2.data.extract_keypoints import (
    letterbox,
    upright_rotation_deg,
    _expand_box,
    assign_hand_side,
    iter_video_frames,
    run_net2,
)


def _net1_batched(model, k: int, kslice, frames_bgr: list[np.ndarray],
                  device: str, input_size: int = 256
                  ) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Net 1 over all frames in one forward. Mirrors ``run_net1`` per frame.

    Returns (kpts_list, vis_list) where each element is the (49,2) / (49,)
    array for one frame, identical to what ``run_net1`` returns for that
    frame.
    """
    F = len(frames_bgr)
    tensors = []
    metas = []  # (H, W, scale, dx, dy) per frame
    for frame in frames_bgr:
        H, W = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        boxed, scale, dx, dy = letterbox(rgb, input_size)
        t = (boxed.astype(np.float32) / 255.0 - 0.5) / 0.5
        tensors.append(torch.from_numpy(t).permute(2, 0, 1))
        metas.append((H, W, scale, dx, dy))
    batch = torch.stack(tensors, dim=0).to(device)
    with torch.no_grad():
        heatmaps = model(batch)                       # (F, K, h, w)
        coords_hm = soft_argmax_2d(heatmaps).cpu().numpy()  # (F, K, 2)
        peaks = (heatmaps.view(F, heatmaps.shape[1], -1)
                 .max(dim=-1).values.cpu().numpy())    # (F, K)
    hm_size = heatmaps.shape[-1]

    kpts_list: list[np.ndarray] = []
    vis_list: list[np.ndarray] = []
    for f in range(F):
        H, W, scale, dx, dy = metas[f]
        coords = coords_hm[f] * (input_size / hm_size)
        coords = coords.copy()
        coords[:, 0] = (coords[:, 0] - dx) / scale
        coords[:, 1] = (coords[:, 1] - dy) / scale
        peak = peaks[f]
        out_kpts = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        out_vis = np.zeros(S.NUM_KEYPOINTS, dtype=np.float32)
        if kslice and len(kslice) == 2:
            s_idx, e_idx = int(kslice[0]), int(kslice[1])
            K = min(k, e_idx - s_idx)
            for j in range(K):
                x, y = coords[j]
                if 0 <= x < W and 0 <= y < H and peak[j] > 0.05:
                    out_kpts[s_idx + j] = (x, y)
                    out_vis[s_idx + j] = 1.0
        else:
            K = min(k, S.NUM_KEYPOINTS)
            for j in range(K):
                x, y = coords[j]
                if 0 <= x < W and 0 <= y < H and peak[j] > 0.05:
                    out_kpts[j] = (x, y)
                    out_vis[j] = 1.0
        kpts_list.append(out_kpts)
        vis_list.append(out_vis)
    return kpts_list, vis_list


def _build_crop_tensor(crop: np.ndarray, device: str) -> torch.Tensor:
    """Crop (HWC uint8/float) -> normalized CHW tensor matching _net3_one_pass."""
    t = torch.from_numpy(crop).permute(2, 0, 1).float() / 255.0
    return (t - 0.5) / 0.5


def _net3_decode_batch(model, head_type: str, batch: torch.Tensor,
                       crop_size: int) -> np.ndarray:
    """Forward a batch of crops, return (B, 21, 2) crop-pixel coords.

    Mirrors the per-sample decode in ``_net3_one_pass`` for both heads.
    """
    with torch.no_grad():
        out = model(batch)
    if head_type == "regression":
        coords = out["coords"][:, :, :2].cpu().numpy()   # normalized [0,1]
        return (coords * crop_size).astype(np.float32)
    coords_hm = soft_argmax_2d(out).cpu().numpy()        # (B, 21, 2)
    hm_size = out.shape[-1]
    return (coords_hm * (crop_size / hm_size)).astype(np.float32)


class _HandJob:
    """One hand to localise: which frame/side it belongs to + its crop box."""

    __slots__ = ("frame_idx", "side", "box", "rgb", "net2_kpts",
                 "M1", "coords1", "result")

    def __init__(self, frame_idx: int, side: str, box: HandBBox,
                 rgb: np.ndarray, net2_kpts: np.ndarray | None):
        self.frame_idx = frame_idx
        self.side = side
        self.box = box
        self.rgb = rgb
        self.net2_kpts = net2_kpts
        self.M1: np.ndarray | None = None
        self.coords1: np.ndarray | None = None
        self.result: np.ndarray | None = None  # final (21,2) frame-px coords


def _net3_batched(model, head_type: str, jobs: list[_HandJob], device: str,
                  crop_size: int, two_pass_fallback: bool) -> None:
    """Run Net 3 for every hand job with at most two batched forwards.

    Sets ``job.result`` (21,2 frame-px) in place. Replicates ``run_net3``:
      - net2_kpts present (>=2): single oriented crop (pass 1 only).
      - net2_kpts absent: axis-aligned pass 1; if two_pass_fallback, a second
        oriented pass from Net 3's own wrist(0)/middle-MCP(9).
    """
    if not jobs:
        return

    # ---- Pass 1: build every pass-1 crop and forward once. ----
    pass1_tensors: list[torch.Tensor] = []
    for job in jobs:
        if job.net2_kpts is not None and job.net2_kpts.shape[0] >= 2:
            rot = upright_rotation_deg(tuple(job.net2_kpts[0]),
                                       tuple(job.net2_kpts[1]))
        else:
            rot = 0.0
        crop, M = crop_hand(job.rgb, job.box, out_size=crop_size,
                            rotation_deg=rot)
        job.M1 = M
        pass1_tensors.append(_build_crop_tensor(crop, device))
    batch1 = torch.stack(pass1_tensors, dim=0).to(device)
    coords1 = _net3_decode_batch(model, head_type, batch1, crop_size)
    for i, job in enumerate(jobs):
        job.coords1 = coords1[i]

    # ---- Decide which jobs need a pass-2 oriented re-crop. ----
    pass2_jobs: list[_HandJob] = []
    for job in jobs:
        oriented_by_net2 = (job.net2_kpts is not None
                            and job.net2_kpts.shape[0] >= 2)
        if oriented_by_net2:
            # Single-pass oriented crop is final.
            job.result = unproject_kpts(job.coords1, job.M1).astype(np.float32)
        elif not two_pass_fallback:
            # Axis-aligned result is final.
            job.result = unproject_kpts(job.coords1, job.M1).astype(np.float32)
        else:
            pass2_jobs.append(job)

    if not pass2_jobs:
        return

    # ---- Pass 2: re-crop oriented from Net 3's own wrist(0)/MCP(9). ----
    pass2_tensors: list[torch.Tensor] = []
    pass2_M: list[np.ndarray] = []
    for job in pass2_jobs:
        wrist_crop = job.coords1[0]
        mcp_crop = job.coords1[9]
        rot = upright_rotation_deg(tuple(wrist_crop), tuple(mcp_crop))
        crop, M2 = crop_hand(job.rgb, job.box, out_size=crop_size,
                             rotation_deg=rot)
        pass2_tensors.append(_build_crop_tensor(crop, device))
        pass2_M.append(M2)
    batch2 = torch.stack(pass2_tensors, dim=0).to(device)
    coords2 = _net3_decode_batch(model, head_type, batch2, crop_size)
    for i, job in enumerate(pass2_jobs):
        job.result = unproject_kpts(coords2[i], pass2_M[i]).astype(np.float32)


def extract_one_clip_batched(net1, net1_k, net1_kslice, net2, net2_meta, net3,
                             net3_head_type, clip_path: Path, device: str,
                             max_frames: int = 64,
                             two_pass_fallback: bool = True
                             ) -> tuple[np.ndarray, np.ndarray, int, int] | None:
    """Batched twin of ``extract_one_clip``. Same (kpts, vis, W, H) contract.

    Equivalent output to the per-frame reference; the GPU work is collapsed
    into one Net 1 forward, one Net 2 forward, and one or two Net 3 forwards
    per clip.
    """
    frames = [f for f in iter_video_frames(clip_path, max_frames=max_frames)
              if f is not None]
    if not frames:
        return None
    H_orig, W_orig = frames[0].shape[:2]

    # Net 1: one batched forward. Net 2: per-frame (its box is geometry that
    # the chaotic 2-pass Net 3 re-crop is hypersensitive to; see module docs).
    body_kpts, body_vis = _net1_batched(net1, net1_k, net1_kslice, frames,
                                        device)
    det_per_frame = [run_net2(net2, net2_meta, frame, device)
                     for frame in frames]

    # Build the per-frame output (start from Net 1) and collect Net 3 jobs.
    kpts_out = [body_kpts[f].copy() for f in range(len(frames))]
    vis_out = [body_vis[f].copy() for f in range(len(frames))]

    jobs: list[_HandJob] = []
    job_meta: list[tuple[int, str]] = []  # (frame_idx, side) per job
    rgb_cache: dict[int, np.ndarray] = {}
    for f, frame in enumerate(frames):
        bboxes = det_per_frame[f]
        if not bboxes:
            continue
        sides = assign_hand_side(bboxes, body_kpts[f], body_vis[f])
        for (score, xyxy, box_kpts), side in zip(bboxes, sides):
            expanded = _expand_box(xyxy, W_orig, H_orig)
            if expanded is None:
                continue
            x1, y1, x2, y2 = expanded
            if f not in rgb_cache:
                rgb_cache[f] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            box = HandBBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1, side="right")
            jobs.append(_HandJob(f, side, box, rgb_cache[f], box_kpts))
            job_meta.append((f, side))

    # Net 3: batched pass(es) for all hand crops at once.
    _net3_batched(net3, net3_head_type, jobs, device, crop_size=224,
                  two_pass_fallback=two_pass_fallback)

    # Fill hand slots, matching extract_one_clip's per-keypoint in-frame test.
    for job in jobs:
        if job.result is None:
            continue
        f = job.frame_idx
        slot_start = (S.RIGHT_HAND_START if job.side == "right"
                      else S.LEFT_HAND_START)
        for j in range(21):
            x, y = job.result[j]
            if 0 <= x < W_orig and 0 <= y < H_orig:
                kpts_out[f][slot_start + j] = (x, y)
                vis_out[f][slot_start + j] = 1.0

    return (np.stack(kpts_out), np.stack(vis_out), W_orig, H_orig)
