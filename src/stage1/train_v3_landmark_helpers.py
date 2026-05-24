"""Helpers for `train_v3_landmark.py`.

Kept in a sibling module to keep the trainer entry point under the
project's 500-line file limit. Anything called only by `main()` lives
here: the per-source WeightedRandomSampler builder, the FreiHAND
held-out PCK val pipeline, and the best-effort S3 uploader.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Subset, WeightedRandomSampler

from src.common.v3_config import deep_get
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.rhd import RHDDataset


# Source-name aliases so config keys (`interhand_single`) map onto whatever
# tag the dataset uses (`interhand`). RHD will be added once the adapter
# lands; the alias keeps the trainer forward-compatible.
SOURCE_ALIASES = {
    "interhand": "interhand_single",
    "interhand_single": "interhand_single",
    "freihand": "freihand",
    "rhd": "rhd",
}


def soft_argmax_xy(heatmaps: torch.Tensor, crop_size: int, hm_size: int,
                   temperature: float = 10.0) -> torch.Tensor:
    """Soft-argmax over a (B, K, H, W) heatmap stack → (B, K, 2) crop coords."""
    B, K, H, W = heatmaps.shape
    flat = heatmaps.view(B, K, -1)
    flat = flat - flat.max(dim=-1, keepdim=True).values
    probs = torch.softmax(flat * temperature, dim=-1).view(B, K, H, W)
    device = heatmaps.device
    ys = torch.arange(H, device=device).float()
    xs = torch.arange(W, device=device).float()
    gy, gx = torch.meshgrid(ys, xs, indexing="ij")
    sx = (probs * gx[None, None]).sum(dim=(-1, -2)) * (crop_size / hm_size)
    sy = (probs * gy[None, None]).sum(dim=(-1, -2)) * (crop_size / hm_size)
    return torch.stack([sx, sy], dim=-1)


def build_rhd_dataset(cfg: dict) -> RHDDataset | None:
    """Load RHD training split when configured. Returns None when
    `data.rhd_root` is empty/missing or the directory does not exist, so
    the trainer keeps its original FreiHAND + InterHand-only behavior.
    """
    rhd_root = deep_get(cfg, "data.rhd_root")
    if not rhd_root:
        return None
    root_path = Path(rhd_root)
    if not root_path.exists():
        return None
    try:
        return RHDDataset(
            root_path,
            split=deep_get(cfg, "data.rhd_split", "training"),
            min_visible_per_hand=deep_get(cfg, "data.rhd_min_visible", 3),
        )
    except FileNotFoundError:
        return None


def build_target_mix_sampler(train_ds, target_mix: dict,
                             source_aliases: dict | None = None,
                             num_samples: int | None = None,
                             ) -> WeightedRandomSampler | None:
    """Per-sample weights so batch frequencies match `target_mix`.

    The dataset must expose `.items` as a list of tuples whose first element
    is the source tag (`"freihand"`, `"interhand"`, `"rhd"`, …). Sources
    absent from the dataset drop out and the remaining weights are
    renormalised. Returns None when no per-source weighting is requested or
    the dataset cannot be weighted.

    `num_samples` caps the items drawn per epoch (defaults to the full
    dataset size). Smaller caps keep epoch wall-clock predictable when the
    underlying pool is very large (InterHand + FreiHAND + RHD).
    """
    aliases = source_aliases or SOURCE_ALIASES
    items = getattr(train_ds, "items", None)
    if items is None or not target_mix:
        return None
    canonical: list[str] = []
    for tup in items:
        src = tup[0] if isinstance(tup, tuple) else tup
        canonical.append(aliases.get(src, src))
    counts: dict[str, int] = {}
    for s in canonical:
        counts[s] = counts.get(s, 0) + 1
    present = {k: counts[k] for k in target_mix if counts.get(k, 0) > 0}
    if not present:
        return None
    total_target = sum(float(target_mix[k]) for k in present)
    if total_target <= 0:
        return None
    per_sample_w = []
    for s in canonical:
        if s in present:
            per_sample_w.append((float(target_mix[s]) / total_target) / counts[s])
        else:
            per_sample_w.append(0.0)
    weights = torch.as_tensor(per_sample_w, dtype=torch.double)
    if float(weights.sum()) <= 0:
        return None
    n = int(num_samples) if num_samples and num_samples > 0 else len(per_sample_w)
    return WeightedRandomSampler(weights=weights,
                                 num_samples=n,
                                 replacement=True)


def build_freihand_val_loader(cfg: dict, crop_size: int):
    """Carve a held-out FreiHAND val split and wrap it in a
    `LandmarkTrainDataset` with augmentation disabled. Returns
    `(DataLoader, n_samples)` or `(None, 0)` if FreiHAND is absent.
    """
    fh_root = deep_get(cfg, "data.freihand_root")
    if not fh_root or not Path(fh_root).exists():
        return None, 0
    try:
        fh_val = FreiHANDDataset(
            fh_root, scene_split="val",
            val_scene_frac=deep_get(cfg, "data.freihand_val_frac", 0.05),
            scene_split_seed=deep_get(cfg, "data.freihand_val_seed", 42),
            use_all_variants=False,
        )
    except FileNotFoundError:
        return None, 0
    if len(fh_val) == 0:
        return None, 0
    from src.stage1.data.landmark_dataset import LandmarkTrainDataset
    val_ds = LandmarkTrainDataset(
        fh_val, None, crop_size=crop_size,
        padding_frac=deep_get(cfg, "data.padding_frac", 0.5),
        jitter_shift=0.0, jitter_scale=0.0, jitter_rot=0.0,
        phase2_bbox_cache=None, phase2_mix_prob=0.0,
    )
    cap = int(deep_get(cfg, "eval.max_val_samples", 2048))
    if cap and len(val_ds) > cap:
        val_ds = Subset(val_ds, range(cap))
    val_bs = int(deep_get(cfg, "eval.val_batch_size", 256))
    nw = int(deep_get(cfg, "train.num_workers", 4))
    loader = DataLoader(val_ds, batch_size=val_bs, shuffle=False,
                        num_workers=min(nw, 4), pin_memory=True, drop_last=False)
    return loader, len(val_ds)


@torch.no_grad()
def eval_pck_freihand_multi(model, val_loader, device: str, crop_size: int,
                             hm_size: int, threshold_fracs: list[float],
                             use_amp_bf16: bool) -> dict[float, float]:
    """Multi-threshold PCK on the FreiHAND val loader. Returns
    {frac: pck_at_that_threshold, ...}. Empty dict when no val data."""
    out: dict[float, float] = {f: float("nan") for f in threshold_fracs}
    if val_loader is None:
        return out
    model.eval()
    thr_px = torch.tensor([f * crop_size for f in threshold_fracs],
                          device=device)
    total_correct = torch.zeros(len(threshold_fracs), device=device)
    total_visible = 0.0
    for batch in val_loader:
        image = batch["image"].to(device, non_blocking=True)
        gt = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)
        if use_amp_bf16 and device == "cuda":
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                pred = model(image)
        else:
            pred = model(image)
        pred_xy = soft_argmax_xy(pred.float(), crop_size, hm_size)
        diffs = (pred_xy - gt).norm(dim=-1)                          # (B, K)
        for i, t in enumerate(thr_px):
            correct = (diffs <= t).float() * vis
            total_correct[i] += correct.sum()
        total_visible += float(vis.sum().item())
    if total_visible <= 0:
        return out
    for i, frac in enumerate(threshold_fracs):
        out[frac] = float(total_correct[i].item()) / total_visible
    return out


@torch.no_grad()
def eval_pck_freihand(model, val_loader, device: str, crop_size: int,
                      hm_size: int, threshold_frac: float,
                      use_amp_bf16: bool) -> float:
    """Single-threshold PCK back-compat wrapper around the multi-threshold
    eval. Kept so the legacy v1 config still loads."""
    multi = eval_pck_freihand_multi(model, val_loader, device, crop_size,
                                     hm_size, [threshold_frac], use_amp_bf16)
    val = multi.get(threshold_frac, float("nan"))
    if val == val:  # not NaN
        return val
    if val_loader is None:
        return float("nan")
    model.eval()
    threshold_px = threshold_frac * crop_size
    total_correct = 0.0
    total_visible = 0.0
    for batch in val_loader:
        image = batch["image"].to(device, non_blocking=True)
        gt = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)
        if use_amp_bf16 and device == "cuda":
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                pred = model(image)
        else:
            pred = model(image)
        pred_xy = soft_argmax_xy(pred.float(), crop_size, hm_size)
        diffs = (pred_xy - gt).norm(dim=-1)
        correct = (diffs <= threshold_px).float() * vis
        total_correct += float(correct.sum().item())
        total_visible += float(vis.sum().item())
    if total_visible <= 0:
        return float("nan")
    return total_correct / total_visible


def s3_upload(local_path: Path, bucket: str, key: str) -> bool:
    """Best-effort upload via the `aws` CLI. Never raises — training
    continues when S3 is misconfigured or transiently flaky. Looks at PATH
    first, then the standard `~/.local/bin/aws` fallback we install on
    spot instances.
    """
    if not bucket or not local_path.exists():
        return False
    aws = shutil.which("aws") or os.path.expanduser("~/.local/bin/aws")
    if not Path(aws).exists():
        print(f"[s3] aws CLI not found; skipping upload of {local_path.name}",
              flush=True)
        return False
    uri = f"s3://{bucket.strip('/')}/{key.lstrip('/')}"
    try:
        subprocess.run([aws, "s3", "cp", str(local_path), uri,
                        "--only-show-errors"], check=True, timeout=600)
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[s3] upload failed for {local_path.name}: {e}", flush=True)
        return False
