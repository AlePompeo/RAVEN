// SPDX-License-Identifier: Apache-2.0
// Visualizzatore RAVEN (Luna e Terra): linea sito-Terra con l'angolo, stato del link sui marcatori, stazioni DSN,
// scenario condiviso nell'URL. Backend reale (kernel e tile LOLA in cache); il 503/422 si simula con una route.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

const T = '2027-04-07T00:00:00Z';
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const OUT = 'test-results/ui/viewer-grazing';
const dec = (v: number, d: number) => v.toFixed(d).replace('.', ',');
const angleText = (el: number) => `Terra a ${dec(Math.abs(el), 1)}° ${el < 0 ? 'sotto l’orizzonte' : 'sull’orizzonte'}`;

interface Site {
  id: string;
  state: string;
  earth_el_deg: number;
  earth_az_deg: number;
  margin_db: number | null;
}
interface Snap {
  sites: Site[];
  earth_moon_range_km: number;
  fspl_delta_db: number;
  dsn: { best_complex: string | null; complexes: { complex: string; moon_el_deg: number; sees_moon: boolean }[] };
}
const RATE = 100000;

async function api(page: Page, t = T): Promise<Snap> {
  const r = await page.request.get(`/api/raven/snapshot?t=${encodeURIComponent(t)}&rate_bps=${RATE}&station=dsn34`);
  expect(r.status()).toBe(200);
  return (await r.json()) as Snap;
}

async function open(page: Page, body = 'moon', t = T): Promise<void> {
  await page.goto(`/viewer?body=${body}&t=${encodeURIComponent(t)}&mode=avanzato`); // il delta FSPL e' un dettaglio della modalita' Avanzata
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.getByRole('button', { name: 'Controlli e impostazioni' }).click();
  }
  await expect(page.getByTestId('fspl-delta')).toBeVisible({ timeout: 20_000 });
}

const place = (page: Page, id: string) => page.locator(`.place[data-place="${id}"]`);

