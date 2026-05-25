// Pure geometry + image-glue ports of the Python Stage-1 pipeline.
//
// Every function here mirrors a specific Python source so the TS pipeline
// reproduces the offline extractor numerically. Cross-references:
//   letterbox            -> extract_keypoints.letterbox
//   softArgmax2d         -> detector.soft_argmax_2d
//   decodeBox            -> anchors.decode_box
//   decodeKpts           -> anchors.decode_kpts
//   nms / iouOneVsMany   -> anchors.nms / _iou_one_vs_many
//   uprightRotationDeg   -> extract_keypoints.upright_rotation_deg
//   cropHandAffine       -> hand_crops.crop_hand (the M matrix only)
//   warpAffineBilinear   -> cv2.warpAffine(flags=INTER_LINEAR, BORDER_CONSTANT=0)
//   invertAffine         -> cv2.invertAffineTransform
//   projectKpts          -> hand_crops.project_kpts
//   unprojectKpts        -> hand_crops.unproject_kpts
//   resizeArea           -> cv2.resize(interpolation=INTER_AREA)
//   expandBox            -> extract_keypoints._expand_box
//
// All angles are degrees unless suffixed Rad. Image coords are (x right, y
// down). A 2x3 affine M maps image px -> crop px as crop = M @ [x, y, 1].

export type Affine = Float64Array; // length 6, row-major [a, b, tx, c, d, ty]

export interface RGBImage {
  data: Uint8ClampedArray | Uint8Array; // HWC, 3 channels, row-major
  width: number;
  height: number;
}

export interface LetterboxResult {
  data: Uint8Array; // size*size*3, HWC RGB
  scale: number;
  dx: number;
  dy: number;
  size: number;
}

const clampInt = (v: number, lo: number, hi: number): number =>
  v < lo ? lo : v > hi ? hi : v;

// ---------------------------------------------------------------------------
// cv2.resize(INTER_AREA) — area-averaging resampler.
//
// INTER_AREA on downscale is equivalent to averaging the source pixels that
// fall under each destination pixel, weighting by fractional overlap. This
// matches OpenCV's implementation for the downsampling case (the only case the
// letterbox uses: scale = size / max(h, w) <= 1 for frames bigger than the net
// input). For the rare upscale case OpenCV falls back to bilinear; we mirror
// that by delegating to the bilinear sampler.
// ---------------------------------------------------------------------------
export function resizeArea(
  src: Uint8ClampedArray | Uint8Array,
  srcW: number,
  srcH: number,
  dstW: number,
  dstH: number,
  channels = 3,
): Uint8Array {
  const out = new Uint8Array(dstW * dstH * channels);
  const scaleX = srcW / dstW;
  const scaleY = srcH / dstH;
  if (scaleX < 1 || scaleY < 1) {
    // Upscale: OpenCV INTER_AREA degrades to bilinear.
    return resizeBilinear(src, srcW, srcH, dstW, dstH, channels);
  }
  for (let dy = 0; dy < dstH; dy++) {
    const fy0 = dy * scaleY;
    const fy1 = (dy + 1) * scaleY;
    const y0 = Math.floor(fy0);
    const y1 = Math.min(srcH, Math.ceil(fy1));
    for (let dx = 0; dx < dstW; dx++) {
      const fx0 = dx * scaleX;
      const fx1 = (dx + 1) * scaleX;
      const x0 = Math.floor(fx0);
      const x1 = Math.min(srcW, Math.ceil(fx1));
      for (let c = 0; c < channels; c++) {
        let acc = 0;
        let wsum = 0;
        for (let sy = y0; sy < y1; sy++) {
          const wy = Math.min(fy1, sy + 1) - Math.max(fy0, sy);
          if (wy <= 0) continue;
          const rowBase = (sy * srcW) * channels;
          for (let sx = x0; sx < x1; sx++) {
            const wx = Math.min(fx1, sx + 1) - Math.max(fx0, sx);
            if (wx <= 0) continue;
            const w = wx * wy;
            acc += src[rowBase + sx * channels + c] * w;
            wsum += w;
          }
        }
        const v = wsum > 0 ? acc / wsum : 0;
        out[(dy * dstW + dx) * channels + c] = clampInt(Math.round(v), 0, 255);
      }
    }
  }
  return out;
}

