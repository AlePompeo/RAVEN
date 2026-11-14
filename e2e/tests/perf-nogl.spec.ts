// SPDX-License-Identifier: Apache-2.0
// Renderer software (Chromium senza WebGL) con CPU rallentata 4x e 6x: dischi presentati al secondo durante la
// rotazione automatica (ombreggiatura nel Worker, mezza risoluzione in movimento) e ritmo del main thread.
// Misure isolate (1 worker, 3 ripetizioni): dischi/s 1x 44-60, 4x 35-43, 6x 26-34; rAF/s 1x 44-60, 4x 34-42, 6x 24-33.
// Soglie: dischi > 4 (> 2 a 6x), rAF > 10: circa un terzo del minimo misurato. Lanciare con `npm run test:perf`.
import { test } from '@playwright/test';
import { diskFps, expect, rafRate, save, throttle } from './perfHelpers';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

for (const rate of [1, 4, 6]) {
  for (const body of ['moon', 'earth'] as const) {
    test(`senza WebGL, CPU ${rate}x, ${body}: rotazione automatica`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.goto(`/viewer?body=${body}`);
      await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
      await throttle(page, rate);
      await page.getByRole('button', { name: 'Rotazione automatica' }).click();
      await page.waitForTimeout(500);
      const [disk, raf] = await Promise.all([diskFps(page, 3000), rafRate(page, 3000)]);
      save(`viewer-canvas2d-${body}-cpu${rate}x`, { cpu: rate, body, diskFps: disk.fps, lastShadeMs: disk.shadeMs, rafPerSec: raf });
      expect(disk.fps).toBeGreaterThan(rate >= 6 ? 2 : 4);
      expect(raf).toBeGreaterThan(10); // il main thread resta reattivo
    });
  }
}
