"""Produce fp16 copies of the four exported nets for a WebGPU A/B speed test.

Reads the fp32 single-file ONNX models the TS pipeline already ships, converts
internal compute to fp16 with onnxconverter-common (keep_io_types=True so the
graph still takes/returns fp32 and no TS change is needed), and validates each
fp16 model against its fp32 twin on the SAME dummy inputs the export script
used (tools/onnx_export/export_all.py). Originals are never touched.

Run from repo root (CPU box):
    python3 tools/onnx_export/make_fp16.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnxconverter_common import float16

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "frontend" / "public" / "models"
OUT_DIR = SRC_DIR / "fp16"

NET1_INPUT = 256
NET2_INPUT = 256
NET3_CROP = 224
NET4_C = 343
NET4_T = 64

RISK_TOL = 5e-2  # diffs above this are flagged as a risk


def _feeds():
    """Mirror export_all.py: same shapes, same rng seeds, same net4 mask."""
    rng1 = np.random.default_rng(1)
    net1 = {"input": rng1.standard_normal((1, 3, NET1_INPUT, NET1_INPUT)).astype(np.float32)}

    rng2 = np.random.default_rng(2)
    net2 = {"input": rng2.standard_normal((1, 3, NET2_INPUT, NET2_INPUT)).astype(np.float32)}

    rng3 = np.random.default_rng(3)
    net3 = {"input": rng3.standard_normal((1, 3, NET3_CROP, NET3_CROP)).astype(np.float32)}

    rng4 = np.random.default_rng(4)
    feats = rng4.standard_normal((1, NET4_T, NET4_C)).astype(np.float32)
    mask = np.ones((1, NET4_T), dtype=np.float32)
    mask[0, :40] = 0.0
    net4 = {"features": feats, "key_padding_mask": mask}

    return {"net1": net1, "net2": net2, "net3": net3, "net4": net4}


def _session(path: Path) -> ort.InferenceSession:
    # Cap optimization at EXTENDED: ORT_ENABLE_ALL pulls in the x86-only
    # NchwcTransformer, which (a) segfaults the native CPU EP on the fp16 net4
    # MHA subgraph and (b) bakes non-portable, hardware-specific layouts. ORT
    # Web (the WebGPU runtime that actually serves these models) has no Nchwc
    # pass, so this only affects CPU-EP validation here, not the browser.
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def _run(path: Path, feed: dict):
    sess = _session(path)
    out_names = [o.name for o in sess.get_outputs()]
    return sess.run(out_names, feed)


def _mask_dtype(path: Path) -> str:
    sess = _session(path)
    for i in sess.get_inputs():
        if i.name == "key_padding_mask":
            return i.type
    return "<none>"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feeds = _feeds()

    rows = []
    for name in ("net1", "net2", "net3", "net4"):
        fp32_path = SRC_DIR / f"{name}.onnx"
        fp16_path = OUT_DIR / f"{name}.onnx"
        feed = feeds[name]

        model = onnx.load(str(fp32_path))
        node_block_list = None
        if name == "net4":
            # net4 embeds an exported nn.MultiheadAttention subgraph. Its
            # key-padding-mask path casts the fp32 mask to bool and back to a
            # float32 additive bias; a couple of attention casts also derive a
            # float32 1/sqrt(head_dim) scale from int shapes. The fp16 converter
            # flips the value_info of these tensors to fp16 but leaves the Cast
            # `to` attribute pointing at float32 -> a type mismatch ORT rejects.
            #
            # Fix: (1) run shape inference so every intermediate tensor has a
            # value_info entry, which is what lets the converter insert the
            # fp32<->fp16 boundary casts; (2) block the float32/bool cast nodes
            # so they stay fp32. The converter wraps them with boundary casts,
            # keeping the bool/additive mask path correct while the heavy
            # MatMul/Softmax/Gemm compute still runs in fp16.
            model = onnx.shape_inference.infer_shapes(model)
            node_block_list = [
                n.name for n in model.graph.node
                if n.op_type == "Cast"
                and next((a.i for a in n.attribute if a.name == "to"), None) in (1, 9)
            ]
        model_fp16 = float16.convert_float_to_float16(
            model, keep_io_types=True, node_block_list=node_block_list)
        onnx.save(model_fp16, str(fp16_path))

        fp32_outs = _run(fp32_path, feed)
        fp16_outs = _run(fp16_path, feed)
        max_diff = 0.0
        for a, b in zip(fp32_outs, fp16_outs):
            max_diff = max(max_diff, float(np.abs(a.astype(np.float64) - b.astype(np.float64)).max()))

        fp32_mb = fp32_path.stat().st_size / 1e6
        fp16_mb = fp16_path.stat().st_size / 1e6
        status = "RISK" if max_diff > RISK_TOL else "OK"

        extra = ""
        if name == "net4":
            extra = f"  mask_in_dtype(fp16)={_mask_dtype(fp16_path)}"
        rows.append((name, fp32_mb, fp16_mb, max_diff, status, extra))

    print(f"{'model':<6} {'fp32 MB':>9} {'fp16 MB':>9} {'max|fp32-fp16|':>16} {'status':>6}")
    for name, fp32_mb, fp16_mb, diff, status, extra in rows:
        print(f"{name:<6} {fp32_mb:>9.2f} {fp16_mb:>9.2f} {diff:>16.3e} {status:>6}{extra}")


if __name__ == "__main__":
    main()
