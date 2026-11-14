// SPDX-License-Identifier: Apache-2.0
// Matrice dispositivi (solo Chromium: i descrittori di Playwright danno viewport, DPR, tocco e user agent).
// Per ogni dispositivo e pagina: nessun overflow orizzontale, nessun errore in console, CLS < 0,1, target
// >= 44px con puntatore grossolano. Più reflow WCAG a 200% e 400% (larghezza 640 e 320 CSS px).
// Screenshot in test-results/ui/devices/; riepilogo in test-results/ui/devices/matrix.json.
import { test, expect, devices, type Page } from '@playwright/test';
import { useFilledTeam } from './contactsFixture';
import { mkdirSync, writeFileSync } from 'node:fs';

const OUT = 'test-results/ui/devices';
// '#explain' = /sims con il foglio "RAVEN SI" aperto; '#answer' = /chat con una risposta e il pannello fonte aperto
const PAGES = ['/', '/viewer', '/telemetry', '/sims', '/chat', '/licenses', '/contacts', '/contacts#filled', '/sims#explain', '/chat#answer'] as const;

type Dev = { name: string; viewport: { width: number; height: number }; deviceScaleFactor: number; isMobile: boolean; hasTouch: boolean; userAgent?: string };
const d = (name: string, key: string): Dev => {
  const x = devices[key]!;
  return { name, viewport: x.viewport, deviceScaleFactor: x.deviceScaleFactor, isMobile: x.isMobile, hasTouch: x.hasTouch, userAgent: x.userAgent };
};
const desk = (name: string, width: number, height: number, deviceScaleFactor = 1): Dev => ({ name, viewport: { width, height }, deviceScaleFactor, isMobile: false, hasTouch: false });

export const MATRIX: Dev[] = [
  d('iphone-se', 'iPhone SE'),
  d('iphone-15-pro-max', 'iPhone 15 Pro Max'),
  d('iphone-15-pro-max-landscape', 'iPhone 15 Pro Max landscape'),
  d('pixel-7', 'Pixel 7'),
  d('galaxy-s9plus', 'Galaxy S9+'),
  d('ipad-mini', 'iPad Mini'),
  d('ipad-mini-landscape', 'iPad Mini landscape'),
  d('ipad-pro-11', 'iPad Pro 11'),
  d('ipad-pro-11-landscape', 'iPad Pro 11 landscape'),
  desk('desktop-1280', 1280, 800),
  desk('desktop-1440', 1440, 900),
  desk('desktop-1920', 1920, 1080),
  desk('desktop-2560', 2560, 1440),
  desk('ultrawide-3440', 3440, 1440),
  { ...desk('tv-1920', 1920, 1080), hasTouch: false },
  desk('tv-3840-dpr1', 3840, 2160, 1),
  desk('tv-1920-dpr2', 1920, 1080, 2), // 3840x2160 fisici a DPR 2
];

const slug = (p: string) => (p === '/' ? 'home' : p.slice(1).replace('#', '-'));

async function open(page: Page, path: string, tv: boolean): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.addInitScript(() => {
    (window as unknown as { __cls: number }).__cls = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) (window as unknown as { __cls: number }).__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
  });
  const [route = '/', state] = path.split('#');
  path = route;
  if (state === 'filled') await useFilledTeam(page);
  await page.goto(`${route}${tv ? '?tv=1' : ''}`);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  if (path === '/viewer') await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
  if (path === '/') await page.waitForTimeout(800);
  if (state === 'explain') {
    await expect(page.getByLabel('Simulazione')).toBeVisible();
    await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(sheet.getByRole('list', { name: 'Domande suggerite' })).toBeVisible();
  }
  if (state === 'answer') {
    await page.getByLabel('La tua domanda').fill('Come si calcola la perdita di spazio libero?');
    await page.getByRole('button', { name: 'Invia' }).click();
    await expect(page.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    await page.getByRole('region', { name: 'Fonti' }).getByRole('button').first().click();
    await expect(page.getByRole('dialog').getByText(/^FSPL_dB =/)).toBeVisible();
  }
  return errors;
}

/** Overflow orizzontale del documento (px oltre la finestra). */
const overflowX = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);