export function resizeBilinear(
  src: Uint8ClampedArray | Uint8Array,
  srcW: number,
  srcH: number,
  dstW: number,
  dstH: number,
  channels = 3,
): Uint8Array {
  const out = new Uint8Array(dstW * dstH * channels);
  // OpenCV bilinear maps dst -> src center at (dx + 0.5) * scale - 0.5.
  const scaleX = srcW / dstW;
  const scaleY = srcH / dstH;
  for (let dy = 0; dy < dstH; dy++) {
    let sy = (dy + 0.5) * scaleY - 0.5;
    if (sy < 0) sy = 0;
    const y0 = Math.floor(sy);
    const y1 = Math.min(y0 + 1, srcH - 1);
    const wy = sy - y0;
    for (let dx = 0; dx < dstW; dx++) {
      let sx = (dx + 0.5) * scaleX - 0.5;
      if (sx < 0) sx = 0;
      const x0 = Math.floor(sx);
      const x1 = Math.min(x0 + 1, srcW - 1);
      const wx = sx - x0;
      for (let c = 0; c < channels; c++) {
        const p00 = src[(y0 * srcW + x0) * channels + c];
        const p01 = src[(y0 * srcW + x1) * channels + c];
        const p10 = src[(y1 * srcW + x0) * channels + c];
        const p11 = src[(y1 * srcW + x1) * channels + c];
        const top = p00 * (1 - wx) + p01 * wx;
        const bot = p10 * (1 - wx) + p11 * wx;
        out[(dy * dstW + dx) * channels + c] = clampInt(
          Math.round(top * (1 - wy) + bot * wy),
          0,
          255,
        );
      }
    }
  }
  return out;
}

// extract_keypoints.letterbox: scale by size/max(h,w), INTER_AREA resize,
// center-pad into a size x size zero canvas. dx/dy are the top-left offsets.
export function letterbox(img: RGBImage, size: number): LetterboxResult {
  const { width: w, height: h } = img;
  const scale = size / Math.max(h, w);
  const nh = Math.round(h * scale);
  const nw = Math.round(w * scale);
  const resized = resizeArea(img.data, w, h, nw, nh, 3);
  const out = new Uint8Array(size * size * 3); // zeros
  const dy = Math.floor((size - nh) / 2);
  const dx = Math.floor((size - nw) / 2);
  for (let y = 0; y < nh; y++) {
    const dstRow = ((dy + y) * size + dx) * 3;
    const srcRow = y * nw * 3;
    out.set(resized.subarray(srcRow, srcRow + nw * 3), dstRow);
  }
  return { data: out, scale, dx, dy, size };
}

// detector.soft_argmax_2d: sharpen (x10) softmax-weighted spatial expectation.
// heatmaps flat as (K, H*W); returns (K, 2) [x, y] in heatmap-pixel coords.
export function softArgmax2d(
  heatmaps: Float32Array,
  K: number,
  H: number,
  W: number,
): Float32Array {
  const out = new Float32Array(K * 2);
  const hw = H * W;
  for (let k = 0; k < K; k++) {
    const base = k * hw;
    // subtract max for numerical stability (matches torch: flat - flat.max)
    let mx = -Infinity;
    for (let i = 0; i < hw; i++) {
      const v = heatmaps[base + i];
      if (v > mx) mx = v;
    }
    // softmax with temperature 10
    let denom = 0;
    // accumulate weighted coords in a second pass to avoid storing probs
    let xAcc = 0;
    let yAcc = 0;
    const exps = new Float64Array(hw);
    for (let i = 0; i < hw; i++) {
      const e = Math.exp((heatmaps[base + i] - mx) * 10.0);
      exps[i] = e;
      denom += e;
    }
    const inv = denom > 0 ? 1 / denom : 0;
    for (let y = 0; y < H; y++) {
      const rb = y * W;
      for (let x = 0; x < W; x++) {
        const p = exps[rb + x] * inv;
        xAcc += p * x;
        yAcc += p * y;
      }
    }
    out[k * 2] = xAcc;
    out[k * 2 + 1] = yAcc;
  }
  return out;
}

// anchors.decode_box: deltas (M,4) + anchors xywh (M,4) -> boxes xywh (M,4).
//   cx = dx*aw + acx; cy = dy*ah + acy; w = exp(dw)*aw; h = exp(dh)*ah.
export function decodeBox(
  deltas: Float32Array,
  anchorsXywh: Float32Array,
  m: number,
): Float32Array {
  const out = new Float32Array(m * 4);
  for (let i = 0; i < m; i++) {
    const di = i * 4;
    const acx = anchorsXywh[di];
    const acy = anchorsXywh[di + 1];
    const aw = anchorsXywh[di + 2];
    const ah = anchorsXywh[di + 3];
    out[di] = deltas[di] * aw + acx;
    out[di + 1] = deltas[di + 1] * ah + acy;
    out[di + 2] = Math.exp(deltas[di + 2]) * aw;
    out[di + 3] = Math.exp(deltas[di + 3]) * ah;
  }
  return out;
}

