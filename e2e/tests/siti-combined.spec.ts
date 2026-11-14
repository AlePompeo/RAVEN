// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('globo e classifica condividono sito e ora senza perdere lo scenario del risultato', async ({ page }) => {
  await page.goto('/siti?site=shackleton&t=2027-04-07T00:00:37Z&gain=10&mode=avanzato');
  await expect(page.getByTestId('siti-combined')).toBeVisible();
  await expect(page.locator('.stage[data-ready="1"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('#g-start')).toHaveValue('2027-04-07T00:00:37');
  await page.getByLabel('Haworth').check();
  await page.getByLabel('Durata (giorni)').fill('3');
  await page.getByLabel('Passo (minuti)').fill('60');
  const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByTestId('rank-table')).toBeVisible({ timeout: 30_000 });
  const updatedSnapshot = page.waitForResponse((r) => r.url().includes('/api/raven/snapshot?') && new URL(r.url()).searchParams.get('gain_dbi') === '20');
  await page.locator('#g-gain').fill('20');
  expect((await updatedSnapshot).status()).toBe(200);

  const sky = page.getByTestId('sky-time');
  const skyToggle = sky.getByRole('button', { name: /Data e ora UTC/ });
  if (await skyToggle.isVisible()) await skyToggle.click();
  await page.locator('#g-start').fill('2027-04-10T12:34:56');
  await expect(page.locator('#sky-date')).toHaveValue('2027-04-10');
  await expect(page.locator('#sky-time')).toHaveValue('12:34:56');
  await expect(page.getByText('Lo scenario è cambiato. Esegui di nuovo il confronto per aggiornare la classifica.')).toBeVisible();
  await page.locator('#sky-date').fill('2027-04-11');
  await page.locator('#sky-date').dispatchEvent('change');
  await expect(page.locator('#g-start')).toHaveValue('2027-04-11T12:34:56');

  await page.getByRole('button', { name: 'Mostra sul globo: Haworth' }).click();
  await expect(page.locator('.place[data-place="haworth"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Mostra sul globo: Haworth' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#g-start')).toHaveValue('2027-04-07T00:00:37');
  await expect(page.locator('#sky-time')).toHaveValue('00:00:37');
  await expect(page.locator('#g-gain')).toHaveValue('10');
  await expect(page.getByText('Lo scenario è cambiato. Esegui di nuovo il confronto per aggiornare la classifica.')).toHaveCount(0);
  await expect(page).toHaveURL(/\/siti\?/);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole('tab', { name: 'Terra', exact: true }).click();
  await page.getByRole('button', { name: 'Mostra sul globo: Haworth' }).click();
  await expect(page.locator('.viewer')).toHaveAttribute('data-body', 'moon');
  const placesToggle = page.getByRole('button', { name: /Luoghi e dati di Luna/ });
  if (await placesToggle.isVisible()) await placesToggle.click();
  await page.locator('.place[data-place="shackleton"]').click();
  await expect(page.getByRole('button', { name: 'Mostra sul globo: Shackleton' })).toHaveAttribute('aria-pressed', 'true');
  await sky.getByRole('button', { name: 'Riproduci' }).click();
  await expect(sky.getByRole('button', { name: 'Ferma' })).toBeVisible();
  await expect(page.locator('#g-start')).not.toHaveValue('2027-04-07T00:00:37');
  await expect(sky.getByRole('button', { name: 'Ferma' })).toBeVisible();
  await page.locator('#g-start').fill('2027-04-15T12:00:01');
  await expect(sky.getByRole('button', { name: 'Riproduci' })).toBeVisible();
  await expect(page.locator('#sky-date')).toHaveValue('2027-04-15');
});

test('scegliere un sito sul globo aggiorna un confronto con un solo sito', async ({ page }) => {
  await page.goto('/siti?site=shackleton&t=2027-04-07T00:00:00Z&mode=avanzato');
  await expect(page.getByRole('checkbox', { name: 'Shackleton' })).toBeChecked();
  const placesToggle = page.getByRole('button', { name: /Luoghi e dati di Luna/ });
  if (await placesToggle.isVisible()) await placesToggle.click();
  await page.locator('.place[data-place="haworth"]').click();
  await expect(page.getByRole('checkbox', { name: 'Haworth' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Shackleton' })).not.toBeChecked();
  await page.evaluate(() => window.scrollTo(0, 0));
  const skyToggle = page.getByTestId('sky-time').getByRole('button', { name: /Data e ora UTC/ });
  if (await skyToggle.isVisible()) await skyToggle.click();
  await page.getByRole('button', { name: 'Un’ora avanti' }).click();
  await expect(page.locator('.place[data-place="haworth"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#g-start')).toHaveValue('2027-04-07T01:00');
});

test('vista unificata utilizzabile su schermo stretto', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/siti?t=2027-04-07T00:00:00Z&mode=avanzato');
  await expect(page.getByTestId('siti-combined')).toBeVisible();
  await expect(page.locator('#g-start')).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('Durata (giorni)').fill('0.1');
  await page.getByLabel('Passo (minuti)').fill('60');
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  await expect(page.getByTestId('rank-table')).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Avoid checking a partially scrolled checkbox underneath the sticky navigation.
  await page.evaluate(() => window.scrollTo(0, 0));
  const report = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  expect(report.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
});
