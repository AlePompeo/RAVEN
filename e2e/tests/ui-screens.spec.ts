// SPDX-License-Identifier: Apache-2.0
// QA visivo: ogni pagina a 1440x900, 834x1112 e 390x844, schema scuro e chiaro, più home e visualizzatore
// con Chromium SENZA WebGL. Le PNG finiscono in e2e/test-results/ui/ (ignorata da git) per la revisione
// manuale descritta in docs/design/design-system.md. Qui si controllano anche overflow orizzontale e axe
// (incluse le voci "incomplete", riportate come annotazioni).
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { PAGES } from './pages';

const OUT = 'test-results/ui';
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const SIZES = [
  { name: '1440', width: 1440, height: 900 },
  { name: '834', width: 834, height: 1112 },
  { name: '390', width: 390, height: 844 },
] as const;
const SCHEMES = ['dark', 'light'] as const;
const ALL = [...PAGES.map((p) => ({ path: p.path, h1: p.h1 })), { path: '/non-esiste', h1: 'Pagina non trovata' }];

const slug = (path: string) => (path === '/' ? 'home' : path.replace(/^\//, '').replace(/[/?=&]/g, '-'));

async function settle(page: Page, path: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  if (path === '/') {
    await expect(page.getByTestId('moon-stage').locator('canvas')).toHaveCount(1, { timeout: 15_000 });
    await page.waitForTimeout(2600); // ingresso orchestrato (1.8s) + comparsa del testo
  }
  if (path === '/telemetry') {
    await expect(page.locator('.chart canvas').first()).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(1500); // qualche campione nel grafico
  }
  if (path === '/siti') {
    await expect(page.locator('.stage canvas').or(page.getByRole('alert')).first()).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(400);
  }
  if (path === '/simula?tab=onda') await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
  if (path === '/sims') await expect(page.getByLabel('Simulazione')).toBeVisible();
  if (path === '/siti?tab=classifica' || path === '/analizza') await expect(page.locator('#f-days, #g-days')).toBeVisible(); // etichetta diversa in Learning
  // scorre tutta la pagina come farebbe una persona: carica le immagini lazy, poi torna in cima
  await page.evaluate(async () => {
    const step = Math.max(200, innerHeight * 0.8);
    for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
      scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 60));
    }
    scrollTo(0, 0);
    await Promise.all([...document.images].map((i) => (i.complete ? null : i.decode().catch(() => null))));
  });
  await page.waitForTimeout(300);
}

/** Nessuna pagina deve scorrere in orizzontale (overflow a 390px). */
async function noHorizontalOverflow(page: Page): Promise<void> {
  const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  expect(o.sw, `scrollWidth ${o.sw} > clientWidth ${o.cw}`).toBeLessThanOrEqual(o.cw);
}

async function axe(page: Page, label: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const violations = r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }));
  expect(violations, `${label}: ${JSON.stringify(violations, null, 2)}`).toEqual([]);
  const incomplete = r.incomplete.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  if (incomplete.length) test.info().annotations.push({ type: 'axe-incomplete', description: `${label} -> ${incomplete.join(' | ')}` });
}

for (const size of SIZES) {
  for (const scheme of SCHEMES) {
    test.describe(`schermate ${size.name} ${scheme}`, () => {
      test.use({ viewport: { width: size.width, height: size.height }, colorScheme: scheme });
      for (const p of ALL) {
        test(`${p.path}`, async ({ page }) => {
          await page.goto(p.path);
          await settle(page, p.path);
          await noHorizontalOverflow(page);
          await page.screenshot({ path: `${OUT}/${slug(p.path)}-${size.name}-${scheme}.png`, fullPage: true });
          if (size.name !== '834') await axe(page, `${p.path} ${size.name} ${scheme}`);
        });
      }
    });
  }
}

