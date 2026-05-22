"""Stage 1 v2 training entry point: cached-data pipeline with GPU heatmaps.

  python -m src.stage1.train_v2 --config configs/stage1_v2.yaml

Differences from v1:
  - Reads from preprocess_cache.py output (decoded .npy images)
  - Lighter augmentation (no Motion/Gaussian/Noise OneOf)
  - Heatmap rasterization on GPU instead of CPU
  - Reports val PCK separately for COCO and FreiHAND
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import ConcatDataset, DataLoader, Subset
from tqdm import tqdm

from src.common.config import Config, dump_config, load_config
from src.common.seed import set_seed
from src.stage1.augment.transforms_v2 import build_train_transform_v2, build_val_transform_v2
from src.stage1.data import schema as S
from src.stage1.data.cached import CachedKeypointDataset, gpu_render_heatmaps
from src.stage1.losses import HeatmapMSELoss
from src.stage1.metrics import compute_pck
from src.stage1.models.detector import KeypointDetector, count_params


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache-root", default="data/cache/stage1")
    parser.add_argument("--data-limit", type=int, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    set_seed(cfg.train.seed)
    device = args.device or _pick_device()
    print(f"[init] device={device}  run={cfg.run_name}")
    print(f"[init] config:\n{json.dumps(dump_config(cfg), indent=2)}")

    train_tx = build_train_transform_v2(cfg.data.image_size, cfg.data.color_jitter)
    val_tx = build_val_transform_v2(cfg.data.image_size)

    cache_root = Path(args.cache_root)
    train_sources, val_sources = [], {}
    for name in ("coco_train", "freihand_train"):
        if (cache_root / name).exists():
            train_sources.append(
                CachedKeypointDataset(cache_root, name, train_tx, cfg.data.image_size)
            )
            print(f"[data] train: {name} ({len(train_sources[-1]):,})")
    for name in ("coco_val", "freihand_val"):
        if (cache_root / name).exists():
            val_sources[name] = CachedKeypointDataset(
                cache_root, name, val_tx, cfg.data.image_size,
            )
            print(f"[data] val:   {name} ({len(val_sources[name]):,})")

    if not train_sources:
        raise SystemExit(f"no cached training datasets at {cache_root}")

    train_ds = ConcatDataset(train_sources)
    if args.data_limit:
        train_ds = Subset(train_ds, range(min(args.data_limit, len(train_ds))))

    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size, shuffle=True,
        num_workers=cfg.train.num_workers, pin_memory=True, drop_last=True,
        persistent_workers=cfg.train.num_workers > 0,
        prefetch_factor=4 if cfg.train.num_workers > 0 else None,
    )
    val_loaders = {
        name: DataLoader(
            ds, batch_size=cfg.train.batch_size, shuffle=False,
            num_workers=cfg.train.num_workers, pin_memory=True,
            persistent_workers=cfg.train.num_workers > 0,
        )
        for name, ds in val_sources.items()
    }

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

    for epoch in range(cfg.train.epochs):
        epoch_t0 = time.time()
        train_loss = _train_one_epoch(model, train_loader, loss_fn, optimizer,
                                      scaler, device, cfg, epoch)
        scheduler.step()

        val_metrics = {"epoch": epoch, "train_loss": train_loss,
                       "lr": optimizer.param_groups[0]["lr"]}
        for name, loader in val_loaders.items():
            m = _evaluate(model, loader, loss_fn, device, cfg)
            for k, v in m.items():
                val_metrics[f"{name}/{k}"] = v

        epoch_secs = time.time() - epoch_t0
        val_metrics["epoch_secs"] = round(epoch_secs, 1)

        with metrics_log.open("a") as f:
            f.write(json.dumps(val_metrics) + "\n")

        # Combined PCK across all val sources for the early-stop criterion.
        pcks = [v for k, v in val_metrics.items() if k.endswith("/pck_overall")]
        combined_pck = sum(pcks) / max(len(pcks), 1)
        print(f"[epoch {epoch:03d}] took={epoch_secs:.1f}s  train_loss={train_loss:.5f}  "
              f"combined_pck={combined_pck:.3f}  "
              + "  ".join(f"{k}={v:.3f}" for k, v in val_metrics.items()
                          if "/pck_overall" in k or "/pck_hands" in k))

        if combined_pck > best_pck + cfg.train.early_stop_min_delta:
            best_pck = combined_pck
            patience_counter = 0
            _save_checkpoint(model, ckpt_dir / "best.pt", epoch, val_metrics, cfg)
        else:
            patience_counter += 1
            if patience_counter >= cfg.train.early_stop_patience:
                print(f"[early-stop] no improvement for {patience_counter} epochs")
                break

        # Periodic checkpoint snapshots — kept across the run for inspection.
        if (epoch + 1) % 10 == 0:
            _save_checkpoint(model, ckpt_dir / f"epoch_{epoch:03d}.pt",
                             epoch, val_metrics, cfg)

    _save_checkpoint(model, ckpt_dir / "last.pt", epoch, val_metrics, cfg)
    print(f"[done] best combined_pck={best_pck:.3f}")


def _train_one_epoch(model, loader, loss_fn, optimizer, scaler, device,
                     cfg: Config, epoch: int) -> float:
    model.train()
    running, n = 0.0, 0
    pbar = tqdm(loader, desc=f"epoch {epoch:03d} train", leave=False)
    for batch in pbar:
        image = batch["image"].to(device, non_blocking=True)
        kp = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)

        with torch.no_grad():
            heatmaps, vis_mask = gpu_render_heatmaps(
                kp, vis, cfg.data.image_size, cfg.data.heatmap_size,
                sigma=cfg.data.heatmap_sigma,
            )

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
        n += 1
    return running / max(n, 1)


@torch.no_grad()
def _evaluate(model, loader, loss_fn, device, cfg: Config) -> dict:
    model.eval()
    val_loss = 0.0
    pck_acc = {"pck_overall": 0.0, "pck_hands": 0.0, "pck_face": 0.0, "pck_body": 0.0}
    n = 0
    for batch in loader:
        image = batch["image"].to(device, non_blocking=True)
        kp = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)
        heatmaps, vis_mask = gpu_render_heatmaps(
            kp, vis, cfg.data.image_size, cfg.data.heatmap_size,
            sigma=cfg.data.heatmap_sigma,
        )
        pred = model(image)
        val_loss += float(loss_fn(pred, heatmaps, vis_mask).item())
        m = compute_pck(
            pred, kp, vis_mask,
            image_size=cfg.data.image_size, heatmap_size=cfg.data.heatmap_size,
        )
        for k, v in m.items():
            if not math.isnan(v):
                pck_acc[k] += v
        n += 1
    out = {k: v / max(n, 1) for k, v in pck_acc.items()}
    out["val_loss"] = val_loss / max(n, 1)
    return out


def _save_checkpoint(model, path: Path, epoch: int, metrics: dict, cfg: Config) -> None:
    torch.save({"model": model.state_dict(), "epoch": epoch,
                "metrics": metrics, "config": dump_config(cfg)}, path)


def _pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


if __name__ == "__main__":
    main()
