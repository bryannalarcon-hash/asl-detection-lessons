"""Stage 1 evaluation script.

  python -m src.stage1.eval --config configs/stage1_baseline.yaml \
      --checkpoint checkpoints/stage1/best.pt \
      [--render-dir /tmp/stage1_renders]

Reports PCK@0.05 on the COCO-WholeBody val split (split by sub-group:
overall / hands / face / body) and renders side-by-side predictions on
the first N samples if --render-dir is provided.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from src.common.config import load_config
from src.stage1.augment.transforms import build_val_transform
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.unified import UnifiedKeypointDataset
from src.stage1.data.visualize import draw_keypoints
from src.stage1.losses import HeatmapMSELoss
from src.stage1.metrics import compute_pck
from src.stage1.models.detector import KeypointDetector, soft_argmax_2d


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--render-dir", default=None)
    p.add_argument("--render-count", type=int, default=20)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    cfg = load_config(args.config)
    device = args.device or _pick_device()

    val_ds_raw = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_val_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_val_images}",
    )
    val_ds = UnifiedKeypointDataset(
        sources=[val_ds_raw],
        transform=build_val_transform(cfg.data.image_size),
        image_size=cfg.data.image_size,
        heatmap_size=cfg.data.heatmap_size,
        heatmap_sigma=cfg.data.heatmap_sigma,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.train.batch_size,
        shuffle=False, num_workers=cfg.train.num_workers,
    )

    model = KeypointDetector(
        num_keypoints=cfg.model.num_keypoints,
        backbone_channels=tuple(cfg.model.backbone_channels),
        heatmap_channels=cfg.model.heatmap_channels,
    ).to(device)
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    model.eval()
    print(f"[init] loaded checkpoint epoch={ckpt.get('epoch')} "
          f"with metrics={ckpt.get('metrics')}")

    loss_fn = HeatmapMSELoss()
    metrics_accum = {"pck_overall": 0.0, "pck_hands": 0.0,
                     "pck_face": 0.0, "pck_body": 0.0, "val_loss": 0.0}
    n = 0

    with torch.no_grad():
        for batch in val_loader:
            image = batch["image"].to(device, non_blocking=True)
            heatmaps = batch["heatmaps"].to(device, non_blocking=True)
            vis_mask = batch["visible"].to(device, non_blocking=True)
            gt_kps = batch["keypoints"].to(device, non_blocking=True)

            pred = model(image)
            loss = loss_fn(pred, heatmaps, vis_mask)
            metrics = compute_pck(
                pred, gt_kps, vis_mask,
                image_size=cfg.data.image_size,
                heatmap_size=cfg.data.heatmap_size,
            )
            for k, v in metrics.items():
                metrics_accum[k] += v
            metrics_accum["val_loss"] += float(loss.item())
            n += 1

    final = {k: v / max(n, 1) for k, v in metrics_accum.items()}
    print(json.dumps(final, indent=2))

    if args.render_dir:
        _render_predictions(model, val_ds_raw, cfg, device, args.render_dir,
                            args.render_count)


@torch.no_grad()
def _render_predictions(model, raw_ds, cfg, device, out_dir: str, count: int) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tx = build_val_transform(cfg.data.image_size)

    for i in range(min(count, len(raw_ds))):
        sample = raw_ds[i]
        img = np.array(Image.open(sample["image_path"]).convert("RGB"))
        from src.stage1.augment.transforms import apply_transform
        proc = apply_transform(
            tx, img, sample["keypoints"], sample["visible"], cfg.data.image_size,
        )
        image_tensor = torch.from_numpy(proc["image"]).permute(2, 0, 1).float()
        image_tensor = image_tensor.unsqueeze(0).to(device)
        heatmaps = model(image_tensor)
        pred_hm = soft_argmax_2d(heatmaps)[0].cpu().numpy()
        scale = cfg.data.image_size / cfg.data.heatmap_size
        pred_image = pred_hm * scale

        # Reconstruct the displayable image (undo normalization).
        disp = (proc["image"] * 0.5 + 0.5) * 255
        disp = disp.clip(0, 255).astype(np.uint8)
        out_img_path = out / f"sample_{i:03d}_input.png"
        Image.fromarray(disp).save(out_img_path)

        draw_keypoints(
            image_path=out_img_path,
            keypoints=pred_image,
            visible=np.ones(pred_image.shape[0], dtype=np.int64),
            out_path=out / f"sample_{i:03d}_pred.png",
        )
        draw_keypoints(
            image_path=out_img_path,
            keypoints=proc["keypoints"],
            visible=proc["visible"],
            out_path=out / f"sample_{i:03d}_gt.png",
        )

    print(f"[render] wrote {count} samples to {out_dir}")


def _pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


if __name__ == "__main__":
    main()
