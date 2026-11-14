// SPDX-License-Identifier: Apache-2.0
// Simula: screenshot da guardare a mano in test-results/ui/ (1440 scuro e 390 chiaro, Learning e Avanzato, con e senza
// WebGL). Ogni test lancia il suo browser; nessun test.use di launchOptions in questo file (lo erediterebbe il launch).
import { test, expect, type Page } from '@playwright/test';
import { frames } from './landerHelpers';

const NO_WEBGL = ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'];
const CANVAS = '[data-testid="sim-stage"] canvas';
const OUT = 'test-results/ui';

async function ready(page: Page, mode: 'webgl' | 'canvas2d'): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible();
  await expect(page.getByTestId('sim-mode')).toHaveAttribute('data-mode', mode, { timeout: 20_000 });
  await frames(page, CANVAS);
}

for (const [w, h, scheme] of [[1440, 900, 'dark'], [390, 844, 'light']] as const) {
  for (const gl of [true, false]) {
    for (const mode of ['learning', 'avanzato'] as const) {
      test(`screenshot /simula ${w} ${scheme} ${mode} ${gl ? 'webgl' : 'nowebgl'}`, async ({ playwright, baseURL }) => {
        test.setTimeout(60_000);
        const browser = await playwright.chromium.launch(gl ? {} : { args: NO_WEBGL });
        try {
          const ctx = await browser.newContext({ baseURL, viewport: { width: w, height: h }, colorScheme: scheme, locale: 'it-IT', reducedMotion: 'reduce' });
          const page = await ctx.newPage();
          await page.goto(`/simula?tab=scena&mode=${mode}&el=0.8`);
          await ready(page, gl ? 'webgl' : 'canvas2d');
          await expect(page.locator('[data-testid="margin-chart"] .chart[data-ready="1"]')).toHaveCount(1, { timeout: 15_000 });
          await page.waitForTimeout(400);
          const o = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(o).toBeLessThanOrEqual(0);
          await page.screenshot({ path: `${OUT}/simula-${w}-${scheme}-${mode}-${gl ? 'webgl' : 'nowebgl'}.png`, fullPage: true });
          await page.screenshot({ path: `${OUT}/simula-${w}-${scheme}-${mode}-${gl ? 'webgl' : 'nowebgl'}-top.png` });
        } finally {
          await browser.close();
        }
      });
    }
  }
}
