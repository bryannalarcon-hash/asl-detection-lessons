"""Stage 2 v4 — Net 4 (isolated sign classifier) training entry point.

  python -u -m src.stage2.train_v4_classifier \\
      --config configs/stage2_v4_classifier.yaml

Reads cached per-clip keypoint .npz files (produced by
src/stage2/data/extract_keypoints.py), builds per-frame feature vectors
(coords + visibility + lag-1 + lag-2 deltas), and trains the hoyso48-style
1DCNN + Transformer classifier from src/stage2/models/sign_classifier.

Top-1 and Top-3 accuracy are tracked per epoch on the val split. Best
checkpoint = highest top-1 EMA on val.
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
from torch.utils.data import DataLoader
from tqdm import tqdm

import torch.multiprocessing as _mp
try:
    _mp.set_sharing_strategy("file_system")
except RuntimeError:
    pass

torch.backends.cudnn.benchmark = True

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage2.data.sign_dataset import (
    SignSequenceDataset, build_gloss_to_idx, feature_dim,
)
from src.stage2.models.sign_classifier import SignClassifier, count_params


def topk_accuracy(logits: torch.Tensor, labels: torch.Tensor,
                  ks: tuple[int, ...] = (1, 3)) -> dict[int, float]:
    """Returns {k: hits} where hits is float in [0, len(labels)]."""
    maxk = max(ks)
    _, pred = logits.topk(maxk, dim=-1, largest=True, sorted=True)  # (B, maxk)
    correct = pred.eq(labels.view(-1, 1).expand_as(pred))           # (B, maxk)
    out: dict[int, float] = {}
    for k in ks:
        out[k] = float(correct[:, :k].any(dim=1).float().sum().item())
    return out


def evaluate(model, loader, device: str, use_amp_bf16: bool,
             ks: tuple[int, ...]) -> dict:
    model.eval()
    n = 0
    hits = {k: 0.0 for k in ks}
    losses = 0.0
    with torch.no_grad():
        for batch in loader:
            x = batch["features"].to(device, non_blocking=True)
            m = batch["key_padding_mask"].to(device, non_blocking=True)
            y = batch["label"].to(device, non_blocking=True)
            if use_amp_bf16 and device == "cuda":
                with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                    logits = model(x, key_padding_mask=m)
                    loss = torch.nn.functional.cross_entropy(logits, y)
            else:
                logits = model(x, key_padding_mask=m)
                loss = torch.nn.functional.cross_entropy(logits, y)
            losses += float(loss.item()) * x.shape[0]
            for k, h in topk_accuracy(logits.float(), y, ks=ks).items():
                hits[k] += h
            n += x.shape[0]
    return {"loss": losses / max(n, 1),
            **{f"top{k}": hits[k] / max(n, 1) for k in ks},
            "n": n}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--device", default=None)
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    set_seed(deep_get(cfg, "train.seed", 42))
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}  run={cfg.get('run_name')}", flush=True)

    gloss_to_idx = build_gloss_to_idx(deep_get(cfg, "data.sign_list_json"))
    num_classes = len(gloss_to_idx)
    print(f"[init] {num_classes} glosses loaded from catalog", flush=True)

    inc_vis = deep_get(cfg, "data.include_visibility", True)
    inc_lag1 = deep_get(cfg, "data.include_lag1", True)
    inc_lag2 = deep_get(cfg, "data.include_lag2", True)
    in_channels = feature_dim(include_visibility=inc_vis,
                              include_lag1=inc_lag1, include_lag2=inc_lag2)
    print(f"[init] per-frame feature dim = {in_channels}", flush=True)

    train_ds = SignSequenceDataset(
        manifest_path=deep_get(cfg, "data.manifest_path"),
        kpt_dir=deep_get(cfg, "data.kpt_dir"),
        gloss_to_idx=gloss_to_idx, split="train",
        max_frames=deep_get(cfg, "data.max_frames", 64),
        augment=True, include_visibility=inc_vis,
        include_lag1=inc_lag1, include_lag2=inc_lag2,
    )
    val_ds = SignSequenceDataset(
        manifest_path=deep_get(cfg, "data.manifest_path"),
        kpt_dir=deep_get(cfg, "data.kpt_dir"),
        gloss_to_idx=gloss_to_idx, split="val",
        max_frames=deep_get(cfg, "data.max_frames", 64),
        augment=False, include_visibility=inc_vis,
        include_lag1=inc_lag1, include_lag2=inc_lag2,
    )
    test_ds = SignSequenceDataset(
        manifest_path=deep_get(cfg, "data.manifest_path"),
        kpt_dir=deep_get(cfg, "data.kpt_dir"),
        gloss_to_idx=gloss_to_idx, split="test",
        max_frames=deep_get(cfg, "data.max_frames", 64),
        augment=False, include_visibility=inc_vis,
        include_lag1=inc_lag1, include_lag2=inc_lag2,
    )
    print(f"[data] train={len(train_ds):,} val={len(val_ds):,} test={len(test_ds):,}",
          flush=True)
    if len(train_ds) == 0:
        raise SystemExit("Empty train set — populate data/signs/kpt_cache/ first")

    batch_size = deep_get(cfg, "train.batch_size", 128)
    num_workers = deep_get(cfg, "train.num_workers", 8)
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        num_workers=num_workers, pin_memory=True, drop_last=True,
        persistent_workers=num_workers > 0,
        prefetch_factor=4 if num_workers > 0 else None,
    )
    val_loader = DataLoader(
        val_ds, batch_size=deep_get(cfg, "eval.val_batch_size", 128),
        shuffle=False, num_workers=min(num_workers, 4), pin_memory=True,
    ) if len(val_ds) > 0 else None
    test_loader = DataLoader(
        test_ds, batch_size=deep_get(cfg, "eval.val_batch_size", 128),
        shuffle=False, num_workers=min(num_workers, 4), pin_memory=True,
    ) if len(test_ds) > 0 else None

    model = SignClassifier(
        in_channels=in_channels,
        num_classes=num_classes,
        dim=deep_get(cfg, "model.dim", 192),
        kernel=deep_get(cfg, "model.kernel", 17),
        drop_path=deep_get(cfg, "model.drop_path", 0.2),
        late_dropout_p=deep_get(cfg, "model.late_dropout_p", 0.8),
        late_dropout_start_step=deep_get(cfg, "model.late_dropout_start_step", 4000),
    ).to(device)
    print(f"[init] SignClassifier params={count_params(model):,}", flush=True)

    optimizer = AdamW(model.parameters(),
                      lr=deep_get(cfg, "train.lr"),
                      weight_decay=deep_get(cfg, "train.weight_decay"))
    scheduler = CosineAnnealingLR(optimizer,
                                  T_max=deep_get(cfg, "train.epochs"),
                                  eta_min=deep_get(cfg, "train.lr_min"))
    use_amp_bf16 = (bool(deep_get(cfg, "train.use_bf16",
                                  deep_get(cfg, "train.mixed_precision", False)))
                    and device == "cuda")
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
        deep_get(cfg, "train.ema_decay", 0.9995)))

    label_smoothing = float(deep_get(cfg, "train.label_smoothing", 0.0))
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=label_smoothing)

    ckpt_dir = Path(deep_get(cfg, "train.checkpoint_dir"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_log = ckpt_dir / "metrics.jsonl"
    (ckpt_dir / "gloss_to_idx.json").write_text(json.dumps(gloss_to_idx, indent=2))

    best_top1 = 0.0
    patience = 0
    warmup = deep_get(cfg, "train.warmup_epochs", 0)
    ks = tuple(deep_get(cfg, "eval.topk", [1, 3]))

    for epoch in range(deep_get(cfg, "train.epochs")):
        epoch_t0 = time.time()
        if epoch < warmup:
            for pg in optimizer.param_groups:
                pg["lr"] = deep_get(cfg, "train.lr") * (epoch + 1) / max(warmup, 1)
        model.train()
        running = 0.0
        n_steps = 0
        train_hits = {k: 0.0 for k in ks}
        train_n = 0
        pbar = tqdm(train_loader, desc=f"epoch {epoch:03d}", leave=False)
        for batch in pbar:
            x = batch["features"].to(device, non_blocking=True)
            m = batch["key_padding_mask"].to(device, non_blocking=True)
            y = batch["label"].to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            if use_amp_bf16:
                with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                    logits = model(x, key_padding_mask=m)
                    loss = loss_fn(logits, y)
            else:
                logits = model(x, key_padding_mask=m)
                loss = loss_fn(logits, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                           deep_get(cfg, "train.grad_clip", 1.0))
            optimizer.step()
            ema.update_parameters(model)
            running += float(loss.item())
            n_steps += 1
            with torch.no_grad():
                for k, h in topk_accuracy(logits.float(), y, ks=ks).items():
                    train_hits[k] += h
                train_n += x.shape[0]
        if epoch >= warmup:
            scheduler.step()

        val_metrics = (evaluate(ema.module, val_loader, device, use_amp_bf16, ks)
                       if val_loader is not None else None)
        epoch_secs = time.time() - epoch_t0
        line = {
            "epoch": epoch, "epoch_secs": round(epoch_secs, 1),
            "train_loss": running / max(n_steps, 1),
            **{f"train_top{k}": train_hits[k] / max(train_n, 1) for k in ks},
            "lr": optimizer.param_groups[0]["lr"],
        }
        if val_metrics is not None:
            line.update({
                "val_loss": val_metrics["loss"],
                **{f"val_top{k}": val_metrics[f"top{k}"] for k in ks},
                "val_n": val_metrics["n"],
            })
        with metrics_log.open("a") as f:
            f.write(json.dumps(line) + "\n")
        msg = (f"epoch {epoch} | tl {line['train_loss']:.3f} "
               f"top1 {line.get('train_top1', 0):.3f}")
        if val_metrics is not None:
            msg += (f" | vl {line['val_loss']:.3f} "
                    f"vt1 {line['val_top1']:.3f} vt3 {line['val_top3']:.3f}")
        msg += f" | {epoch_secs/60:.1f}m"
        print(msg, flush=True)

        # Pick best on val top1 (EMA). Saves both ema + raw weights.
        if val_metrics is not None:
            score = val_metrics["top1"]
            improved = score > best_top1 + deep_get(cfg, "train.early_stop_min_delta", 0.001)
            if improved:
                best_top1 = score
                patience = 0
                torch.save({"model": ema.module.state_dict(),
                            "raw_model": model.state_dict(),
                            "epoch": epoch, "metrics": line, "config": cfg,
                            "gloss_to_idx": gloss_to_idx},
                           ckpt_dir / "best.pt")
            else:
                patience += 1
                if patience >= deep_get(cfg, "train.early_stop_patience", 20):
                    print(f"[early-stop] no val_top1 improvement for {patience} epochs",
                          flush=True)
                    break

    torch.save({"model": ema.module.state_dict(),
                "raw_model": model.state_dict(),
                "epoch": epoch, "metrics": line, "config": cfg,
                "gloss_to_idx": gloss_to_idx},
               ckpt_dir / "last.pt")

    if test_loader is not None:
        test_metrics = evaluate(ema.module, test_loader, device, use_amp_bf16, ks)
        out = {"split": "test", **test_metrics}
        (ckpt_dir / "test_eval.json").write_text(json.dumps(out, indent=2))
        print(f"[test] {out}", flush=True)
    print(f"[done] best_val_top1={best_top1:.3f}", flush=True)


if __name__ == "__main__":
    main()
