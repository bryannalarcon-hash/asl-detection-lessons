"""FreiHAND v2 loader mapped into our 49-keypoint schema.

FreiHAND v2 ships ~130K right-hand images (4 background variants of ~32.5K
unique scenes). 3D keypoints are provided in camera frame; we project to 2D
using the per-image intrinsics matrix. Hand keypoints are in MANO order; we
remap to the MediaPipe-style order used by our schema.

All FreiHAND samples populate the RIGHT_HAND slot. Horizontal-flip
augmentation will produce the corresponding left-hand examples during
training.

Sample contract (consumed by `LandmarkTrainDataset` and any other Net-3
training pipeline):
    {
        "image_path": str,             # path on disk
        "image_id": int,               # FreiHAND image index
        "image_width": 224,            # FreiHAND images are fixed 224 x 224
        "image_height": 224,
        "keypoints": np.ndarray,       # (49, 2) float32 image-pixel coords
        "visible":   np.ndarray,       # (49,)  int64, 0 = unlabeled, 1 = labeled
    }

After the consumer slices the right-hand slot
(`coords[RIGHT_HAND_START:RIGHT_HAND_START + 21]`) the result is the
`(image, kpts[21, 2], mask[21])` triple Net 3 trains on (the image tensor
is built by `LandmarkTrainDataset` from `image_path`).

Limitations:
    - FreiHAND is right-hand-only; the LEFT_HAND slot is always zeros /
      not-visible. Use horizontal-flip augmentation to synthesize the
      left-hand distribution.
    - Image dimensions are hardcoded to 224x224 because FreiHAND ships at
      exactly that resolution. If the underlying dataset ever ships a
      different resolution this needs to read from the actual file.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S
from src.stage1.data.schema import MANO_TO_MP


_VARIANTS_PER_SCENE = 4


class FreiHANDDataset(Dataset):
    """Loads FreiHAND v2 training split.

    Each sample populates only the right-hand portion of the unified schema;
    everything else is marked not-visible.
    """

    def __init__(
        self,
        root: str | Path,
        split: str = "training",
        use_all_variants: bool = True,
        scene_split: str | None = None,    # "train" / "val" / None for all
        val_scene_frac: float = 0.05,
        scene_split_seed: int = 42,
    ) -> None:
        super().__init__()
        self.root = Path(root)
        self.image_dir = self.root / f"{split}/rgb"
        if not self.image_dir.exists():
            raise FileNotFoundError(f"FreiHAND images not found at {self.image_dir}")

        with (self.root / f"{split}_K.json").open() as f:
            self.K = np.array(json.load(f), dtype=np.float32)  # (N, 3, 3)
        with (self.root / f"{split}_xyz.json").open() as f:
            self.xyz = np.array(json.load(f), dtype=np.float32)  # (N, 21, 3)

        self.num_scenes = self.xyz.shape[0]
        self.use_all_variants = use_all_variants

        # Determine which scene indices belong to this split.
        if scene_split is None:
            scene_indices = list(range(self.num_scenes))
        else:
            rng = np.random.default_rng(scene_split_seed)
            perm = rng.permutation(self.num_scenes)
            n_val = max(1, int(self.num_scenes * val_scene_frac))
            val_scenes = set(int(s) for s in perm[:n_val])
            if scene_split == "val":
                scene_indices = sorted(val_scenes)
            elif scene_split == "train":
                scene_indices = sorted(set(range(self.num_scenes)) - val_scenes)
            else:
                raise ValueError(f"unknown scene_split: {scene_split}")
        self.scene_indices = scene_indices

        # Expand scene indices → image indices (all variants per scene if requested).
        variant_count = _VARIANTS_PER_SCENE if use_all_variants else 1
        self.image_indices: list[int] = []
        for scene in scene_indices:
            for v in range(variant_count):
                self.image_indices.append(scene + v * self.num_scenes)

        # Image filenames are zero-padded 8-digit numbers.
        self.image_paths: list[Path] = [
            self.image_dir / f"{i:08d}.jpg" for i in self.image_indices
        ]

    def __len__(self) -> int:
        return len(self.image_paths)

    def __getitem__(self, idx: int) -> dict:
        image_path = self.image_paths[idx]
        image_idx = self.image_indices[idx]
        scene_idx = image_idx % self.num_scenes
        K = self.K[scene_idx]
        xyz = self.xyz[scene_idx]  # (21, 3) in MANO order

        # Project 3D to 2D pixels: uv = K @ xyz; then divide by z.
        uvz = xyz @ K.T  # (21, 3)
        uv = uvz[:, :2] / uvz[:, 2:3]

        # Remap MANO → our hand ordering (MediaPipe-style).
        uv_mp = uv[MANO_TO_MP]  # (21, 2)

        coords = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)
        coords[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = uv_mp
        visible[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = 1

        return {
            "image_path": str(image_path),
            "image_id": image_idx,
            "image_width": 224,
            "image_height": 224,
            "keypoints": coords,
            "visible": visible,
        }
