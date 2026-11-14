// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

// A year-long period is admitted only with a step that keeps it inside the sample caps (chosen automatically and
// explained); the calculation then finishes in seconds and the main thread is never blocked for long.
test('365 days: the step is raised and explained, the simulation ends in under 20 s, no long main-thread block', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/mission-planner?lang=en&mp_step=period&mode=avanzato&site=malapert-massif&t=2027-04-07T00:00:00Z');
  await expect(page.locator('#journey-days')).toBeVisible();
  await page.evaluate(() => {
    const w = window as unknown as { __gaps: number[] };
    w.__gaps = [];
    let last = performance.now();
    setInterval(() => { const n = performance.now(); w.__gaps.push(Math.round(n - last)); last = n; }, 100);
  });
  await page.locator('#journey-resolution').selectOption('10');
  await page.locator('#journey-days').fill('365');
  await page.locator('#journey-days').blur();
  await expect(page.locator('#journey-resolution')).toHaveValue('360');
  await expect(page.getByTestId('auto-step')).toContainText('raised to 360 min');
  await expect(page.getByText('1,460 samples per scenario')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);

  const started = Date.now();
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Mission timeline' })).toBeVisible({ timeout: 40_000 });
  expect(Date.now() - started).toBeLessThan(20_000);
  const gaps = await page.evaluate(() => (window as unknown as { __gaps: number[] }).__gaps);
  expect(Math.max(...gaps), 'longest main-thread block (ms)').toBeLessThan(2000);
});