// xywh (cx,cy,w,h) -> xyxy (x1,y1,x2,y2), matching run_net2's stack.
export function xywhToXyxy(boxes: Float32Array, m: number): Float32Array {
  const out = new Float32Array(m * 4);
  for (let i = 0; i < m; i++) {
    const b = i * 4;
    const cx = boxes[b];
    const cy = boxes[b + 1];
    const w = boxes[b + 2];
    const h = boxes[b + 3];
    out[b] = cx - w * 0.5;
    out[b + 1] = cy - h * 0.5;
    out[b + 2] = cx + w * 0.5;
    out[b + 3] = cy + h * 0.5;
  }
  return out;
}

// anchors.decode_kpts: flat offsets [k0x,k0y,k1x,...] (M, K*2) + anchors xywh
// (M,4) -> (M, K, 2) in input px. kx = ox*aw + acx; ky = oy*ah + acy.
export function decodeKpts(
  offsets: Float32Array,
  anchorsXywh: Float32Array,
  m: number,
  kpts: number,
): Float32Array {
  const out = new Float32Array(m * kpts * 2);
  for (let i = 0; i < m; i++) {
    const acx = anchorsXywh[i * 4];
    const acy = anchorsXywh[i * 4 + 1];
    const aw = anchorsXywh[i * 4 + 2];
    const ah = anchorsXywh[i * 4 + 3];
    for (let k = 0; k < kpts; k++) {
      const oi = (i * kpts + k) * 2;
      out[oi] = offsets[oi] * aw + acx;
      out[oi + 1] = offsets[oi + 1] * ah + acy;
    }
  }
  return out;
}

function iouOneVsMany(
  boxes: Float32Array,
  i: number,
  rest: number[],
): Float64Array {
  const bx1 = boxes[i * 4];
  const by1 = boxes[i * 4 + 1];
  const bx2 = boxes[i * 4 + 2];
  const by2 = boxes[i * 4 + 3];
  const areaBox = (bx2 - bx1) * (by2 - by1);
  const out = new Float64Array(rest.length);
  for (let r = 0; r < rest.length; r++) {
    const j = rest[r];
    const ox1 = boxes[j * 4];
    const oy1 = boxes[j * 4 + 1];
    const ox2 = boxes[j * 4 + 2];
    const oy2 = boxes[j * 4 + 3];
    const iw = Math.max(0, Math.min(bx2, ox2) - Math.max(bx1, ox1));
    const ih = Math.max(0, Math.min(by2, oy2) - Math.max(by1, oy1));
    const inter = iw * ih;
    const areaOther = (ox2 - ox1) * (oy2 - oy1);
    const union = Math.max(areaBox + areaOther - inter, 1e-9);
    out[r] = inter / union;
  }
  return out;
}

// anchors.nms: greedy NMS, returns kept indices sorted by score desc.
export function nms(
  boxesXyxy: Float32Array,
  scores: Float32Array,
  m: number,
  iouThreshold = 0.3,
  topK = 100,
): number[] {
  if (m === 0) return [];
  // order = scores.argsort(descending)[:topK]
  const order: number[] = [];
  for (let i = 0; i < m; i++) order.push(i);
  // Stable descending sort by score, mirroring torch argsort(descending=True).
  order.sort((a, b) => (scores[b] - scores[a]) || (a - b));
  let work = order.slice(0, topK);
  const keep: number[] = [];
  while (work.length > 0) {
    const i = work[0];
    keep.push(i);
    if (work.length === 1) break;
    const rest = work.slice(1);
    const ious = iouOneVsMany(boxesXyxy, i, rest);
    const next: number[] = [];
    for (let r = 0; r < rest.length; r++) {
      if (ious[r] < iouThreshold) next.push(rest[r]);
    }
    work = next;
  }
  return keep;
}