// Nuova struttura nelle due modalità (Learning | Avanzato, forzate con ?mode=): 1440 scuro e 390 chiaro.
const MODE_SHOTS = [
  { path: '/', h1: 'RAVEN' },
  { path: '/simula', h1: 'Simula' },
  { path: '/analizza', h1: 'Link budget' },
  { path: '/siti', h1: 'Siti' },
  { path: '/laboratorio', h1: 'Laboratorio' },
] as const;
for (const [size, scheme] of [[SIZES[0], 'dark'], [SIZES[2], 'light']] as const) {
  test.describe(`modalità ${size.name} ${scheme}`, () => {
    test.use({ viewport: { width: size.width, height: size.height }, colorScheme: scheme });
    for (const p of MODE_SHOTS) {
      for (const mode of ['learning', 'avanzato'] as const) {
        test(`${p.path} ${mode}`, async ({ page }) => {
          await page.goto(`${p.path}?mode=${mode}`);
          await expect(page.getByRole('group', { name: 'Modalità' }).getByRole('button', { pressed: true })).toHaveText(mode === 'learning' ? 'Learning' : 'Avanzato');
          await expect(page.locator('.hub-wait')).toHaveCount(0, { timeout: 20_000 });
          await settle(page, p.path);
          await noHorizontalOverflow(page);
          await page.screenshot({ path: `${OUT}/mode-${slug(p.path)}-${mode}-${size.name}-${scheme}.png`, fullPage: true });
          await axe(page, `${p.path} ${mode} ${size.name} ${scheme}`);
        });
      }
    }
  });
}

// Stati dell'assistente: chat con una risposta (formula e variabili), pannello fonte e foglio "RAVEN SI" su /sims.
for (const size of SIZES) {
  for (const scheme of SCHEMES) {
    test.describe(`assistente ${size.name} ${scheme}`, () => {
      test.use({ viewport: { width: size.width, height: size.height }, colorScheme: scheme, reducedMotion: 'reduce' });
      test('chat con risposta e pannello fonte', async ({ page }) => {
        await page.goto('/chat');
        await expect(page.getByTestId('assistant-mode')).toHaveText('Risposte dal materiale del sito');
        await page.getByLabel('La tua domanda').fill('Come si calcola la perdita di spazio libero?');
        await page.getByRole('button', { name: 'Invia' }).click();
        await expect(page.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/chat-answer-${size.name}-${scheme}.png`, fullPage: true });
        if (size.name !== '834') await axe(page, `chat con risposta ${size.name} ${scheme}`);
        await page.getByRole('region', { name: 'Fonti' }).getByRole('button').first().click();
        await expect(page.getByRole('dialog').getByText(/^FSPL_dB =/)).toBeVisible();
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/chat-source-${size.name}-${scheme}.png` });
        if (size.name !== '834') await axe(page, `pannello fonte ${size.name} ${scheme}`);
      });
      test('/sims con il foglio RAVEN SI', async ({ page }) => {
        await page.goto('/sims');
        await settle(page, '/sims');
        await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
        const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
        await expect(sheet.getByRole('list', { name: 'Domande suggerite' })).toBeVisible();
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/sims-explain-${size.name}-${scheme}.png` });
        if (size.name !== '834') await axe(page, `foglio Spiega ${size.name} ${scheme}`);
      });
    });
  }
}

// Confronto siti con risultati reali (2 siti, 3 giorni, passo 60 min): classifica, metriche e grafici.
for (const size of SIZES) {
  for (const scheme of SCHEMES) {
    test.describe(`confronto siti ${size.name} ${scheme}`, () => {
      test.use({ viewport: { width: size.width, height: size.height }, colorScheme: scheme, reducedMotion: 'reduce' });
      test('/compare con risultati', async ({ page }) => {
        await page.goto('/compare');
        await settle(page, '/compare');
        await page.getByRole('button', { name: 'Nessuno' }).click();
        await page.getByRole('checkbox', { name: /Apollo 11/ }).check();
        await page.getByRole('checkbox', { name: /Shackleton/ }).check();
        await page.getByRole('checkbox', { name: /Haworth/ }).check();
        await page.getByLabel('Durata (giorni)').fill('3');
        await page.getByLabel('Passo (minuti)').fill('60');
        await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
        await expect(page.getByTestId('rank-table')).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId('not-comparable')).toContainText('Apollo 11');
        await page.waitForTimeout(400);
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/compare-results-${size.name}-${scheme}.png`, fullPage: true });
        if (size.name !== '834') await axe(page, `/compare con risultati ${size.name} ${scheme}`);
      });
    });
  }
}

