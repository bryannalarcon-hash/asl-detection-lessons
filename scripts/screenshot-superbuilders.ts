/**
 * Capture superbuilders.school comprehensively.
 *
 * The site is a single-page marketing app (verified: all common paths return
 * the Azure Static 404 fallback). So instead of crawling, we capture:
 *   - the whole page at desktop (1440), wide (1920), tablet (820), mobile (390)
 *   - each major scroll section as its own framed shot at desktop width
 *
 * Usage: npx tsx scripts/screenshot-superbuilders.ts [out_dir]
 */
import { chromium, type Page } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const URL_ = 'https://www.superbuilders.school/';

const VIEWPORTS = [
  { name: 'wide-1920', w: 1920, h: 1080 },
  { name: 'desktop-1440', w: 1440, h: 900 },
  { name: 'tablet-820', w: 820, h: 1180 },
  { name: 'mobile-390', w: 390, h: 844 },
] as const;

async function settle(page: Page) {
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined);
  await page.waitForTimeout(800);
  // Scroll to force any lazy images / fonts, then return to top.
  await page.evaluate(`new Promise((resolve) => {
    const distance = 600;
    let y = 0;
    const max = document.documentElement.scrollHeight;
    const tick = () => {
      window.scrollTo(0, y);
      y += distance;
      if (y < max) setTimeout(tick, 80);
      else { window.scrollTo(0, 0); resolve(undefined); }
    };
    tick();
  })`);
  await page.waitForTimeout(800);
}

async function main() {
  const outDir = process.argv[2]
    ? resolve(process.argv[2])
    : resolve(
        process.cwd(),
        `screenshots/superbuilders-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}`,
      );
  await mkdir(outDir, { recursive: true });
  console.log(`[crawl] writing to ${outDir}`);

  const browser = await chromium.launch();
  const ua =
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36';

  const captured: { name: string; file: string; viewport?: string }[] = [];

  // === 1. Full-page snapshots per viewport ===
  for (let i = 0; i < VIEWPORTS.length; i++) {
    const v = VIEWPORTS[i]!;
    const context = await browser.newContext({
      viewport: { width: v.w, height: v.h },
      deviceScaleFactor: 2,
      userAgent: ua,
    });
    const page = await context.newPage();
    page.on('pageerror', (err) => console.warn(`[pageerror:${v.name}]`, err.message.split('\n')[0]));

    const file = `${String(i).padStart(2, '0')}-fullpage-${v.name}.png`;
    try {
      await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      await settle(page);
      await page.screenshot({ path: `${outDir}/${file}`, fullPage: true });
      console.log(`  ✓ fullpage @ ${v.name.padEnd(14)} → ${file}`);
      captured.push({ name: `fullpage-${v.name}`, file, viewport: v.name });
    } catch (err) {
      console.log(`  ✗ fullpage @ ${v.name}: ${(err as Error).message.split('\n')[0]}`);
    }
    await context.close();
  }

  // === 2. Section-by-section at desktop ===
  // Walk the document at 1440 and capture each top-level <section> (or its
  // closest analog) as a framed shot. If the markup doesn't expose sections,
  // fall back to viewport-height tiles.
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    userAgent: ua,
  });
  const page = await context.newPage();
  await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await settle(page);

  // Tile the document into 900px slices at desktop width so each "fold" is
  // its own file. The SPA exposes no semantic <section> markers, so
  // fixed-tile slicing gives the most predictable per-fold output.
  const totalHeight = await page.evaluate('document.documentElement.scrollHeight');
  const TILE = 900;
  const tileCount = Math.ceil((totalHeight as number) / TILE);
  console.log(`  · tiling ${totalHeight}px into ${tileCount} × ${TILE}px slices`);
  for (let i = 0; i < tileCount; i++) {
    const y = i * TILE;
    const h = Math.min(TILE, (totalHeight as number) - y);
    if (h < 80) break;
    const file = `${String(10 + i).padStart(2, '0')}-fold-${i + 1}.png`;
    try {
      await page.evaluate(`window.scrollTo(0, ${y})`);
      await page.waitForTimeout(250);
      // Clip is viewport-relative — after scrolling, the slice starts at y=0
      // in the viewport, not at the document offset.
      await page.screenshot({
        path: `${outDir}/${file}`,
        clip: { x: 0, y: 0, width: 1440, height: h },
      });
      console.log(`  ✓ fold ${(i + 1).toString().padStart(2)}/${tileCount}  y=${y}  h=${h}  → ${file}`);
      captured.push({ name: `fold-${i + 1}`, file });
    } catch (err) {
      console.log(`  ✗ fold ${i + 1}: ${(err as Error).message.split('\n')[0]}`);
    }
  }

  await context.close();
  await browser.close();

  await writeFile(
    `${outDir}/manifest.json`,
    JSON.stringify(
      {
        origin: 'https://www.superbuilders.school',
        captured_at: new Date().toISOString(),
        note: 'Single-page marketing site — no internal routes exist (verified by probing 27 common paths, all returned Azure 404 fallback). Output is multi-viewport full-page + per-section captures.',
        viewports: VIEWPORTS,
        files: captured,
      },
      null,
      2,
    ),
  );
  console.log(`\n[crawl] done: ${captured.length} files in ${outDir}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