test.describe('Luna: sito, linea verso la Terra e stato del link', () => {
  test('selezionare un sito disegna la linea e scrive l’angolo uguale a /api/raven/snapshot', async ({ page }) => {
    await open(page);
    const snap = await api(page);
    const hw = snap.sites.find((s) => s.id === 'haworth')!;
    await place(page, 'haworth').click();
    await expect(page.getByTestId('dir-line')).toBeVisible();
    await expect(page.getByTestId('dir-label')).toContainText(angleText(hw.earth_el_deg));
    await expect(page.getByTestId('detail-earth')).toContainText(angleText(hw.earth_el_deg));
    await expect(page.getByTestId('detail-earth')).toContainText(`azimut ${dec(hw.earth_az_deg, 1)}°`);
    const label = { open: 'aperto', transition: 'transizione', blocked: 'bloccato' }[hw.state]!;
    await expect(page.getByTestId('detail-state')).toContainText(label);
    if (hw.margin_db === null) {
      await expect(page.getByTestId('detail-state')).not.toContainText('dB');
    } else {
      await expect(page.getByTestId('detail-state')).toContainText(`${dec(hw.margin_db, 1)} dB`);
    }
    await page.screenshot({ path: `${OUT}/moon-haworth-1440.png` });
  });

  test('i marcatori hanno colore e testo: aperto / transizione / bloccato / terreno da scaricare', async ({ page }) => {
    await open(page);
    const snap = await api(page);
    const names: Record<string, string> = { open: 'aperto', transition: 'transizione', blocked: 'bloccato',
      out_of_coverage: 'fuori copertura DEM', unknown: 'sconosciuto',
      unavailable: 'dati DEM non disponibili', needs_download: 'terreno da scaricare' };
    for (const s of snap.sites) {
      const row = place(page, s.id);
      await expect(row).toHaveAttribute('data-state', s.state);
      await expect(row).toContainText(names[s.state]!);
    }
    // un sito fuori dal prodotto a 20 m: con il terreno globale in cache ha uno stato calcolato, altrimenti "terreno da scaricare";
    // mai un valore inventato e mai "fuori copertura" (un sito con un terreno possibile)
    const apollo = snap.sites.find((s) => s.id === 'apollo11')!;
    expect(apollo.state).not.toBe('out_of_coverage');
    await place(page, 'apollo11').click();
    await expect(page.getByTestId('detail-state')).toContainText(names[apollo.state]!);
    if (apollo.state === 'needs_download') await expect(page.getByTestId('detail-state')).not.toContainText('dB');
    await expect(page.getByTestId('detail-earth')).toContainText('Terra a');
  });

  test('cambiare data aggiorna angolo e stato con il valore del backend (richieste limitate)', async ({ page }) => {
    await open(page);
    await place(page, 'haworth').click();
    const calls: string[] = [];
    page.on('request', (r) => r.url().includes('/api/raven/snapshot') && calls.push(r.url()));
    const t2 = '2027-04-20T00:00:00Z';
    const expected = (await api(page, t2)).sites.find((s) => s.id === 'haworth')!;
    const before = await page.getByTestId('dir-label').innerText();
    await page.getByLabel('Data', { exact: true }).fill('2027-04-20');
    await page.getByLabel('Data', { exact: true }).dispatchEvent('change');
    await expect(page.getByTestId('detail-earth')).toContainText(angleText(expected.earth_el_deg), { timeout: 10_000 });
    await expect(page.getByTestId('dir-label')).toContainText(angleText(expected.earth_el_deg));
    expect(await page.getByTestId('dir-label').innerText()).not.toBe(before);
    await expect(page).toHaveURL(/t=2027-04-20T00%3A00%3A00Z/);
    // passi rapidi: una sola richiesta per istante assestato, mai una per clic
    calls.length = 0;
    for (let i = 0; i < 5; i++) await page.getByRole('button', { name: 'Un’ora avanti' }).click();
    await page.waitForTimeout(2500);
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls.length).toBeLessThanOrEqual(3);
  });

  test('503 e 422 del servizio: messaggio, nessuno stato inventato', async ({ page }) => {
    await page.route('**/api/raven/snapshot**', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"x"}' }));
    await page.goto(`/viewer?t=${encodeURIComponent(T)}`);
    await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
    await expect(page.getByTestId('snap-problem')).toContainText('non disponibile');
    await expect(place(page, 'haworth')).toHaveAttribute('data-state', 'unavailable');
    await expect(place(page, 'haworth')).toContainText('stato non disponibile');
    await expect(page.getByTestId('fspl-delta')).toHaveCount(0);
    await page.unroute('**/api/raven/snapshot**');
    await page.route('**/api/raven/snapshot**', (route) => route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"x"}' }));
    await page.getByRole('button', { name: 'Un’ora avanti' }).click();
    await expect(page.getByTestId('snap-problem')).toContainText('non validi');
  });

  test('tastiera: il sito si sceglie con Invio dall’elenco; Apri scena lander porta alla scena con sito e istante', async ({ page }) => {
    await open(page);
    await place(page, 'shackleton').focus();
    await page.keyboard.press('Enter');
    await expect(place(page, 'shackleton')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('dir-label')).toBeVisible();
    const lander = page.getByTestId('open-lander');
    await expect(lander).toContainText('Apri scena lander');
    await expect(lander).not.toContainText('in arrivo');
    await expect(lander).toHaveAttribute('href', /\/lander\?site=shackleton/);
  });

  test('"Analisi completa" porta lo scenario (sito, istante, stazione, velocità) a /analizza', async ({ page }) => {
    await open(page, 'moon', '2027-04-07T00:00:45Z');
    await place(page, 'malapert-massif').click();
    const link = page.getByTestId('open-analysis');
    await expect(link).toHaveAttribute('href', /\/analizza\?.*site=malapert-massif/);
    await expect(link).toHaveAttribute('href', /t=2027-04-07T00%3A00%3A45Z/);
    await link.click();
    await expect(page).toHaveURL(/\/analizza\?/);
    await expect(page.getByLabel('Sito')).toHaveValue('malapert-massif', { timeout: 15_000 });
    await expect(page.getByLabel('Inizio (UTC)')).toHaveValue('2027-04-07T00:00:45');
    const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/experiments/analyze'));
    await page.getByRole('button', { name: 'Esegui analisi' }).click();
    const r = await response;
    expect(r.status()).toBe(200);
    expect(r.request().postDataJSON().start_utc).toBe('2027-04-07T00:00:45Z');
  });

  test('il pannello "Perché RAVEN" e i limiti sono sempre presenti', async ({ page }) => {
    await open(page);
    await expect(page.getByTestId('why-grazinglink')).toContainText('0,5° e 1,5°');
    const limits = page.getByTestId('limits-line');
    await expect(limits).toBeVisible();
    for (const s of ['≤ −85°', 'ostacolo dominante', 'ipotesi illustrative', 'Cresta: T(m,n) di ITU-R P.526-9']) await expect(limits).toContainText(s);
    await page.getByRole('tab', { name: 'Terra' }).click();
    await expect(limits).toBeVisible();
  });

  test('un link con valori malevoli nello scenario viene ignorato', async ({ page }) => {
    await page.goto(`/viewer?site=${encodeURIComponent('<img src=x onerror=alert(1)>')}&t=2999-01-01T00:00:00Z&station=zz&rate=7`);
    await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
    await expect(page.getByTestId('fspl-delta')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('img[src="x"]')).toHaveCount(0);
    await expect(page.getByTestId('sel-station')).toHaveValue('dsn34');
  });
});

