// Shared harness for the WebGPU-port parity specs (V1 per-net, glue, e2e,
// verifier). Loads the Python reference fixtures, runs the .onnx assets through
// onnxruntime-node, and exposes diff helpers. Node-only (the browser uses
// onnxruntime-web; the math is identical, this just validates the graphs +
// the TS glue against the Python ground truth).

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as ort from 'onnxruntime-node';

const HERE = dirname(fileURLToPath(import.meta.url));
export const FIX_DIR = resolve(HERE, 'fixtures');
export const MODEL_DIR = resolve(HERE, '../../public/models');

export interface FixTensor {
  shape: number[];
  data: number[];
}

export function loadFixture<T = any>(name: string): T {
  return JSON.parse(readFileSync(resolve(FIX_DIR, name), 'utf8')) as T;
}

export function f32(t: FixTensor): Float32Array {
  return Float32Array.from(t.data);
}

/** Max abs diff between two flat numeric arrays of equal length. */
export function maxAbsDiff(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length) {
    throw new Error(`length mismatch: ${a.length} vs ${b.length}`);
  }
  let m = 0;
  for (let i = 0; i < a.length; i++) {
    const d = Math.abs(a[i] - b[i]);
    if (d > m) m = d;
  }
  return m;
}

/** Index of and value at the worst element (for diagnostics on failure). */
export function worstElement(a: ArrayLike<number>, b: ArrayLike<number>): {
  index: number;
  diff: number;
  a: number;
  b: number;
} {
  let idx = -1;
  let m = -1;
  for (let i = 0; i < a.length; i++) {
    const d = Math.abs(a[i] - b[i]);
    if (d > m) {
      m = d;
      idx = i;
    }
  }
  return { index: idx, diff: m, a: a[idx], b: b[idx] };
}

const sessionCache = new Map<string, Promise<ort.InferenceSession>>();

export function getSession(modelFile: string): Promise<ort.InferenceSession> {
  let p = sessionCache.get(modelFile);
  if (!p) {
    p = ort.InferenceSession.create(resolve(MODEL_DIR, modelFile), {
      executionProviders: ['cpu'],
    });
    sessionCache.set(modelFile, p);
  }
  return p;
}

/**
 * Run one fixture's inputs through the matching .onnx and return the named
 * output tensors as flat Float32Arrays keyed by output name. `dtypeOf` lets
 * specific inputs (e.g. net4 key_padding_mask -> bool) override float32.
 */
export async function runNet(
  modelFile: string,
  inputs: Record<string, FixTensor>,
  dtypeOf: Record<string, 'float32' | 'bool'> = {},
): Promise<Record<string, { data: Float32Array; dims: number[] }>> {
  const session = await getSession(modelFile);
  const feeds: Record<string, ort.Tensor> = {};
  for (const [name, t] of Object.entries(inputs)) {
    if (dtypeOf[name] === 'bool') {
      const bools = Uint8Array.from(t.data.map((v) => (v > 0.5 ? 1 : 0)));
      feeds[name] = new ort.Tensor('bool', bools, t.shape);
    } else {
      feeds[name] = new ort.Tensor('float32', f32(t), t.shape);
    }
  }
  const out = await session.run(feeds);
  const result: Record<string, { data: Float32Array; dims: number[] }> = {};
  for (const [name, tensor] of Object.entries(out)) {
    result[name] = {
      data: tensor.data as Float32Array,
      dims: tensor.dims as number[],
    };
  }
  return result;
}
