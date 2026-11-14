// SPDX-License-Identifier: Apache-2.0
// Pagina RAVEN con il backend reale (DEM LOLA in cache in build/lola, efemeridi): analisi breve su un sito coperto,
// profilo dell'utente con crinale sintetico (senza DEM), errori 503/422 simulati, schede da tastiera, overflow a 390 px, axe.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

interface Windows {
  geometric_hours: number;
  real_hours: number;
  transition_hours: number;
  total_hours: number;
}
interface Result {
  windows: Windows;
  flags: { terrain: { source: string; product_id: string | null } };
}

async function open(page: Page): Promise<void> {
  await page.goto('/grazinglink');
  await expect(page.getByLabel('Durata (giorni)')).toBeVisible();
  await page.getByLabel('Durata (giorni)').fill('1');
  await page.getByLabel('Passo (minuti)').fill('60');
}
const run = (page: Page) => page.getByRole('button', { name: 'Esegui analisi' }).click();
const tab = (page: Page, name: string) => page.getByRole('tab', { name });

async function axe(page: Page, label: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) })), label).toEqual([]);
}
async function noOverflow(page: Page): Promise<void> {
  const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  const wide = o.sw > o.cw ? await page.evaluate((cw) => [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > cw + 1).slice(0, 4).map((e) => e.tagName + '.' + e.className + ':' + Math.round(e.getBoundingClientRect().right) + '@' + (document.querySelector('[role=tab][aria-selected=true]')?.textContent ?? 'form')).join(' | '), o.cw) : '';
  expect(o.sw, `scrollWidth ${o.sw} > clientWidth ${o.cw}: ${wide}`).toBeLessThanOrEqual(o.cw);
}
/** Analisi con crinale sintetico di prova e spazzolamento della Terra: non servono DEM ne' efemeridi. */
async function runSynthetic(page: Page): Promise<Result> {
  await page.getByRole('button', { name: 'Usa un crinale sintetico di prova' }).click();
  await expect(page.getByTestId('profile-loaded')).toContainText('crinale-sintetico-di-prova.csv');
  await page.getByLabel(/spazzolamento/).check();
  const resp = page.waitForResponse((r) => r.url().endsWith('/api/raven/experiments/analyze'));
  await run(page);
  const r = await resp;
  expect(r.status()).toBe(200);
  return (await r.json()) as Result;
}

