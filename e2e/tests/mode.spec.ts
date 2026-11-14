// SPDX-License-Identifier: Apache-2.0
// Interruttore Learning | Avanzato (docs/design/grazinglink-ux.md): presente dove cambia qualcosa, assente sulle pagine
// legali, stato condiviso tra le pagine e ricordato, ?mode= che vince ed è condivisibile, numeri identici nelle due
// modalità, alias delle vecchie rotte, axe pulito e nessun overflow a 390 px in Learning (Avanzato: a11y/ui-screens).
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { ALIASES, PAGES } from './pages';

// visitatore nuovo: niente hb.mode preimpostato dalla configurazione
test.use({ storageState: { cookies: [], origins: [] } });

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const sw = (page: Page) => page.getByRole('group', { name: 'Modalità' });
const btn = (page: Page, name: 'Learning' | 'Avanzato') => sw(page).getByRole('button', { name });

async function ready(page: Page, h1: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: h1 })).toBeVisible({ timeout: 20_000 });
  // Simula e Siti: l'intestazione provvisoria resta finché la scheda non è caricata
  await expect(page.locator('.hub-wait')).toHaveCount(0, { timeout: 20_000 });
}

test.describe('interruttore Learning | Avanzato', () => {
  for (const p of PAGES) {
    test(`${p.path}: ${p.mode ? 'presente, Learning per default' : 'assente (non cambia nulla)'}`, async ({ page }) => {
      await page.goto(p.path);
      await ready(page, p.h1);
      if (!p.mode) {
        await expect(sw(page)).toHaveCount(0);
        return;
      }
      await expect(sw(page)).toHaveCount(1);
      await expect(btn(page, 'Learning')).toHaveAttribute('aria-pressed', 'true');
      await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'false');
      // bersagli da almeno 44 px
      for (const n of ['Learning', 'Avanzato'] as const) {
        const b = await btn(page, n).boundingBox();
        expect(b!.height).toBeGreaterThanOrEqual(44);
      }
      await expect(page.getByTestId('learn-line')).toContainText('Cosa stai guardando');
    });
  }

  test('stesso posto: subito a destra dell’h1 nelle pagine strumento', async ({ page }) => {
    for (const p of PAGES.filter((x) => x.mode && x.path !== '/')) {
      await page.goto(p.path);
      await ready(page, p.h1);
      const h = (await page.getByRole('heading', { level: 1 }).boundingBox())!;
      const s = (await sw(page).boundingBox())!;
      expect(s.x, p.path).toBeGreaterThan(h.x + h.width - 1);
      expect(Math.abs(s.y + s.height / 2 - (h.y + h.height / 2)), p.path).toBeLessThan(24);
    }
  });

  test('lo stato è unico per il sito, si ricorda e si annuncia; il clic non scrive cookie', async ({ page, context }) => {
    await page.goto('/');
    await ready(page, 'RAVEN');
    await btn(page, 'Avanzato').click();
    await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#announcer')).toHaveText('Modalità Avanzato attiva');
    await expect(page).toHaveURL(/[?&]mode=avanzato/);
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' }).click();
    await page.getByRole('main').getByRole('link', { name: 'Analizza il link budget' }).click();
    await ready(page, 'Link budget');
    await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('learn-line')).toHaveCount(0);
    await page.goto('/laboratorio'); // ricaricamento senza ?mode=: vale la scelta salvata
    await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true');
    expect(await page.evaluate(() => localStorage.getItem('hb.mode'))).toBe('avanzato');
    expect(await context.cookies()).toEqual([]);
    // tastiera: freccia sull'interruttore passa all'altra modalità
    await btn(page, 'Avanzato').focus();
    await page.keyboard.press('ArrowLeft');
    await expect(btn(page, 'Learning')).toHaveAttribute('aria-pressed', 'true');
    await expect(btn(page, 'Learning')).toBeFocused();
  });

  test('?mode= vince sulla scelta salvata, conserva gli altri parametri e i valori malevoli sono ignorati', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.setItem('hb.mode', 'avanzato'));
    await page.goto('/siti?tab=classifica&site=shackleton&mode=learning');
    await ready(page, 'Siti – Globo e classifica');
    await expect(btn(page, 'Learning')).toHaveAttribute('aria-pressed', 'true');
    await btn(page, 'Avanzato').click();
    await expect(page).toHaveURL((url) => url.pathname === '/siti' &&
      url.searchParams.get('tab') === 'classifica' && url.searchParams.get('site') === 'shackleton' &&
      url.searchParams.get('mode') === 'avanzato');
    await page.goto('/analizza?mode=%3Cscript%3Ealert(1)%3C%2Fscript%3E');
    await ready(page, 'Link budget');
    await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true'); // valore non valido: resta la scelta salvata
    await page.evaluate(() => localStorage.setItem('hb.mode', 'boh'));
    await page.goto('/analizza');
    await expect(btn(page, 'Learning')).toHaveAttribute('aria-pressed', 'true');
  });

  test('archiviazione bloccata: l’interruttore funziona in memoria', async ({ page }) => {
    await page.addInitScript(() => {
      const boom = () => {
        throw new DOMException('bloccato', 'SecurityError');
      };
      Object.defineProperty(window, 'localStorage', { get: boom, configurable: true });
    });
    await page.goto('/analizza');
    await ready(page, 'Link budget');
    await btn(page, 'Avanzato').click();
    await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByLabel('Passo (minuti)')).toBeVisible();
  });
});

