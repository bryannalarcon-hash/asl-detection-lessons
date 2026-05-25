// Dedicated vitest config for the WebGPU-port parity harness (V1 per-net, glue,
// e2e, verifier). Runs under the node environment (onnxruntime-node + fs) and
// targets only the *.parity.spec.ts files, so it stays independent of the app's
// jsdom unit-test config. Run: vitest run --config vitest.parity.config.ts
import { defineConfig } from 'vitest/config';
import path from 'node:path';

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'node',
    globals: true,
    include: ['tests/cv/**/*.parity.spec.ts'],
    testTimeout: 60000,
    hookTimeout: 60000,
  },
});
