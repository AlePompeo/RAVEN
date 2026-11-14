// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

// The south-polar site map picks a site by click; the results show key Sun/Earth figures and the lunar-day view for a long window;
// the Expert report carries the sunset/Earthset countdown and the same figures.
test('2D polar map picks a site; key figures and lunar days appear in the results and in the report', async ({ page, request }) => {
  test.setTimeout(240_000);
  const sites = (await (await request.get('/api/raven/sites')).json()).sites as { id: string; lat_deg: number; lon_deg_east: number }[];
  expect(sites.length).toBeGreaterThanOrEqual(14);
  const target = sites.find((s) => s.id === 'shackleton')!;

  await page.goto('/mission-planner?lang=en&mp_step=sites&site=malapert-massif&t=2027-04-16T00:00:00Z&mode=avanzato');
  await page.getByRole('button', { name: '2D polar map', exact: true }).click();
  const canvas = page.getByTestId('site-polar-map').locator('canvas');
  await expect(canvas).toBeVisible();
  await page.waitForTimeout(800); // texture decode
  const box = (await canvas.boundingBox())!;
  const rho = (90 + target.lat_deg) / 30, th = (target.lon_deg_east * Math.PI) / 180;
  await page.mouse.click(box.x + box.width / 2 + rho * (box.width / 2) * Math.sin(th), box.y + box.height / 2 - rho * (box.height / 2) * Math.cos(th));
  await expect(page.getByRole('button', { name: /Shackleton/ }).first()).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Period/ }).click();
  await page.locator('#journey-days').fill('62');
  await page.locator('#journey-days').blur();
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  const figures = page.getByTestId('visibility-figures');
  await expect(figures).toBeVisible({ timeout: 90_000 });
  await expect(figures).toContainText('Highest Sun elevation');
  await expect(figures).toContainText('Longest continuous sunlight');
  await expect(page.getByTestId('lunar-days')).toContainText('Lunar day 1');
  await expect(page.getByTestId('lunar-days')).toContainText('Lunar day 3');

  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  const report = page.getByTestId('mission-lifecycle-report');
  await expect(report.getByTestId('visibility-figures')).toContainText('At the start of the window: Sun');
  await expect(report.getByTestId('visibility-figures')).toContainText(/sets in|rises in|no change in the window|Unknown/);
  await expect(report.getByTestId('lunar-days')).toBeVisible();
  await expect(report.getByTestId('report-moon')).toContainText('Shackleton');
});
