// Pure decode helpers for the GPU-batched cascade (see batchedRuntime.ts).
// Extracted so batchedRuntime.ts stays under the 500-line cap. These are all
// inference-free: given the same logits/coords they produce byte-identical
// output regardless of batch composition. The BatchedRuntime methods just call
// these free functions, passing in the contract slice (+ anchors for Net2).

import {
  NUM_KEYPOINTS,
  type Net2Contract,
  type Net3Contract,
} from './ort/models';
import {
  decodeBox,
  nms,
  sigmoid,
  softArgmax2d,
  xywhToXyxy,
} from './pipeline/geom';
import {
  generateAnchorsLegacy,
  generateAnchorsMultiStride,
} from './pipeline/anchors';

export interface PalmBox {
  score: number;
  xyxy: [number, number, number, number];
}

// ---------------------------------------------------------------------------
// Image normalization: (px/255 - 0.5)/0.5, HWC RGB -> CHW float32. Writes into
// `out` at `offset` so we can pack a batch back-to-back.
// ---------------------------------------------------------------------------
export function chwNormInto(
  hwc: Uint8Array | Uint8ClampedArray,
  size: number,
  out: Float32Array,
  offset: number,
): void {
  const plane = size * size;
  for (let i = 0; i < plane; i++) {
    const base = i * 3;
    out[offset + i] = (hwc[base] / 255 - 0.5) / 0.5;
    out[offset + plane + i] = (hwc[base + 1] / 255 - 0.5) / 0.5;
    out[offset + 2 * plane + i] = (hwc[base + 2] / 255 - 0.5) / 0.5;
  }
}

export function buildAnchors(c: Net2Contract): Float32Array {
  const a = c.anchors;
  if (a.multiStride) {
    return generateAnchorsMultiStride(
      a.inputSize,
      a.scalesPerStride ?? [],
      a.strides ?? [],
      a.square ?? false,
    );
  }
  return generateAnchorsLegacy(a.inputSize, [24, 12, 6], [0.1, 0.2, 0.35]);
}

// --- Net2: decode one frame's (cls,box) rows -> palm boxes ------------- //
// Pure of inference; shared by the per-frame and batched forwards so they are
// bit-identical given the same logits. `lb` is that frame's letterbox meta.
export function decodeNet2(
  c: Net2Contract,
  anchors: Float32Array,
  cls: Float32Array,
  box: Float32Array,
  N: number,
  lb: { scale: number; dx: number; dy: number },
): PalmBox[] {
  const keepIdx: number[] = [];
  for (let i = 0; i < N; i++) if (sigmoid(cls[i]) >= c.conf) keepIdx.push(i);
  if (keepIdx.length === 0) return [];

  const m = keepIdx.length;
  const scores = new Float32Array(m);
  const deltas = new Float32Array(m * 4);
  const anchorsKept = new Float32Array(m * 4);
  for (let r = 0; r < m; r++) {
    const i = keepIdx[r];
    scores[r] = sigmoid(cls[i]);
    deltas[r * 4] = box[i * 4];
    deltas[r * 4 + 1] = box[i * 4 + 1];
    deltas[r * 4 + 2] = box[i * 4 + 2];
    deltas[r * 4 + 3] = box[i * 4 + 3];
    anchorsKept[r * 4] = anchors[i * 4];
    anchorsKept[r * 4 + 1] = anchors[i * 4 + 1];
    anchorsKept[r * 4 + 2] = anchors[i * 4 + 2];
    anchorsKept[r * 4 + 3] = anchors[i * 4 + 3];
  }
  const xyxy = xywhToXyxy(decodeBox(deltas, anchorsKept, m), m);
  const nmsIdx = nms(xyxy, scores, m, c.iouThreshold, c.maxBoxes);
  const boxes: PalmBox[] = [];
  for (const ki of nmsIdx) {
    const x1 = (xyxy[ki * 4] - lb.dx) / lb.scale;
    const y1 = (xyxy[ki * 4 + 1] - lb.dy) / lb.scale;
    const x2 = (xyxy[ki * 4 + 2] - lb.dx) / lb.scale;
    const y2 = (xyxy[ki * 4 + 3] - lb.dy) / lb.scale;
    boxes.push({ score: scores[ki], xyxy: [x1, y1, x2, y2] });
  }
  return boxes;
}

// --- Net3: batched pass(es) -------------------------------------------- //
export function decodeNet3Batch(
  c: Net3Contract,
  out: Float32Array,
  dims: number[],
  B: number,
): Float32Array[] {
  const results: Float32Array[] = [];
  if (c.headType === 'regression') {
    // coords (B, 21, 3); take [:, :2] in [0,1] -> * cropSize.
    const per = c.numKeypoints * 3;
    for (let b = 0; b < B; b++) {
      const cc = new Float32Array(c.numKeypoints * 2);
      for (let k = 0; k < c.numKeypoints; k++) {
        cc[k * 2] = out[b * per + k * 3] * c.cropSize;
        cc[k * 2 + 1] = out[b * per + k * 3 + 1] * c.cropSize;
      }
      results.push(cc);
    }
  } else {
    const [, K, Hm, Wm] = dims;
    const per = K * Hm * Wm;
    const ratio = c.cropSize / Wm;
    for (let b = 0; b < B; b++) {
      const hm = softArgmax2d(out.subarray(b * per, (b + 1) * per), K, Hm, Wm);
      const cc = new Float32Array(c.numKeypoints * 2);
      for (let k = 0; k < c.numKeypoints; k++) {
        cc[k * 2] = hm[k * 2] * ratio;
        cc[k * 2 + 1] = hm[k * 2 + 1] * ratio;
      }
      results.push(cc);
    }
  }
  return results;
}

// assign_hand_side — operates on the lighter PalmBox shape using the same
// midline logic as stage1.ts assignHandSide.
export function assignHandSide(
  boxes: PalmBox[],
  bodyKpts: Float32Array,
  bodyVis: Float32Array,
): string[] {
  if (boxes.length === 0) return [];
  let sumX = 0;
  let nVis = 0;
  for (let i = 0; i < NUM_KEYPOINTS; i++) {
    if (bodyVis[i] > 0.5) {
      sumX += bodyKpts[i * 2];
      nVis++;
    }
  }
  const midline = nVis > 0 ? sumX / nVis : null;
  if (boxes.length === 1) {
    const [bx1, , bx2] = boxes[0].xyxy;
    const cx = (bx1 + bx2) * 0.5;
    return [midline === null || cx < midline ? 'right' : 'left'];
  }
  const order = boxes.map((b, i) => ({ i, cx: (b.xyxy[0] + b.xyxy[2]) * 0.5 }));
  order.sort((a, b) => a.cx - b.cx);
  const sideForPos = ['right', 'left'];
  const posForOrig = new Map<number, string>();
  for (let p = 0; p < Math.min(2, order.length); p++) {
    posForOrig.set(order[p].i, sideForPos[p]);
  }
  return boxes.map((_, i) => posForOrig.get(i) as string);
}
