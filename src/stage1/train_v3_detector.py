"""Stage 1 v3 — Net 2 (palm detector) training.

  python -u -m src.stage1.train_v3_detector --config configs/stage1_v3_detector.yaml
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn
from torch.utils.data import DataLoader
from tqdm import tqdm

import torch.multiprocessing as _mp
# Variable-length JPEG bytes tensors flood the default shm fd budget when
# num_workers=32 + persistent + prefetch_factor=4. Switch to file-system
# tensor sharing so we use regular file descriptors on tmpfs.
try:
    _mp.set_sharing_strategy("file_system")
except RuntimeError:
    pass

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.detector_dataset import DetectorTrainDataset, detector_collate
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset
from src.stage1.losses_v3 import DetectorLoss
from src.stage1.models.anchors import (
    build_targets_gpu, encode_box, get_anchors, match_anchors_to_gt, xywh_to_xyxy,
)
from src.stage1.models.palm_detector import PalmDetector, count_params


def _build_targets(boxes_per_image: list[torch.Tensor], anchors_xywh: np.ndarray,
                   pos_iou: float, neg_iou: float
                   ) -> tuple[torch.Tensor, torch.Tensor]:
    """Encode batch of GT bbox lists → anchor targets.

    Returns:
        cls_target: (B, N) int (-1 ignore / 0 neg / 1 pos)
        box_target: (B, N, 4) float (deltas wrt anchors; zero for non-positive)
    """
    anchors_xyxy = xywh_to_xyxy(anchors_xywh)
    N = anchors_xywh.shape[0]
    batch = len(boxes_per_image)
    cls = np.zeros((batch, N), dtype=np.int64)
    boxr = np.zeros((batch, N, 4), dtype=np.float32)
    for b, boxes in enumerate(boxes_per_image):
        if boxes.shape[0] == 0:
            cls[b] = 0  # all negative
            continue
        gt_xywh = boxes.cpu().numpy()
        gt_xyxy = xywh_to_xyxy(gt_xywh)
        assignment, _ = match_anchors_to_gt(anchors_xyxy, gt_xyxy,
                                            pos_iou=pos_iou, neg_iou=neg_iou)
        cls_row = np.zeros(N, dtype=np.int64)
        cls_row[assignment == -2] = -1  # ignore
        cls_row[assignment >= 0] = 1
        pos_idx = np.where(assignment >= 0)[0]
        if pos_idx.size > 0:
            gt_for_pos = gt_xywh[assignment[pos_idx]]
            boxr[b, pos_idx] = encode_box(gt_for_pos, anchors_xywh[pos_idx])
        cls[b] = cls_row
    return torch.from_numpy(cls), torch.from_numpy(boxr)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--data-limit", type=int, default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--resume-from", type=str, default=None,
                   help="Path to a best.pt / epoch_NNN.pt to resume from")
    p.add_argument("--use-dali", action="store_true",
                   help="Use DALI GPU pipeline instead of cv2 + DataLoader")
    p.add_argument("--use-dali-box-encoder", action="store_true",
                   help="Use DALI's fn.box_encoder to perform SSD-style anchor "
                        "matching inside the data pipeline. Implies --use-dali. "
                        "Eliminates the ~26 ms/batch numpy _build_targets call.")
    p.add_argument("--use-cuda-graphs", action="store_true",
                   help="Capture the per-batch model/loss/backward into a "
                        "CUDA Graph and replay it each step. Requires CUDA + "
                        "static shapes. Optimizer step / grad clip / EMA stay "
                        "outside the graph.")
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    set_seed(deep_get(cfg, "train.seed", 42))
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    use_dali_box_encoder = args.use_dali_box_encoder or bool(
        deep_get(cfg, "train.use_dali_box_encoder", False))
    use_dali = (args.use_dali or bool(deep_get(cfg, "train.use_dali", False))
                or use_dali_box_encoder)  # box_encoder implies DALI
    use_cuda_graphs = args.use_cuda_graphs or bool(
        deep_get(cfg, "train.use_cuda_graphs", False))
    if use_cuda_graphs and device != "cuda":
        print("[warn] --use-cuda-graphs requires CUDA; disabling.")
        use_cuda_graphs = False
    print(f"[init] device={device}  run={cfg.get('run_name')}  "
          f"use_dali={use_dali}  use_dali_box_encoder={use_dali_box_encoder}  "
          f"use_cuda_graphs={use_cuda_graphs}")

    # Datasets ----------------------------------------------------------
    coco = CocoWholeBodyDataset(
        ann_file=deep_get(cfg, "data.coco_ann_file"),
        image_root=f"{deep_get(cfg, 'data.coco_root')}/{deep_get(cfg, 'data.coco_train_images')}",
    )
    frei = FreiHANDDataset(deep_get(cfg, "data.freihand_root"))
    hagrid = None
    h_root = deep_get(cfg, "data.hagrid_root")
    if h_root and (Path(h_root) / "annotations" / "train.json").exists():
        hagrid = HaGRIDDataset(h_root, split="train")
    print(f"[data] coco={len(coco):,}  freihand={len(frei):,}  "
          f"hagrid={len(hagrid) if hagrid else 0:,}")

    if use_dali:
        from src.stage1.data.dali_pipelines import DALIDetectorLoader
        loader = DALIDetectorLoader(
            coco=coco, frei=frei, hagrid=hagrid,
            input_size=deep_get(cfg, "data.input_size"),
            batch_size=deep_get(cfg, "train.batch_size"),
            padding_frac=deep_get(cfg, "data.padding_frac"),
            num_threads=min(8, deep_get(cfg, "train.num_workers", 8)),
            prefetch=4, shuffle=True, drop_last=True,
            seed=deep_get(cfg, "train.seed", 42),
            use_box_encoder=use_dali_box_encoder,
            pos_iou=deep_get(cfg, "anchors.pos_iou", 0.5),
        )
        steps_per_epoch = loader.num_batches_per_epoch()
        print(f"[init] using DALI loader, {steps_per_epoch} batches/epoch  "
              f"box_encoder={use_dali_box_encoder}")
    else:
        train_ds = DetectorTrainDataset(coco, frei, hagrid,
                                        input_size=deep_get(cfg, "data.input_size"),
                                        padding_frac=deep_get(cfg, "data.padding_frac"),
                                        cache_root=deep_get(cfg, "data.cache_root"))
        if args.data_limit:
            from torch.utils.data import Subset
            train_ds = Subset(train_ds, range(min(args.data_limit, len(train_ds))))

        loader = DataLoader(
            train_ds, batch_size=deep_get(cfg, "train.batch_size"),
            shuffle=True, num_workers=deep_get(cfg, "train.num_workers"),
            pin_memory=True, drop_last=True, collate_fn=detector_collate,
            persistent_workers=deep_get(cfg, "train.num_workers") > 0,
            prefetch_factor=4 if deep_get(cfg, "train.num_workers") > 0 else None,
        )
        steps_per_epoch = None  # iter-defined

    # Model + loss ------------------------------------------------------
    model = PalmDetector(
        n_anchors_per_cell=deep_get(cfg, "model.n_anchors_per_cell", 3),
        n_aux_kpts=deep_get(cfg, "model.n_aux_kpts", 0),
    ).to(device)
    print(f"[init] PalmDetector params={count_params(model):,}")

    loss_fn = DetectorLoss(
        alpha=deep_get(cfg, "loss.focal_alpha", 0.25),
        gamma=deep_get(cfg, "loss.focal_gamma", 2.0),
        box_weight=deep_get(cfg, "loss.box_weight", 1.0),
        beta=deep_get(cfg, "loss.smoothl1_beta", 0.11),
    )
    optimizer = AdamW(model.parameters(), lr=deep_get(cfg, "train.lr"),
                      weight_decay=deep_get(cfg, "train.weight_decay"))
    scheduler = CosineAnnealingLR(optimizer,
                                  T_max=deep_get(cfg, "train.epochs"),
                                  eta_min=deep_get(cfg, "train.lr_min"))
    scaler = torch.amp.GradScaler(device=device) if (deep_get(cfg, "train.mixed_precision")
                                                     and device == "cuda") else None
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
        deep_get(cfg, "train.ema_decay", 0.9998)))

    # Resume support — load weights + optional epoch counter from a prior best.pt.
    start_epoch = 0
    if args.resume_from and Path(args.resume_from).exists():
        ckpt = torch.load(args.resume_from, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
            deep_get(cfg, "train.ema_decay", 0.9998)))
        start_epoch = int(ckpt.get("epoch", 0)) + 1
        # Fast-forward the cosine scheduler so LR matches the resumed epoch.
        for _ in range(start_epoch):
            scheduler.step()
        print(f"[init] resumed from {args.resume_from} → starting at epoch {start_epoch}")

    anchors_xywh = get_anchors(deep_get(cfg, "data.input_size"))
    pos_iou = deep_get(cfg, "anchors.pos_iou", 0.5)
    neg_iou = deep_get(cfg, "anchors.neg_iou", 0.4)
    # Pre-move anchors to GPU for the torchified target builder.
    anchors_xywh_gpu = torch.from_numpy(anchors_xywh).to(device=device, dtype=torch.float32)
    anchors_xyxy_gpu = torch.stack([
        anchors_xywh_gpu[:, 0] - anchors_xywh_gpu[:, 2] * 0.5,
        anchors_xywh_gpu[:, 1] - anchors_xywh_gpu[:, 3] * 0.5,
        anchors_xywh_gpu[:, 0] + anchors_xywh_gpu[:, 2] * 0.5,
        anchors_xywh_gpu[:, 1] + anchors_xywh_gpu[:, 3] * 0.5,
    ], dim=1)

    ckpt_dir = Path(deep_get(cfg, "train.checkpoint_dir"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_log = ckpt_dir / "metrics.jsonl"

    warmup = deep_get(cfg, "train.warmup_epochs", 0)
    best_loss = float("inf")
    patience = 0

    # CUDA Graphs state (lazy: captured on the first batch we see).
    # We capture forward + loss + scaler.scale(loss).backward() only.
    # scaler.unscale_, clip_grad_norm_, scaler.step, scaler.update and
    # ema.update_parameters all stay OUTSIDE the graph because they have
    # CPU-side state and/or dynamic control flow (inf/nan handling).
    graph_state: dict = {"graph": None}

    def _capture_detector_graph(sample_image: torch.Tensor,
                                 sample_cls: torch.Tensor,
                                 sample_box: torch.Tensor) -> dict:
        """One-time capture. Returns a dict with static buffers + the graph.

        Warmup runs the full training step (with optimizer step) on a side
        stream so BN running stats, AMP scale state, and the cudnn
        algorithm picker are warm. Capture covers fwd + loss + backward only.
        """
        B = sample_image.shape[0]
        static_image = torch.zeros_like(sample_image)
        static_cls = torch.zeros_like(sample_cls)
        static_box = torch.zeros_like(sample_box)
        static_image.copy_(sample_image)
        static_cls.copy_(sample_cls)
        static_box.copy_(sample_box)

        # Warmup: run a few full steps on a side stream. This includes
        # optimizer.step() so the cudnn algorithm picker + AMP scaler are
        # warm. PyTorch docs require >=3 warmup iters; 11 matches what we
        # use elsewhere.
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(11):
                optimizer.zero_grad(set_to_none=True)
                if scaler is not None:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                        out_w = model(static_image)
                        losses_w = loss_fn(out_w["cls"], out_w["box"],
                                           static_cls, static_box)
                    scaler.scale(losses_w["loss"]).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    out_w = model(static_image)
                    losses_w = loss_fn(out_w["cls"], out_w["box"],
                                       static_cls, static_box)
                    losses_w["loss"].backward()
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                    optimizer.step()
        torch.cuda.current_stream().wait_stream(s)
        # IMPORTANT: don't free the gradient storage between warmup and
        # capture — backward() inside the graph must write into the SAME
        # gradient tensors each replay. set_to_none=True would invalidate
        # those static addresses.
        for p_ in model.parameters():
            if p_.grad is not None:
                p_.grad.detach_()
                p_.grad.zero_()

        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            if scaler is not None:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    static_out = model(static_image)
                    static_losses = loss_fn(static_out["cls"], static_out["box"],
                                            static_cls, static_box)
                scaler.scale(static_losses["loss"]).backward()
            else:
                static_out = model(static_image)
                static_losses = loss_fn(static_out["cls"], static_out["box"],
                                        static_cls, static_box)
                static_losses["loss"].backward()
        return {
            "graph": g,
            "static_image": static_image,
            "static_cls": static_cls,
            "static_box": static_box,
            "static_losses": static_losses,
        }

    for epoch in range(start_epoch, deep_get(cfg, "train.epochs")):
        epoch_t0 = time.time()
        if epoch < warmup:
            for pg in optimizer.param_groups:
                pg["lr"] = deep_get(cfg, "train.lr") * (epoch + 1) / max(warmup, 1)

        model.train()
        running = {"loss": 0.0, "cls": 0.0, "box": 0.0}
        n_steps = 0
        # Unified per-epoch iterator: DALI yields indefinitely → cap at steps_per_epoch.
        if use_dali:
            dali_iter = iter(loader)
            def _epoch_batches():
                for _ in range(steps_per_epoch):
                    yield next(dali_iter)
            pbar = tqdm(_epoch_batches(), total=steps_per_epoch,
                        desc=f"epoch {epoch:03d}", leave=False)
        else:
            pbar = tqdm(loader, desc=f"epoch {epoch:03d}", leave=False)
        for batch in pbar:
            image = batch["image"]  # DALI returns GPU tensor; cv2 path needs .to(device)
            if not use_dali:
                image = image.to(device, non_blocking=True)
            if use_dali_box_encoder:
                # Anchor matching already done by DALI's fn.box_encoder; the
                # loader emits ready-to-use (cls_target, box_target) tensors.
                # See `DALIDetectorLoader` for the math/quality trade-off.
                cls_t = batch["cls_target"].to(device, non_blocking=True)
                box_t = batch["box_target"].to(device, non_blocking=True)
            else:
                # NOTE: a "torchified" GPU anchor matcher was tried but regressed
                # throughput (Python loop × CUDA launch overhead > numpy savings).
                # Numpy version is faster at our batch sizes.
                cls_t, box_t = _build_targets(batch["boxes"], anchors_xywh, pos_iou, neg_iou)
                cls_t = cls_t.to(device, non_blocking=True)
                box_t = box_t.to(device, non_blocking=True)

            if use_cuda_graphs:
                # Lazy capture on the first batch (shapes must be known).
                if graph_state["graph"] is None:
                    graph_state = _capture_detector_graph(image, cls_t, box_t)
                    print(f"[cuda-graphs] captured detector graph "
                          f"(image={tuple(image.shape)})", flush=True)
                # Replay: copy real inputs into the captured static buffers,
                # then replay. The graph's backward writes into the same
                # gradient tensors created during capture.
                graph_state["static_image"].copy_(image, non_blocking=True)
                graph_state["static_cls"].copy_(cls_t, non_blocking=True)
                graph_state["static_box"].copy_(box_t, non_blocking=True)
                graph_state["graph"].replay()
                # Optimizer / clip / EMA happen OUTSIDE the graph because
                # GradScaler.unscale_/step/update have CPU-side state
                # (inf-check, scale factor adjustment) and EMA copies into
                # a separate param tree.
                if scaler is not None:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                    optimizer.step()
                ema.update_parameters(model)
                # Zero gradients IN-PLACE (set_to_none=True would free the
                # graph's static grad buffers and break the next replay).
                for p_ in model.parameters():
                    if p_.grad is not None:
                        p_.grad.zero_()
                losses = graph_state["static_losses"]
            else:
                optimizer.zero_grad(set_to_none=True)
                if scaler is not None:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                        out = model(image)
                        losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
                    scaler.scale(losses["loss"]).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(),
                                                   deep_get(cfg, "train.grad_clip", 1.0))
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    out = model(image)
                    losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
                    losses["loss"].backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(),
                                                   deep_get(cfg, "train.grad_clip", 1.0))
                    optimizer.step()
                ema.update_parameters(model)
            for k in running:
                running[k] += float(losses[k].item() if hasattr(losses[k], "item")
                                    else losses[k])
            n_steps += 1

        if epoch >= warmup:
            scheduler.step()
        epoch_secs = time.time() - epoch_t0
        avg_loss = running["loss"] / max(n_steps, 1)
        line = {
            "epoch": epoch,
            "epoch_secs": round(epoch_secs, 1),
            "train_loss": avg_loss,
            "cls_loss": running["cls"] / max(n_steps, 1),
            "box_loss": running["box"] / max(n_steps, 1),
            "lr": optimizer.param_groups[0]["lr"],
        }
        with metrics_log.open("a") as f:
            f.write(json.dumps(line) + "\n")
        print(f"[epoch {epoch:03d}] took={epoch_secs:.1f}s  loss={avg_loss:.5f}  "
              f"cls={line['cls_loss']:.5f}  box={line['box_loss']:.5f}  lr={line['lr']:.6f}",
              flush=True)

        if avg_loss < best_loss - deep_get(cfg, "train.early_stop_min_delta", 0.001):
            best_loss = avg_loss
            patience = 0
            torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                        "metrics": line, "config": cfg}, ckpt_dir / "best.pt")
        else:
            patience += 1
            if patience >= deep_get(cfg, "train.early_stop_patience", 20):
                print(f"[early-stop] no improvement for {patience} epochs")
                break
        if (epoch + 1) % 10 == 0:
            torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                        "metrics": line, "config": cfg},
                       ckpt_dir / f"epoch_{epoch:03d}.pt")

    torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                "metrics": line, "config": cfg}, ckpt_dir / "last.pt")
    print(f"[done] best_loss={best_loss:.5f}")


if __name__ == "__main__":
    main()
