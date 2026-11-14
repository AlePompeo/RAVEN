// SPDX-License-Identifier: Apache-2.0
// Sito personalizzato da coordinate con il backend reale: un punto polare (stesse coordinate di Malapert Massif, longitudine
// scritta 0-360, quindi le tessere LOLA sono gia' in cache: nessun download) compare nella tabella del confronto e nella
// scena; un sito senza terreno resta "sconosciuto" con la spiegazione; per un sito che richiede dati la finestra di conferma
// chiede prima (e "Non ora" non scarica nulla).
import { test, expect, type Page } from '@playwright/test';

const CS = 'c-polo-prova~-85.98~-1.67~Polo prova';

async function openCompare(page: Page): Promise<void> {
  await page.goto('/compare?mode=avanzato');
  await expect(page.getByLabel('Durata (giorni)')).toBeVisible();
  await page.getByRole('button', { name: 'Nessuno' }).click();
  await page.getByLabel('Durata (giorni)').fill('1');
  await page.getByLabel('Passo (minuti)').fill('60');
}

async function addSite(page: Page, name: string, lat: string, lon: string): Promise<void> {
  await page.getByTestId('custom-toggle').click();
  await expect(page.getByTestId('custom-panel')).toBeVisible();
  await page.locator('#cs-name').fill(name);
  await page.locator('#cs-lat').fill(lat);
  await page.locator('#cs-lon').fill(lon);
  await page.getByTestId('custom-add').click();
  await expect(page.getByTestId('custom-list')).toContainText(name);
}

test('sito polare personalizzato: validazione, tabella del confronto e scena', async ({ page }) => {
  await openCompare(page);
  await page.getByTestId('custom-toggle').click();
  // messaggi di errore per campo, nessun invio
  await page.locator('#cs-lat').fill('95');
  await page.locator('#cs-lon').fill('400');
  await page.getByTestId('custom-add').click();
  await expect(page.locator('#cs-name-err')).not.toBeEmpty();
  await expect(page.locator('#cs-lat-err')).toContainText('−90');
  await expect(page.locator('#cs-lon-err')).toContainText('360');
  await expect(page.getByTestId('custom-list')).toHaveCount(0);
  // valori validi: la longitudine 358,33 diventa -1,67
  await page.locator('#cs-name').fill('Polo prova');
  await page.locator('#cs-lat').fill('-85.98');
  await page.locator('#cs-lon').fill('358.33');
  await page.getByTestId('custom-add').click();
  await expect(page.getByTestId('custom-list')).toContainText('-1.6700');
  const site = page.locator('form[aria-labelledby="g-setup-h"]').getByLabel('Polo prova');
  await expect(site).toBeChecked();
  await page.locator('form[aria-labelledby="g-setup-h"]').getByLabel('Malapert Massif').check();
  const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  const r = await response;
  expect(r.status()).toBe(200);
  const body = (await r.json()) as { sites: { site: { id: string; custom: boolean; verified: boolean }; terrain: { state: string; resolution_m: number | null } }[] };
  const mine = body.sites.find((s) => s.site.id === 'c-polo-prova')!;
  expect(mine.site.custom).toBe(true);
  expect(mine.site.verified).toBe(false);
  expect(mine.terrain).toMatchObject({ state: 'known', resolution_m: 20 }); // la risoluzione del prodotto e' nel risultato
  const table = page.getByTestId('rank-table');
  await expect(table.locator('tbody tr')).toHaveCount(2, { timeout: 30_000 });
  await expect(table.locator('tbody tr[data-site="c-polo-prova"]')).toBeVisible();
  // la scena (pagina Lander) con lo stesso sito: l'URL porta la definizione compatta (cs=)
  await page.goto(`/lander?site=c-polo-prova&t=2027-04-07T00:00:00Z&cs=${encodeURIComponent(CS)}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Scena lander' })).toBeVisible();
  await expect(page.locator('#l-site')).toHaveValue('c-polo-prova');
  await expect(page.getByTestId('lander-status')).toHaveText(/Scena aggiornata/, { timeout: 60_000 });
});

test('sito senza terreno: ignoto, spiegato, mai orizzonte piatto', async ({ page }) => {
  await openCompare(page);
  await addSite(page, 'Polo nord', '89.9', '10');
  await expect(page.getByTestId('custom-list')).toContainText(/Terreno sconosciuto/);
  await page.locator('form[aria-labelledby="g-setup-h"]').getByLabel('Shackleton').check();
  const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  const r = await response;
  expect(r.status()).toBe(200);
  const body = (await r.json()) as { sites: { site: { id: string }; terrain: { state: string; reason: string; resolution_m: number | null }; metrics: { unknown_steps: number; n_steps: number } }[] };
  const pole = body.sites.find((s) => s.site.id === 'c-polo-nord')!;
  expect(pole.terrain).toMatchObject({ state: 'unknown', resolution_m: null });
  expect(pole.metrics.unknown_steps).toBe(pole.metrics.n_steps);
  const nc = page.getByTestId('not-comparable');
  await expect(nc).toBeVisible({ timeout: 30_000 });
  await expect(nc.locator('li[data-site="c-polo-nord"]')).toContainText('unknown');
});

test('sito che richiede dati: la stima e la conferma vengono prima, "Non ora" non scarica nulla', async ({ page }) => {
  await openCompare(page);
  await addSite(page, 'Equatore', '0', '40');
  await expect(page.getByTestId('custom-list')).toContainText(/circa [\d.]+ MB/);
  await page.locator('form[aria-labelledby="g-setup-h"]').getByLabel('Equatore').check();
  await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
  const prompt = page.getByTestId('terrain-prompt');
  await expect(prompt).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('terrain-prompt-mb')).toContainText(/circa [\d.]+ MB/);
  const downloads: string[] = [];
  page.on('request', (q) => { if (q.url().includes('allow_download') || (q.postData() ?? '').includes('allow_download')) downloads.push(q.url()); });
  await page.getByTestId('terrain-cancel').click();
  await expect(prompt).toHaveCount(0);
  await expect(page.getByRole('alert').first()).toBeVisible();
  expect(downloads).toEqual([]);
});
