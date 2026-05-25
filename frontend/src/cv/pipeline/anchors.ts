// SSD anchor generation — TS port of src/stage1/models/anchors.py
// (generate_anchors + multi_stride_anchors). Built once at init from the Net2
// contract and held constant; the per-anchor decode/NMS math lives in geom.ts.
//
// Anchor order MUST match the Python detection-head concat order or box/kpt
// decode is misaligned: grid-major, then cell-major (gy outer, gx inner), then
// scale-major. For multi-stride, strides come smallest-first (P1 -> P2 -> P3).

// anchors.generate_anchors: legacy uniform-scale layout. (N,4) cx,cy,w,h.
export function generateAnchorsLegacy(
  inputSize: number,
  gridSizes: number[],
  scalesFrac: number[],
): Float32Array {
  const rows: number[] = [];
  for (const gridH of gridSizes) {
    const cell = inputSize / gridH;
    for (let gy = 0; gy < gridH; gy++) {
      for (let gx = 0; gx < gridH; gx++) {
        const cx = (gx + 0.5) * cell;
        const cy = (gy + 0.5) * cell;
        for (const s of scalesFrac) {
          const side = s * inputSize;
          rows.push(cx, cy, side, side);
        }
      }
    }
  }
  return new Float32Array(rows);
}

// anchors.multi_stride_anchors: per-stride scale lists. Scales here are scalars
// (the v3 layout uses scalar scales -> square anchors); square=true forces
// w=h=max(w,h), a no-op for scalar scales.
export function generateAnchorsMultiStride(
  inputSize: number,
  scalesPerStride: number[][],
  strides: number[],
  square: boolean,
): Float32Array {
  if (scalesPerStride.length !== strides.length) {
    throw new Error('scalesPerStride and strides must have the same length');
  }
  const rows: number[] = [];
  for (let si = 0; si < strides.length; si++) {
    const stride = strides[si];
    const scales = scalesPerStride[si];
    if (stride <= 0) throw new Error(`strides must be positive (got ${stride})`);
    if (inputSize % stride !== 0) {
      throw new Error(`inputSize ${inputSize} not divisible by stride ${stride}`);
    }
    if (scales.length === 0) throw new Error(`empty scale list at stride ${stride}`);
    const grid = inputSize / stride;
    const cell = stride;
    for (let gy = 0; gy < grid; gy++) {
      for (let gx = 0; gx < grid; gx++) {
        const cx = (gx + 0.5) * cell;
        const cy = (gy + 0.5) * cell;
        for (const s of scales) {
          let w = s * inputSize;
          let h = s * inputSize;
          if (square) {
            w = h = Math.max(w, h);
          }
          rows.push(cx, cy, w, h);
        }
      }
    }
  }
  return new Float32Array(rows);
}
