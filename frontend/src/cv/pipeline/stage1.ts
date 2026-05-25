// Stage-1 keypoint cascade in TypeScript — numerical port of the Python
// offline extractor (src/stage2/data/extract_keypoints.py + src/stage1/*).
//
// Per frame: Net1 (face/body heatmaps) -> Net2 (palm detect + NMS) ->
// Net3 (2-pass oriented hand landmarks) -> 49-kpt global vector + visibility.
//
// The ORT sessions are injected (workstream D). This module owns the pure
// pre/post-processing math (in geom.ts) and the control flow; the only ONNX
// calls are the three forwards. Until D lands, pass a Stage1Sessions object
// whose run* fns satisfy the contract in models.ts (see makeStubSessions).

import {
  type Affine,
  type Box,
  type RGBImage,
  cropHandAffine,
  decodeBox,
  decodeKpts,
  expandBox,
  letterbox,
  nms,
  projectKpts,
  sigmoid,
  softArgmax2d,
  unprojectKpts,
  uprightRotationDeg,
  warpAffineBilinear,
  xywhToXyxy,
} from './geom';
import { generateAnchorsLegacy, generateAnchorsMultiStride } from './anchors';
import {
  DEFAULT_STAGE1_CONTRACT,
  LEFT_HAND_START,
  NUM_KEYPOINTS,
  RIGHT_HAND_START,
  type Net1Contract,
  type Net2Contract,
  type Net3Contract,
  type Stage1Contract,
} from '../ort/models';

// Schema constants live in the contract (mirror src/stage1/data/schema.py);
// re-exported here for callers that import them off the pipeline.
export { NUM_KEYPOINTS, RIGHT_HAND_START, LEFT_HAND_START };

// A tensor result from an ORT session: a flat Float32Array + its dims.
export interface OrtTensor {
  data: Float32Array;
  dims: number[];
}

// The three model forwards. Each takes a CHW-normalized float input
// (Float32Array of length 3*size*size) and returns named output tensors.
export interface Stage1Sessions {
  net1(input: Float32Array, size: number): Promise<{ heatmaps: OrtTensor }>;
  net2(
    input: Float32Array,
    size: number,
  ): Promise<{ cls: OrtTensor; box: OrtTensor; kpt?: OrtTensor }>;
  net3(
    input: Float32Array,
    size: number,
  ): Promise<{ coords?: OrtTensor; heatmaps?: OrtTensor }>;
}

// Per-frame Stage-1 output — matches extract_one_clip's per-frame slice.
export interface Stage1FrameResult {
  keypoints: Float32Array; // (49*2) interleaved [x0,y0,x1,y1,...], image px
  visibility: Float32Array; // (49) 1=present 0=missing
  handsPresent: number; // count of palm boxes that produced hand kpts
}

// Detected palm box (Net2 output): score, xyxy in frame px, optional kpts.
interface PalmBox {
  score: number;
  xyxy: [number, number, number, number];
  kpts: Float32Array | null; // (nKpts*2) wrist + middle-MCP, frame px
}