test.describe('/grazinglink con il backend reale', () => {
  test('modulo: nota sulle ipotesi illustrative, siti fuori copertura DEM disabilitati con il motivo', async ({ page }) => {
    await page.goto('/grazinglink');
    await expect(page.getByTestId('illustrative-note')).toContainText('ipotesi illustrative (tag I)');
    const opts = page.locator('#f-site option');
    expect(await opts.count()).toBeGreaterThan(1);
    const out = page.locator('#f-site option:disabled');
    expect(await out.count()).toBeGreaterThan(0);
    await expect(out.first()).toContainText('fuori copertura DEM');
    await expect(page.getByLabel('Stazione di terra')).toContainText('34');
    await expect(page.getByRole('heading', { level: 1, name: 'Link budget' })).toBeVisible();
  });

  test('analisi su un sito coperto dal DEM: finestre, diffrazione, antenna, compensatore, parametri coincidono con l API', async ({ page }) => {
    await open(page);
    const resp = page.waitForResponse((r) => r.url().endsWith('/api/raven/experiments/analyze'));
    await run(page);
    const r = await resp;
    expect(r.status()).toBe(200);
    const body = (await r.json()) as Result;
    expect(body.flags.terrain.source).toBe('lola');
    const h = (v: number) => `${v.toFixed(1).replace('.', ',')} h`;
    await expect(page.getByTestId('summary-geometric')).toHaveText(h(body.windows.geometric_hours));
    await expect(page.getByTestId('summary-link')).toHaveText(h(body.windows.real_hours));
    await expect(page.getByTestId('summary-transition')).toHaveText(h(body.windows.transition_hours));
    // 1 margine nel tempo: grafici uPlot e tabella alternativa
    await expect(tab(page, 'Margine nel tempo')).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('.chart canvas').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Tabella dei valori', { exact: true })).toBeVisible();
    // 2 finestre: le ore del riepilogo sono quelle della risposta
    await tab(page, 'Finestre').click();
    const sum = page.getByTestId('windows-summary');
    await expect(sum).toContainText('Zona di transizione');
    await expect(sum).toContainText(h(body.windows.geometric_hours));
    await expect(sum).toContainText(h(body.windows.real_hours));
    await expect(sum).toContainText(h(body.windows.transition_hours));
    // 3 diffrazione: curva, mappa di calore con tabella alternativa
    await tab(page, 'Diffrazione').click();
    await expect(page.locator('.chart canvas').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('img', { name: /Mappa di calore/ })).toBeVisible();
    await expect(page.getByText(/Sotto tale soglia lo zero/)).toBeVisible();
    // 4 antenna
    await tab(page, 'Antenna').click();
    await expect(page.getByRole('table', { name: /^Antenne:/ })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('pointing-table')).toBeVisible();
    // 5 compensatore
    await tab(page, 'Compensatore').click();
    await expect(page.getByTestId('tradeoff-table').locator('tbody tr')).not.toHaveCount(0);
    // 6 parametri e limiti
    await tab(page, 'Parametri e limiti').click();
    await expect(page.getByTestId('params-table').locator('.badge').first()).toBeVisible();
    await expect(page.getByTestId('declared-limits')).toContainText('Ostacolo singolo dominante');
    await expect(page.getByTestId('declared-limits')).toContainText('Nessuna misura radio reale al polo Sud');
    await expect(page.getByTestId('declared-limits')).toContainText('la correzione della cresta è T(m,n)');
    // l'incoerenza tra le tre fonti non è più «aperta»: lo stato è la politica ITU-R P.526-9 predefinita, split-step come banda
    await expect(page.getByText(/politica/).first()).toBeVisible();
    await expect(page.getByText(new RegExp(String(body.flags.terrain.product_id))).first()).toBeVisible();
    await axe(page, 'parametri e limiti');
  });

  test('esportazioni CSV e JSON di una scheda', async ({ page }) => {
    await open(page);
    await run(page);
    await tab(page, 'Finestre').click();
    await expect(page.getByTestId('windows-summary')).toBeVisible({ timeout: 30_000 });
    const [csv] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Scarica CSV' }).first().click()]);
    expect(csv.suggestedFilename()).toBe('raven-finestre.csv');
    const [json] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Scarica JSON' }).first().click()]);
    expect(json.suggestedFilename()).toBe('raven-finestre.json');
  });

  test('profilo dell utente con crinale sintetico: funziona senza DEM e mostra "profilo sintetico di prova"', async ({ page }) => {
    await open(page);
    const body = await runSynthetic(page);
    expect(body.flags.terrain.source).toBe('user');
    await expect(page.getByTestId('synthetic-banner')).toContainText('Profilo sintetico di prova');
    await expect(page.getByTestId('windows-summary').or(page.locator('.chart canvas').first()).first()).toBeVisible({ timeout: 15_000 });
    await tab(page, 'Finestre').click();
    await expect(page.getByTestId('windows-summary')).toContainText('Zona di transizione');
    // il crinale e' a ~1,4 gradi: con lo spazzolamento da -1 a 3 gradi la geometria e il link divergono
    expect(body.windows.total_hours).toBeGreaterThan(0);
    await tab(page, 'Parametri e limiti').click();
    await expect(page.getByTestId('synthetic-warning')).toContainText('Profilo sintetico di prova');
    await axe(page, 'profilo sintetico');
  });

  test('il gimbal C simulato contribuisce al puntamento senza essere presentato come hardware', async ({ page }) => {
    await open(page);
    await page.getByLabel('Montaggio antenna').selectOption('gimbal');
    await expect(page.getByText('Simulazione C illustrativa a due assi', { exact: false })).toBeVisible();
    const body = await runSynthetic(page) as Result & {
      antenna: { mount: string; gimbal_mechanical_limit_fraction: number };
      series: { pointing_loss_db: number[] };
    };
    expect(body.antenna.mount).toBe('gimbal');
    expect(body.antenna.gimbal_mechanical_limit_fraction).toBe(0);
    expect(body.series.pointing_loss_db.every(Number.isFinite)).toBe(true);
    await tab(page, 'Antenna').click();
    await expect(page.getByText('Simulazione C illustrativa a due assi', { exact: false }).last()).toBeVisible();
    await expect(page.getByText('Movimento richiesto oltre la corsa meccanica', { exact: false })).toBeVisible();
  });

  test('CSV non valido: messaggio chiaro, nessuna richiesta; file troppo grande rifiutato', async ({ page }) => {
    await open(page);
    let called = false;
    await page.route('**/api/raven/experiments/analyze', (r) => {
      called = true;
      return r.abort();
    });
    await page.getByLabel('File CSV').setInputFiles({ name: 'x.csv', mimeType: 'text/csv', buffer: Buffer.from('5,1\n6,2\n') });
    await expect(page.getByRole('alert').filter({ hasText: 'deve essere 0' })).toBeVisible();
    await page.getByLabel('File CSV').setInputFiles({ name: 'big.csv', mimeType: 'text/csv', buffer: Buffer.alloc(70_000, '0,0\n') });
    await expect(page.getByRole('alert').filter({ hasText: 'troppo grande' })).toBeVisible();
    expect(called).toBe(false);
    await page.getByLabel('File CSV').setInputFiles({ name: 'ok.csv', mimeType: 'text/csv', buffer: Buffer.from('distanza,quota\n0,0\n10,1\n20,0.5\n') });
    await expect(page.getByTestId('profile-loaded')).toContainText('ok.csv, 3 punti');
  });

  test('503 senza LOLA: dice come scaricare i dati; 422: parametri non validi; nessun risultato inventato', async ({ page }) => {
    await open(page);
    await page.route('**/api/raven/experiments/analyze', (r) =>
      r.fulfill({ status: 503, contentType: 'application/json', headers: { 'Retry-After': '30' }, body: JSON.stringify({ detail: 'dati DEM non disponibili' }) }),
    );
    await run(page);
    const alert = page.getByRole('alert').filter({ hasText: 'make grazing-dem' });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('Dati LOLA non disponibili');
    await expect(page.getByRole('tab')).toHaveCount(0);
    await page.unroute('**/api/raven/experiments/analyze');
    await page.route('**/api/raven/experiments/analyze', (r) => r.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'parametri non validi' }) }));
    await run(page);
    await expect(page.getByRole('alert').filter({ hasText: 'Parametri non validi' })).toBeVisible();
    await expect(page.getByRole('tab')).toHaveCount(0);
  });

  test('validazione: durata non valida porta il focus sul campo', async ({ page }) => {
    await open(page);
    await page.getByLabel('Durata (giorni)').fill('0');
    await run(page);
    await expect(page.getByLabel('Durata (giorni)')).toBeFocused();
    await expect(page.getByLabel('Durata (giorni)')).toHaveAttribute('aria-invalid', 'true');
  });

  test('schede da tastiera: frecce, Home, Fine; una sola scheda nel Tab; pannello associato', async ({ page }) => {
    await open(page);
    await runSynthetic(page);
    const first = tab(page, 'Margine nel tempo');
    await first.focus();
    await page.keyboard.press('ArrowRight');
    await expect(tab(page, 'Finestre')).toBeFocused();
    await expect(tab(page, 'Finestre')).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('#panel-windows')).toBeVisible();
    await expect(page.locator('#panel-time')).toBeHidden();
    await page.keyboard.press('End');
    await expect(tab(page, 'Parametri e limiti')).toBeFocused();
    await page.keyboard.press('ArrowRight'); // si richiude sul primo
    await expect(first).toBeFocused();
    await page.keyboard.press('ArrowLeft');
    await expect(tab(page, 'Parametri e limiti')).toBeFocused();
    await page.keyboard.press('Home');
    await expect(first).toBeFocused();
    expect(await page.locator('[role=tab][tabindex="0"]').count()).toBe(1);
    await page.keyboard.press('Tab');
    await expect(page.locator('#panel-time')).toBeFocused();
  });

  test.describe('390 px', () => {
    test.use({ viewport: { width: 390, height: 844 } });
    test('nessun overflow orizzontale in nessuna scheda', async ({ page }) => {
      await open(page);
      await noOverflow(page);
      await runSynthetic(page);
      for (const name of ['Margine nel tempo', 'Finestre', 'Diffrazione', 'Antenna', 'Compensatore', 'Parametri e limiti']) {
        await tab(page, name).click();
        await expect(page.locator('[role=tabpanel]:not([hidden]) h3').first()).toBeVisible({ timeout: 15_000 });
        await page.waitForTimeout(400);
        await noOverflow(page);
      }
    });
  });

  test('axe: modulo, schede Finestre e Diffrazione con i risultati', async ({ page }) => {
    await open(page);
    await axe(page, 'modulo');
    await runSynthetic(page);
    for (const name of ['Margine nel tempo', 'Finestre', 'Diffrazione', 'Antenna', 'Compensatore']) {
      await tab(page, name).click();
      await expect(page.locator('[role=tabpanel]:not([hidden]) h3').first()).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(500);
      await axe(page, name);
    }
  });
});