// RAVEN con risultati reali (sito coperto dal DEM, 1 giorno, passo 60 min): ogni scheda.
const GL_TABS = ['Margine nel tempo', 'Finestre', 'Diffrazione', 'Antenna', 'Compensatore', 'Parametri e limiti'] as const;
for (const size of SIZES) {
  for (const scheme of SCHEMES) {
    test.describe(`grazinglink ${size.name} ${scheme}`, () => {
      test.use({ viewport: { width: size.width, height: size.height }, colorScheme: scheme, reducedMotion: 'reduce' });
      test('/grazinglink con risultati, tutte le schede', async ({ page }) => {
        await page.goto('/grazinglink');
        await settle(page, '/grazinglink');
        await page.getByLabel('Durata (giorni)').fill('1');
        await page.getByLabel('Passo (minuti)').fill('60');
        await page.getByRole('button', { name: 'Esegui analisi' }).click();
        await expect(page.getByRole('tab', { name: GL_TABS[0] })).toBeVisible({ timeout: 40_000 });
        for (const name of GL_TABS) {
          await page.getByRole('tab', { name }).click();
          await expect(page.locator('[role=tabpanel]:not([hidden]) h3').first()).toBeVisible({ timeout: 15_000 });
          if (name === 'Antenna') await expect(page.getByRole('table', { name: /^Antenne:/ })).toBeVisible({ timeout: 15_000 });
          if (name === 'Diffrazione' || name === 'Margine nel tempo' || name === 'Compensatore') await expect(page.locator('.chart canvas').first()).toBeVisible({ timeout: 15_000 });
          await page.waitForTimeout(500);
          await noHorizontalOverflow(page);
          const id = name.toLowerCase().replace(/[^a-z]+/g, '-');
          await page.screenshot({ path: `${OUT}/grazinglink-${id}-${size.name}-${scheme}.png`, fullPage: true });
          if (size.name !== '834') await axe(page, `/grazinglink ${name} ${size.name} ${scheme}`);
        }
      });
    });
  }
}

test.describe('menu mobile', () => {
  for (const scheme of SCHEMES) {
    test.describe(scheme, () => {
      test.use({ viewport: { width: 390, height: 844 }, colorScheme: scheme });
      test('aperto a 390px: tastiera, Esc, focus e axe', async ({ page }) => {
        await page.goto('/telemetry');
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const nav = page.getByRole('navigation', { name: 'Principale' });
        await expect(nav.getByRole('link', { name: 'Explore' })).toBeHidden();
        const toggle = page.getByRole('button', { name: 'Menu' });
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        await toggle.focus();
        await page.keyboard.press('Enter');
        await expect(toggle).toHaveAttribute('aria-expanded', 'true');
        await expect(nav.getByRole('link', { name: 'Home' })).toBeFocused();
        await expect(nav.getByRole('link', { name: 'Explore' })).toHaveAttribute('aria-current', 'page');
        await expect(page.locator('main')).toHaveAttribute('inert', '');
        await page.screenshot({ path: `${OUT}/nav-open-390-${scheme}.png` });
        await axe(page, `menu aperto 390 ${scheme}`);
        await page.keyboard.press('Escape');
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        await expect(toggle).toBeFocused();
        // apertura e navigazione: il menu si chiude e il focus va sull'h1 della nuova pagina
        await toggle.click();
        await nav.getByRole('link', { name: 'Learn' }).click();
        await expect(page).toHaveURL(/\/learn$/);
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        await expect(page.getByRole('heading', { level: 1, name: 'Learn' })).toBeFocused();
      });
    });
  }
});

