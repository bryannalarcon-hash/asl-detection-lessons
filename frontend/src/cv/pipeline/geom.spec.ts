import { describe, it, expect } from 'vitest';
import {
  type RGBImage,
  cropHandAffine,
  decodeBox,
  decodeKpts,
  expandBox,
  invertAffine,
  letterbox,
  nms,
  projectKpts,
  resizeArea,
  softArgmax2d,
  unprojectKpts,
  uprightRotationDeg,
  warpAffineBilinear,
  xywhToXyxy,
} from './geom';
import { generateAnchorsLegacy, generateAnchorsMultiStride } from './anchors';

const near = (a: number, b: number, tol = 1e-4) =>
  expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);

describe('letterbox', () => {
  it('scales by size/max(h,w) and centers with correct dx/dy', () => {
    // 40x20 image -> size 10. scale = 10/40 = 0.25. nh=5, nw=2 (round(20*.25)).
    const img: RGBImage = {
      data: new Uint8Array(40 * 20 * 3).fill(200),
      width: 20,
      height: 40,
    };
    const lb = letterbox(img, 10);
    expect(lb.scale).toBe(0.25);
    // nw = round(20*0.25)=5, nh = round(40*0.25)=10. dx=(10-5)/2=2, dy=0.
    expect(lb.dx).toBe(2);
    expect(lb.dy).toBe(0);
    expect(lb.data.length).toBe(10 * 10 * 3);
    // Left/right pad columns are zero; center is the resized content (200).
    // pixel (row 0, col 0) is padding -> 0.
    expect(lb.data[0]).toBe(0);
    // pixel (row 0, col dx=2) is content -> ~200.
    expect(lb.data[(0 * 10 + 2) * 3]).toBe(200);
  });
});

describe('resizeArea', () => {
  it('averages a 2x2 block down to 1 pixel', () => {
    // single channel-like via 3 identical channels.
    const src = new Uint8Array([
      10, 10, 10, 20, 20, 20,
      30, 30, 30, 40, 40, 40,
    ]); // 2x2 RGB
    const out = resizeArea(src, 2, 2, 1, 1, 3);
    // mean(10,20,30,40)=25
    expect(out[0]).toBe(25);
    expect(out[1]).toBe(25);
    expect(out[2]).toBe(25);
  });
});

describe('softArgmax2d', () => {
  it('peaks at the hot cell with temperature-10 sharpening', () => {
    // 1 channel, 3x3, single hot pixel at (x=2, y=1). With temp 10 the softmax
    // is effectively a hard argmax, so the expectation lands on the hot cell.
    const hm = new Float32Array(9);
    hm[1 * 3 + 2] = 5.0; // y=1, x=2
    const out = softArgmax2d(hm, 1, 3, 3);
    near(out[0], 2.0, 1e-3); // x
    near(out[1], 1.0, 1e-3); // y
  });

  it('centers on a symmetric two-peak ridge', () => {
    // Two equal peaks at x=0 and x=2 (y=1) -> expectation x≈1, y≈1.
    const hm = new Float32Array(9);
    hm[1 * 3 + 0] = 3.0;
    hm[1 * 3 + 2] = 3.0;
    const out = softArgmax2d(hm, 1, 3, 3);
    near(out[0], 1.0, 1e-3);
    near(out[1], 1.0, 1e-3);
  });
});

describe('decodeBox / xywhToXyxy', () => {
  it('inverts encode_box convention: cx=dx*aw+acx, w=exp(dw)*aw', () => {
    // anchor (cx,cy,w,h)=(50,60,20,20); deltas (0.5,-0.5, ln2, 0).
    const anchors = new Float32Array([50, 60, 20, 20]);
    const deltas = new Float32Array([0.5, -0.5, Math.log(2), 0]);
    const dec = decodeBox(deltas, anchors, 1);
    near(dec[0], 0.5 * 20 + 50); // 60
    near(dec[1], -0.5 * 20 + 60); // 50
    near(dec[2], 2 * 20); // 40
    near(dec[3], 1 * 20); // 20
    const xyxy = xywhToXyxy(dec, 1);
    near(xyxy[0], 60 - 20); // 40
    near(xyxy[1], 50 - 10); // 40
    near(xyxy[2], 60 + 20); // 80
    near(xyxy[3], 50 + 10); // 60
  });
});

describe('decodeKpts', () => {
  it('maps anchor-relative offsets to input px', () => {
    const anchors = new Float32Array([100, 100, 40, 40]);
    // 2 kpts: (0,0) -> anchor center; (0.5,0.5) -> (+20,+20)
    const off = new Float32Array([0, 0, 0.5, 0.5]);
    const pts = decodeKpts(off, anchors, 1, 2);
    near(pts[0], 100);
    near(pts[1], 100);
    near(pts[2], 120);
    near(pts[3], 120);
  });
});

describe('nms', () => {
  it('keeps the highest score and drops a heavy overlap', () => {
    // Box A (score .9) and box B (score .8) overlap heavily; C disjoint.
    const boxes = new Float32Array([
      0, 0, 10, 10, // A
      1, 1, 11, 11, // B (IoU with A ~0.68)
      100, 100, 110, 110, // C
    ]);
    const scores = new Float32Array([0.9, 0.8, 0.7]);
    const keep = nms(boxes, scores, 3, 0.3, 100);
    expect(keep).toEqual([0, 2]); // B suppressed by A; C kept
  });

  it('respects top_k', () => {
    const boxes = new Float32Array([
      0, 0, 1, 1,
      10, 10, 11, 11,
      20, 20, 21, 21,
    ]);
    const scores = new Float32Array([0.5, 0.9, 0.7]);
    const keep = nms(boxes, scores, 3, 0.3, 2);
    expect(keep).toEqual([1, 2]); // top-2 by score, both disjoint
  });

  it('returns empty for zero boxes', () => {
    expect(nms(new Float32Array(0), new Float32Array(0), 0)).toEqual([]);
  });
});

