// SPDX-License-Identifier: Apache-2.0
// Home "Il problema": pitch con una CTA per Simula, storia in 4 passi, mini-simulatore
// pigro (due cursori -> indicatore e frase, "Apri nel simulatore completo" porta i valori in Simula), Learning e
// Avanzato, senza WebGL, ordine del focus in TV, nessun overflow a 390 px, axe, CLS < 0.1 e screenshot da guardare
// (test-results/ui/home-*.png). Ogni test con un browser proprio lo lancia da sé (nessun test.use di launchOptions).
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { pixels } from './landerHelpers';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const NO_WEBGL = ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'];
const OUT = 'test-results/ui';

async function ready(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
}
/** Scorre fino al mini-simulatore e aspetta il chunk pigro. */
async function mini(page: Page): Promise<void> {
  await page.getByTestId('step-compute').scrollIntoViewIfNeeded();
  await expect(page.getByTestId('mini-sim')).toBeVisible({ timeout: 15_000 });
}
async function noOverflow(page: Page): Promise<void> {
  const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  expect(o.sw, `scrollWidth ${o.sw} > clientWidth ${o.cw}`).toBeLessThanOrEqual(o.cw);
}
async function axe(page: Page, label: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const v = r.violations.map((x) => ({ id: x.id, nodes: x.nodes.map((n) => n.target.join(' ')) }));
  expect(v, `${label}: ${JSON.stringify(v, null, 2)}`).toEqual([]);
}

