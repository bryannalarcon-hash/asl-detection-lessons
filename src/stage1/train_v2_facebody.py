"""Net 1 (face + body only) retrain.

Fork of `train_v2.py` with Round 2 transferable optimizations:
  - BF16 mixed precision (no GradScaler; works on Blackwell + Hopper)
  - channels_last NHWC memory format
  - Fused AdamW kernel
  - num_workers=32 for cached DataLoader (page-fault parallelism)

Plus the face+body slice (`data.keypoint_slice = [42, 49]`) — drops the
21+21 hand keypoints, training only NOSE/CHIN/FOREHEAD + CHEST/L_SHO/R_SHO/NECK.
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
from torch.utils.data import ConcatDataset, DataLoader, Subset, WeightedRandomSampler
from tqdm import tqdm

from src.common.config import Config, dump_config, load_config
from src.common.seed import set_seed
from src.stage1.augment.transforms_v2 import build_train_transform_v2, build_val_transform_v2
from src.stage1.data import schema as S
from src.stage1.data.cached import CachedKeypointDataset, gpu_render_heatmaps
from src.stage1.losses import HeatmapMSELoss
from src.stage1.metrics import compute_pck
from src.stage1.models.detector import KeypointDetector, count_params


def _slice_kp(kp: torch.Tensor, vis: torch.Tensor, kslice: list | None) -> tuple[torch.Tensor, torch.Tensor]:
    if kslice is None:
        return kp, vis
    s, e = int(kslice[0]), int(kslice[1])
    return kp[..., s:e, :], vis[..., s:e]


# Maps target_mix YAML keys to the cache subdir names produced by
# preprocess_cache.py. Aliases are intentional: configs use the human-readable
# dataset name, the cache is keyed by split-suffixed dir.
_SOURCE_TO_CACHE: dict[str, str] = {
    "coco_wholebody": "coco_train",
    "coco": "coco_train",
    "freihand": "freihand_train",
    "mpii": "mpii_train",
}


def _build_weighted_sampler(
    train_sources: list, source_names: list[str], target_mix: dict,
) -> WeightedRandomSampler | None:
    """Per-sample WeightedRandomSampler that yields the requested mix.

    train_sources / source_names are aligned: source_names[i] is the
    config key for train_sources[i]. Unknown mix keys are dropped with a
    warning. Sources present in the cache but absent from the mix are
    weighted to zero (they won't appear during this run). Remaining
    weights are renormalized over the surviving sources.

    Returns None if the mix degenerates to a single source (use the default
    shuffle path instead).
    """
    if not target_mix:
        return None
    present = {name for name in source_names}
    pruned = {k: float(v) for k, v in target_mix.items() if k in present and v > 0}
    for missing in set(target_mix) - pruned.keys():
        print(f"[sampler] warn: target_mix key {missing!r} has no cache "
              f"or zero weight; skipping")
    if not pruned:
        print("[sampler] warn: no target_mix sources resolved; falling back "
              "to uniform shuffle")
        return None
    if len(pruned) == 1:
        print(f"[sampler] note: only one source ({next(iter(pruned))}) "
              "resolved; falling back to uniform shuffle")
        return None
    total = sum(pruned.values())
    norm = {k: v / total for k, v in pruned.items()}

    # Per-sample weight = (target_proportion_of_source / samples_in_source).
    # WeightedRandomSampler then yields ~target_proportion of its draws
    # from each source.
    weights: list[float] = []
    counts: list[int] = []
    for ds, name in zip(train_sources, source_names):
        n = len(ds)
        counts.append(n)
        p = norm.get(name, 0.0)
        if p == 0.0 or n == 0:
            weights.extend([0.0] * n)
        else:
            weights.extend([p / n] * n)
    sampler_len = sum(counts)
    print(f"[sampler] target_mix={norm}  total_samples={sampler_len:,}")
    return WeightedRandomSampler(
        weights=weights, num_samples=sampler_len, replacement=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache-root", default="data/cache/stage1")
    parser.add_argument("--data-limit", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--resume-from", type=str, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    set_seed(cfg.train.seed)
    device = args.device or _pick_device()
    print(f"[init] device={device}  run={cfg.run_name}")
    print(f"[init] keypoint_slice={cfg.data.keypoint_slice}  num_keypoints={cfg.model.num_keypoints}")
    print(f"[init] bf16={cfg.train.use_bf16}  channels_last={cfg.train.channels_last}  fused_adamw={cfg.train.fused_adamw}")

    # cudnn benchmark — auto-pick fastest conv algo per shape.
    torch.backends.cudnn.benchmark = True

    train_tx = build_train_transform_v2(cfg.data.image_size, cfg.data.color_jitter)
    val_tx = build_val_transform_v2(cfg.data.image_size)

    cache_root = Path(args.cache_root)
    train_sources, val_sources = [], {}
    # Reverse-map cache dir name back to the target_mix key so the sampler
    # can resolve weights even when configs use either alias.
    cache_to_source: dict[str, str] = {}
    for src_key, cache_name in _SOURCE_TO_CACHE.items():
        cache_to_source.setdefault(cache_name, src_key)
    source_names: list[str] = []
    for cache_name in ("coco_train", "freihand_train", "mpii_train"):
        if (cache_root / cache_name).exists():
            train_sources.append(
                CachedKeypointDataset(cache_root, cache_name, train_tx, cfg.data.image_size)
            )
            source_names.append(cache_to_source.get(cache_name, cache_name))
            print(f"[data] train: {cache_name} ({len(train_sources[-1]):,})")
    for name in ("coco_val", "freihand_val"):
        if (cache_root / name).exists():
            val_sources[name] = CachedKeypointDataset(
                cache_root, name, val_tx, cfg.data.image_size,
            )
            print(f"[data] val:   {name} ({len(val_sources[name]):,})")
    if not train_sources:
        raise SystemExit(f"no cached training datasets at {cache_root}")

    train_ds = ConcatDataset(train_sources)
    sampler = _build_weighted_sampler(train_sources, source_names, cfg.data.target_mix)
    if args.data_limit:
        train_ds = Subset(train_ds, range(min(args.data_limit, len(train_ds))))
        # Subset breaks the per-source index mapping the sampler was built on.
        sampler = None

    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size,
        shuffle=(sampler is None), sampler=sampler,
        num_workers=cfg.train.num_workers, pin_memory=True, drop_last=True,
        persistent_workers=cfg.train.num_workers > 0,
        prefetch_factor=4 if cfg.train.num_workers > 0 else None,
    )
    val_loaders = {
        name: DataLoader(
            ds, batch_size=cfg.train.batch_size, shuffle=False,
            num_workers=min(cfg.train.num_workers, 8), pin_memory=True,
            persistent_workers=cfg.train.num_workers > 0,
        )
        for name, ds in val_sources.items()
    }

    model = KeypointDetector(
        num_keypoints=cfg.model.num_keypoints,
        backbone_channels=tuple(cfg.model.backbone_channels),
        heatmap_channels=cfg.model.heatmap_channels,
    ).to(device)
    if cfg.train.channels_last and device == "cuda":
        model = model.to(memory_format=torch.channels_last)
        print("[init] model converted to channels_last (NHWC)")
    print(f"[init] params={count_params(model):,}")

    loss_fn = HeatmapMSELoss()
    optimizer = AdamW(model.parameters(), lr=cfg.train.lr,
                      weight_decay=cfg.train.weight_decay,
                      fused=(cfg.train.fused_adamw and device == "cuda"))
    scheduler = CosineAnnealingLR(
        optimizer, T_max=cfg.train.epochs, eta_min=cfg.train.lr_min,
    )
    # BF16: no GradScaler needed (BF16 has FP32 exponent range).
    use_bf16 = cfg.train.use_bf16 and cfg.train.mixed_precision and device == "cuda"
    scaler = None
    if cfg.train.mixed_precision and device == "cuda" and not use_bf16:
        scaler = torch.amp.GradScaler(device=device)

    ckpt_dir = Path(cfg.train.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_log = ckpt_dir / "metrics.jsonl"

    # Resume support — CLI flag overrides config-side resume_from.
    resume_path = args.resume_from or cfg.train.resume_from
    start_epoch = 0
    best_pck = 0.0
    if resume_path and Path(resume_path).exists():
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        # Two modes:
        #   (a) checkpoint contains optimizer state -> "resume" of an
        #       interrupted run; preserve epoch counter, fast-forward
        #       scheduler, keep the prior best_pck.
        #   (b) optimizer state absent -> "finetune" from a pretrained
        #       checkpoint. Reset epoch counter so the new cosine
        #       schedule runs cfg.train.epochs from scratch, and reset
        #       best_pck so the new run can save its own best.pt.
        opt_state = ckpt.get("optimizer")
        if opt_state is not None:
            try:
                optimizer.load_state_dict(opt_state)
                start_epoch = int(ckpt.get("epoch", 0)) + 1
                for _ in range(start_epoch):
                    scheduler.step()
                last_metrics = ckpt.get("metrics", {})
                pcks = [v for k, v in last_metrics.items()
                        if k.endswith("/pck_overall")]
                if pcks:
                    best_pck = sum(pcks) / max(len(pcks), 1)
                print(f"[init] resumed from {resume_path} → epoch {start_epoch}  "
                      f"best_pck={best_pck:.3f}")
            except (ValueError, RuntimeError) as exc:
                print(f"[init] warn: optimizer state present but failed to "
                      f"restore ({exc}); treating as finetune-from-pretrained")
        else:
            print(f"[init] finetune from {resume_path} (no optimizer state); "
                  f"scheduler restarts at epoch 0")

    patience_counter = 0
    kslice = cfg.data.keypoint_slice

    for epoch in range(start_epoch, cfg.train.epochs):
        epoch_t0 = time.time()
        train_loss = _train_one_epoch(
            model, train_loader, loss_fn, optimizer, scaler, device, cfg, epoch,
            use_bf16=use_bf16, kslice=kslice,
        )
        scheduler.step()

        val_metrics = {"epoch": epoch, "train_loss": train_loss,
                       "lr": optimizer.param_groups[0]["lr"]}
        for name, loader in val_loaders.items():
            m = _evaluate(model, loader, loss_fn, device, cfg, use_bf16=use_bf16, kslice=kslice)
            for k, v in m.items():
                val_metrics[f"{name}/{k}"] = v

        epoch_secs = time.time() - epoch_t0
        val_metrics["epoch_secs"] = round(epoch_secs, 1)

        with metrics_log.open("a") as f:
            f.write(json.dumps(val_metrics) + "\n")

        pcks = [v for k, v in val_metrics.items() if k.endswith("/pck_overall")]
        combined_pck = sum(pcks) / max(len(pcks), 1)
        print(f"[epoch {epoch:03d}] took={epoch_secs:.1f}s  train_loss={train_loss:.5f}  "
              f"combined_pck={combined_pck:.3f}  "
              + "  ".join(f"{k}={v:.3f}" for k, v in val_metrics.items()
                          if "/pck_face" in k or "/pck_body" in k), flush=True)

        if combined_pck > best_pck + cfg.train.early_stop_min_delta:
            best_pck = combined_pck
            patience_counter = 0
            _save_checkpoint(model, ckpt_dir / "best.pt", epoch, val_metrics, cfg,
                             optimizer=optimizer)
        else:
            patience_counter += 1
            if patience_counter >= cfg.train.early_stop_patience:
                print(f"[early-stop] no improvement for {patience_counter} epochs")
                break

        if (epoch + 1) % 10 == 0:
            _save_checkpoint(model, ckpt_dir / f"epoch_{epoch:03d}.pt",
                             epoch, val_metrics, cfg, optimizer=optimizer)

    _save_checkpoint(model, ckpt_dir / "last.pt", epoch, val_metrics, cfg,
                     optimizer=optimizer)
    print(f"[done] best combined_pck={best_pck:.3f}")


def _train_one_epoch(model, loader, loss_fn, optimizer, scaler, device,
                     cfg: Config, epoch: int, use_bf16: bool, kslice) -> float:
    model.train()
    running, n = 0.0, 0
    pbar = tqdm(loader, desc=f"epoch {epoch:03d} train", leave=False)
    for batch in pbar:
        image = batch["image"].to(device, non_blocking=True)
        if cfg.train.channels_last and device == "cuda":
            image = image.contiguous(memory_format=torch.channels_last)
        kp = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)
        kp, vis = _slice_kp(kp, vis, kslice)

        with torch.no_grad():
            heatmaps, vis_mask = gpu_render_heatmaps(
                kp, vis, cfg.data.image_size, cfg.data.heatmap_size,
                sigma=cfg.data.heatmap_sigma,
            )

        optimizer.zero_grad(set_to_none=True)
        if use_bf16:
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                pred = model(image)
                loss = loss_fn(pred, heatmaps, vis_mask)
            loss.backward()
            optimizer.step()
        elif scaler is not None:
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
def _evaluate(model, loader, loss_fn, device, cfg: Config, use_bf16: bool, kslice) -> dict:
    model.eval()
    val_loss = 0.0
    pck_acc = {"pck_overall": 0.0, "pck_hands": 0.0, "pck_face": 0.0, "pck_body": 0.0}
    n = 0
    for batch in loader:
        image = batch["image"].to(device, non_blocking=True)
        if cfg.train.channels_last and device == "cuda":
            image = image.contiguous(memory_format=torch.channels_last)
        kp = batch["keypoints"].to(device, non_blocking=True)
        vis = batch["visible"].to(device, non_blocking=True)
        kp, vis = _slice_kp(kp, vis, kslice)
        heatmaps, vis_mask = gpu_render_heatmaps(
            kp, vis, cfg.data.image_size, cfg.data.heatmap_size,
            sigma=cfg.data.heatmap_sigma,
        )
        if use_bf16:
            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                pred = model(image)
                lv = loss_fn(pred, heatmaps, vis_mask)
        else:
            pred = model(image)
            lv = loss_fn(pred, heatmaps, vis_mask)
        val_loss += float(lv.item())
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


def _save_checkpoint(model, path: Path, epoch: int, metrics: dict, cfg: Config,
                     optimizer=None) -> None:
    payload = {"model": model.state_dict(), "epoch": epoch,
               "metrics": metrics, "config": dump_config(cfg)}
    if optimizer is not None:
        payload["optimizer"] = optimizer.state_dict()
    torch.save(payload, path)


def _pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


if __name__ == "__main__":
    main()
