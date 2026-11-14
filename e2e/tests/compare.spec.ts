// SPDX-License-Identifier: Apache-2.0
// Classifica dei siti sul modello unico RAVEN (/api/raven/compare) con il backend reale: componenti visibili,
// nessun punteggio, siti non confrontabili a parte con il motivo, tetto dei passi, errori simulati.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const form = (page: Page) => page.locator('form[aria-labelledby="g-setup-h"]');
const run = (page: Page) => page.getByRole('button', { name: 'Confronta con RAVEN' }).click();

async function setup(page: Page, sites: string[], days = '1', step = '60'): Promise<void> {
  await page.goto('/compare?mode=avanzato');
  await expect(page.getByLabel('Durata (giorni)')).toBeVisible();
  await page.getByRole('button', { name: 'Nessuno' }).click();
  for (const s of sites) await form(page).getByLabel(s).check();
  await page.getByLabel('Durata (giorni)').fill(days);
  await page.getByLabel('Passo (minuti)').fill(step);
}

test('classifica unica: componenti visibili, nessun punteggio, modello dichiarato', async ({ page }) => {
  await setup(page, ['Shackleton', 'Malapert Massif']);
  const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
  await run(page);
  const r = await response;
  expect(r.status()).toBe(200);
  const body = (await r.json()) as { model_version: string; ranking: { score: null; order: string[]; ranking: { site_id: string; components: Record<string, unknown> }[] } };
  expect(body.ranking.score).toBeNull();
  const table = page.getByTestId('rank-table');
  await expect(table).toBeVisible({ timeout: 30_000 });
  expect(body.ranking.ranking.length).toBeGreaterThan(0);
  await expect(table.locator('tbody tr')).toHaveCount(body.ranking.ranking.length);
  for (const c of ['useful_hours', 'unknown_hours', 'margin_min_db', 'margin_median_db', 'min_soc']) await expect(table.locator(`th[data-component="${c}"]`)).toBeVisible();
  await expect(table.locator('thead')).not.toContainText(/punteggio/i);
  await expect(page.getByTestId('rank-stamp')).toContainText(body.model_version);
  await expect(page.getByTestId('ranking-rule')).toContainText('site id');
  // l'ordine mostrato e' quello del modello
  const ids = await table.locator('tbody tr').evaluateAll((rows) => rows.map((x) => x.getAttribute('data-site')));
  expect(ids).toEqual(body.ranking.ranking.map((x) => x.site_id));
  const report = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(report.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
});

test('un sito senza terreno LOLA sta tra i non confrontabili con il motivo', async ({ page }) => {
  await setup(page, ['Malapert Massif', 'Apollo 11']);
  await run(page);
  const nc = page.getByTestId('not-comparable');
  await expect(nc).toBeVisible({ timeout: 30_000 });
  await expect(nc.locator('li[data-site="apollo11"]')).toContainText('unknown');
  await expect(page.getByTestId('rank-table').locator('tbody tr')).toHaveCount(1);
});

test('la finestra lunare di 29,53 giorni a 10 minuti e oltre il tetto e viene spiegata prima della chiamata', async ({ page }) => {
  await setup(page, ['Shackleton'], '29.53', '10');
  let called = false;
  page.on('request', (q) => { if (q.url().endsWith('/api/raven/compare')) called = true; });
  await run(page);
  await expect(page.getByRole('alert').first()).toContainText(/1\.?500/);
  expect(called).toBe(false);
});

test('errore del server mostrato senza risultati inventati', async ({ page }) => {
  await setup(page, ['Shackleton']);
  await page.route('**/api/raven/compare', (route) => route.fulfill({ status: 503, json: { detail: 'efemeridi non disponibili' } }));
  await run(page);
  await expect(page.getByRole('alert').first()).toContainText(/Efemeridi non disponibili/);
  await expect(page.getByTestId('rank-table')).toHaveCount(0);
});
