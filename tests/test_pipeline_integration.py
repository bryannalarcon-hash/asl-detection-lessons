"""Cross-vertical CPU verification for the 3-net architecture change.

Covers (per the QA brief):
  2. config load + key presence for the 3 new configs
  3. Net 3 reg model+loss+trainer-step + PCK helper sanity
  4. Net 2 encode/decode round-trip + forward shapes + DetectorLoss backward
  5. CRITICAL end-to-end inference chain (Net1 stub + real Net2/Net3) through
     BOTH the Net2-kpts-present 1-pass and the 2-pass fallback branches
  6. rotation-convention SIGN agreement between train canonicalization and
     inference upright_rotation_deg
  7. build_manifest_popsign against a tiny fake kpt_dir and a missing dir

Run: python3 -m pytest tests/test_pipeline_integration.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CROP = 224
TOL = 1e-3


# ---------------------------------------------------------------------------
# Test 2 — config load + key presence
# ---------------------------------------------------------------------------
def test_config_landmark_reg_keys():
    from src.common.v3_config import deep_get, load_v3_config
    cfg = load_v3_config(REPO / "configs/stage1_v3_landmark_reg.yaml")
    assert deep_get(cfg, "model.head_type") == "regression"
    assert deep_get(cfg, "model.num_keypoints") == 21
    assert deep_get(cfg, "data.canonicalize_rotation") is True
    assert deep_get(cfg, "loss.loss_type") == "smooth_l1"
    assert deep_get(cfg, "loss.beta") is not None
    kw = deep_get(cfg, "loss.keypoint_weights")
    assert isinstance(kw, list) and len(kw) == 21
    assert deep_get(cfg, "eval.pck_threshold_fracs") == [0.05, 0.10, 0.20]
    assert deep_get(cfg, "data.crop_size") == 224


def test_config_detector_kpt_keys():
    from src.common.v3_config import deep_get, load_v3_config
    cfg = load_v3_config(REPO / "configs/stage1_v3_detector_kpt.yaml")
    assert deep_get(cfg, "model.n_kpts") == 2
    assert deep_get(cfg, "model.use_fpn") is True
    assert deep_get(cfg, "model.anchors_per_scale") == [2, 2, 1]
    assert deep_get(cfg, "anchors.square") is True
    assert deep_get(cfg, "loss.kpt_weight") == 1.0
    assert deep_get(cfg, "anchors.strides") == [8, 16, 32]
    sps = deep_get(cfg, "anchors.scales_per_stride")
    assert isinstance(sps, list) and len(sps) == 3


def test_config_classifier_popsign_keys():
    from src.common.v3_config import deep_get, load_v3_config
    cfg = load_v3_config(REPO / "configs/stage2_v4_classifier_popsign.yaml")
    assert deep_get(cfg, "data.sign_list_json") is not None
    assert deep_get(cfg, "data.kpt_dir") is not None
    assert deep_get(cfg, "data.max_frames") == 64
    assert deep_get(cfg, "model.dim") is not None


# ---------------------------------------------------------------------------
# Test 3 — Net 3 model + loss + trainer-step + PCK helper
# ---------------------------------------------------------------------------
def test_net3_forward_backward_finite():
    from src.stage1.losses_landmark_reg import RegressionLandmarkLoss
    from src.stage1.models.landmark_net import HandLandmarkRegNet
    torch.manual_seed(0)
    model = HandLandmarkRegNet(num_keypoints=21, with_z=True, with_presence=True)
    model.train()
    loss_fn = RegressionLandmarkLoss(keypoint_weights=[1.0] * 21)
    img = torch.randn(8, 3, CROP, CROP)
    gt = torch.rand(8, 21, 2)
    vis = (torch.rand(8, 21) > 0.3).float()
    pred = model(img)
    out = loss_fn(pred["coords"], gt, vis, presence_logit=pred.get("presence"))
    assert torch.isfinite(out["loss"]), out["loss"]
    out["loss"].backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads, "no grads produced"
    assert all(torch.isfinite(g).all() for g in grads), "non-finite grad"


def test_net3_with_z_false_zeros_z_column():
    from src.stage1.models.landmark_net import HandLandmarkRegNet
    torch.manual_seed(1)
    model = HandLandmarkRegNet(num_keypoints=21, with_z=False, with_presence=False)
    model.eval()
    with torch.no_grad():
        out = model(torch.randn(4, 3, CROP, CROP))
    z = out["coords"][..., 2]
    assert torch.count_nonzero(z) == 0, f"z column not zeroed: {z.abs().max()}"
    assert "presence" not in out


def _pck_helper():
    from src.stage1.train_v3_landmark_reg import eval_pck_reg
    return eval_pck_reg


def test_net3_pck_perfect_vs_random():
    """Perfect preds -> PCK ~1.0; random preds -> much lower."""
    from src.stage1.train_v3_landmark_reg import eval_pck_reg

    class _Const(torch.nn.Module):
        def __init__(self, coords):
            super().__init__()
            self.coords = coords

        def forward(self, x):
            b = x.shape[0]
            return {"coords": self.coords[:b]}

    torch.manual_seed(2)
    B, K = 8, 21
    gt_px = torch.rand(B, K, 2) * CROP
    vis = torch.ones(B, K)
    batch = {"image": torch.zeros(B, 3, CROP, CROP),
             "keypoints": gt_px, "visible": vis}
    loader = [batch]
    fracs = [0.05, 0.10, 0.20]

    # Perfect: model emits exactly gt (normalized to [0,1]).
    perfect = _Const(torch.cat([gt_px / CROP,
                                torch.zeros(B, K, 1)], dim=-1))
    pck_perfect = eval_pck_reg(perfect, loader, "cpu", CROP, fracs, False)
    assert pck_perfect[0.05] > 0.99, pck_perfect

    # Random preds: PCK should be well below 1.0 at the tight threshold.
    rand = _Const(torch.cat([torch.rand(B, K, 2),
                             torch.zeros(B, K, 1)], dim=-1))
    pck_rand = eval_pck_reg(rand, loader, "cpu", CROP, fracs, False)
    assert pck_rand[0.05] < 0.5, pck_rand
    for f in fracs:
        assert 0.0 <= pck_perfect[f] <= 1.0 and 0.0 <= pck_rand[f] <= 1.0


# ---------------------------------------------------------------------------
# Test 4 — Net 2 encode/decode round-trip + forward + loss backward
# ---------------------------------------------------------------------------
def test_net2_encode_decode_roundtrip():
    from src.stage1.models.anchors import decode_kpts, encode_kpts
    rng = np.random.default_rng(3)
    N, K = 50, 2
    anchors = np.zeros((N, 4), dtype=np.float32)
    anchors[:, 0] = rng.uniform(20, 230, N)   # cx
    anchors[:, 1] = rng.uniform(20, 230, N)   # cy
    anchors[:, 2] = rng.uniform(10, 80, N)    # w
    anchors[:, 3] = rng.uniform(10, 80, N)    # h
    kpts = rng.uniform(0, 256, (N, K, 2)).astype(np.float32)
    enc = encode_kpts(kpts, anchors)
    dec = decode_kpts(torch.from_numpy(enc), torch.from_numpy(anchors)).numpy()
    err = np.abs(dec - kpts).max()
    assert err < TOL, f"kpt round-trip error {err}"
    # flat-form decode (matches model "kpt" channel layout) must agree too.
    flat = torch.from_numpy(enc.reshape(N, K * 2))
    dec_flat = decode_kpts(flat, torch.from_numpy(anchors)).numpy()
    assert np.abs(dec_flat - kpts).max() < TOL


def test_net2_forward_shapes_match_anchors():
    from src.stage1.models.anchors import get_anchors
    from src.stage1.models.palm_detector import PalmDetector
    input_size = 256
    scales = [[0.05, 0.10], [0.20, 0.35], [0.55]]
    strides = [8, 16, 32]
    anchors = get_anchors(input_size, scales_per_stride=scales,
                          strides=strides, square=True)
    model = PalmDetector(use_fpn=True, n_kpts=2, anchors_per_scale=(2, 2, 1))
    model.eval()
    with torch.no_grad():
        out = model(torch.randn(2, 3, input_size, input_size))
    n = anchors.shape[0]
    assert out["cls"].shape == (2, n)
    assert out["box"].shape == (2, n, 4)
    assert out["kpt"].shape == (2, n, 2 * 2)


def test_net2_detector_loss_backward_finite():
    from src.stage1.losses_v3 import DetectorLoss
    from src.stage1.models.anchors import get_anchors
    from src.stage1.models.palm_detector import PalmDetector
    input_size = 256
    scales = [[0.05, 0.10], [0.20, 0.35], [0.55]]
    anchors = get_anchors(input_size, scales_per_stride=scales,
                          strides=[8, 16, 32], square=True)
    n = anchors.shape[0]
    model = PalmDetector(use_fpn=True, n_kpts=2, anchors_per_scale=(2, 2, 1))
    model.train()
    out = model(torch.randn(2, 3, input_size, input_size))
    torch.manual_seed(4)
    cls_t = torch.zeros(2, n, dtype=torch.long)
    cls_t[:, :10] = 1                       # a handful of positives
    box_t = torch.randn(2, n, 4) * 0.1
    kpt_t = torch.randn(2, n, 4) * 0.1
    kpt_valid = torch.zeros(2, n)
    kpt_valid[:, :10] = 1.0
    loss_fn = DetectorLoss(kpt_weight=1.0)
    res = loss_fn(out["cls"], out["box"], cls_t, box_t,
                  kpt_pred=out["kpt"], kpt_target=kpt_t, kpt_valid=kpt_valid)
    assert torch.isfinite(res["loss"]), res
    assert "kpt" in res
    res["loss"].backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads and all(torch.isfinite(g).all() for g in grads)


def test_net2_build_kpt_targets():
    from src.stage1.models.anchors import build_kpt_targets
    N, M, K = 6, 2, 2
    anchors = np.array([[50, 50, 40, 40]] * N, dtype=np.float32)
    assignment = np.array([-1, 0, 1, -2, 0, -1], dtype=np.int64)
    gt_kpts = np.random.default_rng(5).uniform(0, 100, (M, K, 2)).astype(np.float32)
    gt_valid = np.array([1, 0], dtype=np.float32)   # GT 1 has invalid kpts
    tgt, valid = build_kpt_targets(assignment, anchors, gt_kpts, gt_valid, K)
    assert tgt.shape == (N, K * 2)
    assert valid.shape == (N,)
    # anchor 1 + 4 matched GT0 (valid); anchor 2 matched GT1 (invalid) -> 0.
    assert valid[1] == 1.0 and valid[4] == 1.0
    assert valid[2] == 0.0
    assert valid[0] == 0.0 and valid[3] == 0.0 and valid[5] == 0.0


# ---------------------------------------------------------------------------
# Test 6 — rotation-convention SIGN agreement (train vs inference)
# ---------------------------------------------------------------------------
def test_rotation_sign_train_vs_inference_agree():
    """A +x wrist->MCP vector must end pointing UP (-y) in the crop, and the
    training-dataset rot_deg formula must equal the inference one."""
    from src.stage1.data.hand_crops import crop_hand, project_kpts
    from src.stage1.data.palm_boxes import HandBBox
    from src.stage2.data.extract_keypoints import upright_rotation_deg

    wrist = (100.0, 100.0)
    mcp = (140.0, 100.0)               # vector points +x (to the RIGHT)

    # Inference convention.
    rot_inf = upright_rotation_deg(wrist, mcp)
    # Training-dataset convention (landmark_dataset.__getitem__ inline math).
    vx, vy = mcp[0] - wrist[0], mcp[1] - wrist[1]
    phi = np.degrees(np.arctan2(vy, vx))
    rot_train = -90.0 - phi
    assert abs(rot_inf - rot_train) < 1e-6, (rot_inf, rot_train)

    # Empirically: apply that rotation through crop_hand and confirm the
    # wrist->MCP vector points UP (negative crop-y) in the crop frame.
    box = HandBBox(x=60.0, y=60.0, w=80.0, h=80.0, side="right")
    pts = np.array([wrist, mcp], dtype=np.float32)
    _, M = crop_hand(np.zeros((256, 256, 3), np.uint8), box,
                     out_size=224, rotation_deg=rot_inf)
    crop_pts = project_kpts(pts, M)
    cv = crop_pts[1] - crop_pts[0]     # wrist->MCP in crop pixels
    # UP means dy strongly negative and dx ~ 0.
    assert cv[1] < -1.0, f"vector not pointing up: {cv}"
    assert abs(cv[0]) < 1e-2, f"vector has lateral component: {cv}"


# ---------------------------------------------------------------------------
# Test 5 — CRITICAL cross-vertical inference integration
# ---------------------------------------------------------------------------
class _Net1Stub(torch.nn.Module):
    """Minimal Net1 stand-in producing a (1, 7, hm, hm) heatmap tensor so the
    real run_net1 soft-argmax path executes unchanged."""
    def __init__(self, k=7, hm=64):
        super().__init__()
        self.k, self.hm = k, hm

    def forward(self, x):
        b = x.shape[0]
        return torch.rand(b, self.k, self.hm, self.hm)


def _run_chain(net2_kpts_path: bool, two_pass: bool):
    from src.stage1.models.anchors import get_anchors
    from src.stage1.models.landmark_net import HandLandmarkRegNet
    from src.stage1.models.palm_detector import PalmDetector
    from src.stage2.data import extract_keypoints as ek
    import src.stage1.data.schema as S

    torch.manual_seed(7)
    device = "cpu"
    net1 = _Net1Stub().eval()
    net2 = PalmDetector(use_fpn=True, n_kpts=(2 if net2_kpts_path else 0),
                        anchors_per_scale=(2, 2, 1)).eval()
    net3 = HandLandmarkRegNet(num_keypoints=21, with_z=True,
                              with_presence=True).eval()
    anchors = get_anchors(256, scales_per_stride=[[0.05, 0.10], [0.20, 0.35], [0.55]],
                          strides=[8, 16, 32], square=True)
    net2_meta = {"input_size": 256,
                 "anchors_xywh": torch.from_numpy(anchors).float()}

    frame = (np.random.default_rng(8).integers(0, 255, (480, 640, 3))
             .astype(np.uint8))

    body_k, body_v = ek.run_net1(net1, 7, [0, 7], frame, device)
    assert body_k.shape == (S.NUM_KEYPOINTS, 2)
    assert body_v.shape == (S.NUM_KEYPOINTS,)

    # Drive run_net2 at conf=0 so an untrained net still yields boxes, forcing
    # the full decode/NMS + (when present) kpt-decode path to execute.
    bboxes = ek.run_net2(net2, net2_meta, frame, device, conf=0.0, max_boxes=2)
    assert len(bboxes) >= 1, "untrained net2 produced no boxes at conf=0"
    if net2_kpts_path:
        assert bboxes[0][2] is not None, "kpt-head net2 must supply box_kpts"
    else:
        assert bboxes[0][2] is None, "no-kpt net2 must report None kpts"

    # Drive the full per-frame chain (mirrors extract_one_clip's inner loop).
    kpts_frame = body_k.copy()
    vis_frame = body_v.copy()
    sides = ek.assign_hand_side(bboxes, body_k, body_v)
    H, W = frame.shape[:2]
    saw_hand = False
    for (score, xyxy, box_kpts), side in zip(bboxes, sides):
        hand_kpts = ek.run_net3(net3, "regression", frame, xyxy, device,
                                net2_kpts=box_kpts, two_pass_fallback=two_pass)
        if hand_kpts is None:
            continue
        saw_hand = True
        assert hand_kpts.shape == (21, 2)
        assert np.isfinite(hand_kpts).all()
        slot = S.RIGHT_HAND_START if side == "right" else S.LEFT_HAND_START
        for j in range(21):
            x, y = hand_kpts[j]
            if 0 <= x < W and 0 <= y < H:
                kpts_frame[slot + j] = (x, y)
                vis_frame[slot + j] = 1.0
    assert saw_hand, "no hand survived the chain"
    assert kpts_frame.shape == (S.NUM_KEYPOINTS, 2)
    assert vis_frame.shape == (S.NUM_KEYPOINTS,)
    assert np.isfinite(kpts_frame).all()
    in_bounds = ((kpts_frame[:, 0] >= 0) & (kpts_frame[:, 0] < W) &
                 (kpts_frame[:, 1] >= 0) & (kpts_frame[:, 1] < H))
    assert in_bounds[vis_frame > 0].all(), "visible kpt out of frame bounds"


def test_integration_net2_kpts_present_one_pass():
    _run_chain(net2_kpts_path=True, two_pass=True)


def test_integration_two_pass_fallback():
    _run_chain(net2_kpts_path=False, two_pass=True)


def test_integration_one_pass_no_fallback():
    _run_chain(net2_kpts_path=False, two_pass=False)


# ---------------------------------------------------------------------------
# Test 7 — build_manifest_popsign on fake kpt_dir + missing dir
# ---------------------------------------------------------------------------
def _write_vocab(p: Path):
    p.write_text(json.dumps({
        "categories": {"animals": ["dog", "cat"], "food": ["icecream"]},
        "popsign_tar_aliases": {},
    }))


def test_build_manifest_with_fake_npz(tmp_path):
    vocab = tmp_path / "vocab.json"
    _write_vocab(vocab)
    kpt_dir = tmp_path / "kpt"
    kpt_dir.mkdir()
    for stem in ["dog_001", "dog_002", "cat_001", "icecream_001", "noise_999"]:
        np.savez(kpt_dir / f"{stem}.npz", keypoints=np.zeros((2, 49, 2)))
    sign_out = tmp_path / "sign_list.json"
    man_out = tmp_path / "manifest.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "src.stage2.data.build_manifest_popsign",
         "--vocab", str(vocab), "--kpt-dir", str(kpt_dir),
         "--sign-list-out", str(sign_out), "--manifest-out", str(man_out)],
        cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    sl = json.loads(sign_out.read_text())
    assert sl["total"] == 3                      # num_classes derivation
    assert sl["glosses_flat"] == ["DOG", "CAT", "ICECREAM"]
    rows = [json.loads(x) for x in man_out.read_text().splitlines() if x]
    assert len(rows) == 4                         # noise_999 unmapped, skipped
    glosses = sorted(r2["gloss"] for r2 in rows)
    assert glosses == ["CAT", "DOG", "DOG", "ICECREAM"]


def test_build_manifest_missing_dir(tmp_path):
    vocab = tmp_path / "vocab.json"
    _write_vocab(vocab)
    sign_out = tmp_path / "sign_list.json"
    man_out = tmp_path / "manifest.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "src.stage2.data.build_manifest_popsign",
         "--vocab", str(vocab), "--kpt-dir", str(tmp_path / "does_not_exist"),
         "--sign-list-out", str(sign_out), "--manifest-out", str(man_out)],
        cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert man_out.read_text() == ""              # empty manifest, graceful
    sl = json.loads(sign_out.read_text())
    assert sl["total"] == 3
    assert "per-sign download" in r.stdout


def _run_standalone() -> int:
    """Run every test_* in this module without pytest (none installed here).

    Tests that take a ``tmp_path`` arg get a fresh temp dir injected.
    Returns process exit code (0 = all passed).
    """
    import inspect
    import tempfile
    import traceback

    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    n_pass = n_fail = 0
    for name, fn in fns:
        params = inspect.signature(fn).parameters
        try:
            if "tmp_path" in params:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"PASS  {name}")
            n_pass += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc!r}")
            traceback.print_exc()
            n_fail += 1
    print(f"\n{n_pass} passed, {n_fail} failed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
