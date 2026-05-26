"""Global random-seed utility that seeds Python, NumPy, and PyTorch (CPU and CUDA) for reproducible training runs. Used across the CV pipeline trainers to make data shuffling and weight initialization deterministic."""
from __future__ import annotations

import os
import random

import numpy as np
import torch


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
