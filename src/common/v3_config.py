"""Lightweight v3 config loader — YAML → dict + a few typed helpers.

v2 used dataclasses; for v3 we keep it as a plain dict to avoid schema
churn while we iterate. Required keys are documented in
configs/stage1_v3_*.yaml.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_v3_config(path: str | Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def deep_get(cfg: dict, path: str, default=None):
    """deep_get(cfg, "train.batch_size") → cfg["train"]["batch_size"]."""
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
