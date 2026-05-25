// ORT Web runtime — workstream D. Loads the 4 v3 ONNX models via
// onnxruntime-web, picks WebGPU with a WASM fallback, warms each session, and
// exposes the session seams the ported pipeline modules consume:
//   - Stage1Sessions (net1/net2/net3 image forwards) for pipeline/stage1.ts
//   - Net4Session (features+mask -> logits) for pipeline/stage2.ts
//
// Backend pick: executionProviders: ['webgpu', 'wasm']. ORT tries WebGPU first
// and silently falls back to WASM if navigator.gpu is missing or EP init fails.
// We probe the active EP after a warm-up run so callers can show webgpu/wasm.
//
// GOTCHA (already bit the Net 1 PoC): you MUST import the *.webgpu* bundle of
// onnxruntime-web. ort.min.js / ort.wasm.js ship WITHOUT the WebGPU EP, so
// requesting executionProviders:['webgpu'] there silently drops to wasm. We
// import 'onnxruntime-web/webgpu' which is the bundle that registers the EP.
//
// wasm runtime config: numThreads=1 so it works behind a plain static server
// with no cross-origin isolation (SharedArrayBuffer/COOP+COEP not required).

import * as ort from 'onnxruntime-web/webgpu';

import {
  DEFAULT_PIPELINE_CONTRACT,
  type Net1Contract,
  type Net2Contract,
  type Net3Contract,
  type Net4Contract,
  type PipelineContract,
} from './models';
import type { OrtTensor, Stage1Sessions } from '../pipeline/stage1';
import type { Net4Session } from '../pipeline/stage2';

export type Backend = 'webgpu' | 'wasm';

export interface RuntimeConfig {
  contract?: PipelineContract;
  // Where the .onnx assets live, relative to the page (default '/models').
  // Each contract url is already absolute (e.g. '/models/net1.onnx'); this is
  // a prefix override for hosting the PoC under a sub-path or a CDN.
  modelBaseUrl?: string;
  // CDN that hosts the matching ort wasm/jsep binaries. Defaults to the
  // jsdelivr dist for the installed onnxruntime-web version.
  wasmCdnBase?: string;
  // Force a single EP (skips the fallback list). Mainly for the WASM-only
  // parity harness in Node, where WebGPU is unavailable.
  forceBackend?: Backend;
}

export interface InitRuntimeResult {
  backend: Backend;
  modelVersion: string;
  warmupLatencyMs: number;
  // Per-net warm-up timings (ms), handy for the PoC perf readout.
  perNetWarmupMs: { net1: number; net2: number; net3: number; net4: number };
}

// The version string we report up the contract. Mirrors the v3 checkpoint set
// the ONNX assets were exported from (see ort/models.ts header).
export const MODEL_VERSION = 'v3-onnx-webgpu' as const;

