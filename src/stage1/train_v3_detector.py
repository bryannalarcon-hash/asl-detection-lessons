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
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

import torch.multiprocessing as _mp
# Variable JPEG bytes tensors overrun default shm fd budget at num_workers=32
# + persistent + prefetch_factor=4; file_system sharing uses tmpfs fds.
try:
    _mp.set_sharing_strategy("file_system")
except RuntimeError:
    pass

# cudnn benchmark auto-picks the fastest conv algo per shape (~2x throughput
# on Blackwell vs default).
torch.backends.cudnn.benchmark = True

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.detector_dataset import (
    DetectorTrainDataset, build_mix_sample_weights, detector_collate,
)
from src.stage1.data.egohands import EgoHandsDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset
from src.stage1.data.synthetic_composite import SyntheticCompositeDataset
from src.stage1.losses_v3 import DetectorLoss
from src.stage1.models.anchors import (
    build_targets_gpu, build_targets_gpu_batched, encode_box, get_anchors,
    match_anchors_to_gt, xywh_to_xyxy,
)
from src.stage1.models.palm_detector import PalmDetector, count_params


def _build_targets(boxes_per_image: list[torch.Tensor], anchors_xywh: np.ndarray,
                   pos_iou: float, neg_iou: float
                   ) -> tuple[torch.Tensor, torch.Tensor]:
    """Encode GT bbox lists → (cls_target (B,N), box_target (B,N,4))."""
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
                   help="DALI fn.box_encoder does anchor matching inside the "
                        "pipeline. Implies --use-dali.")
    p.add_argument("--use-cuda-graphs", action="store_true",
                   help="Capture model/loss/backward into a CUDA Graph; static "
                        "shapes required. Optimizer/clip/EMA stay outside.")
    p.add_argument("--channels-last", action="store_true",
                   help="NHWC memory format; 1.2-1.5x on Blackwell convs.")
    p.add_argument("--fused-adamw", action="store_true",
                   help="AdamW(fused=True) single-kernel optimizer step.")
    p.add_argument("--use-gpu-anchor-matcher", action="store_true",
                   help="Fully-batched GPU matcher (build_targets_gpu_batched). "
                        "Mutually exclusive with --use-dali-box-encoder.")
    p.add_argument("--use-numba-anchors", action="store_true",
                   help="Numba-JIT batched matcher; ~10x faster than numpy.")
    p.add_argument("--batch-size", type=int, default=None,
                   help="Override config train.batch_size (for smokes).")
    p.add_argument("--input-size", type=int, default=None,
                   help="Override config data.input_size (for smokes).")
    p.add_argument("--torch-compile-default", action="store_true",
                   help="torch.compile(mode='default') JIT kernel fusion.")
    p.add_argument("--stage", type=str, default=None,
                   choices=["stage_a", "stage_b"],
                   help="Curriculum stage: overrides train.epochs/lr/"
                        "checkpoint_dir, data.sources, and resume_from from "
                        "cfg.curriculum.<stage>.")
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    if args.batch_size is not None:
        cfg.setdefault("train", {})["batch_size"] = args.batch_size
        print(f"[init] batch_size override → {args.batch_size}", flush=True)
    if args.input_size is not None:
        cfg.setdefault("data", {})["input_size"] = args.input_size
        print(f"[init] input_size override → {args.input_size}", flush=True)
    if args.stage is not None:
        stage_cfg = deep_get(cfg, f"curriculum.{args.stage}")
        if not isinstance(stage_cfg, dict):
            raise SystemExit(
                f"[err] --stage {args.stage} requested but config has no "
                f"curriculum.{args.stage} section")
        train_overrides = cfg.setdefault("train", {})
        if "epochs" in stage_cfg:
            train_overrides["epochs"] = stage_cfg["epochs"]
        if "lr" in stage_cfg:
            train_overrides["lr"] = stage_cfg["lr"]
        if "checkpoint_dir" in stage_cfg:
            train_overrides["checkpoint_dir"] = stage_cfg["checkpoint_dir"]
        if "sources" in stage_cfg:
            cfg.setdefault("data", {})["sources"] = list(stage_cfg["sources"])
        # init_from forwards into args.resume_from when no explicit CLI override.
        # warm_start separates "load weights from a prior stage" from a true
        # resume — the former resets the epoch counter so the new stage's
        # epoch budget is honored.
        args.warm_start = False
        if stage_cfg.get("init_from") and not args.resume_from:
            init_from = stage_cfg["init_from"]
            if Path(init_from).exists():
                args.resume_from = init_from
                args.warm_start = True
            else:
                print(f"[warn] curriculum.{args.stage}.init_from={init_from!r} "
                      f"does not exist; starting from scratch", flush=True)
        print(f"[init] curriculum stage={args.stage} "
              f"epochs={train_overrides.get('epochs')} "
              f"lr={train_overrides.get('lr')} "
              f"sources={cfg.get('data', {}).get('sources')} "
              f"ckpt={train_overrides.get('checkpoint_dir')}", flush=True)
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
    use_gpu_anchor_matcher = args.use_gpu_anchor_matcher or bool(
        deep_get(cfg, "train.use_gpu_anchor_matcher", False))
    if use_gpu_anchor_matcher and use_dali_box_encoder:
        # box_encoder already produces (cls_target, box_target); the GPU
        # matcher would be dead code in that path.
        print("[warn] --use-gpu-anchor-matcher is redundant when "
              "--use-dali-box-encoder is set; disabling the former.")
        use_gpu_anchor_matcher = False
    if use_gpu_anchor_matcher and device != "cuda":
        print("[warn] --use-gpu-anchor-matcher requires CUDA; disabling.")
        use_gpu_anchor_matcher = False
    print(f"[init] device={device}  run={cfg.get('run_name')}  "
          f"use_dali={use_dali}  use_dali_box_encoder={use_dali_box_encoder}  "
          f"use_cuda_graphs={use_cuda_graphs}  "
          f"use_gpu_anchor_matcher={use_gpu_anchor_matcher}")

    # Datasets — `data.sources` (set by --stage) is an allow-list of canonical
    # names; when unset, every detected source loads (legacy behaviour).
    sources_allow = deep_get(cfg, "data.sources")
    if sources_allow is not None:
        sources_allow = set(sources_allow)

    def _enabled(name: str) -> bool:
        return sources_allow is None or name in sources_allow

    coco = None
    if _enabled("coco_wholebody"):
        coco = CocoWholeBodyDataset(
            ann_file=deep_get(cfg, "data.coco_ann_file"),
            image_root=f"{deep_get(cfg, 'data.coco_root')}/{deep_get(cfg, 'data.coco_train_images')}",
        )
    frei = None
    if _enabled("freihand"):
        frei = FreiHANDDataset(deep_get(cfg, "data.freihand_root"))
    hagrid = None
    h_root = deep_get(cfg, "data.hagrid_root")
    if _enabled("hagrid") and h_root and (Path(h_root) / "annotations" / "train.json").exists():
        hagrid = HaGRIDDataset(h_root, split="train")
    egohands = None
    e_root = deep_get(cfg, "data.egohands_root")
    if _enabled("egohands") and e_root and (Path(e_root) / "train" / "images").exists():
        egohands = EgoHandsDataset(e_root, split="train")
    synthetic = None
    s_root = deep_get(cfg, "data.synthetic_root")
    if _enabled("synthetic") and s_root and (Path(s_root) / "anno.jsonl").exists():
        synthetic = SyntheticCompositeDataset(s_root)
    print(f"[data] coco={len(coco) if coco else 0:,}  "
          f"freihand={len(frei) if frei else 0:,}  "
          f"hagrid={len(hagrid) if hagrid else 0:,}  "
          f"egohands={len(egohands) if egohands else 0:,}  "
          f"synthetic={len(synthetic) if synthetic else 0:,}")

    target_mix = deep_get(cfg, "data.target_mix")
    if use_dali:
        if target_mix:
            print("[warn] data.target_mix is set but --use-dali is active; "
                  "DALI does not honor target_mix — uniform sampling instead.")
        if egohands is not None:
            print("[warn] EgoHands not supported by DALI pipeline — ignored.")
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
            cache_root=deep_get(cfg, "data.cache_root"),
        )
        steps_per_epoch = loader.num_batches_per_epoch()
        print(f"[init] using DALI loader, {steps_per_epoch} batches/epoch  "
              f"box_encoder={use_dali_box_encoder}")
    else:
        train_ds = DetectorTrainDataset(coco, frei, hagrid,
                                        input_size=deep_get(cfg, "data.input_size"),
                                        padding_frac=deep_get(cfg, "data.padding_frac"),
                                        cache_root=deep_get(cfg, "data.cache_root"),
                                        egohands_train=egohands,
                                        synthetic_train=synthetic)
        if args.data_limit:
            from torch.utils.data import Subset
            train_ds = Subset(train_ds, range(min(args.data_limit, len(train_ds))))

        sampler = None
        shuffle_flag = True
        if target_mix and not args.data_limit:
            weights, active_mix = build_mix_sample_weights(train_ds, target_mix)
            sampler = WeightedRandomSampler(
                weights=torch.as_tensor(weights, dtype=torch.double),
                num_samples=len(train_ds),
                replacement=True,
            )
            shuffle_flag = False
            mix_str = ", ".join(f"{k}={v:.3f}" for k, v in active_mix.items())
            print(f"[init] WeightedRandomSampler active_mix: {mix_str}")
        elif target_mix and args.data_limit:
            print("[warn] data.target_mix set but --data-limit overrides it; "
                  "using sequential subset instead.")

        # persistent_workers=False + timeout=60 to prevent the dataloader
        # deadlocks observed in Stage B (workers accumulate state across
        # epochs and the mix of mmap caches + WeightedRandomSampler eventually
        # stalls; respawning each epoch eliminates the accumulation).
        loader = DataLoader(
            train_ds, batch_size=deep_get(cfg, "train.batch_size"),
            shuffle=shuffle_flag, sampler=sampler,
            num_workers=deep_get(cfg, "train.num_workers"),
            pin_memory=True, drop_last=True, collate_fn=detector_collate,
            persistent_workers=False,
            prefetch_factor=4 if deep_get(cfg, "train.num_workers") > 0 else None,
            timeout=60 if deep_get(cfg, "train.num_workers") > 0 else 0,
        )
        steps_per_epoch = None  # iter-defined

    # Model + loss ------------------------------------------------------
    # Multi-stride FPN config is opt-in: missing fields keep the legacy
    # single-list-of-scales SSDLite arch byte-compatible with old checkpoints.
    model_kwargs = dict(
        n_anchors_per_cell=deep_get(cfg, "model.n_anchors_per_cell", 3),
        n_aux_kpts=deep_get(cfg, "model.n_aux_kpts", 0),
    )
    if deep_get(cfg, "model.use_fpn") is not None:
        model_kwargs["use_fpn"] = bool(deep_get(cfg, "model.use_fpn"))
    if deep_get(cfg, "model.fpn_channels") is not None:
        model_kwargs["fpn_channels"] = int(deep_get(cfg, "model.fpn_channels"))
    aps = deep_get(cfg, "model.anchors_per_scale")
    if aps is not None:
        model_kwargs["anchors_per_scale"] = tuple(int(x) for x in aps)
    model = PalmDetector(**model_kwargs).to(device)
    use_channels_last = args.channels_last and device == "cuda"
    if use_channels_last:
        model = model.to(memory_format=torch.channels_last)
        print(f"[init] model converted to channels_last (NHWC)")
    print(f"[init] PalmDetector params={count_params(model):,}")

    loss_fn = DetectorLoss(
        alpha=deep_get(cfg, "loss.focal_alpha", 0.25),
        gamma=deep_get(cfg, "loss.focal_gamma", 2.0),
        box_weight=deep_get(cfg, "loss.box_weight", 1.0),
        beta=deep_get(cfg, "loss.smoothl1_beta", 0.11),
    )
    optimizer = AdamW(model.parameters(), lr=deep_get(cfg, "train.lr"),
                      weight_decay=deep_get(cfg, "train.weight_decay"),
                      fused=(args.fused_adamw and device == "cuda"))
    scheduler = CosineAnnealingLR(optimizer,
                                  T_max=deep_get(cfg, "train.epochs"),
                                  eta_min=deep_get(cfg, "train.lr_min"))
    # BF16 shares FP32's exponent range, so no GradScaler — its CPU-side
    # state invalidates CUDA Graph capture and BF16 is full-rate on Blackwell.
    use_amp_bf16 = bool(deep_get(cfg, "train.mixed_precision")) and device == "cuda"
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
        deep_get(cfg, "train.ema_decay", 0.9998)))

    # Resume support — load weights + optional epoch counter from a prior best.pt.
    start_epoch = 0
    if args.resume_from and Path(args.resume_from).exists():
        ckpt = torch.load(args.resume_from, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
            deep_get(cfg, "train.ema_decay", 0.9998)))
        if getattr(args, "warm_start", False):
            print(f"[init] warm-start weights from {args.resume_from} (epoch counter reset to 0)")
        else:
            start_epoch = int(ckpt.get("epoch", 0)) + 1
            # Fast-forward the cosine scheduler so LR matches the resumed epoch.
            for _ in range(start_epoch):
                scheduler.step()
            print(f"[init] resumed from {args.resume_from} → starting at epoch {start_epoch}")

    if args.use_numba_anchors:
        from src.stage1.models.anchors_numba import warmup as _numba_warmup
        print("[init] numba anchor matcher: warming up JIT...", flush=True)
        import time as _t
        _t0 = _t.time()
        _numba_warmup(input_size=deep_get(cfg, "data.input_size"))
        print(f"[init] numba JIT warmup done in {_t.time()-_t0:.1f}s", flush=True)
    # Multi-stride anchors when both scales_per_stride + strides are set;
    # otherwise legacy uniform-scale anchors at input_size.
    scales_per_stride = deep_get(cfg, "anchors.scales_per_stride")
    strides_cfg = deep_get(cfg, "anchors.strides")
    if scales_per_stride is not None and strides_cfg is not None:
        anchors_xywh = get_anchors(
            deep_get(cfg, "data.input_size"),
            scales_per_stride=scales_per_stride,
            strides=strides_cfg,
        )
    else:
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

    # `reduce-overhead` mode invokes CUDA Graphs through TorchDynamo/Inductor —
    # avoids the AccumulateGrad-stream mismatch the raw `torch.cuda.graph()` and
    # `make_graphed_callables` paths hit (see optimization-attempts/README.md #7).
    if use_cuda_graphs:
        print(f"[cuda-graphs] compiling model via torch.compile(mode='reduce-overhead')...",
              flush=True)
        model = torch.compile(model, mode="reduce-overhead", fullgraph=False)
        print(f"[cuda-graphs] model wrapped — first batch will trigger compilation "
              f"(~10-30s warmup) then use cached graphs", flush=True)
    elif args.torch_compile_default:
        print(f"[compile] wrapping model with torch.compile(mode='default')...",
              flush=True)
        model = torch.compile(model, mode="default", fullgraph=False)
        print(f"[compile] model wrapped — first batch will JIT-fuse kernels",
              flush=True)
    graph_state: dict = {}

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
            if use_channels_last:
                image = image.contiguous(memory_format=torch.channels_last)
            if use_dali_box_encoder:
                # DALI's fn.box_encoder already emitted (cls_target, box_target).
                cls_t = batch["cls_target"].to(device, non_blocking=True)
                box_t = batch["box_target"].to(device, non_blocking=True)
            elif use_gpu_anchor_matcher:
                # Fully-batched GPU matcher: pads GTs to max-M, one IoU+encode op.
                cls_t, box_t = build_targets_gpu_batched(
                    batch["boxes"], anchors_xywh_gpu, anchors_xyxy_gpu,
                    pos_iou=pos_iou, neg_iou=neg_iou)
            elif args.use_numba_anchors:
                from src.stage1.models.anchors_numba import build_targets_numba
                cls_t, box_t = build_targets_numba(batch["boxes"], anchors_xywh,
                                                    pos_iou=pos_iou, neg_iou=neg_iou)
                cls_t = cls_t.to(device, non_blocking=True)
                box_t = box_t.to(device, non_blocking=True)
            else:
                # Numpy matcher is fastest at our batch sizes; a torchified
                # variant regressed (see --use-gpu-anchor-matcher).
                cls_t, box_t = _build_targets(batch["boxes"], anchors_xywh, pos_iou, neg_iou)
                cls_t = cls_t.to(device, non_blocking=True)
                box_t = box_t.to(device, non_blocking=True)

            if use_cuda_graphs:
                if use_amp_bf16:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                        out = model(image)
                        losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
                else:
                    out = model(image)
                    losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
                losses["loss"].backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                ema.update_parameters(model)
            else:
                optimizer.zero_grad(set_to_none=True)
                if use_amp_bf16:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                        out = model(image)
                        losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
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

    # Defense in depth: if the for-loop never ran (empty range), skip the
    # final save instead of crashing on an undefined `epoch`.
    if "epoch" not in dir() and "epoch" not in locals():
        print("[warn] no epochs ran (range was empty); not writing last.pt")
        print(f"[done] best_loss={best_loss:.5f}")
        return

    torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                "metrics": line, "config": cfg}, ckpt_dir / "last.pt")
    print(f"[done] best_loss={best_loss:.5f}")


if __name__ == "__main__":
    main()
