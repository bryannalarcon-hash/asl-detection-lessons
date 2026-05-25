// ONNX IO contract — the seam every TS pipeline module (B/C/D) codes against.
//
// CANONICAL (workstream A). The .onnx assets in frontend/public/models/ and the
// parity fixtures in frontend/tests/cv/fixtures/ are produced from these exact
// v3 checkpoints by tools/onnx_export/export_all.py + dump_reference.py:
//   net1  results/v3/net1_v3_1/best_export.pt    KeypointDetector  (K=7 sliced)
//   net2  results/v3/net2_v3_1/best.pt           PalmDetector (FPN, NO kpt head)
//   net3  results/v3/net3/best.pt                HandLandmarkRegNet (regression)
//   net4  results/v3/net4_popsign_baseline40/best.pt  SignClassifier (96 cls)
//
// Only the PURE conv/transformer forwards are in-graph. All glue (letterbox,
// soft-argmax, anchor decode + NMS, crop/rotate/2-pass, 343-dim feature build,
// window pad/subsample, softmax/top-k) lives in TS and is parity-tested against
// the Python reference. The pre/post notes on each net say what TS owns.
//
// Image nets (net1/2/3): NCHW FP32, normalised (rgb/255 - 0.5)/0.5 -> [-1,1],
// applied in TS BEFORE feeding. Net4 features are pre-normalised in TS.
//
// IMPORTANT vs the earlier stub: this Net 2 checkpoint has NO keypoint head
// (n_kpts=0), and its anchors use square=false. Net 3 therefore runs its
// 2-pass self-orient path (no Net-2-supplied wrist/MCP).

export interface TensorSpec {
  name: string;
  // -1 marks a dynamic dim (batch, frames). Informational; the runtime reads
  // actual dims from the ORT tensor.
  shape: number[];
  dtype: 'float32';
}

export interface Net1Contract {
  url: string;
  inputSize: number; // letterbox target side (256)
  input: TensorSpec; // (B, 3, 256, 256), normalized (rgb/255-0.5)/0.5
  heatmaps: TensorSpec; // (B, 7, 64, 64)
  heatmapSize: number; // 64 (output stride 4)
  numKeypoints: number; // K of the sliced detector (face+body) = 7
  // keypointSlice = [start, end) into the 49-kpt global schema. The 7 kpts
  // land in global slots 42..48.
  keypointSlice: [number, number] | null;
  softArgmaxTemp: number; // 10.0 (sharpen before softmax)
  peakThreshold: number; // run_net1 visibility gate (0.05)
}

export interface Net2Contract {
  url: string;
  inputSize: number; // 256
  input: TensorSpec; // (B, 3, 256, 256)
  cls: TensorSpec; // (B, N) objectness LOGITS (apply sigmoid in TS)
  box: TensorSpec; // (B, N, 4) cx,cy,w,h deltas, anchor-relative
  kpt: TensorSpec | null; // null — this ckpt has no kpt head
  nKpts: number; // 0
  anchors: AnchorConfig;
  conf: number; // 0.3
  iouThreshold: number; // 0.3
  maxBoxes: number; // 2
}

export interface AnchorConfig {
  inputSize: number;
  multiStride: boolean;
  scalesPerStride?: number[][]; // [[0.05,0.10],[0.20,0.35],[0.55]]
  strides?: number[]; // [8, 16, 32]
  anchorsPerScale?: number[]; // [2, 2, 1]
  square?: boolean; // false
  nAnchors?: number; // 2624
}

export type Net3Head = 'regression' | 'heatmap';

export interface Net3Contract {
  url: string;
  cropSize: number; // 224
  input: TensorSpec; // (B, 3, 224, 224)
  headType: Net3Head;
  // regression: coords (B, 21, 3), coords[...,:2] in [0,1] crop coords,
  // coords[...,2]=z held at 0 (unused: this ckpt is with_z=false).
  output: TensorSpec;
  numKeypoints: number; // 21
  boxExpandFrac: number; // 0.05
  twoPass: boolean; // true (no Net-2 kpts -> self-orient 2-pass)
}

export interface Net4Contract {
  url: string;
  inChannels: number; // 343
  numClasses: number; // 96
  maxFrames: number; // 64
  features: TensorSpec; // (B, T, 343) FP32
  // (B, T) FP32, 1.0 = padded step, 0.0 = valid. Cast to bool in-graph;
  // True == padded (matches window_to_model_input).
  keyPaddingMask: TensorSpec;
  logits: TensorSpec; // (B, 96)
}

export interface Stage1Contract {
  net1: Net1Contract;
  net2: Net2Contract;
  net3: Net3Contract;
}

export interface PipelineContract extends Stage1Contract {
  net4: Net4Contract;
}

