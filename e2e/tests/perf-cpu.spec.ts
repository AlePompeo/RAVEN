// SPDX-License-Identifier: Apache-2.0
// Macchina debole simulata: CPU rallentata 4x e 6x via CDP, più un profilo telefono (Pixel 7, CPU 4x).
// Home: FCP/LCP/TBT stimato, palco con la Luna NASA pronto, CTA che risponde. Visualizzatore (WebGL o 2D):
// ritmo del main thread durante la rotazione automatica. Numeri in test-results/ui/perf/*.json.
// Soglie (esecuzione isolata, 1 worker, 3 ripetizioni): rAF/s visualizzatore WebGL 17-22 a 4x e 14 a 6x -> soglia > 5.
// Da lanciare con `npm run test:perf` (mai in parallelo con la suite funzionale).
// (v2: la Luna del palco è ferma dopo l'ingresso, quindi non si misura più il cambio dei pixel nel tempo.)
import { test, devices } from '@playwright/test';
import { expect, observe, rafRate, save, throttle, vitals } from './perfHelpers';

for (const rate of [4, 6]) {
  test(`CPU ${rate}x: home interattiva, Luna pronta, LCP e TBT misurati`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await observe(page);
    await throttle(page, rate);
    const t0 = Date.now();
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
    const h1Ms = Date.now() - t0;
    await expect(page.locator('[data-testid="moon-stage"][data-ready="1"]')).toHaveCount(1, { timeout: 60_000 });
    const moonReadyMs = Date.now() - t0;
    const v = await vitals(page);
    const raf = await rafRate(page);
    const t1 = Date.now();
    await page.getByRole('link', { name: 'Prova il simulatore' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible({ timeout: 30_000 });
    const r = { cpu: rate, h1VisibleWallMs: h1Ms, moonReadyWallMs: moonReadyMs, ...v, rafPerSec: raf, ctaToTelemetryMs: Date.now() - t1 };
    save(`home-cpu${rate}x`, r);
    expect(raf).toBeGreaterThan(5);
    expect(r.ctaToTelemetryMs).toBeLessThan(10_000);
  });

  test(`CPU ${rate}x: visualizzatore in rotazione automatica, main thread libero`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await observe(page);
    await throttle(page, rate);
    await page.goto('/viewer');
    await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 60_000 });
    const mode = await page.getByTestId('viewer-mode').getAttribute('data-mode');
    await page.getByRole('button', { name: 'Rotazione automatica' }).click();
    await page.waitForTimeout(500);
    const raf = await rafRate(page, 3000);
    const v = await vitals(page);
    save(`viewer-${mode}-cpu${rate}x`, { cpu: rate, mode, ...v, rafPerSec: raf });
    expect(raf).toBeGreaterThan(5);
  });
}

test.describe('profilo telefono', () => {
  const { defaultBrowserType: _b, ...pixel } = devices['Pixel 7']!;
  test.use({ ...pixel });
  test('Pixel 7 + CPU 4x: home', async ({ page }) => {
    test.setTimeout(120_000);
    await observe(page);
    await throttle(page, 4);
    await page.goto('/');
    await expect(page.locator('[data-testid="moon-stage"][data-ready="1"]')).toHaveCount(1, { timeout: 60_000 });
    const v = await vitals(page);
    save('home-pixel7-cpu4x', v);
    expect(v.lcp).toBeGreaterThan(0);
  });
});
