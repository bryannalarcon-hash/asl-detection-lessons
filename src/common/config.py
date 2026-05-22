from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DataConfig:
    coco_root: str = "data/coco"
    coco_ann_file: str = "data/coco/annotations/coco_wholebody_train_v1.0.json"
    coco_val_ann_file: str = "data/coco/annotations/coco_wholebody_val_v1.0.json"
    coco_train_images: str = "train2017"
    coco_val_images: str = "train2017"  # default: our random split lives in train2017
    freihand_root: str = "data/FreiHAND_pub_v2"
    image_size: int = 384
    heatmap_size: int = 96
    heatmap_sigma: float = 2.0
    sample_ratio_coco: float = 0.7
    sample_ratio_freihand: float = 0.3
    flip_prob: float = 0.5
    color_jitter: float = 0.2


@dataclass
class ModelConfig:
    num_keypoints: int = 49
    backbone_channels: tuple = (32, 64, 128, 256, 384)
    heatmap_channels: int = 256


@dataclass
class TrainConfig:
    batch_size: int = 32
    num_workers: int = 4
    epochs: int = 210
    lr: float = 1e-3
    lr_min: float = 5e-4
    weight_decay: float = 1e-4
    early_stop_patience: int = 30
    early_stop_min_delta: float = 0.001
    mixed_precision: bool = True
    log_every: int = 50
    val_every: int = 1
    checkpoint_dir: str = "checkpoints/stage1"
    seed: int = 42


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    run_name: str = "stage1_baseline"


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f) or {}
    base = {
        "data": DataConfig().__dict__,
        "model": ModelConfig().__dict__,
        "train": TrainConfig().__dict__,
        "run_name": "stage1_baseline",
    }
    merged = _merge(base, raw)
    return Config(
        data=DataConfig(**merged["data"]),
        model=ModelConfig(**merged["model"]),
        train=TrainConfig(**merged["train"]),
        run_name=merged["run_name"],
    )


def dump_config(cfg: Config) -> dict[str, Any]:
    return {
        "run_name": cfg.run_name,
        "data": cfg.data.__dict__,
        "model": cfg.model.__dict__,
        "train": cfg.train.__dict__,
    }
