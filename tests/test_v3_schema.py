"""Pure-Python (no torch/numpy) integrity checks for v3 components.

Catches schema typos and key constants before we get on a GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_palm_bbox_indices():
    from src.stage1.data.palm_boxes import PALM_KP_LOCAL
    # Wrist + thumb-CMC + 4 finger-MCPs (index/middle/ring/pinky)
    assert PALM_KP_LOCAL == [0, 1, 5, 9, 13, 17]
    print("OK PALM_KP_LOCAL")


def test_anchor_count():
    # 24*24 + 12*12 + 6*6 = 756; *3 anchors per cell = 2268
    # We import via numpy here; if not installed locally, skip.
    try:
        from src.stage1.models.anchors import (
            FEAT_GRID_SIZES, N_ANCHORS_PER_CELL, generate_anchors,
        )
        anchors = generate_anchors()
        expected = sum(g * g for g in FEAT_GRID_SIZES) * N_ANCHORS_PER_CELL
        assert anchors.shape == (expected, 4)
        print(f"OK anchor count ({expected})")
    except ImportError:
        print("SKIP anchor count (numpy missing locally)")


def test_finger_groups():
    from src.stage1.eval_v3 import FINGER_GROUPS
    assert FINGER_GROUPS["wrist"] == [0]
    assert FINGER_GROUPS["thumb"] == [1, 2, 3, 4]
    assert FINGER_GROUPS["pinky"] == [17, 18, 19, 20]
    assert FINGER_GROUPS["fingertips"] == [4, 8, 12, 16, 20]
    # All finger indices except 'fingertips' and 'wrist' should partition 0..20.
    seen = set()
    for name in ("wrist", "thumb", "index", "middle", "ring", "pinky"):
        for idx in FINGER_GROUPS[name]:
            assert idx not in seen, f"{idx} appears twice"
            seen.add(idx)
    assert seen == set(range(21))
    print("OK finger groups partition 0..20")


def test_v3_configs_loadable():
    import yaml
    for cfg_name in ("stage1_v3_detector.yaml",
                     "stage1_v3_landmark_phase1.yaml",
                     "stage1_v3_landmark_phase2.yaml"):
        cfg_path = Path(__file__).resolve().parent.parent / "configs" / cfg_name
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f)
        assert "train" in cfg and "epochs" in cfg["train"]
        print(f"OK config {cfg_name} loads")


if __name__ == "__main__":
    test_palm_bbox_indices()
    test_anchor_count()
    test_finger_groups()
    try:
        test_v3_configs_loadable()
    except ImportError:
        print("SKIP config load (yaml missing locally)")
    print("\nAll v3 schema tests passed (or skipped if missing local deps).")
