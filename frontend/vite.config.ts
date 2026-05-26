/**
 * Vite build and dev-server configuration for the frontend, wiring the React plugin,
 * PWA manifest and service-worker caching rules, the `@` source alias, and the jsdom
 * unit-test setup. Caching deliberately bypasses lesson videos, ONNX models, and API calls.
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'ASL Pilot',
        short_name: 'ASL Pilot',
        description: 'Vocabulary practice for ASL 1 learners',
        theme_color: '#1c1c1c',
        background_color: '#1c1c1c',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // Never precache large runtime-fetched assets: lesson videos, ONNX
        // models, and the ORT wasm runtime (the 23.7MB asyncify wasm exceeds
        // the 2MB workbox precache limit and fails the build otherwise).
        globIgnores: ['**/*.mp4', '**/*.webm', '**/*.onnx', '**/*.wasm'],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        runtimeCaching: [
          {
            // Always go to network for lesson videos. A prior CacheFirst rule
            // poisoned the cache: before models/videos were served, these URLs
            // returned the SPA index.html (200), which CacheFirst then served
            // forever as the "video" — the element errored and fell back to the
            // mock clip. The browser's HTTP cache (range-capable) covers replays.
            urlPattern: /\/videos\/.*\.(mp4|webm)$/,
            handler: 'NetworkOnly',
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkOnly',
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: [
      'tests/unit/**/*.spec.ts',
      'tests/unit/**/*.spec.tsx',
      'src/cv/**/*.spec.ts',
    ],
  },
});
