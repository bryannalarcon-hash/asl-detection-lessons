import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';

/**
 * Aurora tokens presence check.
 *
 * Reads `frontend/src/styles/globals.css` as raw text and asserts the
 * Aurora design tokens + utility classes are declared. Catches drift if
 * a future refactor accidentally drops the gradient utilities or the
 * page-background HSL triple.
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const GLOBALS_PATH = resolve(__dirname, '../../src/styles/globals.css');

describe('aurora tokens in globals.css', () => {
  const css = readFileSync(GLOBALS_PATH, 'utf8');

  it('declares the primary gradient + corner-glow gradients', () => {
    expect(css).toMatch(/--grad-primary\s*:/);
    expect(css).toMatch(/--grad-glow-a\s*:/);
    expect(css).toMatch(/--grad-glow-b\s*:/);
  });

  it('declares the wordmark + gradient-text utility classes', () => {
    expect(css).toMatch(/\.wordmark-stripe\b/);
    expect(css).toMatch(/\.gradient-text\b/);
  });

  it('declares the eyebrow + Aurora primary button utility classes', () => {
    expect(css).toMatch(/\.eyebrow\b/);
    expect(css).toMatch(/\.btn-aurora-primary\b/);
  });

  it('declares the page background HSL triple at 220 51% 12%', () => {
    expect(css).toMatch(/--bg\s*:\s*220\s+51%\s+12%/);
  });
});
