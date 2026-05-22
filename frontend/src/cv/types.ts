// CV module type contracts — see docs/ml-handoff.md for canonical reference

export interface Frame {
  timestamp: number;
  imageData: ImageBitmap;
}

export type DrillType = 'handshape' | 'movement' | 'sign';

export interface DetectionResult {
  state: 'target-met' | 'low-confidence' | 'no-hands';
  confidence: number;
  oodScore?: number;
  parameter?: 'handshape' | 'movement' | 'palm-orientation' | 'location' | 'timing' | 'framing';
  detail?: string;
  latencyMs: number;
  modelVersion: string;
}

export interface InitResult {
  modelVersion: string;
  backend: 'webgpu' | 'wasm';
  warmupLatencyMs: number;
}
