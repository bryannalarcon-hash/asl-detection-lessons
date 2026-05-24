"""Stage 1 v3 — Net 3 (hand landmark) training.

  python -u -m src.stage1.train_v3_landmark --config configs/stage1_v3_landmark_v1.yaml

A single-config run targeting 200 epochs with a weighted per-source sampler
(`data.target_mix`), BF16 mixed precision, FreiHAND held-out PCK@0.05 eval
each epoch, and periodic S3 checkpoint sync when `train.s3_bucket` is set.
The older two-phase configs are still accepted; missing keys fall back to
the historical defaults.
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

# cudnn auto-picks the fastest conv algo per shape. Enabled by default —
# leave on for ~2x throughput vs the cudnn default algorithm.
torch.backends.cudnn.benchmark = True

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.augment.transforms_v3 import GPUAugmentation
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.data.landmark_dataset import LandmarkTrainDataset
from src.stage1.losses_v3 import LandmarkLoss
from src.stage1.models.landmark_net import HandLandmarkNet, count_params
from src.stage1.train_v3_landmark_helpers import (
    build_freihand_val_loader, build_rhd_dataset, build_target_mix_sampler,
    eval_pck_freihand, s3_upload,
)


def _gpu_render_heatmaps(coords: torch.Tensor, vis: torch.Tensor,
                        crop_size: int, hm_size: int, sigma: float
                        ) -> tuple[torch.Tensor, torch.Tensor]:
    """Build Gaussian heatmaps on GPU from kpts in crop coords."""
    B, K, _ = coords.shape
    device = coords.device
    scale = hm_size / crop_size
    c = coords * scale
    ys = torch.arange(hm_size, device=device).view(1, 1, hm_size, 1).float()
    xs = torch.arange(hm_size, device=device).view(1, 1, 1, hm_size).float()
    cx = c[..., 0:1].unsqueeze(-1)
    cy = c[..., 1:2].unsqueeze(-1)
    hm = torch.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma * sigma))
    hm = hm * vis.view(B, K, 1, 1)
    out_of_frame = ((c[..., 0] < 0) | (c[..., 0] >= hm_size) |
                    (c[..., 1] < 0) | (c[..., 1] >= hm_size))
    vis_mask = vis.clone()
    vis_mask[out_of_frame] = 0
    hm = hm * vis_mask.view(B, K, 1, 1)
    return hm, vis_mask, c  # also return scaled coords for soft-argmax aux


def _pck_at_threshold(pred_coords: torch.Tensor, gt_coords: torch.Tensor,
                      vis_mask: torch.Tensor, threshold_px: float) -> float:
    diffs = (pred_coords - gt_coords).norm(dim=-1)
    correct = (diffs <= threshold_px).float() * vis_mask
    return float(correct.sum() / vis_mask.sum().clamp(min=1).item())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--data-limit", type=int, default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--use-dali", action="store_true",
                   help="Use DALI GPU pipeline (NVJPEG + warp_affine) instead of cv2 DataLoader")
    p.add_argument("--use-cuda-graphs", action="store_true",
                   help="Capture per-batch GPU aug + heatmap render + model + "
                        "loss + backward into a CUDA Graph and replay each "
                        "step. Re-captured at each epoch boundary so the "
                        "coord-loss ramp picks up the new epoch.")
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    set_seed(deep_get(cfg, "train.seed", 42))
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    use_dali = args.use_dali or bool(deep_get(cfg, "train.use_dali", False))
    use_cuda_graphs = args.use_cuda_graphs or bool(
        deep_get(cfg, "train.use_cuda_graphs", False))
    if use_cuda_graphs and device != "cuda":
        print("[warn] --use-cuda-graphs requires CUDA; disabling.")
        use_cuda_graphs = False
    print(f"[init] device={device}  run={cfg.get('run_name')}  "
          f"use_dali={use_dali}  use_cuda_graphs={use_cuda_graphs}", flush=True)

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

    if use_dali:
        from src.stage1.data.dali_pipelines import DALILandmarkLoader
        # Load phase2 cache if configured
        phase2_bbox = None
        p2c = deep_get(cfg, "data.phase2_bbox_cache")
        if p2c and Path(p2c).exists():
            with open(p2c) as f:
                phase2_bbox = json.load(f)
        loader = DALILandmarkLoader(
            freihand=freihand, interhand=interhand,
            crop_size=deep_get(cfg, "data.crop_size", 224),
            batch_size=deep_get(cfg, "train.batch_size"),
            padding_frac=deep_get(cfg, "data.padding_frac", 0.5),
            jitter_shift=deep_get(cfg, "data.jitter_shift", 0.10),
            jitter_scale=deep_get(cfg, "data.jitter_scale", 0.15),
            jitter_rot=deep_get(cfg, "data.jitter_rot", 10.0),
            phase2_bbox=phase2_bbox,
            phase2_mix_prob=deep_get(cfg, "data.phase2_mix_prob", 0.0),
            num_threads=min(8, deep_get(cfg, "train.num_workers", 8)),
            prefetch=4, shuffle=True, drop_last=True,
            seed=deep_get(cfg, "train.seed", 42),
        )
        steps_per_epoch = loader.num_batches_per_epoch()
        print(f"[init] using DALI landmark loader, {steps_per_epoch} batches/epoch", flush=True)
    else:
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
        )
        # WeightedRandomSampler honours data.target_mix when configured.
        # We compute weights against the unwrapped dataset before any Subset.
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
        steps_per_epoch = None

    # Model + loss ------------------------------------------------------
    model = HandLandmarkNet(
        num_keypoints=deep_get(cfg, "model.num_keypoints", 21),
        heatmap_channels=deep_get(cfg, "model.heatmap_channels", 128),
        use_unet_skip=bool(deep_get(cfg, "model.use_unet_skip", False)),
    ).to(device)
    print(f"[init] HandLandmarkNet params={count_params(model):,} "
          f"unet_skip={bool(deep_get(cfg, 'model.use_unet_skip', False))}",
          flush=True)

    # Resume from a previous checkpoint if specified (Phase 2 case).
    resume_from = deep_get(cfg, "train.resume_from")
    if resume_from and Path(resume_from).exists():
        ckpt = torch.load(resume_from, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        print(f"[init] resumed from {resume_from} (epoch={ckpt.get('epoch')})",
              flush=True)

    loss_fn = LandmarkLoss(
        awing_alpha=deep_get(cfg, "loss.awing_alpha", 2.1),
        awing_omega=deep_get(cfg, "loss.awing_omega", 14.0),
        awing_epsilon=deep_get(cfg, "loss.awing_epsilon", 1.0),
        awing_theta=deep_get(cfg, "loss.awing_theta", 0.5),
        coord_weight=deep_get(cfg, "loss.coord_weight", 0.1),
        coord_ramp_epochs=deep_get(cfg, "loss.coord_ramp_epochs", 5),
        keypoint_weights=deep_get(cfg, "loss.keypoint_weights"),
    )
    optimizer = AdamW(model.parameters(), lr=deep_get(cfg, "train.lr"),
                      weight_decay=deep_get(cfg, "train.weight_decay"))
    scheduler = CosineAnnealingLR(optimizer,
                                  T_max=deep_get(cfg, "train.epochs"),
                                  eta_min=deep_get(cfg, "train.lr_min"))
    # BF16 mixed precision: same exponent range as FP32, no loss scaling
    # needed. Dropping GradScaler eliminates the CPU-side state that was
    # invalidating CUDA Graph capture. BF16 is the modern training default
    # on Blackwell (RTX 5090 has full BF16 throughput). Either
    # train.use_bf16 or train.mixed_precision can request BF16.
    use_amp_bf16 = (bool(deep_get(cfg, "train.use_bf16",
                                  deep_get(cfg, "train.mixed_precision", False)))
                    and device == "cuda")
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(
        deep_get(cfg, "train.ema_decay", 0.9998)))

    # Allow each augment knob to be overridden via the config's `augment`
    # block — falls back to GPUAugmentation defaults when missing.
    aug_cfg = (cfg.get("augment") if isinstance(cfg, dict) else None) or {}
    gpu_aug = GPUAugmentation(
        image_size=deep_get(cfg, "data.crop_size", 224),
        rotate_deg=float(aug_cfg.get("rotate_deg", 30.0)),
        scale_range=tuple(aug_cfg.get("scale_range", (0.75, 1.25))),
        shift_frac=float(aug_cfg.get("shift_frac", 0.08)),
        hflip_p=float(aug_cfg.get("hflip_p", 0.5)),
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
    hm_size = deep_get(cfg, "data.heatmap_size", 56)
    sigma = deep_get(cfg, "data.heatmap_sigma", 2.0)

    # Held-out FreiHAND val loader for per-epoch PCK eval. None if the data
    # is missing — training still proceeds, val_pck reports as nan.
    val_loader, val_n = build_freihand_val_loader(cfg, crop_size)
    if val_loader is not None:
        print(f"[val] FreiHAND held-out PCK eval enabled — {val_n} samples", flush=True)
    else:
        print("[val] FreiHAND held-out split unavailable; val_pck will be nan", flush=True)
    pck_thresh_frac = float(deep_get(cfg, "eval.pck_threshold_frac", 0.05))

    # S3 sync config. Empty bucket disables network uploads.
    s3_bucket = str(deep_get(cfg, "train.s3_bucket", "") or "").strip()
    s3_prefix = str(deep_get(cfg, "train.s3_prefix", "net3/checkpoints")).strip("/")
    s3_sync_every = int(deep_get(cfg, "train.s3_sync_every", 10))
    if s3_bucket:
        print(f"[s3] sync target: s3://{s3_bucket}/{s3_prefix}/ every "
              f"{s3_sync_every} epochs", flush=True)

    # CUDA Graphs state. We re-capture at each epoch boundary because the
    # landmark loss bakes the `epoch` int into its coord-ramp coefficient —
    # capturing once would freeze the ramp value. Capture is ~1 s; amortized
    # over thousands of steps it is negligible.
    #
    # The captured region includes:
    #   gpu_aug(image, coords)           # kornia GPU aug — graph-safe
    #   _gpu_render_heatmaps(...)        # pure-tensor GPU ops
    #   model(aug_image)                 # forward (BF16 autocast, no scaler)
    #   loss_fn(...)                     # AdaptiveWing + soft-argmax
    #   loss.backward()
    # OUTSIDE the graph (per-step, after replay):
    #   clip_grad_norm_ / optimizer.step
    #   ema.update_parameters(model)
    #   live PCK computation (logging only)
    graph_state: dict = {"graph": None, "epoch": -1}

    def _capture_landmark_graph(sample_image: torch.Tensor,
                                 sample_coords: torch.Tensor,
                                 sample_vis: torch.Tensor,
                                 epoch_for_capture: int) -> dict:
        """Capture model + loss + backward (plus aug & heatmap) into a graph.

        gpu_aug uses torch.rand on the default CUDA generator, which is
        graph-safe in modern PyTorch — each replay advances the RNG state on
        device, so we still get fresh randomness per step. BatchNorm running
        stats are also updated correctly via the in-graph forward.
        """
        static_image = torch.zeros_like(sample_image)
        static_coords = torch.zeros_like(sample_coords)
        static_vis = torch.zeros_like(sample_vis)
        static_image.copy_(sample_image)
        static_coords.copy_(sample_coords)
        static_vis.copy_(sample_vis)

        # Warmup on a side stream. Full training step (with optimizer.step)
        # to warm cudnn algorithm picker, kornia compiled internals, etc.
        # BF16 autocast has no CPU-side state so it is capture-safe.
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(11):
                optimizer.zero_grad(set_to_none=True)
                with torch.no_grad():
                    aug_img_w, coords_aug_w = gpu_aug(static_image, static_coords)
                    heatmaps_w, vis_mask_w, coords_hm_w = _gpu_render_heatmaps(
                        coords_aug_w, static_vis, crop_size, hm_size, sigma)
                if use_amp_bf16:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                        pred_w = model(aug_img_w)
                        out_w = loss_fn(pred_w, heatmaps_w, coords_hm_w, vis_mask_w,
                                        epoch=epoch_for_capture)
                else:
                    pred_w = model(aug_img_w)
                    out_w = loss_fn(pred_w, heatmaps_w, coords_hm_w, vis_mask_w,
                                    epoch=epoch_for_capture)
                out_w["loss"].backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                optimizer.step()
        torch.cuda.current_stream().wait_stream(s)
        # Zero grads in place to keep gradient storage addresses stable for
        # the captured graph (do NOT use set_to_none=True here).
        for p_ in model.parameters():
            if p_.grad is not None:
                p_.grad.detach_()
                p_.grad.zero_()

        # Disable cudnn.benchmark during capture (trial-kernel probes are NOT
        # stream-capture-safe). The warmup already picked the best algo for
        # these shapes; the cache persists across the benchmark=False window.
        prev_benchmark = torch.backends.cudnn.benchmark
        torch.backends.cudnn.benchmark = False

        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            with torch.no_grad():
                aug_image, coords_aug = gpu_aug(static_image, static_coords)
                heatmaps, vis_mask, coords_hm = _gpu_render_heatmaps(
                    coords_aug, static_vis, crop_size, hm_size, sigma)
            if use_amp_bf16:
                with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                    static_pred = model(aug_image)
                    static_out = loss_fn(static_pred, heatmaps, coords_hm, vis_mask,
                                         epoch=epoch_for_capture)
            else:
                static_pred = model(aug_image)
                static_out = loss_fn(static_pred, heatmaps, coords_hm, vis_mask,
                                     epoch=epoch_for_capture)
            static_out["loss"].backward()
        torch.backends.cudnn.benchmark = prev_benchmark
        return {
            "graph": g,
            "epoch": epoch_for_capture,
            "static_image": static_image,
            "static_coords": static_coords,
            "static_vis": static_vis,
            "static_pred": static_pred,        # used for live PCK after replay
            "static_coords_aug": coords_aug,   # used for live PCK after replay
            "static_vis_mask": vis_mask,
            "static_out": static_out,
        }

    for epoch in range(deep_get(cfg, "train.epochs")):
        epoch_t0 = time.time()
        if epoch < warmup:
            for pg in optimizer.param_groups:
                pg["lr"] = deep_get(cfg, "train.lr") * (epoch + 1) / max(warmup, 1)

        model.train()
        running = 0.0
        n_steps = 0
        pck_acc = 0.0
        threshold_px = 0.05 * crop_size

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
            image = batch["image"]
            if not use_dali:
                image = image.to(device, non_blocking=True)
            coords = batch["keypoints"].to(device, non_blocking=True)
            vis = batch["visible"].to(device, non_blocking=True)

            if use_cuda_graphs:
                # (Re)capture if this is the first batch of a new epoch:
                # the loss bakes `epoch` into the coord-ramp coefficient.
                if (graph_state["graph"] is None
                        or graph_state["epoch"] != epoch):
                    graph_state = _capture_landmark_graph(image, coords, vis, epoch)
                    print(f"[cuda-graphs] captured landmark graph for epoch "
                          f"{epoch} (image={tuple(image.shape)})", flush=True)
                # Replay.
                graph_state["static_image"].copy_(image, non_blocking=True)
                graph_state["static_coords"].copy_(coords, non_blocking=True)
                graph_state["static_vis"].copy_(vis, non_blocking=True)
                graph_state["graph"].replay()
                # Optimizer / clip / EMA stay OUTSIDE the graph (CPU state).
                # With BF16 (no scaler), no scale/unscale dance needed.
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), deep_get(cfg, "train.grad_clip", 1.0))
                optimizer.step()
                ema.update_parameters(model)
                # Zero grads in-place to preserve the graph's static grad
                # storage. set_to_none=True would invalidate addresses.
                for p_ in model.parameters():
                    if p_.grad is not None:
                        p_.grad.zero_()
                # Reuse the graph's static outputs for logging / PCK.
                out = graph_state["static_out"]
                pred = graph_state["static_pred"]
                coords_aug = graph_state["static_coords_aug"]
                vis_mask = graph_state["static_vis_mask"]
            else:
                # GPU augmentation (no_grad — we don't backprop into aug params).
                with torch.no_grad():
                    image, coords_aug = gpu_aug(image, coords)
                    if coords_aug is None:
                        coords_aug = coords
                    heatmaps, vis_mask, coords_hm = _gpu_render_heatmaps(
                        coords_aug, vis, crop_size, hm_size, sigma,
                    )

                optimizer.zero_grad(set_to_none=True)
                if use_amp_bf16:
                    with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                        pred = model(image)
                        out = loss_fn(pred, heatmaps, coords_hm, vis_mask, epoch=epoch)
                else:
                    pred = model(image)
                    out = loss_fn(pred, heatmaps, coords_hm, vis_mask, epoch=epoch)
                out["loss"].backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(),
                                               deep_get(cfg, "train.grad_clip", 1.0))
                optimizer.step()
                ema.update_parameters(model)
            running += float(out["loss"].item())
            n_steps += 1

            with torch.no_grad():
                # Quick PCK from pred soft-argmax for live monitoring.
                B, K, H, W = pred.shape
                flat = pred.view(B, K, -1)
                flat = flat - flat.max(dim=-1, keepdim=True).values
                probs = torch.softmax(flat * 10.0, dim=-1).view(B, K, H, W)
                ys = torch.arange(H, device=device).float()
                xs = torch.arange(W, device=device).float()
                gy, gx = torch.meshgrid(ys, xs, indexing="ij")
                px = (probs * gx[None, None]).sum(dim=(-1, -2)) * (crop_size / hm_size)
                py = (probs * gy[None, None]).sum(dim=(-1, -2)) * (crop_size / hm_size)
                pred_xy = torch.stack([px, py], dim=-1)
                pck_acc += _pck_at_threshold(pred_xy, coords_aug, vis_mask, threshold_px)

        if epoch >= warmup:
            scheduler.step()
        # Held-out FreiHAND PCK eval (EMA weights — what we ship).
        val_pck = eval_pck_freihand(ema.module, val_loader, device,
                                    crop_size, hm_size, pck_thresh_frac,
                                    use_amp_bf16)

        epoch_secs = time.time() - epoch_t0
        avg_loss = running / max(n_steps, 1)
        avg_pck = pck_acc / max(n_steps, 1)
        line = {
            "epoch": epoch, "epoch_secs": round(epoch_secs, 1),
            "train_loss": avg_loss, "train_pck": avg_pck,
            "val_pck": val_pck,
            "lr": optimizer.param_groups[0]["lr"],
        }
        with metrics_log.open("a") as f:
            f.write(json.dumps(line) + "\n")
        val_pck_str = f"{val_pck:.3f}" if val_pck == val_pck else "nan"
        print(f"epoch {epoch} | train_loss {avg_loss:.3f} | "
              f"val_pck {val_pck_str} | elapsed {epoch_secs/60:.1f} min",
              flush=True)

        # `best` tracks val PCK when available, otherwise the training PCK
        # surrogate as before. This keeps the legacy phase configs working.
        score = val_pck if (val_pck == val_pck) else avg_pck
        improved = score > best_pck + deep_get(cfg, "train.early_stop_min_delta", 0.001)
        if improved:
            best_pck = score
            patience = 0
            best_path = ckpt_dir / "best.pt"
            torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                        "metrics": line, "config": cfg}, best_path)
            if s3_bucket:
                s3_upload(best_path, s3_bucket, f"{s3_prefix}/best.pt")
        else:
            patience += 1
            if patience >= deep_get(cfg, "train.early_stop_patience", 25):
                print(f"[early-stop] no improvement for {patience} epochs", flush=True)
                break
        if (epoch + 1) % 10 == 0:
            snap_path = ckpt_dir / f"epoch_{epoch:03d}.pt"
            torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                        "metrics": line, "config": cfg}, snap_path)
            if s3_bucket and ((epoch + 1) % s3_sync_every == 0):
                s3_upload(snap_path, s3_bucket, f"{s3_prefix}/{snap_path.name}")
                s3_upload(metrics_log, s3_bucket, f"{s3_prefix}/metrics.jsonl")

    last_path = ckpt_dir / "last.pt"
    torch.save({"model": ema.module.state_dict(), "epoch": epoch,
                "metrics": line, "config": cfg}, last_path)
    if s3_bucket:
        s3_upload(last_path, s3_bucket, f"{s3_prefix}/last.pt")
        s3_upload(metrics_log, s3_bucket, f"{s3_prefix}/metrics.jsonl")
    print(f"[done] best_pck={best_pck:.3f}", flush=True)


if __name__ == "__main__":
    main()