// ---------------------------------------------------------------------------
// Image normalization: (px/255 - 0.5)/0.5, HWC RGB uint8 -> CHW float32.
// Matches every Python forward: tensor = (boxed/255 - 0.5)/0.5, permute(2,0,1).
// ---------------------------------------------------------------------------
function toCHWNormalized(
  hwc: Uint8Array | Uint8ClampedArray,
  size: number,
): Float32Array {
  const out = new Float32Array(3 * size * size);
  const plane = size * size;
  for (let i = 0; i < plane; i++) {
    const base = i * 3;
    out[i] = (hwc[base] / 255 - 0.5) / 0.5;
    out[plane + i] = (hwc[base + 1] / 255 - 0.5) / 0.5;
    out[2 * plane + i] = (hwc[base + 2] / 255 - 0.5) / 0.5;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Anchor cache — generated once from the contract (mirrors get_anchors cache).
// ---------------------------------------------------------------------------
function buildAnchors(c: Net2Contract): Float32Array {
  const a = c.anchors;
  if (a.multiStride) {
    return generateAnchorsMultiStride(
      a.inputSize,
      a.scalesPerStride ?? [],
      a.strides ?? [],
      a.square ?? false,
    );
  }
  // Legacy uniform-scale layout (back-compat; the canonical v3 net2 is
  // multi-stride). Falls back to the documented 192-input defaults.
  return generateAnchorsLegacy(a.inputSize, [24, 12, 6], [0.1, 0.2, 0.35]);
}

// ---------------------------------------------------------------------------
// Net1: face/body heatmaps -> soft-argmax -> remap to frame px -> 49 schema.
// Port of run_net1.
// ---------------------------------------------------------------------------
async function runNet1(
  sessions: Stage1Sessions,
  c: Net1Contract,
  rgb: RGBImage,
  out: { kpts: Float32Array; vis: Float32Array },
): Promise<void> {
  const W = rgb.width;
  const H = rgb.height;
  const lb = letterbox(rgb, c.inputSize);
  const input = toCHWNormalized(lb.data, c.inputSize);
  const { heatmaps } = await sessions.net1(input, c.inputSize);
  const [, K, Hm, Wm] = heatmaps.dims;
  const coordsHm = softArgmax2d(heatmaps.data, K, Hm, Wm);
  // peak = max over each heatmap channel.
  const hw = Hm * Wm;
  const peak = new Float32Array(K);
  for (let k = 0; k < K; k++) {
    let mx = -Infinity;
    const base = k * hw;
    for (let i = 0; i < hw; i++) {
      const v = heatmaps.data[base + i];
      if (v > mx) mx = v;
    }
    peak[k] = mx;
  }
  // coords = coordsHm * (inputSize/hmSize); then undo letterbox.
  const ratio = c.inputSize / Wm; // Hm == Wm in the detector
  const coords = new Float32Array(K * 2);
  for (let k = 0; k < K; k++) {
    const x = coordsHm[k * 2] * ratio;
    const y = coordsHm[k * 2 + 1] * ratio;
    coords[k * 2] = (x - lb.dx) / lb.scale;
    coords[k * 2 + 1] = (y - lb.dy) / lb.scale;
  }

  const slice = c.keypointSlice;
  if (slice && slice.length === 2) {
    const [sIdx, eIdx] = slice;
    const Kn = Math.min(K, eIdx - sIdx);
    for (let j = 0; j < Kn; j++) {
      const x = coords[j * 2];
      const y = coords[j * 2 + 1];
      if (x >= 0 && x < W && y >= 0 && y < H && peak[j] > c.peakThreshold) {
        out.kpts[(sIdx + j) * 2] = x;
        out.kpts[(sIdx + j) * 2 + 1] = y;
        out.vis[sIdx + j] = 1.0;
      }
    }
  } else {
    const Kn = Math.min(K, NUM_KEYPOINTS);
    for (let j = 0; j < Kn; j++) {
      const x = coords[j * 2];
      const y = coords[j * 2 + 1];
      if (x >= 0 && x < W && y >= 0 && y < H && peak[j] > c.peakThreshold) {
        out.kpts[j * 2] = x;
        out.kpts[j * 2 + 1] = y;
        out.vis[j] = 1.0;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Net2: palm detect. Port of run_net2 + decode_box + decode_kpts + nms.
// ---------------------------------------------------------------------------
async function runNet2(
  sessions: Stage1Sessions,
  c: Net2Contract,
  anchors: Float32Array,
  rgb: RGBImage,
): Promise<PalmBox[]> {
  const lb = letterbox(rgb, c.inputSize);
  const input = toCHWNormalized(lb.data, c.inputSize);
  const preds = await sessions.net2(input, c.inputSize);
  const N = preds.cls.dims[1];

  // cls = sigmoid(cls).squeeze; keep = cls >= conf.
  const keepIdx: number[] = [];
  for (let i = 0; i < N; i++) {
    if (sigmoid(preds.cls.data[i]) >= c.conf) keepIdx.push(i);
  }
  if (keepIdx.length === 0) return [];

  const m = keepIdx.length;
  const scores = new Float32Array(m);
  const deltas = new Float32Array(m * 4);
  const anchorsKept = new Float32Array(m * 4);
  for (let r = 0; r < m; r++) {
    const i = keepIdx[r];
    scores[r] = sigmoid(preds.cls.data[i]);
    deltas[r * 4] = preds.box.data[i * 4];
    deltas[r * 4 + 1] = preds.box.data[i * 4 + 1];
    deltas[r * 4 + 2] = preds.box.data[i * 4 + 2];
    deltas[r * 4 + 3] = preds.box.data[i * 4 + 3];
    anchorsKept[r * 4] = anchors[i * 4];
    anchorsKept[r * 4 + 1] = anchors[i * 4 + 1];
    anchorsKept[r * 4 + 2] = anchors[i * 4 + 2];
    anchorsKept[r * 4 + 3] = anchors[i * 4 + 3];
  }

  const dec = decodeBox(deltas, anchorsKept, m);
  const xyxy = xywhToXyxy(dec, m);

  // Decode keypoints for kept anchors, mapped to frame px.
  let kptsFrame: Float32Array | null = null;
  if (preds.kpt && c.nKpts > 0) {
    const off = new Float32Array(m * c.nKpts * 2);
    for (let r = 0; r < m; r++) {
      const i = keepIdx[r];
      for (let kk = 0; kk < c.nKpts * 2; kk++) {
        off[r * c.nKpts * 2 + kk] = preds.kpt.data[i * c.nKpts * 2 + kk];
      }
    }
    const pts = decodeKpts(off, anchorsKept, m, c.nKpts); // (m, nKpts, 2) input px
    for (let r = 0; r < m * c.nKpts; r++) {
      pts[r * 2] = (pts[r * 2] - lb.dx) / lb.scale;
      pts[r * 2 + 1] = (pts[r * 2 + 1] - lb.dy) / lb.scale;
    }
    kptsFrame = pts;
  }

  const nmsIdx = nms(xyxy, scores, m, c.iouThreshold, c.maxBoxes);
  const out: PalmBox[] = [];
  for (const ki of nmsIdx) {
    const x1 = (xyxy[ki * 4] - lb.dx) / lb.scale;
    const y1 = (xyxy[ki * 4 + 1] - lb.dy) / lb.scale;
    const x2 = (xyxy[ki * 4 + 2] - lb.dx) / lb.scale;
    const y2 = (xyxy[ki * 4 + 3] - lb.dy) / lb.scale;
    let boxKpts: Float32Array | null = null;
    if (kptsFrame) {
      boxKpts = new Float32Array(c.nKpts * 2);
      for (let kk = 0; kk < c.nKpts * 2; kk++) {
        boxKpts[kk] = kptsFrame[ki * c.nKpts * 2 + kk];
      }
    }
    out.push({ score: scores[ki], xyxy: [x1, y1, x2, y2], kpts: boxKpts });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Net3 one pass: crop+forward -> (21,2) crop px + the affine M.
// Port of _net3_one_pass.
// ---------------------------------------------------------------------------
async function net3OnePass(
  sessions: Stage1Sessions,
  c: Net3Contract,
  rgb: RGBImage,
  box: Box,
  rotationDeg: number,
): Promise<{ coordsCrop: Float32Array; M: Affine }> {
  const M = cropHandAffine(box, c.cropSize, rotationDeg);
  const crop = warpAffineBilinear(rgb, M, c.cropSize);
  const input = toCHWNormalized(crop, c.cropSize);
  const out = await sessions.net3(input, c.cropSize);
  const coordsCrop = new Float32Array(c.numKeypoints * 2);
  if (c.headType === 'regression') {
    if (!out.coords) throw new Error('Net3 regression head returned no coords');
    // coords (1, 21, 3); take [:, :2] normalized [0,1] -> * cropSize.
    for (let k = 0; k < c.numKeypoints; k++) {
      coordsCrop[k * 2] = out.coords.data[k * 3] * c.cropSize;
      coordsCrop[k * 2 + 1] = out.coords.data[k * 3 + 1] * c.cropSize;
    }
  } else {
    if (!out.heatmaps) throw new Error('Net3 heatmap head returned no heatmaps');
    const [, K, Hm, Wm] = out.heatmaps.dims;
    const hm = softArgmax2d(out.heatmaps.data, K, Hm, Wm);
    const ratio = c.cropSize / Wm;
    for (let k = 0; k < c.numKeypoints; k++) {
      coordsCrop[k * 2] = hm[k * 2] * ratio;
      coordsCrop[k * 2 + 1] = hm[k * 2 + 1] * ratio;
    }
  }
  return { coordsCrop, M };
}

// ---------------------------------------------------------------------------
// Net3: oriented 2-pass hand landmarks -> 21 kpts in frame px. Port of run_net3.
// ---------------------------------------------------------------------------
async function runNet3(
  sessions: Stage1Sessions,
  c: Net3Contract,
  rgb: RGBImage,
  bboxXyxy: [number, number, number, number],
  net2Kpts: Float32Array | null,
  twoPassFallback = true,
): Promise<Float32Array | null> {
  const W = rgb.width;
  const H = rgb.height;
  const expanded = expandBox(bboxXyxy, W, H);
  if (!expanded) return null;
  const [x1, y1, x2, y2] = expanded;
  const box: Box = { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };

  // (a) Net2 supplied wrist + middle-MCP: rotate once, unproject.
  if (net2Kpts && net2Kpts.length >= 4) {
    const rot = uprightRotationDeg(
      [net2Kpts[0], net2Kpts[1]],
      [net2Kpts[2], net2Kpts[3]],
    );
    const { coordsCrop, M } = await net3OnePass(sessions, c, rgb, box, rot);
    return unprojectKpts(coordsCrop, M, c.numKeypoints);
  }

  // Pass 1: axis-aligned.
  const pass1 = await net3OnePass(sessions, c, rgb, box, 0.0);
  if (!twoPassFallback) {
    return unprojectKpts(pass1.coordsCrop, pass1.M, c.numKeypoints);
  }

  // Pass 2: re-crop oriented using Net3's own wrist(0) + middle-MCP(9).
  const wristCrop: [number, number] = [pass1.coordsCrop[0], pass1.coordsCrop[1]];
  const mcpCrop: [number, number] = [
    pass1.coordsCrop[9 * 2],
    pass1.coordsCrop[9 * 2 + 1],
  ];
  const rot = uprightRotationDeg(wristCrop, mcpCrop);
  const pass2 = await net3OnePass(sessions, c, rgb, box, rot);
  return unprojectKpts(pass2.coordsCrop, pass2.M, c.numKeypoints);
}

// ---------------------------------------------------------------------------
// assign_hand_side: 'right'/'left' per palm box (signer POV). Port of
// assign_hand_side. body kpts/vis are the Net1 49-vectors.
// ---------------------------------------------------------------------------
export function assignHandSide(
  boxes: PalmBox[],
  bodyKpts: Float32Array,
  bodyVis: Float32Array,
): string[] {
  if (boxes.length === 0) return [];
  // midline = mean x of visible Net1 kpts, else null.
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
  // sort by box center-x ascending; first -> right, second -> left.
  const order = boxes.map((b, i) => ({ i, cx: (b.xyxy[0] + b.xyxy[2]) * 0.5 }));
  order.sort((a, b) => a.cx - b.cx);
  const sideForPos = ['right', 'left'];
  const posForOrig = new Map<number, string>();
  for (let p = 0; p < Math.min(2, order.length); p++) {
    posForOrig.set(order[p].i, sideForPos[p]);
  }
  return boxes.map((_, i) => posForOrig.get(i) as string);
}

// ---------------------------------------------------------------------------
// Public entry: run the full Stage-1 cascade on one RGB frame.
// Returns the 49-kpt frame vector matching extract_one_clip's per-frame output.
// ---------------------------------------------------------------------------
export async function stage1ProcessFrame(
  rgb: RGBImage,
  sessions: Stage1Sessions,
  contract: Stage1Contract = DEFAULT_STAGE1_CONTRACT,
  options: { twoPassFallback?: boolean; anchors?: Float32Array } = {},
): Promise<Stage1FrameResult> {
  const W = rgb.width;
  const H = rgb.height;
  const twoPass = options.twoPassFallback ?? true;

  const kpts = new Float32Array(NUM_KEYPOINTS * 2);
  const vis = new Float32Array(NUM_KEYPOINTS);

  // Net1 face/body, written in-place into kpts/vis.
  await runNet1(sessions, contract.net1, rgb, { kpts, vis });
  // Snapshot the Net1 body kpts/vis for side assignment (run_net2 uses the
  // Net1 result, not the hand-filled vector).
  const bodyKpts = kpts.slice();
  const bodyVis = vis.slice();

  const anchors = options.anchors ?? buildAnchors(contract.net2);
  const boxes = await runNet2(sessions, contract.net2, anchors, rgb);
  const sides = assignHandSide(boxes, bodyKpts, bodyVis);

  let handsPresent = 0;
  for (let bi = 0; bi < boxes.length; bi++) {
    const box = boxes[bi];
    const side = sides[bi];
    const handKpts = await runNet3(
      sessions,
      contract.net3,
      rgb,
      box.xyxy,
      box.kpts,
      twoPass,
    );
    if (!handKpts) continue;
    const slotStart = side === 'right' ? RIGHT_HAND_START : LEFT_HAND_START;
    let wrote = false;
    for (let j = 0; j < 21; j++) {
      const x = handKpts[j * 2];
      const y = handKpts[j * 2 + 1];
      if (x >= 0 && x < W && y >= 0 && y < H) {
        kpts[(slotStart + j) * 2] = x;
        kpts[(slotStart + j) * 2 + 1] = y;
        vis[slotStart + j] = 1.0;
        wrote = true;
      }
    }
    if (wrote) handsPresent++;
  }

  return { keypoints: kpts, visibility: vis, handsPresent };
}

// Re-export the affine/crop helper so callers can build oriented crops if
// needed without reaching into geom.
export { cropHandAffine, projectKpts };