// launchOptions non si può cambiare dentro un describe: browser dedicato lanciato a mano.
const NO_WEBGL = ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'];
test.describe('senza WebGL', () => {
  for (const size of SIZES) {
    for (const scheme of SCHEMES) {
      for (const path of ['/', '/viewer']) {
        test(`${path} ${size.name} ${scheme}`, async ({ playwright, baseURL }) => {
          const browser = await playwright.chromium.launch({ args: NO_WEBGL });
          try {
            const ctx = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, colorScheme: scheme, locale: 'it-IT' });
            const page = await ctx.newPage();
            expect(await page.evaluate(() => document.createElement('canvas').getContext('webgl'))).toBeNull();
            await page.goto(path);
            await settle(page, path);
            if (path === '/viewer') await expect(page.getByTestId('viewer-mode')).toHaveAttribute('data-mode', 'canvas2d');
            await noHorizontalOverflow(page);
            await page.screenshot({ path: `${OUT}/${slug(path)}-${size.name}-${scheme}-nowebgl.png`, fullPage: true });
          } finally {
            await browser.close();
          }
        });
      }
    }
  }
});

// Onda 3D: superficie con WebGL e senza (1440 scuro, 390 chiaro), da guardare a mano in test-results/ui/.
for (const [size, scheme] of [[SIZES[0], 'dark'], [SIZES[2], 'light']] as const) {
  for (const gl of [true, false]) {
    test(`/wave ${size.name} ${scheme} ${gl ? 'webgl' : 'nowebgl'}`, async ({ playwright, baseURL }) => {
      const browser = await playwright.chromium.launch(gl ? {} : { args: NO_WEBGL });
      try {
        const ctx = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, colorScheme: scheme, locale: 'it-IT', reducedMotion: 'reduce' });
        const page = await ctx.newPage();
        await page.goto('/wave');
        await settle(page, '/wave');
        await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/, { timeout: 30_000 });
        await page.getByLabel(/Distanza dal crinale/).fill('900');
        await expect(page.getByTestId('section-note')).toHaveAttribute('data-source', 'api', { timeout: 20_000 });
        await expect(page.locator('.chart[data-ready="1"] canvas').first()).toBeVisible({ timeout: 15_000 });
        await page.waitForTimeout(600);
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/wave-${size.name}-${scheme}-${gl ? 'webgl' : 'nowebgl'}.png`, fullPage: true });
        if (size.name !== '834') await axe(page, `/wave ${size.name} ${scheme} ${gl ? 'webgl' : 'nowebgl'}`);
      } finally {
        await browser.close();
      }
    });
  }
}

// Scena lander: WebGL e senza (1440 scuro, 390 chiaro), da guardare a mano in test-results/ui/.
for (const [size, scheme] of [[SIZES[0], 'dark'], [SIZES[2], 'light']] as const) {
  for (const gl of [true, false]) {
    test(`/lander ${size.name} ${scheme} ${gl ? 'webgl' : 'nowebgl'}`, async ({ playwright, baseURL }) => {
      const browser = await playwright.chromium.launch(gl ? {} : { args: NO_WEBGL });
      try {
        const ctx = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, colorScheme: scheme, locale: 'it-IT', reducedMotion: 'reduce' });
        const page = await ctx.newPage();
        await page.goto('/lander?site=de-gerlache&t=2027-04-07T00:00:00Z');
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        await expect(page.getByTestId('lander-status')).toHaveText(/Scena aggiornata/, { timeout: 40_000 });
        await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
        await page.waitForTimeout(800);
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `${OUT}/lander-${size.name}-${scheme}-${gl ? 'webgl' : 'nowebgl'}.png`, fullPage: true });
        if (gl) {
          await page.getByRole('tab', { name: 'Sezione laterale' }).click();
          await page.waitForTimeout(500);
          await page.getByTestId('section-canvas').screenshot({ path: `${OUT}/lander-section-${size.name}-${scheme}.png` });
        }
        await page.evaluate(() => window.scrollTo(0, 0));
        await axe(page, `/lander ${size.name} ${scheme} ${gl ? 'webgl' : 'nowebgl'}`);
      } finally {
        await browser.close();
      }
    });
  }
}
