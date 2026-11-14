// SPDX-License-Identifier: Apache-2.0
// Simula in Chromium SENZA WebGL: la sezione laterale in Canvas 2D e il ripiego, disegnata e aggiornata dai controlli.
import { test, expect, type Page } from '@playwright/test';
import { frames, pixels } from './landerHelpers';

const NO_WEBGL = ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'];
const CANVAS = '[data-testid="sim-stage"] canvas';

async function ready(page: Page, mode: 'webgl' | 'canvas2d'): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible();
  await expect(page.getByTestId('sim-mode')).toHaveAttribute('data-mode', mode, { timeout: 20_000 });
  await frames(page, CANVAS);
}

test.use({ launchOptions: { args: NO_WEBGL } });

test.describe('Simula senza WebGL', () => {

  test('la sezione 2D è disegnata, cambia con i controlli e i numeri restano', async ({ page }) => {
    await page.goto('/simula?tab=scena&mode=learning');
    await ready(page, 'canvas2d');
    await expect(page.getByTestId('sim-mode')).toContainText('senza WebGL');
    await expect(page.getByRole('button', { name: 'Ruota a destra' })).toHaveCount(0);
    await expect(page.getByTestId('sim-stage')).toHaveAttribute('aria-roledescription', 'sezione');
    const p0 = await pixels(page, CANVAS);
    expect(p0.lit / p0.total).toBeGreaterThan(0.05);
    await page.getByTestId('preset-blocking').click();
    await expect(page.getByTestId('sim-stage')).toHaveAttribute('data-state', 'blocked');
    await frames(page, CANVAS);
    const p1 = await pixels(page, CANVAS);
    expect(p1.hash).not.toBe(p0.hash);
    await expect(page.getByTestId('gauge-state')).toContainText('Bloccato');
  });
});

