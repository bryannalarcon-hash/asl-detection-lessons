"""Export all four v3 nets to single-file ONNX for ONNX Runtime Web.

Workstream A of the WebGPU browser port (see docs/WEBGPU_PORT_PLAN.md). We
export only the PURE conv/transformer forwards. Everything around the graph
(letterbox, soft-argmax, anchor decode + NMS, crop/rotate/2-pass, the 343-dim
feature build, the window pad/subsample, softmax/top-k) stays in TS so parity
is verified against the Python reference, not baked into a brittle graph.

Each net is built exactly as the Python loaders build it (mirroring
src/stage2/data/extract_keypoints.py and src/stage2/predict_clip.py), so the
exported weights match what the live pipeline runs.

Dict-returning nets (Net 2, Net 3) and the mask-taking net (Net 4) are wrapped
in thin nn.Module adapters that return plain named tensors — ORT Web has no
notion of a Python dict output.

Export uses the legacy TorchScript exporter (dynamo=False): torch 2.12's
dynamo path externalizes weights to a .onnx.data sidecar, which is brittle to
serve to ORT Web over HTTP. The legacy path embeds weights inline in a single
file.

Run from repo root (CPU box):
    python3 tools/onnx_export/export_all.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.stage2.data.extract_keypoints import load_net1, load_net2, load_net3  # noqa: E402
from src.stage2.predict_clip import load_net4  # noqa: E402

OUT_DIR = REPO_ROOT / "frontend" / "public" / "models"
OPSET = 17
PARITY_TOL = 1e-3

NET1_CKPT = REPO_ROOT / "results" / "v3" / "net1_v3_1" / "best_export.pt"
NET2_CKPT = REPO_ROOT / "results" / "v3" / "net2_v3_1" / "best.pt"
NET3_CKPT = REPO_ROOT / "results" / "v3" / "net3" / "best.pt"
NET4_CKPT = REPO_ROOT / "results" / "v3" / "net4_popsign_125word" / "best.pt"

NET1_INPUT = 256   # letterboxed full-frame input
NET2_INPUT = 256   # letterboxed full-frame input
NET3_CROP = 224    # hand-crop input (crop_size in run_net3 / net3 data cfg)
NET4_C = 343       # per-frame feature dim (49*2 coords + 49 vis + 49*2 + 49*2)
NET4_T = 64        # max_frames (window length); exported as a dynamic axis too


# --------------------------------------------------------------------------
# Thin tensor-only adapters around the dict / mask interfaces.
# --------------------------------------------------------------------------
class Net2Adapter(nn.Module):
    """PalmDetector forward -> (cls, box). This Net 2 has no kpt head."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor):
        out = self.model(x)
        return out["cls"], out["box"]


class Net3Adapter(nn.Module):
    """HandLandmarkRegNet forward -> coords (B, 21, 3).

    This Net 3 was trained with with_presence=False, so the forward returns
    only {"coords"}. coords[..., :2] are sigmoid [0,1] crop coords; coords[...,
    2] is z held at 0 (with_z=False). TS uses only the xy columns.
    """

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor):
        return self.model(x)["coords"]


class Net4Adapter(nn.Module):
    """SignClassifier forward(features, key_padding_mask) -> logits (B, C).

    The bool mask is exported as a float tensor (1.0 = padded) and cast back
    to bool inside the graph: ORT Web feeds tensors, and a float input is the
    least surprising dtype to plumb from JS. True == padded matches the Python
    contract (window_to_model_input).
    """

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, feats: torch.Tensor, mask: torch.Tensor):
        return self.model(feats, key_padding_mask=mask.to(torch.bool))


def _export(model: nn.Module, dummies, out: Path, input_names, output_names,
            dynamic_axes) -> float:
    sidecar = out.with_suffix(".onnx.data")
    if sidecar.exists():
        sidecar.unlink()
    torch.onnx.export(
        model,
        dummies,
        str(out),
        input_names=input_names,
        output_names=output_names,
        opset_version=OPSET,
        dynamic_axes=dynamic_axes,
        do_constant_folding=True,
        dynamo=False,
    )
    assert not sidecar.exists(), f"{out.name}: export produced an external-data sidecar"
    return out.stat().st_size / 1e6


def _torch_forward(model: nn.Module, dummies):
    with torch.no_grad():
        out = model(*dummies) if isinstance(dummies, tuple) else model(dummies)
    if isinstance(out, (tuple, list)):
        return [t.cpu().numpy() for t in out]
    return [out.cpu().numpy()]


def _validate(out_path: Path, feed: dict, output_names, torch_outs) -> float:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    onnx_outs = sess.run(output_names, feed)
    max_diff = 0.0
    for to, oo in zip(torch_outs, onnx_outs):
        max_diff = max(max_diff, float(np.abs(to - oo).max()))
    return max_diff


