// SPDX-License-Identifier: Apache-2.0
// Simula, scheda Scena: simulatore con il modello nel browser (backend reale per tabella, registro e scena del sito).
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { frames } from './landerHelpers';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const CANVAS = '[data-testid="sim-stage"] canvas';

async function open(page: Page, query = 'mode=learning'): Promise<void> {
  await page.goto(`/simula?tab=scena&${query}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible();
  await expect(page.getByTestId('sim-mode')).toHaveAttribute('data-mode', /webgl|canvas2d/, { timeout: 20_000 });
  await expect(page.locator(CANVAS)).toHaveCount(1);
  await frames(page, CANVAS);
}
const margin = async (page: Page) => Number(await page.getByTestId('gauge').getAttribute('data-margin'));
const setNum = async (page: Page, id: string, v: number) => page.getByTestId(`${id}-num`).fill(String(v));

async function axe(page: Page, label: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const v = r.violations.map((x) => ({ id: x.id, nodes: x.nodes.map((n) => n.target.join(' ')) }));
  expect(v, `${label}: ${JSON.stringify(v, null, 2)}`).toEqual([]);
}
async function noOverflow(page: Page): Promise<void> {
  const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  expect(o.sw, `scrollWidth ${o.sw} > clientWidth ${o.cw}`).toBeLessThanOrEqual(o.cw);
}

test.describe('Simula: scenario didattico', () => {
  test('la vista cinematografica nasconde e ripristina le sovrapposizioni senza cambiare il margine', async ({ page }) => {
    await open(page);
    await expect(page.getByTestId('sim-mode')).toHaveAttribute('data-mode', 'webgl');
    await expect(page.locator(CANVAS)).toHaveAttribute('data-sky-orientation', 'illustrative');
    await expect(page.getByTestId('sim-visual-credit')).toContainText('orientamento del cielo è illustrativo');
    const before = await margin(page);
    const height = (await page.getByTestId('sim-stage').boundingBox())!.height;
    const toggle = page.getByRole('button', { name: 'Vista cinematografica' });
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator(CANVAS)).toHaveAttribute('data-overlays', 'hidden');
    expect((await page.getByTestId('sim-stage').boundingBox())!.height).toBeGreaterThan(height);
    expect(await margin(page)).toBe(before);
    await toggle.click();
    await expect(page.locator(CANVAS)).toHaveAttribute('data-overlays', 'visible');
  });

  test('etichetta, riga d’onestà, tabella di correzione caricata, scenario predefinito aperto e affidabile', async ({ page }) => {
    await open(page);
    await expect(page.getByTestId('scenario-label')).toHaveText('Scenario didattico (non è un sito reale)');
    await expect(page.getByTestId('honesty')).toContainText('un solo ostacolo');
    await expect(page.getByTestId('honesty')).toContainText('cresta arrotondata da ITU-R P.526-9');
    await expect(page.getByTestId('table-missing')).toHaveCount(0);
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', 'open');
    await expect(page.getByTestId('validity')).toHaveAttribute('data-level', 'reliable');
    await expect(page.getByTestId('sentence')).toHaveText(/^Il segnale arriva con \d+ dB di margine: puoi inviare 100 kbps\.$/);
  });

  test('muovere un controllo cambia indicatore, frase, punto del grafico e stato della scena 3D', async ({ page }) => {
    await open(page);
    const m0 = await margin(page);
    const s0 = await page.getByTestId('sentence').textContent();
    const c0 = await page.getByTestId('margin-chart').getAttribute('data-current');
    const g0 = Number(await page.getByTestId('sim-stage').getAttribute('data-gen'));
    const f0 = Number(await page.locator(CANVAS).getAttribute('data-frames'));
    await setNum(page, 'ctl-el', 0.8);
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', 'transition');
    await expect(page.getByTestId('gauge-state')).toContainText('Transizione');
    expect(await margin(page)).toBeLessThan(m0);
    await expect(page.getByTestId('sentence')).not.toHaveText(s0!);
    await expect(page.getByTestId('sentence')).toContainText('piegato');
    await expect(page.getByTestId('margin-chart')).not.toHaveAttribute('data-current', c0!);
    await expect(page.getByTestId('sim-stage')).toHaveAttribute('data-state', 'transition');
    expect(Number(await page.getByTestId('sim-stage').getAttribute('data-gen'))).toBeGreaterThan(g0);
    await expect.poll(async () => Number(await page.locator(CANVAS).getAttribute('data-frames'))).toBeGreaterThan(f0);
    // stesso valore con la tastiera sul cursore
    await page.locator('#sim-el').focus();
    for (let i = 0; i < 40; i++) await page.keyboard.press('ArrowRight');
    await expect(page.getByTestId('ctl-el-num')).toHaveValue('2.8');
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', 'open');
  });

  test('preset a un tocco', async ({ page }) => {
    await open(page);
    const want = { high: 'open', grazing: 'transition', blocking: 'blocked', small: 'blocked' } as const;
    for (const [id, st] of Object.entries(want)) {
      await page.getByTestId(`preset-${id}`).click();
      await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', st);
    }
    await expect(page.getByTestId('ctl-rate-value')).toHaveText('3 Mbps');
    await expect(page.getByTestId('sentence')).toContainText('ma 300 kbps passano');
  });

  test('missione guidata: i 5 passi si completano facendo ciò che chiedono', async ({ page }) => {
    await open(page);
    const done = () => page.getByTestId('mission').getAttribute('data-done');
    expect(await done()).toBe('0');
    await setNum(page, 'ctl-el', 6);
    await expect.poll(done).toBe('1');
    await setNum(page, 'ctl-el', 0.8);
    await expect.poll(done).toBe('2');
    await setNum(page, 'ctl-ridge', 90);
    await expect.poll(done).toBe('3');
    await setNum(page, 'ctl-dia', 1.5);
    await expect.poll(done).toBe('4');
    await page.locator('#sim-rate').focus();
    await page.keyboard.press('End');
    await expect.poll(done).toBe('5');
    await expect(page.getByTestId('mission')).toContainText('Missione completata');
    await expect(page.locator('[data-step="rate"]')).toHaveAttribute('data-done', '1');
  });

  test('mappa di validità: calcolata in meno di 100 ms; clic e frecce impostano i controlli', async ({ page }) => {
    await open(page);
    const map = page.getByTestId('validity-map');
    expect(Number(await map.getAttribute('data-ms'))).toBeLessThan(100);
    const c = page.getByTestId('validity-canvas').locator('canvas');
    const box = (await c.boundingBox())!;
    // il riquadro dei dati ha margini 48/10 px in orizzontale e 10/36 px in verticale: clic a metà dei dati
    await c.click({ position: { x: 48 + (box.width - 58) / 2, y: 10 + (box.height - 46) / 2 } });
    await expect(page.getByTestId('ctl-el-num')).toHaveValue('5');
    await expect(page.getByTestId('ctl-ridge-num')).toHaveValue('75');
    await page.getByTestId('validity-canvas').focus();
    await page.keyboard.press('ArrowUp');
    await expect(page.getByTestId('ctl-ridge-num')).not.toHaveValue('75');
    await expect(page.getByTestId('vmap-summary')).toContainText('Punto corrente: Terra a 5,00°');
    await page.getByText('Tabella ridotta della mappa').click();
    await expect(map.locator('table td').first()).toContainText(/Aperto|Transizione|Bloccato/);
  });

  test('la Terra all’orizzonte è fuori modello, con il perché', async ({ page }) => {
    await open(page);
    await setNum(page, 'ctl-el', 0);
    await expect(page.getByTestId('validity')).toHaveAttribute('data-level', 'outside');
    await expect(page.getByTestId('validity-reasons')).toContainText('sotto l’orizzonte');
    await expect(page.getByTestId('sentence')).toContainText('sotto l’orizzonte');
  });

  test('stessi numeri in Learning e Avanzato', async ({ page }) => {
    await open(page);
    await setNum(page, 'ctl-el', 0.7);
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', 'transition');
    const m = await margin(page);
    await page.getByRole('button', { name: 'Avanzato', exact: true }).click();
    await expect(page.getByTestId('numbers')).toBeVisible();
    expect(await margin(page)).toBe(m);
    await expect(page.getByTestId('num-margin')).toContainText(m.toFixed(2).replace('.', ',').replace('-', '−'));
  });

  test('Avanzato: tag V/D/I con fonte, varianti, incertezze, esportazione, stato completo nell’URL', async ({ page }) => {
    await open(page, 'mode=avanzato');
    const freq = page.getByTestId('ctl-freq');
    await expect(freq.locator('.badge')).toHaveText(/^V/);
    await expect(freq).toContainText('DSN 810-005 Module 104');
    await expect(page.getByTestId('ctl-tsys')).toContainText('DSN 810-005 Module 104');
    await expect(page.getByTestId('variants').locator('tbody tr')).toHaveCount(6); // lama, cresta ITU, cresta split-step (solo con la tabella caricata), multipath, antenna script, antenna corretta
    await expect(page.getByTestId('uncertainty')).toContainText('perigeo');
    await expect(page.getByTestId('flags')).toContainText('radius_unresolved');
    await setNum(page, 'ctl-el', 0.6);
    await setNum(page, 'ctl-tsys', 60);
    await page.getByTestId('ctl-mp').check();
    await expect(page).toHaveURL(/el=0\.6/);
    await expect(page).toHaveURL(/tsys=60/);
    await expect(page).toHaveURL(/mp=1/);
    const m = await margin(page);
    const dl = page.waitForEvent('download');
    await page.getByTestId('export-json').click();
    const file = await (await dl).path();
    const j = JSON.parse(readFileSync(file, 'utf8'));
    expect(j.input.earthElDeg).toBe(0.6);
    expect(j.input.tsysK).toBe(60);
    expect(Math.abs(j.output.marginDb - m)).toBeLessThan(0.01);
    const dl2 = page.waitForEvent('download');
    await page.getByTestId('export-csv').click();
    const csv = readFileSync(await (await dl2).path(), 'utf8') as string;
    expect(csv.startsWith('key,value\n')).toBe(true);
    // il link condiviso riproduce lo stesso margine
    await page.reload();
    await expect(page.getByTestId('ctl-el-num')).toHaveValue('0.6');
    await expect.poll(() => margin(page)).toBe(m);
  });

  test('valori malevoli nell’URL ignorati', async ({ page }) => {
    await open(page, 'mode=avanzato&el=NaN&rh=1e999&dia=%3Cscript%3E&rate=7&station=x');
    await expect(page.getByTestId('ctl-el-num')).toHaveValue('1.5');
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', 'open');
    await expect(page.locator('script:not([src])', { hasText: 'alert' })).toHaveCount(0);
  });

  test('la scheda L’onda parte da frequenza, raggio e distanza della scena', async ({ page }) => {
    await open(page, 'mode=avanzato');
    await setNum(page, 'ctl-radius', 200);
    await setNum(page, 'ctl-d1', 3000);
    await page.getByRole('tab', { name: 'L’onda' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Onda 3D' })).toBeVisible();
    await expect(page.locator('#f-radius')).toHaveValue('200');
  });

  for (const mode of ['learning', 'avanzato'] as const) {
    test(`${mode}: axe pulito e nessun overflow a 390 px`, async ({ page }) => {
      await open(page, `mode=${mode}`);
      await axe(page, `simula ${mode} 1280`);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);
      if ((await page.getByTestId('sim-mode').getAttribute('data-mode')) === 'webgl') {
        await page.getByRole('button', { name: 'Vista cinematografica' }).click();
      }
      await noOverflow(page);
      await axe(page, `simula ${mode} 390`);
    });
  }
});

test.describe('Simula: sito reale', () => {
  test('unknown RF keeps actual terrain visible without a synthetic gauge, table or export', async ({ page }) => {
    await page.goto('/simula?tab=scena&mode=avanzato&real=1&site=de-gerlache&t=2027-04-07T00:00:00Z');
    await page.getByRole('button', { name: 'Analisi radio interattiva' }).click();
    await expect(page.getByTestId('sim-rf-unknown')).toContainText("Il margine RF corrente e' ignoto", { timeout: 60_000 });
    await expect(page.getByTestId('real-error')).toBeVisible();
    await expect(page.getByTestId('gauge')).toHaveCount(0);
    await expect(page.getByTestId('numbers')).toHaveCount(0);
    await expect(page.getByTestId('export-json')).toHaveCount(0);
    await expect(page.locator(CANVAS)).toHaveAttribute('data-sky-orientation', 'site-time');
    await expect(page.getByTestId('ctl-dia')).toBeVisible();
  });
  test('il margine dell’indicatore è quello di /api/raven/scene; i controlli regolano solo antenna, dati e tempo', async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto('/simula?tab=scena&mode=learning&site=malapert-massif&t=2027-04-07T00:00:00Z');
    await expect(page.getByTestId('sim-mode')).toHaveAttribute('data-mode', /webgl|canvas2d/, { timeout: 20_000 });
    await page.getByRole('button', { name: 'Sito reale nel tempo' }).click();
    await expect(page.locator('#lander-stage')).toHaveAttribute('data-ready', '1', { timeout: 60_000 });
    const resp = page.waitForResponse((r) => r.url().includes('/api/raven/scene') && r.ok(), { timeout: 60_000 });
    await page.getByRole('button', { name: 'Analisi radio interattiva' }).click();
    await expect(page.getByTestId('simula')).toHaveAttribute('data-real', '1');
    const j = (await (await resp).json()) as { link: { margin_db: number; state: string } };
    await expect(page.getByTestId('real-status')).toContainText('margine del motore', { timeout: 60_000 });
    await expect(page.getByTestId('scenario-label')).toContainText('Sito reale');
    if ((await page.getByTestId('sim-mode').getAttribute('data-mode')) === 'webgl') {
      await expect(page.locator(CANVAS)).toHaveAttribute('data-sky-orientation', 'site-time');
      await expect(page.getByTestId('sim-visual-credit')).toContainText("orientata per il sito e l'istante");
    }
    await expect.poll(() => margin(page)).toBeCloseTo(j.link.margin_db, 2);
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-state', j.link.state);
    await expect(page.getByTestId('ctl-el')).toHaveCount(0);
    await expect(page.getByTestId('ctl-ridge')).toHaveCount(0);
    await expect(page.getByTestId('ctl-dia')).toBeVisible();
    await expect(page.getByTestId('ctl-hours')).toBeVisible();
    await expect(page).toHaveURL(/real=1/);
    // più dati al secondo: nuova richiesta e lo stesso margine del motore
    const resp2 = page.waitForResponse((r) => r.url().includes('/api/raven/scene') && r.url().includes('rate_bps=3000000') && r.ok(), { timeout: 60_000 });
    await page.locator('#sim-rate').focus();
    await page.keyboard.press('End');
    const j2 = (await (await resp2).json()) as { link: { margin_db: number } };
    await expect.poll(() => margin(page)).toBeCloseTo(j2.link.margin_db, 2);
    await page.getByRole('button', { name: 'Scenario didattico', exact: true }).click();
    if ((await page.getByTestId('sim-mode').getAttribute('data-mode')) === 'webgl') {
      await expect(page.locator(CANVAS)).toHaveAttribute('data-sky-orientation', 'illustrative');
      await expect(page.getByTestId('sim-visual-credit')).toContainText('orientamento del cielo è illustrativo');
    }
  });
});