/** Testi tagliati: elementi di testo il cui contenuto eccede il box con overflow nascosto. */
const clipped = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('h1, h2, h3, p, a, button, label, dt, dd, th, td, li')]
      .filter((el) => {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('.visually-hidden, [hidden]')) return false;
        if (el.clientWidth <= 1) return false; // testo nascosto solo alla vista (sr-only): voluto
        const hidden = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
        return hidden && el.scrollWidth > el.clientWidth + 1 && cs.textOverflow !== 'ellipsis';
      })
      .map((el) => `${el.tagName.toLowerCase()}.${el.className}`.slice(0, 80)),
  );

/** Target piccoli con puntatore grossolano: pulsanti e link fuori dal testo corrente. */
const smallTargets = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('button, a[href], input, select, [role="tab"]')]
      .filter((el) => {
        if (el.closest('[hidden], [inert], .visually-hidden') || el.classList.contains('skip-link')) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return false;
        // eccezione WCAG 2.5.8: link nel testo di un paragrafo o di una didascalia
        if (el.tagName === 'A' && el.closest('p, figcaption, td, .credits li')) return false;
        // idem per i chip di citazione dentro il testo di una risposta (la stessa fonte è anche nell'elenco "Fonti", a 44px)
        if (el.classList.contains('cite')) return false;
        if ((el as HTMLInputElement).type === 'range') return r.height < 24;
        return Math.min(r.width, r.height) < 43.5;
      })
      .map((el) => `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`),
  );

function record(dev: string, page: string, ok: boolean, notes: string[]): void {
  // un file per dispositivo e pagina: i test girano in parallelo e un file condiviso (leggi-modifica-scrivi) si corrompe
  const dir = `${OUT}/matrix`;
  mkdirSync(dir, { recursive: true });
  writeFileSync(`${dir}/${dev}-${slug(page)}.json`, JSON.stringify({ dev, page, ok, notes }, null, 2));
}

for (const dev of MATRIX) {
  test.describe(`dispositivo ${dev.name}`, () => {
    test.use({ viewport: dev.viewport, deviceScaleFactor: dev.deviceScaleFactor, isMobile: dev.isMobile, hasTouch: dev.hasTouch, ...(dev.userAgent ? { userAgent: dev.userAgent } : {}), reducedMotion: 'reduce' });
    for (const path of PAGES) {
      test(path, async ({ page }) => {
        test.setTimeout(60_000);
        const tv = dev.name.startsWith('tv-');
        const errors = await open(page, path, tv);
        if (tv) await expect(page.locator('html')).toHaveAttribute('data-tv', '1');
        const ox = await overflowX(page);
        const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
        const small = dev.hasTouch ? await smallTargets(page) : [];
        await page.screenshot({ path: `${OUT}/${dev.name}-${slug(path)}.png` });
        const notes = [
          ...(ox > 1 ? [`overflow ${ox}px`] : []),
          ...errors.map((e) => `console: ${e.slice(0, 120)}`),
          ...(cls >= 0.1 ? [`CLS ${cls.toFixed(3)}`] : []),
          ...small.map((s) => `target ${s}`),
        ];
        record(dev.name, path, notes.length === 0, notes);
        expect(ox, 'overflow orizzontale').toBeLessThanOrEqual(1);
        expect(errors, 'errori in console').toEqual([]);
        expect(cls, 'CLS').toBeLessThan(0.1);
        expect(small, 'target < 44px con puntatore grossolano').toEqual([]);
      });
    }
  });
}

for (const zoom of [200, 400]) {
  test.describe(`reflow WCAG a ${zoom}%`, () => {
    test.use({ viewport: { width: 1280 / (zoom / 100), height: 1024 / (zoom / 100) }, deviceScaleFactor: zoom / 100, reducedMotion: 'reduce' });
    for (const path of PAGES) {
      test(path, async ({ page }) => {
        await open(page, path, false);
        expect(await overflowX(page), 'overflow orizzontale').toBeLessThanOrEqual(1);
        expect(await clipped(page), 'testo tagliato').toEqual([]);
        await page.screenshot({ path: `${OUT}/zoom${zoom}-${slug(path)}.png` });
      });
    }
  });
}