test.describe('home: Il problema', () => {
  test('English Home translates the story, live simulator and accessibility text; switching language keeps the inputs', async ({ page }) => {
    await page.goto('/?lang=en&mode=avanzato');
    await ready(page);
    await mini(page);
    for (const name of [
      'How it works, in four steps', 'The Earth stays close to the horizon',
      'Why a ridge matters', 'What RAVEN calculates', 'Compare sites by useful hours', 'The research stack',
    ]) await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    await expect(page.getByRole('img', { name: /The half-lit Earth/ })).toHaveCount(1);
    await expect(page.getByTestId('strip-summary')).toContainText('hours of contact');
    await expect(page.getByTestId('mini-tech')).toContainText('diffraction loss');
    await expect(page.getByTestId('honesty')).toHaveCount(0);
    await page.getByTestId('mini-el-num').fill('8');
    await expect(page.getByTestId('sentence')).toContainText('The signal arrives');
    await expect(page.getByTestId('gauge-state')).toContainText('Open');
    await page.getByTestId('mini-el-num').fill('0');
    await expect(page.getByTestId('sentence')).toContainText('The Earth is below the horizon');
    await expect(page.getByTestId('validity')).toContainText('Model validity: Outside model');
    await expect(page.getByTestId('mini-stage')).toHaveAttribute('aria-label', /^Side view:/);
    const margin = await page.getByTestId('gauge').getAttribute('data-margin');
    await page.getByTestId('lang-switch').getByRole('button').click();
    await page.getByRole('option', { name: 'Italiano' }).click();
    await expect(page.getByRole('heading', { name: 'Come funziona, in quattro passi' })).toBeVisible();
    await expect(page.getByTestId('mini-el-num')).toHaveValue('0');
    await expect(page.getByTestId('gauge')).toHaveAttribute('data-margin', margin!);
    await expect(page.getByTestId('sentence')).toContainText('La Terra è sotto');
  });

  test('il logo RAVEN e la favicon sono caricati', async ({ page }) => {
    await page.goto('/');
    await ready(page);
    const images = page.locator('.brand img, #home-title img');
    await expect(images).toHaveCount(3);
    await expect.poll(() => images.evaluateAll((items) =>
      items.every((item) => item instanceof HTMLImageElement && item.complete && item.naturalWidth > 0),
    )).toBe(true);
    const favicon = await page.locator('link[rel="icon"]').getAttribute('href');
    expect(favicon).toBeTruthy();
    expect((await page.request.get(favicon!)).ok()).toBe(true);
  });

  test('Learning: il pitch, le azioni e il testo semplice; "Prova e impara" apre Simula', async ({ page }) => {
    await page.goto('/?mode=learning');
    await ready(page);
    const hero = page.getByRole('region', { name: 'RAVEN', exact: true });
    await expect(hero).toContainText('Confronta due siti lunari in una finestra di missione');
    await expect(hero).toContainText('Deep Space Network');
    await expect(hero.getByRole('link')).toHaveText(['Prova e impara', 'Inizia il Mission Planner', 'Demo guidata', 'About']);
    await expect(page.getByTestId('learn-line')).toBeVisible();
    await expect(page.getByTestId('tech-line')).toHaveCount(0);
    await expect(page.getByTestId('stack')).toHaveCount(0);
    await expect(page.getByTestId('honesty')).toHaveCount(0);
    await expect(page.getByRole('main').getByRole('link', { name: 'Chi siamo' })).toHaveCount(0);
    await page.getByRole('link', { name: 'Prova e impara' }).click();
    await expect(page).toHaveURL(/\/simula/);
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible({ timeout: 20_000 });
  });

  test('Avanzato: una riga tecnica per passo e lo stack nella storia', async ({ page }) => {
    await page.goto('/?mode=avanzato');
    await ready(page);
    await expect(page.getByTestId('tech-line')).toHaveCount(4);
    await expect(page.getByTestId('tech-line').nth(1)).toContainText('Fresnel-Kirchhoff');
    await expect(page.getByTestId('stack')).toContainText('Skyfield');
    await expect(page.getByTestId('learn-line')).toHaveCount(0);
    await page.getByRole('heading', { level: 2, name: 'Come funziona, in quattro passi' }).scrollIntoViewIfNeeded();
    await expect(page.getByRole('heading', { level: 2, name: 'Come funziona, in quattro passi' })).toBeInViewport();
  });

  test('mini-simulatore: pigro, i cursori aggiornano indicatore, frase e vista; i valori arrivano in Simula', async ({ page }) => {
    const chunks: string[] = [];
    page.on('request', (r) => r.url().includes('MiniSim') && chunks.push(r.url()));
    await page.goto('/?mode=learning');
    await ready(page);
    expect(chunks, 'il chunk del mini-simulatore non si scarica al caricamento').toEqual([]);
    await mini(page);
    expect(chunks.length).toBeGreaterThan(0);
    const m = page.getByTestId('mini-sim');
    const gauge = m.getByTestId('gauge');
    const sentence = m.getByTestId('sentence');
    await expect(m.getByLabel('Quanto è alta la Terra nel cielo', { exact: true })).toBeVisible();
    await expect(m.getByLabel('Quanto è alto il crinale', { exact: true })).toBeVisible();
    // Terra alta: aperto
    await page.getByTestId('mini-el-num').fill('8');
    await expect(gauge).toHaveAttribute('data-state', 'open');
    await expect(m.getByTestId('mini-stage')).toHaveAttribute('data-bent', '0');
    const s1 = await sentence.textContent();
    const g1 = await gauge.getAttribute('data-margin');
    // Terra radente e crinale alto: bloccato, segnale piegato sulla cima
    await page.getByTestId('mini-el-num').fill('0.5');
    await page.getByTestId('mini-ridge-num').fill('120');
    await expect(gauge).toHaveAttribute('data-state', 'blocked');
    await expect(m.getByTestId('mini-stage')).toHaveAttribute('data-bent', '1');
    await expect(sentence).not.toHaveText(s1 ?? '');
    expect(Number(await gauge.getAttribute('data-margin'))).toBeLessThan(Number(g1));
    // la tastiera sul cursore funziona (Fine = massimo)
    await m.getByLabel('Quanto è alta la Terra nel cielo', { exact: true }).focus();
    await page.keyboard.press('End');
    await expect(page.getByTestId('mini-el-num')).toHaveValue('10');
    await page.getByTestId('mini-el-num').fill('1.2');
    await page.getByTestId('mini-ridge-num').fill('47.5');
    const open = m.getByRole('link', { name: 'Apri nel simulatore completo' });
    await expect(open).toHaveAttribute('href', '/simula?el=1.2&rh=47.5');
    const margin = await gauge.getAttribute('data-margin');
    await open.click();
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('ctl-el-num')).toHaveValue('1.2');
    await expect(page.getByTestId('ctl-ridge-num')).toHaveValue('47.5');
    // stessi numeri: stesso modello e stessa tabella della correzione
    await expect(page.locator('[data-testid="simula"] [data-testid="gauge"]')).toHaveAttribute('data-margin', margin!);
  });

  test('senza WebGL: la home e la vista di lato del mini-simulatore funzionano', async ({ playwright, baseURL }) => {
    const browser = await playwright.chromium.launch({ args: NO_WEBGL });
    try {
      const ctx = await browser.newContext({ baseURL, viewport: { width: 1280, height: 800 }, locale: 'it-IT' });
      const page = await ctx.newPage();
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto('/?mode=learning');
      await ready(page);
      await mini(page);
      await page.waitForTimeout(300);
      const p0 = await pixels(page, '[data-testid="mini-stage"]');
      expect(p0.lit / p0.total).toBeGreaterThan(0.05);
      await page.getByTestId('mini-ridge-num').fill('140');
      await page.getByTestId('mini-el-num').fill('0.3');
      await expect(page.getByTestId('mini-stage')).toHaveAttribute('data-state', 'blocked');
      await page.waitForTimeout(300);
      const p1 = await pixels(page, '[data-testid="mini-stage"]');
      expect(p1.hash).not.toBe(p0.hash);
      expect(errors).toEqual([]);
    } finally {
      await browser.close();
    }
  });

  test('ordine del focus: dopo la barra la prima tappa è "Prova e impara" (Tab e frecce TV)', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/');
    await ready(page);
    // Tab: ultimo link della barra, selettore lingua, poi la CTA
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Contatti' }).focus();
    await page.keyboard.press('Tab');
    await expect(page.getByTestId('lang-switch').getByRole('button')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Prova e impara' })).toBeFocused();
    // TV: freccia giù da una voce della barra arriva alla CTA, non al pulsante fluttuante "RAVEN SI"
    await page.goto('/?tv=1');
    await ready(page);
    for (const name of ['Home', 'Mission Planner']) {
      await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name }).focus();
      await page.keyboard.press('ArrowDown');
      const at = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 120));
      await expect(page.getByRole('link', { name: 'Prova e impara' }), `giù da ${name}: ${at}`).toBeFocused();
    }
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('link', { name: 'Inizia il Mission Planner' })).toBeFocused();
  });

  for (const mode of ['learning', 'avanzato'] as const) {
    test(`${mode}: axe pulito (anche il mini-simulatore) e nessun overflow a 390 px`, async ({ page }) => {
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
        await page.goto(`/?mode=${mode}`);
        await ready(page);
        await mini(page);
        await axe(page, `${mode} ${scheme}`);
      }
      for (const w of [390, 834]) {
        await page.setViewportSize({ width: w, height: 844 });
        await page.goto(`/?mode=${mode}`);
        await ready(page);
        await mini(page);
        await noOverflow(page);
      }
    });
  }

  test('CLS < 0.1 caricando e scorrendo fino in fondo', async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __cls: number }).__cls = 0;
      new PerformanceObserver((l) => {
        for (const e of l.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
          if (!e.hadRecentInput) (window as unknown as { __cls: number }).__cls += e.value;
        }
      }).observe({ type: 'layout-shift', buffered: true });
    });
    await page.goto('/?mode=learning');
    await ready(page);
    for (let i = 0; i < 14; i++) {
      await page.mouse.wheel(0, 600);
      await page.waitForTimeout(150);
    }
    await expect(page.getByTestId('mini-sim')).toHaveCount(1);
    await page.waitForTimeout(500);
    const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
    expect(cls).toBeLessThan(0.1);
  });
});

for (const [w, h, scheme] of [[1440, 900, 'dark'], [390, 844, 'light']] as const) {
  for (const mode of ['learning', 'avanzato'] as const) {
    test(`screenshot home ${w} ${scheme} ${mode}`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h });
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await page.goto(`/?mode=${mode}`);
      await ready(page);
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${OUT}/home-${w}-${scheme}-${mode}-top.png` });
      await mini(page);
      await page.getByTestId('mini-sim').scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/home-${w}-${scheme}-${mode}-mini.png` });
      await page.screenshot({ path: `${OUT}/home-${w}-${scheme}-${mode}.png`, fullPage: true });
    });
  }
}
