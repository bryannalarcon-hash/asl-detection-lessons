// V1 — per-net numerical parity: each .onnx asset, fed the fixed-seed Python
// reference input, must reproduce the PyTorch reference output within 1e-3
// (fp32). Catches ONNX export drift independent of the TS pre/post glue.

import { describe, expect, it } from 'vitest';
import { f32, loadFixture, maxAbsDiff, runNet, worstElement } from './_harness';

const TOL = 1e-3;

describe('V1 per-net parity (ORT vs PyTorch reference) @ tol 1e-3', () => {
  it('net1 heatmaps', async () => {
    const fx = loadFixture<any>('net1_io.json');
    const out = await runNet('net1.onnx', fx.inputs);
    const ref = f32(fx.outputs.heatmaps);
    const diff = maxAbsDiff(out.heatmaps.data, ref);
    console.log(`[net1] heatmaps maxAbsDiff = ${diff.toExponential(3)}  dims=${out.heatmaps.dims}`);
    if (diff > TOL) console.log('  worst:', worstElement(out.heatmaps.data, ref));
    expect(diff).toBeLessThan(TOL);
  });

  it('net2 cls + box', async () => {
    const fx = loadFixture<any>('net2_io.json');
    const out = await runNet('net2.onnx', fx.inputs);
    const dCls = maxAbsDiff(out.cls.data, f32(fx.outputs.cls));
    const dBox = maxAbsDiff(out.box.data, f32(fx.outputs.box));
    console.log(`[net2] cls maxAbsDiff = ${dCls.toExponential(3)}  box maxAbsDiff = ${dBox.toExponential(3)}`);
    expect(dCls).toBeLessThan(TOL);
    expect(dBox).toBeLessThan(TOL);
  });

  it('net3 coords', async () => {
    const fx = loadFixture<any>('net3_io.json');
    const out = await runNet('net3.onnx', fx.inputs);
    const ref = f32(fx.outputs.coords);
    const diff = maxAbsDiff(out.coords.data, ref);
    console.log(`[net3] coords maxAbsDiff = ${diff.toExponential(3)}  dims=${out.coords.dims}`);
    if (diff > TOL) console.log('  worst:', worstElement(out.coords.data, ref));
    expect(diff).toBeLessThan(TOL);
  });

  it('net4 logits', async () => {
    const fx = loadFixture<any>('net4_io.json');
    // The exported net4 graph takes key_padding_mask as FLOAT32 (1.0 = padded),
    // NOT bool — despite the stale "cast to bool in-graph" note in models.ts.
    // workstream D must feed a float32 mask tensor.
    const out = await runNet('net4.onnx', fx.inputs);
    const ref = f32(fx.outputs.logits);
    const diff = maxAbsDiff(out.logits.data, ref);
    console.log(`[net4] logits maxAbsDiff = ${diff.toExponential(3)}  dims=${out.logits.dims}`);
    if (diff > TOL) console.log('  worst:', worstElement(out.logits.data, ref));
    expect(diff).toBeLessThan(TOL);
  });
});