test.describe('Learning e Avanzato: contenuti diversi, numeri uguali', () => {
  test('Analizza: campi essenziali e due grafici in Learning, tutto in Avanzato, stesse ore delle finestre', async ({ page }) => {
    await page.goto('/analizza');
    await ready(page, 'Link budget');
    await expect(page.getByLabel('Per quanti giorni')).toBeVisible();
    await expect(page.getByLabel('Passo (minuti)')).toHaveCount(0);
    const start = page.getByLabel('Quando iniziare (UTC)');
    await expect(start).toBeVisible();
    await expect(page.getByTestId('more-in-advanced')).toBeVisible();
    await start.fill('');
    await page.getByRole('button', { name: 'Esegui analisi' }).click();
    await expect(start).toBeFocused();
    await expect(start).toHaveAttribute('aria-invalid', 'true');
    await start.fill('2027-04-10T06:00');
    await page.getByLabel('Per quanti giorni').fill('1');
    await page.getByLabel('Quanti dati al secondo').selectOption('30000');
    const resp = page.waitForResponse((r) => r.url().endsWith('/api/raven/experiments/analyze'));
    await page.getByRole('button', { name: 'Esegui analisi' }).click();
    const response = await resp;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON().start_utc).toBe('2027-04-10T06:00:00Z');
    expect(response.request().postDataJSON().overrides.rate_bps).toBe(30000);
    const overview = page.getByTestId('analysis-summary');
    await expect(overview).toBeVisible();
    const overviewLearning = await overview.textContent();
    const charts = page.getByTestId('learning-charts');
    await expect(charts.locator('.chart canvas')).toHaveCount(1);
    await expect(charts.locator('.bars')).toBeVisible();
    const legend = charts.getByRole('list', { name: 'Legenda delle velocità' });
    await expect(legend.getByRole('listitem')).toHaveCount(1);
    await expect(legend).toContainText('30 kbit/s');
    await expect(page.getByRole('tablist', { name: 'Risultati dell’analisi' })).toHaveCount(0);
    const learning = await page.getByTestId('windows-summary').textContent();
    expect(learning).toMatch(/\d+,\d h/);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const accessibility = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(accessibility.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);

    await btn(page, 'Avanzato').click();
    await expect(overview).toHaveText(overviewLearning!);
    await expect(page.getByLabel('Inizio (UTC)')).toHaveValue('2027-04-10T06:00');
    await expect(page.getByRole('tablist', { name: 'Risultati dell’analisi' }).getByRole('tab')).toHaveCount(6);
    await expect(page.getByLabel('Passo (minuti)')).toBeVisible();
    await page.getByRole('tab', { name: 'Finestre' }).click();
    await expect(page.getByTestId('windows-summary')).toHaveText(learning!);
    // una scheda tecnica aperta: tornando a Learning si rivedono i grafici senza ricalcolare
    await page.getByRole('tab', { name: 'Diffrazione' }).click();
    await btn(page, 'Learning').click();
    await expect(page.getByTestId('learning-charts')).toBeVisible();
    await expect(page.getByTestId('windows-summary')).toHaveText(learning!);
  });

  test('Siti, Classifica: colonne essenziali in Learning, tutte in Avanzato, stessi valori', async ({ page }) => {
    await page.goto('/siti?tab=classifica');
    await ready(page, 'Siti – Globo e classifica');
    await page.getByRole('button', { name: 'Nessuno' }).click();
    for (const s of ['Shackleton', 'Malapert Massif']) await page.getByLabel(s).check();
    await page.getByLabel('Durata (giorni)').fill('2');
    await expect(page.getByLabel('Passo (minuti)')).toHaveCount(0);
    const start = page.getByLabel('Inizio (UTC)');
    await start.fill('2027-04-10T06:00');
    const resp = page.waitForResponse((r) => r.url().endsWith('/api/raven/compare'));
    await page.getByRole('button', { name: 'Confronta con RAVEN' }).click();
    const response = await resp;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON().start_utc).toBe('2027-04-10T06:00:00Z');
    const table = page.getByTestId('rank-table');
    await expect(table.locator('thead th')).toHaveCount(6); // #, sito, 3 componenti, azioni
    const read = () => table.locator('tbody tr td.num').allTextContents();
    const learning = (await read()).slice(0, 4);
    await btn(page, 'Avanzato').click();
    await expect(page.getByLabel('Passo (minuti)')).toBeVisible();
    await expect(table.locator('thead th')).toHaveCount(9); // + mediano, carica minima, blackout, azioni
    expect((await table.locator('tbody tr:first-child td.num').allTextContents()).slice(0, 4)).toEqual(learning);
  });
});

