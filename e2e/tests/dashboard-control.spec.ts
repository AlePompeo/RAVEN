// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { openSimulationDetails } from './plannerHelpers';
import AxeBuilder from '@axe-core/playwright';

test('dashboard keeps site selection in the three-zone navigator on desktop and mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard?lang=en');
  const nav = page.getByTestId('dashboard-navigator');
  const detail = page.getByTestId('dashboard-site-detail');
  const selector = page.locator('#dashboard-site');
  await expect(nav).toBeVisible({ timeout: 30_000 });
  const controlsBox = await nav.getByRole('complementary', { name: 'Navigator controls and overlays' }).boundingBox();
  const map = page.getByTestId('site-polar-map').locator('canvas');
  const mapBox = await map.boundingBox();
  const detailBox = await detail.boundingBox();
  expect(controlsBox!.x).toBeLessThan(mapBox!.x);
  expect(detailBox!.x).toBeGreaterThan(mapBox!.x);
  await selector.selectOption('haworth');
  await expect(detail).toContainText('Haworth');
  await expect(detail).toContainText('East longitude');
  await expect(page).toHaveURL(/\/dashboard/);

  const response = await page.request.get('/api/raven/sites');
  const catalog = await response.json();
  const site = catalog.sites.find((s: { id: string }) => s.id === 'malapert-massif');
  const rho = (90 + site.lat_deg) / 15;
  const theta = site.lon_deg_east * Math.PI / 180;
  await map.click({ position: { x: mapBox!.width / 2 * (1 + rho * Math.sin(theta)), y: mapBox!.height / 2 * (1 - rho * Math.cos(theta)) } });
  await expect(selector).toHaveValue('malapert-massif');
  await expect(detail).toContainText('Malapert');
  await expect(page).toHaveURL(/\/dashboard/);
  await nav.getByRole('button', { name: '3D Moon' }).click();
  await expect(nav.locator('button.marker[data-place="malapert-massif"][aria-pressed="true"]')).toBeVisible();
  await nav.getByRole('button', { name: 'Places and data for Moon' }).click();
  await nav.locator('button.place[data-place="haworth"]').click();
  await expect(selector).toHaveValue('haworth');
  await expect(detail).toContainText('Haworth');
  await nav.getByRole('button', { name: 'Polar map' }).click();
  await selector.selectOption('malapert-massif');

  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(selector).toHaveValue('malapert-massif');
  await detail.getByRole('button', { name: 'Open in Planner' }).click();
  await expect(page).toHaveURL(/\/mission-planner\?.*site=malapert-massif/);
});

test('dashboard navigator labels are available in Italian', async ({ page }) => {
  await page.goto('/dashboard?lang=it');
  const nav = page.getByTestId('dashboard-navigator');
  await expect(nav.getByRole('complementary', { name: 'Controlli e livelli del navigatore' })).toBeVisible({ timeout: 30_000 });
  await page.locator('#dashboard-site').selectOption('haworth');
  await expect(page.getByTestId('dashboard-site-detail')).toContainText('Longitudine est');
  await expect(page.getByTestId('dashboard-site-detail').getByRole('button', { name: 'Apri nel Planner' })).toBeVisible();
});