// jsdelivr dist for the wasm/jsep binaries that match the JS bundle. Keep the
// version in lockstep with the onnxruntime-web devDependency.
const ORT_VERSION = '1.23.0';
const DEFAULT_WASM_CDN =
  `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;

let configured = false;

/**
 * One-time global ORT env config. Idempotent: safe to call before each init.
 * Points the wasm loader at the CDN dist and forces single-thread so the PoC
 * runs behind a plain static server (no COOP/COEP headers needed).
 */
function configureOrtEnv(wasmCdnBase: string): void {
  if (configured) return;
  ort.env.wasm.wasmPaths = wasmCdnBase;
  ort.env.wasm.numThreads = 1;
  // Proxy off — we run inference on the main thread / a caller-owned worker.
  ort.env.wasm.proxy = false;
  configured = true;
}

function joinUrl(base: string | undefined, url: string): string {
  if (!base) return url;
  // url is like '/models/net1.onnx'; swap the '/models' prefix for base.
  const file = url.slice(url.lastIndexOf('/') + 1);
  const trimmed = base.endsWith('/') ? base.slice(0, -1) : base;
  return `${trimmed}/${file}`;
}

function epList(force?: Backend): Backend[] {
  if (force) return [force];
  return ['webgpu', 'wasm'];
}

async function createSession(
  url: string,
  force?: Backend,
): Promise<ort.InferenceSession> {
  // graphOptimizationLevel 'all' is the default; we keep it. enableCpuMemArena
  // is irrelevant for webgpu and harmless for wasm.
  return ort.InferenceSession.create(url, {
    executionProviders: epList(force),
  });
}

// ---------------------------------------------------------------------------
// The live runtime. Holds the 4 sessions + the contract; exposes the two
// session seams + dispose. init() loads, warms, and probes the active EP.
// ---------------------------------------------------------------------------
export class OrtRuntime {
  readonly contract: PipelineContract;
  private readonly modelBaseUrl?: string;
  private readonly wasmCdnBase: string;
  private readonly forceBackend?: Backend;

  private net1Session?: ort.InferenceSession;
  private net2Session?: ort.InferenceSession;
  private net3Session?: ort.InferenceSession;
  private net4Session?: ort.InferenceSession;

  private _backend: Backend = 'wasm';
  private _ready = false;

  constructor(config: RuntimeConfig = {}) {
    this.contract = config.contract ?? DEFAULT_PIPELINE_CONTRACT;
    this.modelBaseUrl = config.modelBaseUrl;
    this.wasmCdnBase = config.wasmCdnBase ?? DEFAULT_WASM_CDN;
    this.forceBackend = config.forceBackend;
  }

  get backend(): Backend {
    return this._backend;
  }

  get ready(): boolean {
    return this._ready;
  }

  /** Load all 4 sessions and run one warm-up forward each. */
  async init(): Promise<InitRuntimeResult> {
    configureOrtEnv(this.wasmCdnBase);

    const u = (url: string) => joinUrl(this.modelBaseUrl, url);
    // Load the four sessions. WebGPU EP init happens lazily on first run for
    // some builds, so we don't trust the create() call to tell us the EP —
    // we infer it from whether a webgpu warm-up forward succeeds.
    [this.net1Session, this.net2Session, this.net3Session, this.net4Session] =
      await Promise.all([
        createSession(u(this.contract.net1.url), this.forceBackend),
        createSession(u(this.contract.net2.url), this.forceBackend),
        createSession(u(this.contract.net3.url), this.forceBackend),
        createSession(u(this.contract.net4.url), this.forceBackend),
      ]);

    const t0 = now();
    const perNetWarmupMs = await this.warmup();
    const warmupLatencyMs = now() - t0;

    // Probe the active EP. ORT does not expose it directly; we treat "webgpu
    // requested AND navigator.gpu present AND warm-up didn't throw" as webgpu.
    this._backend = this.probeBackend();
    this._ready = true;

    return {
      backend: this._backend,
      modelVersion: MODEL_VERSION,
      warmupLatencyMs,
      perNetWarmupMs,
    };
  }

  /** Run one zero-input forward per net to compile shaders / JIT the graph. */
  private async warmup(): Promise<InitRuntimeResult['perNetWarmupMs']> {
    const c = this.contract;
    const net1 = await timed(() =>
      this.runImage(this.net1Session!, c.net1, c.net1.inputSize),
    );
    const net2 = await timed(() =>
      this.runImage(this.net2Session!, c.net2, c.net2.inputSize),
    );
    const net3 = await timed(() =>
      this.runImage(this.net3Session!, c.net3, c.net3.cropSize),
    );
    const net4 = await timed(() => this.runNet4Warmup(c.net4));
    return { net1: net1.ms, net2: net2.ms, net3: net3.ms, net4: net4.ms };
  }

  private probeBackend(): Backend {
    if (this.forceBackend) return this.forceBackend;
    // navigator may be undefined in Node; guard for the parity harness.
    const hasGpu =
      typeof navigator !== 'undefined' &&
      typeof (navigator as Navigator & { gpu?: unknown }).gpu !== 'undefined';
    return hasGpu ? 'webgpu' : 'wasm';
  }

  // --- image-net forward (net1/net2/net3) -------------------------------- //
  private async runImage(
    session: ort.InferenceSession,
    spec: Net1Contract | Net2Contract | Net3Contract,
    size: number,
    input?: Float32Array,
  ): Promise<Record<string, OrtTensor>> {
    const data = input ?? new Float32Array(3 * size * size);
    const inputName = spec.input.name;
    const tensor = new ort.Tensor('float32', data, [1, 3, size, size]);
    const feeds: Record<string, ort.Tensor> = { [inputName]: tensor };
    const out = await session.run(feeds);
    return toOrtTensors(out);
  }

  private async runNet4Warmup(spec: Net4Contract): Promise<void> {
    const T = spec.maxFrames;
    const C = spec.inChannels;
    const feats = new Float32Array(T * C);
    const mask = new Uint8Array(T); // all-valid warm-up
    await this.runNet4(feats, mask, T, C, spec);
  }

  // --- net4 forward ------------------------------------------------------ //
  private async runNet4(
    features: Float32Array,
    mask: Uint8Array,
    T: number,
    C: number,
    spec: Net4Contract,
  ): Promise<Float32Array> {
    const featTensor = new ort.Tensor('float32', features, [1, T, C]);
    // The graph casts mask to bool internally (true == padded). We feed it as
    // the float32 the contract declares (1.0 = padded), letting the in-graph
    // cast do the bool conversion. windowToModelInput produces 1=padded.
    const maskData = new Float32Array(T);
    for (let i = 0; i < T; i++) maskData[i] = mask[i] ? 1 : 0;
    const maskTensor = new ort.Tensor('float32', maskData, [1, T]);
    const feeds: Record<string, ort.Tensor> = {
      [spec.features.name]: featTensor,
      [spec.keyPaddingMask.name]: maskTensor,
    };
    const out = await this.net4Session!.run(feeds);
    const logits = out[spec.logits.name];
    return logits.data as Float32Array;
  }

  // --- public session seams --------------------------------------------- //

  /** Adapter satisfying pipeline/stage1.ts's Stage1Sessions. */
  get stage1Sessions(): Stage1Sessions {
    const c = this.contract;
    return {
      net1: async (input: Float32Array, size: number) => {
        const out = await this.runImage(this.net1Session!, c.net1, size, input);
        return { heatmaps: out[c.net1.heatmaps.name] };
      },
      net2: async (input: Float32Array, size: number) => {
        const out = await this.runImage(this.net2Session!, c.net2, size, input);
        const res: { cls: OrtTensor; box: OrtTensor; kpt?: OrtTensor } = {
          cls: out[c.net2.cls.name],
          box: out[c.net2.box.name],
        };
        if (c.net2.kpt) res.kpt = out[c.net2.kpt.name];
        return res;
      },
      net3: async (input: Float32Array, size: number) => {
        const out = await this.runImage(this.net3Session!, c.net3, size, input);
        if (c.net3.headType === 'regression') {
          return { coords: out[c.net3.output.name] };
        }
        return { heatmaps: out[c.net3.output.name] };
      },
    };
  }

  /** Adapter satisfying pipeline/stage2.ts's Net4Session. */
  get net4SessionAdapter(): Net4Session {
    const spec = this.contract.net4;
    return {
      run: (features: Float32Array, mask: Uint8Array, T: number, C: number) =>
        this.runNet4(features, mask, T, C, spec),
    };
  }

  async dispose(): Promise<void> {
    await Promise.all(
      [this.net1Session, this.net2Session, this.net3Session, this.net4Session]
        .filter((s): s is ort.InferenceSession => !!s)
        .map((s) => s.release()),
    );
    this.net1Session = undefined;
    this.net2Session = undefined;
    this.net3Session = undefined;
    this.net4Session = undefined;
    this._ready = false;
  }
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
function toOrtTensors(out: ort.InferenceSession.OnnxValueMapType): Record<string, OrtTensor> {
  const res: Record<string, OrtTensor> = {};
  for (const [name, value] of Object.entries(out)) {
    const t = value as ort.Tensor;
    res[name] = { data: t.data as Float32Array, dims: t.dims as number[] };
  }
  return res;
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

async function timed<T>(fn: () => Promise<T>): Promise<{ value: T; ms: number }> {
  const t0 = now();
  const value = await fn();
  return { value, ms: now() - t0 };
}

/**
 * Convenience: construct + init a runtime in one call. Returns the runtime and
 * the init metadata so the PoC / evaluate.real can hold both.
 */
export async function createRuntime(
  config: RuntimeConfig = {},
): Promise<{ runtime: OrtRuntime; info: InitRuntimeResult }> {
  const runtime = new OrtRuntime(config);
  const info = await runtime.init();
  return { runtime, info };
}