// extract_keypoints.upright_rotation_deg: rotation (deg, CCW) pointing the
// wrist->mcp vector "up" (crop angle -90) in the (x-right, y-down) frame.
export function uprightRotationDeg(
  wrist: readonly [number, number],
  mcp: readonly [number, number],
): number {
  const dx = mcp[0] - wrist[0];
  const dy = mcp[1] - wrist[1];
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return 0.0;
  const a = (Math.atan2(dy, dx) * 180) / Math.PI;
  return -90.0 - a;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

// hand_crops.crop_hand: build the 2x3 affine M mapping image px -> crop px.
//   scale = out_size / max(w, h)
//   cos_a = cos(rad)*scale; sin_a = sin(rad)*scale
//   M = [[cos_a, -sin_a, out/2 - cos_a*cx + sin_a*cy],
//        [sin_a,  cos_a, out/2 - sin_a*cx - cos_a*cy]]
export function cropHandAffine(
  box: Box,
  outSize: number,
  rotationDeg: number,
): Affine {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  const scale = outSize / Math.max(box.w, box.h);
  const rad = (rotationDeg * Math.PI) / 180;
  const cosA = Math.cos(rad) * scale;
  const sinA = Math.sin(rad) * scale;
  const m = new Float64Array(6);
  m[0] = cosA;
  m[1] = -sinA;
  m[2] = outSize / 2 - cosA * cx + sinA * cy;
  m[3] = sinA;
  m[4] = cosA;
  m[5] = outSize / 2 - sinA * cx - cosA * cy;
  return m;
}

// cv2.invertAffineTransform of a 2x3 matrix.
export function invertAffine(m: Affine): Affine {
  const a = m[0];
  const b = m[1];
  const tx = m[2];
  const c = m[3];
  const d = m[4];
  const ty = m[5];
  const det = a * d - b * c;
  const idet = det !== 0 ? 1 / det : 0;
  const ia = d * idet;
  const ib = -b * idet;
  const ic = -c * idet;
  const id = a * idet;
  const inv = new Float64Array(6);
  inv[0] = ia;
  inv[1] = ib;
  inv[2] = -(ia * tx + ib * ty);
  inv[3] = ic;
  inv[4] = id;
  inv[5] = -(ic * tx + id * ty);
  return inv;
}

// hand_crops.project_kpts: apply 2x3 affine to (N,2) points.
export function projectKpts(kpts: Float32Array, m: Affine, n: number): Float32Array {
  const out = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) {
    const x = kpts[i * 2];
    const y = kpts[i * 2 + 1];
    out[i * 2] = m[0] * x + m[1] * y + m[2];
    out[i * 2 + 1] = m[3] * x + m[4] * y + m[5];
  }
  return out;
}

// hand_crops.unproject_kpts: invert M, then project crop px -> image px.
export function unprojectKpts(cropKpts: Float32Array, m: Affine, n: number): Float32Array {
  return projectKpts(cropKpts, invertAffine(m), n);
}

// cv2.warpAffine(M, (out,out), INTER_LINEAR, BORDER_CONSTANT=0).
// OpenCV applies the FORWARD matrix M (image->dst) by inverting it internally
// and sampling source at M_inv @ dst. We replicate that: for each dst pixel,
// map back through invertAffine(M) and bilinearly sample, 0 outside bounds.
export function warpAffineBilinear(
  src: RGBImage,
  m: Affine,
  outSize: number,
  channels = 3,
): Uint8Array {
  const inv = invertAffine(m);
  const out = new Uint8Array(outSize * outSize * channels);
  const { data, width: sw, height: sh } = src;
  for (let dy = 0; dy < outSize; dy++) {
    for (let dx = 0; dx < outSize; dx++) {
      const sx = inv[0] * dx + inv[1] * dy + inv[2];
      const sy = inv[3] * dx + inv[4] * dy + inv[5];
      const di = (dy * outSize + dx) * channels;
      // OpenCV: pixels whose sample center is fully outside get borderValue 0.
      if (sx < -1 || sx > sw || sy < -1 || sy > sh) continue;
      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const wx = sx - x0;
      const wy = sy - y0;
      const x1 = x0 + 1;
      const y1 = y0 + 1;
      for (let c = 0; c < channels; c++) {
        const p00 = sampleClampedZero(data, sw, sh, x0, y0, c, channels);
        const p01 = sampleClampedZero(data, sw, sh, x1, y0, c, channels);
        const p10 = sampleClampedZero(data, sw, sh, x0, y1, c, channels);
        const p11 = sampleClampedZero(data, sw, sh, x1, y1, c, channels);
        const top = p00 * (1 - wx) + p01 * wx;
        const bot = p10 * (1 - wx) + p11 * wx;
        out[di + c] = clampInt(Math.round(top * (1 - wy) + bot * wy), 0, 255);
      }
    }
  }
  return out;
}

function sampleClampedZero(
  data: Uint8ClampedArray | Uint8Array,
  w: number,
  h: number,
  x: number,
  y: number,
  c: number,
  channels: number,
): number {
  if (x < 0 || x >= w || y < 0 || y >= h) return 0;
  return data[(y * w + x) * channels + c];
}

// extract_keypoints._expand_box: pad by frac each side, clamp to frame.
// Returns null when the source box is tiny (<4px either side).
export function expandBox(
  bbox: readonly [number, number, number, number],
  W: number,
  H: number,
  frac = 0.05,
): [number, number, number, number] | null {
  let [x1, y1, x2, y2] = bbox;
  if (x2 - x1 < 4 || y2 - y1 < 4) return null;
  const bw = x2 - x1;
  const bh = y2 - y1;
  x1 = Math.max(0, x1 - frac * bw);
  x2 = Math.min(W - 1, x2 + frac * bw);
  y1 = Math.max(0, y1 - frac * bh);
  y2 = Math.min(H - 1, y2 + frac * bh);
  return [x1, y1, x2, y2];
}

// sigmoid for Net2 cls logits.
export function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}
