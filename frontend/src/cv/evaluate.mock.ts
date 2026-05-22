// v1 mock CV — see docs/ml-handoff.md §"v1 mock implementation".
// The mock NEVER returns 'target-met'. Mastery state is driven by self-report row.
import type { Frame, DrillType, DetectionResult, InitResult } from './types';

let currentBoxState: 'no-hands' | 'hands-detected' = 'no-hands';
let framesBuffered = 0;

export async function init(): Promise<InitResult> {
  return { modelVersion: 'mock-0.1', backend: 'wasm', warmupLatencyMs: 0 };
}

export function processFrame(_frame: Frame) {
  framesBuffered++;
  return { state: currentBoxState, framesBuffered };
}

export async function evaluateRep(_drillType: DrillType, _target: string): Promise<DetectionResult> {
  // Mock NEVER returns 'target-met'. Mastery is driven by self-report row.
  return {
    state: 'low-confidence',
    confidence: 0,
    latencyMs: 0,
    modelVersion: 'mock-0.1',
  };
}

export function resetRepBuffer() {
  framesBuffered = 0;
}

export async function dispose() {
  // no-op in mock
}

// Dev-panel-only — callers must gate by isDevToolsEnabled() (VITE_DEV_TOOLS)
export function __devSetBoxState(state: 'no-hands' | 'hands-detected') {
  currentBoxState = state;
}
