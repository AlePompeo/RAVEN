// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { openLander, T0 } from './landerHelpers';

test('lander: fractional replay milliseconds match the second-resolution scene and solar API', async ({ page }) => {
  test.setTimeout(60_000);
  await page.addInitScript(() => {
    const now = performance.now.bind(performance);
    // Exercise fractional elapsed time deterministically, even when timer ticks land on whole milliseconds.
    Object.defineProperty(performance, 'now', { value: () => now() * 1.000001 });
  });
  await openLander(page, 'webgl');
  await expect(page.getByTestId('sun-note')).toContainText('Luce: Sole reale');
  const updated = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/raven/scene' && url.searchParams.get('t') !== T0;
  });
  await page.getByRole('button', { name: 'Riproduci', exact: true }).click();
  await updated;
  await page.getByRole('button', { name: 'Ferma', exact: true }).click();
  await expect(page.getByTestId('lander-status')).not.toContainText('00:00:00 UTC');
  await expect(page.getByTestId('lander-status')).toContainText('Scena aggiornata', { timeout: 20_000 });
  await expect(page.getByTestId('sun-note')).toContainText('Luce: Sole reale');
});