test.describe('Terra: complessi DSN e stazione che vede la Luna', () => {
  test('stazioni con 34 m e 18 m, quella che vede la Luna è evidenziata; distanza e delta come da backend', async ({ page }) => {
    await open(page, 'earth');
    const snap = await api(page);
    for (const c of snap.dsn.complexes) await expect(place(page, c.complex.toLowerCase())).toBeVisible();
    const best = snap.dsn.best_complex;
    expect(best).not.toBeNull();
    await expect(page.getByTestId('moon-seen').locator('.is-best')).toContainText(best!);
    for (const c of snap.dsn.complexes) {
      await expect(place(page, c.complex.toLowerCase())).toContainText(c.sees_moon ? 'vede la Luna' : 'Luna non visibile');
    }
    await expect(page.getByTestId('stat-value')).toHaveText(new RegExp(`^${Math.round(snap.earth_moon_range_km).toLocaleString('it-IT').replace('.', '\\.')}$`));
    const delta = `${snap.fspl_delta_db < 0 ? '−' : '+'}${Math.abs(snap.fspl_delta_db).toFixed(2).replace('.', ',')} dB`;
    await expect(page.getByTestId('fspl-delta')).toContainText(delta);
    await place(page, best!.toLowerCase()).click();
    await expect(page.getByTestId('detail-moon')).toContainText('Luna a');
    await expect(page.getByTestId('place-detail')).toContainText('34 m');
    await expect(page.getByTestId('place-detail')).toContainText('18 m');
    await expect(page.getByTestId('place-detail')).toContainText('ipotesi senza fonte');
    await expect(page.getByTestId('dir-line')).toBeVisible();
    await expect(page.getByText('DSN 810-005 Module 301 Rev. P').first()).toBeVisible();
    await page.screenshot({ path: `${OUT}/earth-stations-1440.png` });
  });
});

test.describe('scenario condiviso nell’URL', () => {
  test('sito e istante scelti nel visualizzatore tornano nel link verso l’analisi completa', async ({ page }) => {
    await open(page);
    await place(page, 'nobile-rim').click();
    const href = await page.getByRole('link', { name: 'Analisi completa' }).getAttribute('href');
    expect(href).toMatch(/site=nobile-rim/);
    await page.goto('/compare?site=haworth');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });
});

test.describe('accessibilità e layout', () => {
  for (const body of ['moon', 'earth']) {
    test(`axe pulito (${body}, 1440 e 390) e nessun overflow orizzontale a 390`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await open(page, body);
      if (body === 'moon') await place(page, 'haworth').click();
      else await place(page, (await api(page)).dsn.best_complex!.toLowerCase()).click();
      await expect(page.getByTestId('dir-label')).toBeVisible();
      let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(400);
      const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      expect(o.sw).toBeLessThanOrEqual(o.cw);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
    });
  }

  test('screenshot: 1440 scuro e 390 chiaro, Luna con sito polare e Terra con stazioni', async ({ page }) => {
    for (const [w, h, scheme] of [
      [1440, 900, 'dark'],
      [390, 844, 'light'],
    ] as const) {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width: w, height: h });
      await open(page, 'moon');
      if (w === 390) await page.getByRole('button', { name: /Luoghi e dati di Luna/ }).click();
      await place(page, 'haworth').click();
      if (w === 390) await page.getByRole('button', { name: 'Chiudi', exact: true }).click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/moon-polar-${w}-${scheme}.png` });
      await open(page, 'earth');
      if (w === 390) await page.getByRole('button', { name: /Luoghi e dati di Terra/ }).click();
      await place(page, (await api(page)).dsn.best_complex!.toLowerCase()).click();
      if (w === 390) await page.getByRole('button', { name: 'Chiudi', exact: true }).click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/earth-stations-${w}-${scheme}.png` });
    }
  });
});