test.describe('vecchie rotte', () => {
  for (const a of ALIASES) {
    test(`${a.from} porta a ${a.to}${a.tab ? `?tab=${a.tab}` : ''} con la query intatta`, async ({ page }) => {
      await page.goto(`${a.from}?site=shackleton&mode=avanzato#x`);
      await expect(page).toHaveURL(new RegExp(`${a.to}\\?site=shackleton&mode=avanzato${a.tab ? `&tab=${a.tab}` : ''}#x$`));
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 });
      await expect(btn(page, 'Avanzato')).toHaveAttribute('aria-pressed', 'true');
      if (a.tab) await expect(page.getByRole('tab', { selected: true }).first()).toBeVisible();
    });
  }

  test('le schede di Simula cambiano con ?tab= e conservano gli altri parametri', async ({ page }) => {
    await page.goto('/simula?site=shackleton');
    await ready(page, 'Simula – Simulatore');
    await page.getByRole('tab', { name: 'L’onda' }).click();
    await ready(page, 'Simula – Onda 3D');
    await expect(page).toHaveURL(/\/simula\?site=shackleton&tab=onda$/);
    await expect(page.getByRole('tab', { name: 'L’onda' })).toBeFocused();
  });
});

test.describe('barra principale e piè di pagina entrano senza overflow', () => {
  for (const width of [390, 834, 1024, 1440]) {
    test(`${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/analizza');
      await ready(page, 'Link budget');
      const o = await page.evaluate(() => {
        const over = (sel: string) => {
          const el = document.querySelector<HTMLElement>(sel)!;
          return el.scrollWidth > el.clientWidth + 1;
        };
        const items = [...document.querySelectorAll('#global-nav-list a')].map((a) => a.getBoundingClientRect());
        return {
          page: document.documentElement.scrollWidth > document.documentElement.clientWidth,
          bar: over('.global-nav .bar'),
          footer: over('.footer-inner'),
          // sopra 833 px le voci stanno su una riga dentro la barra da 44 px
          oneRow: items.every((r) => Math.abs(r.top - items[0]!.top) < 2 && r.bottom <= 44 + 1),
          visible: items.filter((r) => r.width > 0).length,
          boxes: items.map((r) => ({ top: r.top, bottom: r.bottom, width: r.width, height: r.height })),
        };
      });
      expect(o.page).toBe(false);
      expect(o.bar).toBe(false);
      expect(o.footer).toBe(false);
      if (width >= 834) {
        expect(o.visible).toBe(7);
        expect(o.oneRow, JSON.stringify(o)).toBe(true);
      } else {
        await page.getByRole('button', { name: 'Menu' }).click();
        await expect(page.getByRole('navigation', { name: 'Principale' }).getByRole('link')).toHaveCount(7);
      }
    });
  }
});

test.describe('Learning: axe pulito e nessun overflow a 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  for (const p of PAGES.filter((x) => x.mode)) {
    test(`${p.path}`, async ({ page }) => {
      await page.goto(p.path);
      await ready(page, p.h1);
      await page.waitForTimeout(500);
      const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      expect(o.sw, `scrollWidth ${o.sw} > clientWidth ${o.cw}`).toBeLessThanOrEqual(o.cw);
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
    });
  }
});