// Mission control: the sessions panel, the Lunar Landing Sites Navigator with overlays, the key numbers and the charts.
test('dashboard without a session: navigator, data-coverage overlay with its legend, rover view disabled', async ({ page }) => {
  await page.goto('/dashboard?lang=en');
  const nav = page.getByTestId('dashboard-navigator');
  await expect(nav).toBeVisible({ timeout: 30_000 });
  await expect(nav.getByRole('button', { name: 'Rover scene' })).toBeDisabled();
  await expect(nav.getByRole('button', { name: 'Polar map' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('site-polar-map').locator('canvas')).toBeVisible();
  await nav.getByRole('radio', { name: 'Data coverage' }).check();
  const legend = page.getByTestId('overlay-legend');
  await expect(legend).toContainText('LOLA 20 m', { timeout: 20_000 });
  await expect(legend).toContainText('LOLA 240 m');
  await expect(legend).toContainText('Hatched: no data');
  await nav.getByRole('radio', { name: 'Sunlight share (2027)' }).check();
  await expect(legend).toContainText('0 – 100 %', { timeout: 20_000 });
  await expect(legend).toContainText('Not validated against NASA illumination products');
  // the availability layers: both bodies at once and the longest gaps
  await nav.getByRole('radio', { name: 'Sun and Earth together (2027)' }).check();
  await expect(legend).toContainText('0 – 100 %', { timeout: 20_000 });
  await nav.getByRole('radio', { name: 'Longest night without Sun' }).check();
  await expect(legend).toContainText(' h', { timeout: 20_000 });
  await nav.getByRole('radio', { name: 'Longest blackout without Earth' }).check();
  await expect(legend).toContainText('blackout', { timeout: 20_000 });
  await nav.getByRole('radio', { name: 'False colour: Sun, Earth, slope' }).check();
  await expect(legend).toContainText('Red: share of 2027 with the Sun', { timeout: 20_000 });
  await expect(legend).toContainText('Blue: regional slope');
  await expect(page.getByTestId('dashboard-navigator').getByRole('alert')).toHaveCount(0); // a composite that drew is not an error
  // the same overlay on the 3D Moon
  await nav.getByRole('button', { name: '3D Moon' }).click();
  await expect(page.locator('#viewer-stage')).toBeVisible({ timeout: 30_000 }); // the 3D Moon of the Sites page
  await expect(legend).toContainText('Red: share of 2027 with the Sun');
  await nav.getByRole('radio', { name: 'Height (LOLA)' }).check();
  await expect(legend).toContainText(' m', { timeout: 20_000 });
  await nav.getByRole('button', { name: 'Polar map' }).click();
  await nav.getByRole('radio', { name: 'None' }).check();
  await expect(legend).toContainText('No overlay selected');
  expect((await new AxeBuilder({ page }).include('[data-testid="dashboard-navigator"]').analyze()).violations).toEqual([]);
});

test('dashboard after a simulation: key numbers for A and B, replay, rover view, height overlay', async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto('/mission-planner?lang=en&mp_step=period&site=malapert-massif&t=2027-04-16T00:00:00Z&mode=avanzato');
  await page.locator('#journey-days').fill('7');
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  await openSimulationDetails(page);
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Dashboard' }).click();
  const kpi = page.getByTestId('dashboard-kpi');
  await expect(kpi.locator('article[data-scenario="A"]')).toContainText('Malapert', { timeout: 30_000 });
  await expect(kpi.locator('article[data-scenario="B"]')).toBeVisible();
  await expect(kpi.locator('article[data-scenario="A"]')).toContainText(/Useful|h/);
  await page.locator('#dashboard-site').selectOption('haworth');
  await expect(page.getByRole('button', { name: /Inspect scenario B/ })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#dashboard-site').selectOption('malapert-massif');
  await expect(page.getByRole('button', { name: /Inspect scenario A/ })).toHaveAttribute('aria-pressed', 'true');
  // the replay moves the shared cursor: the label of the timeline changes
  const label = page.locator('label[for="journey-time"]');
  const before = await label.innerText();
  await kpi.getByRole('button', { name: /Play|Replay|Riproduci/i }).click();
  await expect.poll(async () => label.innerText(), { timeout: 10_000 }).not.toBe(before);
  const nav = page.getByTestId('dashboard-navigator');
  await nav.getByRole('button', { name: '3D Moon' }).click();
  await page.locator('#dashboard-site').selectOption('haworth');
  await expect(page.getByRole('button', { name: /Inspect scenario B/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(nav.locator('button.marker[data-place="haworth"][aria-pressed="true"]')).toBeVisible();
  const afterSelection = await label.innerText();
  await expect.poll(async () => label.innerText(), { timeout: 10_000 }).not.toBe(afterSelection);
  await expect(page.locator('#dashboard-site')).toHaveValue('haworth');
  await kpi.getByRole('button', { name: /Pause|Pausa/i }).click();
  // the height overlay needs the shipped raster: it must show a legend with metres, or an honest "not available"
  await nav.getByRole('radio', { name: 'Height (LOLA)' }).check();
  await expect(page.getByTestId('overlay-legend')).toContainText(/ m|not available/, { timeout: 30_000 });
  await nav.getByRole('button', { name: 'Rover scene' }).click();
  await expect(page.locator('#lander-stage')).toBeVisible({ timeout: 60_000 });
});

test('sites page: the same overlays on the 3D Moon', async ({ page }) => {
  await page.goto('/siti?lang=en');
  const legend = page.getByTestId('overlay-legend');
  await expect(page.locator('#viewer-stage')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('radio', { name: 'Sunlight share (2027)' }).check();
  await expect(legend).toContainText('0 – 100 %', { timeout: 20_000 });
  await expect(legend).toContainText('Not validated against NASA illumination products');
  await expect(page.getByTestId('overlay-scope')).toContainText('Whole Moon'); // the 3D Moon shows the whole surface
  await page.getByRole('radio', { name: 'Data coverage' }).check();
  await expect(legend).toContainText('LOLA global 237 m', { timeout: 20_000 });
  await page.getByRole('radio', { name: 'None' }).check();
  await expect(legend).toContainText('No overlay selected');
});
