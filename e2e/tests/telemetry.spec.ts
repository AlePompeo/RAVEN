// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

// Integrazione reale: CSV (e2e/fixtures) -> csv_replay -> hub -> SSE /api/telemetry/stream -> EventSource -> parseSample -> tabella.
test('la pagina telemetria riceve campioni SSE reali dal replay del backend', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/telemetry');
  await expect(page.getByRole('status').first()).toContainText('Connesso');
  await expect(page.getByTestId('telemetry-provenance')).toContainText('non sono identificati come misure');

  const rows = page.getByRole('region', { name: 'Ultimi campioni' }).locator('tbody tr');
  await expect(rows.first()).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => rows.count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(3);

  // i valori arrivano dalla fixture: power_w 101.5..105.5, sito e2e-site, istanti 2026-10-12T10:00:0x
  const powers = await rows.locator('td:nth-child(3)').allTextContents();
  for (const p of powers) expect(p).toMatch(/^10[1-5]\.5$/);
  const sites = await rows.locator('td:nth-child(2)').allTextContents();
  for (const s of sites) expect(s).toBe('e2e-site');
  await expect(rows.first().locator('th')).toHaveText(/^2026-10-12T10:00:0[0-4]Z$/);

  // uPlot reale: canvas disegnato nel contenitore del grafico
  await expect(page.locator('.chart canvas').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('Spiega usa l’ultimo campione ricevuto senza presentarlo come misura', async ({ page }) => {
  await page.goto('/telemetry');
  await expect(page.locator('.site')).toHaveText('e2e-site', { timeout: 15_000 });
  await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
  await sheet.locator('details.settings > summary').click();
  await sheet.getByLabel('Includi i parametri tecnici visibili').check(); // the values are shared only when the user includes them
  await expect(sheet.getByTestId('explain-context')).toContainText('provenienza = non specificata');
  const request = page.waitForRequest((r) => r.url().endsWith('/api/assistant/chat'));
  await sheet.getByLabel('La tua domanda').fill('Come si legge il margine?');
  await sheet.getByRole('button', { name: 'Invia' }).click();
  const body = (await request).postDataJSON();
  expect(body.page_context).toMatchObject({
    page_id: 'telemetry',
    params: { sito: 'e2e-site', provenienza: 'non specificata', stato_flusso: 'open' },
  });
  expect(body.page_context.params.potenza_w).toBeGreaterThanOrEqual(101.5);
  expect(body.page_context.params.istante_utc).toMatch(/^2026-10-12T10:00:0[0-4]Z$/);
  await expect(sheet.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
});

test('importa CSV del link senza attribuire una provenienza o un confronto non verificati', async ({ page }) => {
  await page.goto('/telemetry');
  const file = page.getByLabel('Scegli un file CSV');
  await file.setInputFiles({
    name: 'link.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('t_utc,link_margin_db,earth_el_deg,rate_bps\n2026-10-12T10:00:00Z,6.2,0.9,100000\n'),
  });
  await expect(page.getByRole('status').filter({ hasText: '1 campioni caricati da link.csv' })).toBeVisible();
  await expect(page.getByText('Questi campioni non sono ancora confrontati con le previsioni del modello.')).toBeVisible();
  const table = page.getByRole('table', { name: 'Telemetria del link, primi 50 campioni' });
  await expect(table.getByRole('row').last()).toContainText('6.2');

  await file.setInputFiles({
    name: 'bad.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('t_utc,link_margin_db,earth_el_deg,rate_bps\n2026-10-12T10:00:00Z,NaN,0.9,100000\n'),
  });
  await expect(page.getByRole('alert')).toContainText('Dati CSV non validi alla riga 2');
  await expect(table).toHaveCount(0);
});

test('confronta il CSV con il modello per il sito selezionato', async ({ page }) => {
  await page.goto('/telemetry');
  await expect(page.locator('.site')).toHaveText('e2e-site', { timeout: 15_000 });
  await page.getByLabel('Scegli un file CSV').setInputFiles({
    name: 'link.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('t_utc,link_margin_db,earth_el_deg,rate_bps\n2026-10-12T10:00:00Z,6,0.9,100000\n2026-10-12T10:00:30Z,-1,0.8,100000\n'),
  });
  const site = page.getByLabel('Sito dei campioni');
  await expect(site.locator('option[value="malapert-massif"]')).toHaveCount(1, { timeout: 15_000 });
  await site.selectOption('malapert-massif');
  const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Confronta con il modello' }).click();
  const res = await response;
  expect(res.ok()).toBeTruthy();
  expect(res.request().postDataJSON().site_id).toBe('malapert-massif');
  await expect(page.getByRole('status').filter({ hasText: 'Confrontati 2 campioni su 2' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('Bias', { exact: false })).toContainText('sequenze con margine negativo: 1');
  await expect(page.getByRole('columnheader', { name: 'Residuo (dB)' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Margini importati e previsti/ })).toBeVisible();
  await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
  await sheet.locator('details.settings > summary').click();
  await sheet.getByLabel('Includi i parametri tecnici visibili').check(); // the values are shared only when the user includes them
  await expect(sheet.getByTestId('explain-context')).toContainText('CSV, provenienza non verificata');
  const chat = page.waitForRequest((r) => r.url().endsWith('/api/assistant/chat'));
  await sheet.getByLabel('La tua domanda').fill('Come si legge il confronto?');
  await sheet.getByRole('button', { name: 'Invia' }).click();
  expect((await chat).postDataJSON().page_context.params).toMatchObject({
    link_provenienza: 'CSV, provenienza non verificata',
    link_ultimo_margine_db: -1,
    link_sito_selezionato: 'malapert-massif',
    link_campioni_confrontati: 2,
  });
  const params = (await chat).postDataJSON().page_context.params;
  for (const [key, value] of Object.entries(params)) {
    if (!key.startsWith('link_')) continue;
    await sheet.locator('details.settings > summary').click();
    await sheet.getByLabel('Includi i parametri tecnici visibili').check(); // the values are shared only when the user includes them
    await expect(sheet.getByTestId('explain-context')).toContainText(`${key} = ${value}`);
  }
});

test('genera telemetria di esempio etichettata come simulata, non misurata', async ({ page }) => {
  await page.goto('/telemetry?site=malapert-massif&t=2026-10-12T10%3A00%3A00Z');
  const site = page.getByLabel('Sito dei campioni');
  await expect(site).toHaveValue('malapert-massif', { timeout: 15_000 });
  await page.getByRole('button', { name: 'Genera esempio simulato' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'campioni simulati dal modello con rumore, non misure' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('status').filter({ hasText: 'Confrontati' })).toBeVisible();
  await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
  await page.locator('details.settings > summary').click();
  await page.getByLabel('Includi i parametri tecnici visibili').check(); // the values are shared only when the user includes them
  await expect(page.getByTestId('explain-context')).toContainText('simulati dal modello, non misure');
  await page.getByRole('button', { name: 'Riduci RAVEN SI' }).click();
  await site.selectOption('shackleton');
  await expect(page.getByText('campioni simulati dal modello con rumore, non misure')).toHaveCount(0);
});
