"""Stage 1 v3 — Net 3 (hand landmark) DIRECT-REGRESSION training.

  python3 -u -m src.stage1.train_v3_landmark_reg \
      --config configs/stage1_v3_landmark_reg.yaml

Mirrors ``train_v3_landmark.py`` but trains ``HandLandmarkRegNet`` (direct
coordinate regression, BlazeHand-style) instead of the heatmap head:
  - no heatmap rendering, no CUDA-Graphs capture (kept simple);
  - GPU-augments image + keypoints, then normalizes GT coords to [0, 1] by
    dividing by crop_size;
  - RegressionLandmarkLoss (masked smooth-L1 on xy, optional z/presence);
  - per-epoch FreiHAND PCK at fracs [0.05, 0.10, 0.20] from the regressed
    coords directly, using EMA weights.

Checkpoints use the shared dict format plus ``"head_type": "regression"``.
Reuses build_target_mix_sampler / build_freihand_val_loader / s3_upload from
``train_v3_landmark_helpers`` (the heatmap PCK helpers are NOT used — the
regression head has no heatmaps to soft-argmax).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm

import torch.multiprocessing as _mp
try:
    _mp.set_sharing_strategy("file_system")
except RuntimeError:
    pass

torch.backends.cudnn.benchmark = True

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.augment.transforms_v3 import GPUAugmentation
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.data.landmark_dataset import LandmarkTrainDataset
from src.stage1.losses_landmark_reg import RegressionLandmarkLoss
from src.stage1.models.landmark_net import HandLandmarkRegNet, count_params
from src.stage1.train_v3_landmark_helpers import (
    build_freihand_val_loader, build_rhd_dataset, build_target_mix_sampler,
    s3_upload,
)


@torch.no_grad()
def eval_pck_reg(model, val_loader, device: str, crop_size: int,
                 threshold_fracs: list[float], use_amp_bf16: bool
                 ) -> dict[float, float]:
    """Multi-threshold PCK for the regression head, computed directly from
    the regressed coords. pred_xy_norm * crop_size → px; PCK = fraction of
    visible joints within frac * crop_size. Returns {frac: pck}.
    """
    out: dict[float, float] = {f: float("nan") for f in threshold_fracs}
    if val_loader is None:
        return out
    model.eval()
    thr_px = torch.tensor([f * crop_size for f in threshold_fracs], device=device)
    total_correct = torch.zeros(len(threshold_fracs), device=device)
    total_visible = 0.0
    for batch in val_loader:
        image = batch["image"].to(device, non_blocking=True)
        gt = batch["keypoints"].to(device, non_blocking=True)        # (B, K, 2) px
        vis = batch["visible"].to(device, non_blocking=True)         # (B, K)
        if use_amp_bf16 and device == "cuda":
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                pred = model(image)
        else:
            pred = model(image)
        pred_xy = pred["coords"][..., :2].float() * crop_size        # (B, K, 2) px
        diffs = (pred_xy - gt).norm(dim=-1)                          # (B, K)
        for i, t in enumerate(thr_px):
            total_correct[i] += ((diffs <= t).float() * vis).sum()
        total_visible += float(vis.sum().item())
    if total_visible <= 0:
        return out
    for i, frac in enumerate(threshold_fracs):
        out[frac] = float(total_correct[i].item()) / total_visible
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--data-limit", type=int, default=None)
    p.add_argument("--max-steps", type=int, default=None,
                   help="Cap training steps per epoch (smoke testing).")
    p.add_argument("--max-epochs", type=int, default=None,
                   help="Override config epochs (smoke testing).")
    p.add_argument("--device", default=None)
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    set_seed(deep_get(cfg, "train.seed", 42))
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}  run={cfg.get('run_name')}  head=regression",
          flush=True)

    # Data --------------------------------------------------------------
    freihand = FreiHANDDataset(deep_get(cfg, "data.freihand_root"))
    interhand = None
    ih_root = deep_get(cfg, "data.interhand_root")
    if ih_root and (Path(ih_root) / "annotations" / "train").exists():
        interhand = InterHand26MDataset(ih_root, split="train")
    rhd = build_rhd_dataset(cfg)
    print(f"[data] freihand={len(freihand):,}  "
          f"interhand={len(interhand) if interhand else 0:,}  "
          f"rhd={len(rhd) if rhd else 0:,}", flush=True)

    canonicalize = bool(deep_get(cfg, "data.canonicalize_rotation", False))
    train_ds = LandmarkTrainDataset(
        freihand, interhand,
        crop_size=deep_get(cfg, "data.crop_size", 224),
        padding_frac=deep_get(cfg, "data.padding_frac", 0.5),
        jitter_shift=deep_get(cfg, "data.jitter_shift", 0.10),
        jitter_scale=deep_get(cfg, "data.jitter_scale", 0.15),
        jitter_rot=deep_get(cfg, "data.jitter_rot", 10.0),
        phase2_bbox_cache=deep_get(cfg, "data.phase2_bbox_cache"),
        phase2_mix_prob=deep_get(cfg, "data.phase2_mix_prob", 0.0),
        rhd_dataset=rhd,
        canonicalize_rotation=canonicalize,
    )
    print(f"[data] canonicalize_rotation={canonicalize}", flush=True)

    target_mix = deep_get(cfg, "data.target_mix") or {}
    samples_per_epoch = deep_get(cfg, "train.samples_per_epoch")
    sampler = build_target_mix_sampler(train_ds, target_mix,
                                       num_samples=samples_per_epoch)
    if args.data_limit:
        train_ds = Subset(train_ds, range(min(args.data_limit, len(train_ds))))
        sampler = None  # Subset breaks the sampler's index alignment

    loader = DataLoader(
        train_ds, batch_size=deep_get(cfg, "train.batch_size"),
        shuffle=(sampler is None), sampler=sampler,
        num_workers=deep_get(cfg, "train.num_workers"),
        pin_memory=True, drop_last=True,
        persistent_workers=deep_get(cfg, "train.num_workers") > 0,
        prefetch_factor=4 if deep_get(cfg, "train.num_workers") > 0 else None,
    )
    if sampler is not None:
        print(f"[data] target_mix sampler active: {target_mix}", flush=True)

    # Model + loss ------------------------------------------------------
    model = HandLandmarkRegNet(
        num_keypoints=deep_get(cfg, "model.num_keypoints", 21),
        with_z=bool(deep_get(cfg, "model.with_z", True)),
        with_presence=bool(deep_get(cfg, "model.with_presence", True)),
    ).to(device)
    print(f"[init] HandLandmarkRegNet params={count_params(model):,}", flush=True)

    resume_from = deep_get(cfg, "train.resume_from")
    if resume_from and Path(resume_from).exists():
        ckpt = torch.load(resume_from, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        print(f"[init] resumed from {resume_from} (epoch={ckpt.get('epoch')})",
              flush=True)

    loss_fn = RegressionLandmarkLoss(
        loss_type=str(deep_get(cfg, "loss.loss_type", "smooth_l1")),
        beta=float(deep_get(cfg, "loss.beta", 0.04)),
        wing_omega=float(deep_get(cfg, "loss.wing_omega", 0.1)),
        wing_epsilon=float(deep_get(cfg, "loss.wing_epsilon", 0.02)),
        z_weight=float(deep_get(cfg, "loss.z_weight", 0.0)),
        presence_weight=float(deep_get(cfg, "loss.presence_weight", 0.0)),
        keypoint_weights=deep_get(cfg, "loss.keypoint_weights"),
    )
    optimizer = AdamW(model.parameters(), lr=deep_get(cfg, "train.lr"),
                      weight_decay=deep_get(cfg, "train.weight_decay"))
    total_epochs = args.max_epochs or deep_get(cfg, "train.epochs")
    scheduler = CosineAnnealingLR(optimizer, T_max=total_epochs,
                                  eta_min=deep_get(cfg, "train.lr_min"))
    use_amp_bf16 = (bool(deep_get(cfg, "train.use_bf16",
                                  deep_get(cfg, "train.mixed_precision", False)))
                    and device == "cuda")
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
        deep_get(cfg, "train.ema_decay", 0.9998)))

    aug_cfg = (cfg.get("augment") if isinstance(cfg, dict) else None) or {}
    gpu_aug = GPUAugmentation(
        image_size=deep_get(cfg, "data.crop_size", 224),
        rotate_deg=float(aug_cfg.get("rotate_deg", 15.0)),
        scale_range=tuple(aug_cfg.get("scale_range", (0.75, 1.25))),
        shift_frac=float(aug_cfg.get("shift_frac", 0.08)),
        hflip_p=float(aug_cfg.get("hflip_p", 0.0)),
        brightness=float(aug_cfg.get("brightness", 0.3)),
        contrast=float(aug_cfg.get("contrast", 0.3)),
        saturation=float(aug_cfg.get("saturation", 0.3)),
        hue=float(aug_cfg.get("hue", 0.1)),
        blur_p=float(aug_cfg.get("blur_p", 0.2)),
        noise_p=float(aug_cfg.get("noise_p", 0.2)),
    )

    ckpt_dir = Path(deep_get(cfg, "train.checkpoint_dir"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_log = ckpt_dir / "metrics.jsonl"

    warmup = deep_get(cfg, "train.warmup_epochs", 0)
    best_pck = 0.0
    patience = 0
    crop_size = deep_get(cfg, "data.crop_size", 224)

    val_loader, val_n = build_freihand_val_loader(cfg, crop_size)
    if val_loader is not None:
        print(f"[val] FreiHAND held-out PCK eval enabled — {val_n} samples",
              flush=True)
    else:
        print("[val] FreiHAND held-out split unavailable; val_pck will be nan",
              flush=True)
    pck_thresh_frac = float(deep_get(cfg, "eval.pck_threshold_frac", 0.05))
    pck_thresh_fracs = [float(x) for x in
                        deep_get(cfg, "eval.pck_threshold_fracs", [pck_thresh_frac])]
    pck_headline_frac = 0.05 if 0.05 in pck_thresh_fracs else min(pck_thresh_fracs)

    s3_bucket = str(deep_get(cfg, "train.s3_bucket", "") or "").strip()
    s3_prefix = str(deep_get(cfg, "train.s3_prefix", "net3/checkpoints_reg")).strip("/")
    s3_sync_every = int(deep_get(cfg, "train.s3_sync_every", 10))
    if s3_bucket:
        print(f"[s3] sync target: s3://{s3_bucket}/{s3_prefix}/ every "
              f"{s3_sync_every} epochs", flush=True)

    def _save(path: Path, epoch: int, line: dict) -> None:
        torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                    "metrics": line, "config": cfg,
                    "head_type": "regression"}, path)

    line: dict = {}
    epoch = 0
    for epoch in range(total_epochs):
        epoch_t0 = time.time()
        if epoch < warmup:
            for pg in optimizer.param_groups:
                pg["lr"] = deep_get(cfg, "train.lr") * (epoch + 1) / max(warmup, 1)

        model.train()
        running = 0.0
        n_steps = 0
        pck_acc = 0.0
        threshold_px = pck_headline_frac * crop_size

        pbar = tqdm(loader, desc=f"epoch {epoch:03d}", leave=False)
        for batch in pbar:
            image = batch["image"].to(device, non_blocking=True)
            coords = batch["keypoints"].to(device, non_blocking=True)   # px
            vis = batch["visible"].to(device, non_blocking=True)

            with torch.no_grad():
                image, coords_aug = gpu_aug(image, coords)
                if coords_aug is None:
                    coords_aug = coords
                # Out-of-frame after aug → not visible.
                in_frame = ((coords_aug[..., 0] >= 0) & (coords_aug[..., 0] < crop_size)
                            & (coords_aug[..., 1] >= 0) & (coords_aug[..., 1] < crop_size))
                vis_eff = vis * in_frame.float()
                gt_norm = coords_aug / crop_size                        # → [0, 1]

            optimizer.zero_grad(set_to_none=True)
            if use_amp_bf16:
                with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                    pred = model(image)
                    out = loss_fn(pred["coords"], gt_norm, vis_eff,
                                  presence_logit=pred.get("presence"))
            else:
                pred = model(image)
                out = loss_fn(pred["coords"], gt_norm, vis_eff,
                              presence_logit=pred.get("presence"))
            out["loss"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                           deep_get(cfg, "train.grad_clip", 1.0))
            optimizer.step()
            ema.update_parameters(model)
            running += float(out["loss"].item())
            n_steps += 1

            with torch.no_grad():
                pred_px = pred["coords"][..., :2].float() * crop_size
                diffs = (pred_px - coords_aug).norm(dim=-1)
                correct = (diffs <= threshold_px).float() * vis_eff
                pck_acc += float(correct.sum() / vis_eff.sum().clamp(min=1).item())

            if args.max_steps is not None and n_steps >= args.max_steps:
                break

        if epoch >= warmup:
            scheduler.step()

        val_pck_multi = eval_pck_reg(ema.module, val_loader, device, crop_size,
                                     pck_thresh_fracs, use_amp_bf16)
        val_pck_headline = val_pck_multi.get(pck_headline_frac, float("nan"))

        epoch_secs = time.time() - epoch_t0
        avg_loss = running / max(n_steps, 1)
        avg_pck = pck_acc / max(n_steps, 1)
        line = {
            "epoch": epoch, "epoch_secs": round(epoch_secs, 1),
            "train_loss": avg_loss, "train_pck": avg_pck,
            "val_pck": val_pck_headline,
            "lr": optimizer.param_groups[0]["lr"],
        }
        for frac in pck_thresh_fracs:
            line[f"val_pck_{int(round(frac * 100)):02d}"] = \
                val_pck_multi.get(frac, float("nan"))
        with metrics_log.open("a") as f:
            f.write(json.dumps(line) + "\n")
        parts = []
        for frac in pck_thresh_fracs:
            v = val_pck_multi.get(frac, float("nan"))
            tag = f"val_pck_{int(round(frac * 100)):02d}"
            parts.append(f"{tag} {v:.3f}" if v == v else f"{tag} nan")
        print(f"epoch {epoch} | train_loss {avg_loss:.3f} | "
              f"{' | '.join(parts)} | elapsed {epoch_secs/60:.1f} min", flush=True)

        score = val_pck_headline if (val_pck_headline == val_pck_headline) else avg_pck
        improved = score > best_pck + deep_get(cfg, "train.early_stop_min_delta", 0.001)
        if improved:
            best_pck = score
            patience = 0
            best_path = ckpt_dir / "best.pt"
            _save(best_path, epoch, line)
            # Lean export mirror — already has no optimizer state.
            export_path = ckpt_dir / "best_export.pt"
            _save(export_path, epoch, line)
            if s3_bucket:
                s3_upload(best_path, s3_bucket, f"{s3_prefix}/best.pt")
                s3_upload(export_path, s3_bucket, f"{s3_prefix}/best_export.pt")
        else:
            patience += 1
            if patience >= deep_get(cfg, "train.early_stop_patience", 25):
                print(f"[early-stop] no improvement for {patience} epochs", flush=True)
                break
        if (epoch + 1) % 10 == 0:
            snap_path = ckpt_dir / f"epoch_{epoch:03d}.pt"
            _save(snap_path, epoch, line)
            if s3_bucket and ((epoch + 1) % s3_sync_every == 0):
                s3_upload(snap_path, s3_bucket, f"{s3_prefix}/{snap_path.name}")
                s3_upload(metrics_log, s3_bucket, f"{s3_prefix}/metrics.jsonl")

    last_path = ckpt_dir / "last.pt"
    _save(last_path, epoch, line)
    if s3_bucket:
        s3_upload(last_path, s3_bucket, f"{s3_prefix}/last.pt")
        s3_upload(metrics_log, s3_bucket, f"{s3_prefix}/metrics.jsonl")
    print(f"[done] best_pck={best_pck:.3f}", flush=True)


if __name__ == "__main__":
    main()