def _report(name: str, size_mb: float, diff: float, shapes: str) -> None:
    status = "PASS" if diff < PARITY_TOL else "FAIL"
    print(f"[{name}] {size_mb:6.2f} MB  max|torch-onnx|={diff:.2e}  "
          f"[{status}]  {shapes}")
    assert diff < PARITY_TOL, (
        f"{name}: ONNX diverges from torch (max diff {diff:.2e} >= {PARITY_TOL})")


# --------------------------------------------------------------------------
# Per-net export routines.
# --------------------------------------------------------------------------
def export_net1() -> None:
    model, k, kslice = load_net1(str(NET1_CKPT), "cpu")
    out = OUT_DIR / "net1.onnx"
    rng = np.random.default_rng(1)
    x = rng.standard_normal((1, 3, NET1_INPUT, NET1_INPUT)).astype(np.float32)
    dummy = torch.from_numpy(x)
    size = _export(
        model, dummy, out,
        input_names=["input"], output_names=["heatmaps"],
        dynamic_axes={"input": {0: "batch"}, "heatmaps": {0: "batch"}},
    )
    torch_outs = _torch_forward(model, dummy)
    diff = _validate(out, {"input": x}, ["heatmaps"], torch_outs)
    _report("net1", size, diff, f"K={k} slice={kslice} -> heatmaps{torch_outs[0].shape}")


def export_net2() -> None:
    model, meta = load_net2(str(NET2_CKPT), "cpu")
    adapter = Net2Adapter(model).eval()
    out = OUT_DIR / "net2.onnx"
    rng = np.random.default_rng(2)
    x = rng.standard_normal((1, 3, NET2_INPUT, NET2_INPUT)).astype(np.float32)
    dummy = torch.from_numpy(x)
    size = _export(
        adapter, dummy, out,
        input_names=["input"], output_names=["cls", "box"],
        dynamic_axes={"input": {0: "batch"}, "cls": {0: "batch"},
                      "box": {0: "batch"}},
    )
    torch_outs = _torch_forward(adapter, dummy)
    diff = _validate(out, {"input": x}, ["cls", "box"], torch_outs)
    _report("net2", size, diff,
            f"n_kpts={meta['n_kpts']} N_anchors={torch_outs[0].shape[1]} "
            f"-> cls{torch_outs[0].shape} box{torch_outs[1].shape}")


def export_net3() -> None:
    model, head_type = load_net3(str(NET3_CKPT), "cpu")
    assert head_type == "regression", f"expected regression head, got {head_type}"
    adapter = Net3Adapter(model).eval()
    out = OUT_DIR / "net3.onnx"
    rng = np.random.default_rng(3)
    x = rng.standard_normal((1, 3, NET3_CROP, NET3_CROP)).astype(np.float32)
    dummy = torch.from_numpy(x)
    size = _export(
        adapter, dummy, out,
        input_names=["input"], output_names=["coords"],
        dynamic_axes={"input": {0: "batch"}, "coords": {0: "batch"}},
    )
    torch_outs = _torch_forward(adapter, dummy)
    diff = _validate(out, {"input": x}, ["coords"], torch_outs)
    _report("net3", size, diff,
            f"head={head_type} crop={NET3_CROP} -> coords{torch_outs[0].shape}")


def export_net4() -> None:
    model, gloss_to_idx, data_cfg = load_net4(str(NET4_CKPT), "cpu")
    adapter = Net4Adapter(model).eval()
    out = OUT_DIR / "net4.onnx"
    n_classes = len(gloss_to_idx)
    rng = np.random.default_rng(4)
    feats = rng.standard_normal((1, NET4_T, NET4_C)).astype(np.float32)
    # First 40 frames valid, rest padded — exercises the masked GAP path.
    mask = np.ones((1, NET4_T), dtype=np.float32)
    mask[0, :40] = 0.0
    d_feats = torch.from_numpy(feats)
    d_mask = torch.from_numpy(mask)
    size = _export(
        adapter, (d_feats, d_mask), out,
        input_names=["features", "key_padding_mask"], output_names=["logits"],
        dynamic_axes={"features": {0: "batch", 1: "frames"},
                      "key_padding_mask": {0: "batch", 1: "frames"},
                      "logits": {0: "batch"}},
    )
    torch_outs = _torch_forward(adapter, (d_feats, d_mask))
    diff = _validate(out, {"features": feats, "key_padding_mask": mask},
                     ["logits"], torch_outs)
    _report("net4", size, diff,
            f"C={NET4_C} T={NET4_T} classes={n_classes} "
            f"-> logits{torch_outs[0].shape}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"exporting to {OUT_DIR}  (opset {OPSET}, dynamo=False, single file)\n")
    export_net1()
    export_net2()
    export_net3()
    export_net4()
    print("\nALL EXPORTS VALIDATED (parity < 1e-3)")


if __name__ == "__main__":
    main()
