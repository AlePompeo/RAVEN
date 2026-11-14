// SPDX-License-Identifier: Apache-2.0
// Visualizzatore RAVEN con Chromium SENZA WebGL (renderer Canvas 2D): stessa linea, stessi marcatori e testi.
import { test, expect, type Page } from '@playwright/test';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

const T = '2027-04-07T00:00:00Z';
const OUT = 'test-results/ui/viewer-grazing';
const dec = (v: number) => Math.abs(v).toFixed(1).replace('.', ',');

async function open(page: Page, body: string): Promise<void> {
  await page.goto(`/viewer?body=${body}&t=${encodeURIComponent(T)}`);
  await expect(page.getByTestId('viewer-mode')).toHaveAttribute('data-mode', 'canvas2d', { timeout: 20_000 });
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.getByRole('button', { name: 'Controlli e impostazioni' }).click();
  }
  await expect(page.getByTestId('fspl-delta')).toBeVisible({ timeout: 20_000 });
}

test('Canvas 2D: sito polare con linea verso la Terra, angolo e stato (screenshot 1440 scuro e 390 chiaro)', async ({ page }) => {
  const snap = await (await page.request.get(`/api/raven/snapshot?t=${encodeURIComponent(T)}&rate_bps=100000&station=dsn34`)).json();
  const hw = snap.sites.find((s: { id: string }) => s.id === 'haworth');
  for (const [w, h, scheme] of [
    [1440, 900, 'dark'],
    [390, 844, 'light'],
  ] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: w, height: h });
    await open(page, 'moon');
    if (w === 390) await page.getByRole('button', { name: /Luoghi e dati di Luna/ }).click();
    await page.locator('.place[data-place="haworth"]').click();
    if (w === 390) await page.getByRole('button', { name: 'Chiudi', exact: true }).click();
    await page.evaluate(() => scrollTo(0, 0));
    await expect(page.getByTestId('dir-line')).toBeVisible();
    await expect(page.getByTestId('dir-label')).toContainText(`Terra a ${dec(hw.earth_el_deg)}°`);
    await expect(page.locator('.marker[data-place="haworth"]')).toHaveAttribute('data-state', hw.state);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/moon-polar-${w}-${scheme}-nogl.png` });
    await open(page, 'earth');
    if (w === 390) await page.getByRole('button', { name: /Luoghi e dati di Terra/ }).click();
    await page.locator(`.place[data-place="${snap.dsn.best_complex.toLowerCase()}"]`).click();
    if (w === 390) await page.getByRole('button', { name: 'Chiudi', exact: true }).click();
    await page.evaluate(() => scrollTo(0, 0));
    await expect(page.getByTestId('dir-line')).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/earth-stations-${w}-${scheme}-nogl.png` });
  }
});
