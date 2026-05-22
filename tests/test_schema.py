"""Pure-Python integrity checks for the keypoint schema and FreiHAND remap.

Runs without torch/numpy. Catches schema typos before we get on a GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stage1.data import schema as S
from src.stage1.data.schema import MANO_TO_MP


def test_keypoint_counts() -> None:
    assert S.NUM_KEYPOINTS == 49
    assert len(S.KEYPOINT_NAMES) == 49
    assert len(S.HAND_INDICES_RIGHT) == 21
    assert len(S.HAND_INDICES_LEFT) == 21
    assert set(S.HAND_INDICES_RIGHT).isdisjoint(set(S.HAND_INDICES_LEFT))
    print("OK keypoint_counts")


def test_named_indices_are_unique() -> None:
    named = {
        S.NOSE, S.CHIN, S.FOREHEAD, S.CHEST_CENTER,
        S.LEFT_SHOULDER, S.RIGHT_SHOULDER, S.NECK,
    }
    assert len(named) == 7
    # No collisions with hand ranges.
    for idx in named:
        assert idx not in S.HAND_INDICES_RIGHT
        assert idx not in S.HAND_INDICES_LEFT
    print("OK named_indices_are_unique")


def test_flip_pairs_cover_hands_and_shoulders() -> None:
    # 21 hand pairs + 1 shoulder pair.
    assert len(S.FLIP_PAIRS) == 22
    # Every pair index is in range.
    for a, b in S.FLIP_PAIRS:
        assert 0 <= a < S.NUM_KEYPOINTS
        assert 0 <= b < S.NUM_KEYPOINTS
        assert a != b
    # Each index appears at most once across all pairs.
    seen: set[int] = set()
    for a, b in S.FLIP_PAIRS:
        for x in (a, b):
            assert x not in seen, f"index {x} appears in multiple flip pairs"
            seen.add(x)
    print("OK flip_pairs")


def test_mano_to_mp_is_a_permutation() -> None:
    assert len(MANO_TO_MP) == 21
    assert sorted(MANO_TO_MP) == list(range(21))
    # Wrist is identity.
    assert MANO_TO_MP[0] == 0
    # Thumb (mp 1..4) maps from mano 17..20.
    assert MANO_TO_MP[1:5] == [17, 18, 19, 20]
    # Index (mp 5..8) maps from mano 1..4.
    assert MANO_TO_MP[5:9] == [1, 2, 3, 4]
    # Pinky (mp 17..20) maps from mano 9..12.
    assert MANO_TO_MP[17:21] == [9, 10, 11, 12]
    print("OK mano_to_mp")


def test_empty_keypoints_round_trip() -> None:
    ks = S.empty_keypoints()
    assert all(c == (0.0, 0.0) for c in ks.coords)
    assert all(v == 0 for v in ks.visible)
    print("OK empty_keypoints")


if __name__ == "__main__":
    test_keypoint_counts()
    test_named_indices_are_unique()
    test_flip_pairs_cover_hands_and_shoulders()
    test_mano_to_mp_is_a_permutation()
    test_empty_keypoints_round_trip()
    print("\nAll schema tests passed.")
