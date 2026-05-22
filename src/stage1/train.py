"""Stage 1 training entry point. Run via:

    python -m src.stage1.train --config configs/stage1_baseline.yaml
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm

from src.common.config import Config, dump_config, load_config
from src.common.seed import set_seed
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.unified import UnifiedKeypointDataset
from src.stage1.augment.transforms import build_train_transform, build_val_transform
from src.stage1.losses import HeatmapMSELoss
from src.stage1.metrics import compute_pck
from src.stage1.models.detector import KeypointDetector, count_params


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=str)
    parser.add_argument("--data-limit", type=int, default=None,
                        help="Optional cap on samples for smoke tests.")
    parser.add_argument("--device", type=str, default=None,
                        help="Override device (cuda / cpu / mps).")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to a checkpoint to resume from.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    set_seed(cfg.train.seed)

    device = args.device or _pick_device()
    print(f"[init] device={device}  run={cfg.run_name}")
    print(f"[init] config:\n{json.dumps(dump_config(cfg), indent=2)}")

    train_loader, val_loader = _build_loaders(cfg, args.data_limit)

    model = KeypointDetector(
        num_keypoints=cfg.model.num_keypoints,
        backbone_channels=tuple(cfg.model.backbone_channels),
        heatmap_channels=cfg.model.heatmap_channels,
    ).to(device)
    print(f"[init] params={count_params(model):,}")

    loss_fn = HeatmapMSELoss()
    optimizer = AdamW(model.parameters(), lr=cfg.train.lr,
                      weight_decay=cfg.train.weight_decay)
    scheduler = CosineAnnealingLR(
        optimizer, T_max=cfg.train.epochs, eta_min=cfg.train.lr_min,
    )

    scaler = torch.amp.GradScaler(device=device) if (cfg.train.mixed_precision and device == "cuda") else None

    ckpt_dir = Path(cfg.train.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_log = ckpt_dir / "metrics.jsonl"

    best_pck = 0.0
    patience_counter = 0
    start_epoch = 0

    if args.resume:
        print(f"[resume] loading checkpoint {args.resume}")
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        start_epoch = int(ckpt.get("epoch", 0)) + 1
        if "metrics" in ckpt and "pck_overall" in ckpt["metrics"]:
            best_pck = ckpt["metrics"]["pck_overall"]
        # Advance the scheduler so LR matches where we left off.
        for _ in range(start_epoch):
            scheduler.step()
        print(f"[resume] resuming from epoch {start_epoch}  best_pck={best_pck:.3f}  "
              f"lr={optimizer.param_groups[0]['lr']:.6f}")

    for epoch in range(start_epoch, cfg.train.epochs):
        epoch_t0 = time.time()
        train_loss = _train_one_epoch(
            model, train_loader, loss_fn, optimizer, scaler, device,
            cfg.train.log_every, epoch,
        )
        scheduler.step()

        val_metrics = _evaluate(model, val_loader, loss_fn, device, cfg)
        val_metrics["epoch"] = epoch
        val_metrics["train_loss"] = train_loss
        val_metrics["lr"] = optimizer.param_groups[0]["lr"]
        val_metrics["epoch_secs"] = round(time.time() - epoch_t0, 1)

        with metrics_log.open("a") as f:
            f.write(json.dumps(val_metrics) + "\n")

        print(f"[epoch {epoch:03d}] took={val_metrics['epoch_secs']:.1f}s  train_loss={train_loss:.5f}  "
              f"val_loss={val_metrics['val_loss']:.5f}  "
              f"pck_overall={val_metrics['pck_overall']:.3f}  "
              f"pck_hands={val_metrics['pck_hands']:.3f}  "
              f"pck_face={val_metrics['pck_face']:.3f}  "
              f"lr={val_metrics['lr']:.6f}")

        if val_metrics["pck_overall"] > best_pck + cfg.train.early_stop_min_delta:
            best_pck = val_metrics["pck_overall"]
            patience_counter = 0
            _save_checkpoint(model, ckpt_dir / "best.pt", epoch, val_metrics, cfg)
        else:
            patience_counter += 1
            if patience_counter >= cfg.train.early_stop_patience:
                print(f"[early-stop] no improvement for {patience_counter} epochs")
                break

    _save_checkpoint(model, ckpt_dir / "last.pt", epoch, val_metrics, cfg)
    print(f"[done] best pck_overall={best_pck:.3f}")


def _build_loaders(cfg: Config, data_limit: int | None) -> tuple[DataLoader, DataLoader]:
    train_tx = build_train_transform(cfg.data.image_size, cfg.data.color_jitter)
    val_tx = build_val_transform(cfg.data.image_size)

    coco_train = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_train_images}",
    )
    coco_val = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_val_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_val_images}",
    )

    # FreiHAND is optional — skip silently if not available.
    train_sources: list = [coco_train]
    freihand_path = Path(cfg.data.freihand_root)
    if (freihand_path / "training_K.json").exists():
        try:
            frei_train = FreiHANDDataset(cfg.data.freihand_root)
            train_sources.append(frei_train)
            print(f"[data] FreiHAND included: {len(frei_train):,} samples")
        except Exception as e:
            print(f"[data] FreiHAND load failed ({e}); proceeding with COCO only")
    else:
        print(f"[data] FreiHAND not at {freihand_path} — training on COCO-WholeBody only")
    print(f"[data] COCO train: {len(coco_train):,}  COCO val: {len(coco_val):,}")

    train_ds = UnifiedKeypointDataset(
        sources=train_sources,
        transform=train_tx,
        image_size=cfg.data.image_size,
        heatmap_size=cfg.data.heatmap_size,
        heatmap_sigma=cfg.data.heatmap_sigma,
    )
    val_ds = UnifiedKeypointDataset(
        sources=[coco_val],
        transform=val_tx,
        image_size=cfg.data.image_size,
        heatmap_size=cfg.data.heatmap_size,
        heatmap_sigma=cfg.data.heatmap_sigma,
    )

    if data_limit is not None:
        train_ds = Subset(train_ds, range(min(data_limit, len(train_ds))))
        val_ds = Subset(val_ds, range(min(max(data_limit // 4, 8), len(val_ds))))

    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size,
        shuffle=True, num_workers=cfg.train.num_workers,
        pin_memory=True, drop_last=True,
        persistent_workers=cfg.train.num_workers > 0,
        prefetch_factor=4 if cfg.train.num_workers > 0 else None,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.train.batch_size,
        shuffle=False, num_workers=cfg.train.num_workers,
        pin_memory=True,
        persistent_workers=cfg.train.num_workers > 0,
        prefetch_factor=4 if cfg.train.num_workers > 0 else None,
    )
    return train_loader, val_loader


def _train_one_epoch(model, loader, loss_fn, optimizer, scaler, device,
                     log_every, epoch) -> float:
    model.train()
    running = 0.0
    n_batches = 0
    pbar = tqdm(loader, desc=f"epoch {epoch:03d} train", leave=False)
    for step, batch in enumerate(pbar):
        image = batch["image"].to(device, non_blocking=True)
        heatmaps = batch["heatmaps"].to(device, non_blocking=True)
        vis_mask = batch["visible"].to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        if scaler is not None:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                pred = model(image)
                loss = loss_fn(pred, heatmaps, vis_mask)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            pred = model(image)
            loss = loss_fn(pred, heatmaps, vis_mask)
            loss.backward()
            optimizer.step()

        running += float(loss.detach().item())
        n_batches += 1
        if (step + 1) % log_every == 0:
            pbar.set_postfix(loss=f"{running / n_batches:.5f}")

    return running / max(n_batches, 1)


@torch.no_grad()
def _evaluate(model, loader, loss_fn, device, cfg) -> dict:
    model.eval()
    val_loss = 0.0
    pck_acc = {"pck_overall": 0.0, "pck_hands": 0.0, "pck_face": 0.0, "pck_body": 0.0}
    n = 0
    for batch in loader:
        image = batch["image"].to(device, non_blocking=True)
        heatmaps = batch["heatmaps"].to(device, non_blocking=True)
        vis_mask = batch["visible"].to(device, non_blocking=True)
        gt_kps = batch["keypoints"].to(device, non_blocking=True)

        pred = model(image)
        val_loss += float(loss_fn(pred, heatmaps, vis_mask).item())
        m = compute_pck(
            pred, gt_kps, vis_mask,
            image_size=cfg.data.image_size,
            heatmap_size=cfg.data.heatmap_size,
        )
        for k in pck_acc:
            v = m[k]
            if not math.isnan(v):
                pck_acc[k] += v
        n += 1

    out = {k: v / max(n, 1) for k, v in pck_acc.items()}
    out["val_loss"] = val_loss / max(n, 1)
    return out


def _save_checkpoint(model, path: Path, epoch: int, metrics: dict, cfg: Config) -> None:
    torch.save(
        {
            "model": model.state_dict(),
            "epoch": epoch,
            "metrics": metrics,
            "config": dump_config(cfg),
        },
        path,
    )


def _pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


if __name__ == "__main__":
    main()