// Canonical contract for the live v3 checkpoints.
export const DEFAULT_STAGE1_CONTRACT: Stage1Contract = {
  net1: {
    url: '/models/net1.onnx',
    inputSize: 256,
    input: { name: 'input', shape: [-1, 3, 256, 256], dtype: 'float32' },
    heatmaps: { name: 'heatmaps', shape: [-1, 7, 64, 64], dtype: 'float32' },
    heatmapSize: 64,
    numKeypoints: 7,
    // Face+body slice into the 49-kpt schema: nose(42)..neck(48) = [42, 49).
    keypointSlice: [42, 49],
    softArgmaxTemp: 10.0,
    peakThreshold: 0.05,
  },
  net2: {
    url: '/models/net2.onnx',
    inputSize: 256,
    input: { name: 'input', shape: [-1, 3, 256, 256], dtype: 'float32' },
    cls: { name: 'cls', shape: [-1, 2624], dtype: 'float32' },
    box: { name: 'box', shape: [-1, 2624, 4], dtype: 'float32' },
    kpt: null, // no kpt head on this checkpoint
    nKpts: 0,
    anchors: {
      inputSize: 256,
      multiStride: true,
      scalesPerStride: [[0.05, 0.1], [0.2, 0.35], [0.55]],
      strides: [8, 16, 32],
      anchorsPerScale: [2, 2, 1],
      square: false,
      nAnchors: 2624,
    },
    conf: 0.3,
    iouThreshold: 0.3,
    maxBoxes: 2,
  },
  net3: {
    url: '/models/net3.onnx',
    cropSize: 224,
    input: { name: 'input', shape: [-1, 3, 224, 224], dtype: 'float32' },
    headType: 'regression',
    output: { name: 'coords', shape: [-1, 21, 3], dtype: 'float32' },
    numKeypoints: 21,
    boxExpandFrac: 0.05,
    twoPass: true,
  },
};

export const DEFAULT_NET4_CONTRACT: Net4Contract = {
  url: '/models/net4.onnx',
  inChannels: 343,
  numClasses: 96,
  maxFrames: 64,
  features: { name: 'features', shape: [-1, -1, 343], dtype: 'float32' },
  keyPaddingMask: { name: 'key_padding_mask', shape: [-1, -1], dtype: 'float32' },
  logits: { name: 'logits', shape: [-1, 96], dtype: 'float32' },
};

export const DEFAULT_PIPELINE_CONTRACT: PipelineContract = {
  ...DEFAULT_STAGE1_CONTRACT,
  net4: DEFAULT_NET4_CONTRACT,
};

// Shared schema constants (mirror src/stage1/data/schema.py).
export const NUM_KEYPOINTS = 49 as const;
export const RIGHT_HAND_START = 0 as const;
export const LEFT_HAND_START = 21 as const;
export const FACE_INDICES = [42, 43, 44] as const; // nose, chin, forehead
export const BODY_INDICES = [45, 46, 47, 48] as const; // chest, L-sh, R-sh, neck

// Image-net normalisation: (rgb/255 - MEAN) / STD, channel-broadcast.
export const IMG_MEAN = 0.5 as const;
export const IMG_STD = 0.5 as const;

// Pre/post-processing notes per net — what TS owns around each graph.
export const PROCESSING_NOTES = {
  net1: {
    pre:
      'Letterbox BGR->RGB into 256x256 keeping aspect (scale=256/max(h,w); ' +
      'center pad zeros; record scale,dx,dy). Normalise (rgb/255-0.5)/0.5, ' +
      'NCHW. Mirror extract_keypoints.letterbox + run_net1.',
    post:
      'Soft-argmax per heatmap (sharpen temp 10, softmax, spatial expectation)' +
      ' -> (7,2) hm-px; *4 to input px; undo letterbox x=(x-dx)/scale, ' +
      'y=(y-dy)/scale. peak=max(heatmap); accept peak>0.05 AND inside frame. ' +
      'Write into global slots 42..48, vis=1. Mirror soft_argmax_2d + run_net1.',
  },
  net2: {
    pre: 'Same letterbox+normalise as Net1 (input 256). Mirror run_net2.',
    post:
      'sigmoid(cls); keep>=0.3. Rebuild 2624 anchors (get_anchors: strides ' +
      '[8,16,32], scales [[0.05,0.1],[0.2,0.35],[0.55]], square=false, ' +
      'anchors_per_scale [2,2,1], P1->P2->P3). decode_box->cx,cy,w,h->xyxy. ' +
      'NMS(iou 0.3, top_k 2). Undo letterbox per corner. NO kpt head -> Net3 ' +
      '2-pass. assign_hand_side via midline of visible Net1 kpts.',
  },
  net3: {
    pre:
      'Expand palm box 5%/side, clamp (skip if <4px). crop_hand 224x224 with ' +
      'rotation pointing wrist->MCP up; M maps image->crop. Normalise ' +
      '(rgb/255-0.5)/0.5, NCHW. Mirror crop_hand + _net3_one_pass.',
    post:
      'coords[...,:2]*224 -> crop px (21,2); unproject_kpts(crop_px, M) -> ' +
      'frame px. 2-PASS (no Net2 kpts): pass1 rotation 0 to read wrist(0)+' +
      'middle-MCP(9) crop px -> upright_rotation_deg; pass2 re-crop rotated, ' +
      'forward, unproject. Write into slots 0..20 (right) / 21..41 (left), ' +
      'vis=1. Mirror run_net3 + upright_rotation_deg + unproject_kpts.',
  },
  net4: {
    pre:
      'Build 343-dim per-frame features from the 49-kpt buffer: per-part ' +
      'normalise (face/body body-scale via centroid+span; per-hand finger ' +
      'offsets rescaled by hand span, wrist at body-norm pos), zero ' +
      'invisibles, then [coords(98), vis(49), lag1(98)=norm[t]-norm[t-1], ' +
      'lag2(98)=norm[t]-norm[t-2]]. window: T>=64 uniform-subsample to 64 ' +
      'else zero-pad tail; mask=1.0 on padded. Mirror _normalise_frame / ' +
      '_build_per_frame_features / window_to_model_input.',
    post:
      'softmax(logits[0]); argsort desc; top-3 {gloss,prob} via gloss_to_idx ' +
      '(96 classes; ordering in the fixtures). Mirror predict_clip.predict.',
  },
} as const;