describe('uprightRotationDeg', () => {
  it('rotates a rightward wrist->mcp vector to point up (theta=-90)', () => {
    // mcp to the right of wrist: vector angle a=0 -> theta = -90 - 0 = -90.
    near(uprightRotationDeg([0, 0], [10, 0]), -90.0);
  });
  it('returns 0 when already pointing up (vector angle -90)', () => {
    // mcp above wrist (y smaller): a = atan2(-10,0) = -90 -> theta = -90+90 = 0.
    near(uprightRotationDeg([0, 0], [0, -10]), 0.0);
  });
  it('handles a degenerate zero vector', () => {
    expect(uprightRotationDeg([5, 5], [5, 5])).toBe(0.0);
  });
});

describe('cropHandAffine + invert/project/unproject', () => {
  it('maps the box center to the crop center', () => {
    const box = { x: 10, y: 20, w: 40, h: 40 }; // center (30,40)
    const M = cropHandAffine(box, 224, 0);
    const center = projectKpts(new Float32Array([30, 40]), M, 1);
    near(center[0], 112); // out/2
    near(center[1], 112);
  });

  it('unproject is the inverse of project (round-trip)', () => {
    const box = { x: 10, y: 20, w: 40, h: 60 };
    const M = cropHandAffine(box, 224, 37.5);
    const pts = new Float32Array([15, 22, 48, 70, 30, 50]);
    const crop = projectKpts(pts, M, 3);
    const back = unprojectKpts(crop, M, 3);
    for (let i = 0; i < pts.length; i++) near(back[i], pts[i], 1e-3);
  });

  it('invertAffine composes to identity', () => {
    const M = cropHandAffine({ x: 0, y: 0, w: 20, h: 20 }, 100, 45);
    const inv = invertAffine(M);
    // M(inv(p)) == p for a sample point.
    const p = new Float32Array([33, 77]);
    const a = projectKpts(p, inv, 1);
    const b = projectKpts(a, M, 1);
    near(b[0], 33, 1e-3);
    near(b[1], 77, 1e-3);
  });
});

describe('warpAffineBilinear', () => {
  it('crops a centered axis-aligned region at the right scale', () => {
    // 8x8 image, left half value 100, right half 200. Box covering full image,
    // out 4x4, no rotation. The crop should keep the left/right split.
    const w = 8;
    const h = 8;
    const data = new Uint8Array(w * h * 3);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const v = x < 4 ? 100 : 200;
        const i = (y * w + x) * 3;
        data[i] = v;
        data[i + 1] = v;
        data[i + 2] = v;
      }
    }
    const img: RGBImage = { data, width: w, height: h };
    const M = cropHandAffine({ x: 0, y: 0, w: 8, h: 8 }, 4, 0);
    const crop = warpAffineBilinear(img, M, 4);
    // Left columns sample the 100 region, right columns the 200 region.
    expect(crop[(0 * 4 + 0) * 3]).toBeLessThan(150);
    expect(crop[(0 * 4 + 3) * 3]).toBeGreaterThan(150);
    expect(crop.length).toBe(4 * 4 * 3);
  });
});

describe('expandBox', () => {
  it('pads by frac each side and clamps to frame', () => {
    const out = expandBox([10, 10, 110, 110], 200, 200, 0.05);
    expect(out).not.toBeNull();
    const [x1, y1, x2, y2] = out!;
    near(x1, 10 - 5); // 5
    near(y1, 10 - 5);
    near(x2, 110 + 5); // 115
    near(y2, 110 + 5);
  });
  it('clamps to frame bounds', () => {
    const out = expandBox([2, 2, 198, 198], 200, 200, 0.5);
    const [x1, y1, x2, y2] = out!;
    expect(x1).toBe(0);
    expect(y1).toBe(0);
    expect(x2).toBe(199);
    expect(y2).toBe(199);
  });
  it('returns null for a tiny box', () => {
    expect(expandBox([10, 10, 12, 12], 200, 200)).toBeNull();
  });
});

describe('anchor generators', () => {
  it('legacy: count and ordering (grid->cell->scale major)', () => {
    const a = generateAnchorsLegacy(192, [24, 12, 6], [0.1, 0.2, 0.35]);
    const n = (24 * 24 + 12 * 12 + 6 * 6) * 3;
    expect(a.length).toBe(n * 4);
    // First cell of grid 24: cell=8, cx=cy=4. First scale 0.1*192=19.2.
    near(a[0], 4);
    near(a[1], 4);
    near(a[2], 19.2);
    near(a[3], 19.2);
  });

  it('multi-stride: 2624 anchors for the v3_1 layout', () => {
    const a = generateAnchorsMultiStride(
      256,
      [[0.05, 0.1], [0.2, 0.35], [0.55]],
      [8, 16, 32],
      false,
    );
    const n = 32 * 32 * 2 + 16 * 16 * 2 + 8 * 8 * 1; // 2624
    expect(a.length).toBe(n * 4);
    // Stride 8 first cell: cx=cy=4 (stride/2). First scale 0.05*256=12.8.
    near(a[0], 4);
    near(a[1], 4);
    near(a[2], 12.8);
    near(a[3], 12.8);
  });
});
