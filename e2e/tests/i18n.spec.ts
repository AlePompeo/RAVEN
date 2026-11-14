// SPDX-License-Identifier: Apache-2.0
// Lingue (docs/i18n.md): solo inglese (predefinita) e italiano. Selettore su ogni pagina, cambio senza ricarica e
// ricordato, precedenza di ?lang=, valori malevoli o di lingue rimosse ignorati, nessun overflow orizzontale a 390 e
// 1440, axe pulito. Partenza: italiano (hb.lang=it dalla config).
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { PAGES } from './pages';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

// stringhe della shell per lingua (dai cataloghi frontend/src/i18n/*.json)
const SHELL = {
  en: { tag: 'en', native: 'English', lab: 'Lab', try: 'Try it', footer: 'Licenses', title: 'Home | RAVEN', nav: 'Main' },
  it: { tag: 'it', native: 'Italiano', lab: 'Laboratorio', try: 'Prova tu', footer: 'Licenze', title: 'Home | RAVEN', nav: 'Principale' },
} as const;
type L = keyof typeof SHELL;
const LANGS = Object.keys(SHELL) as L[];

const ready = (page: Page) => expect(page.locator('main[data-route-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
const langBtn = (page: Page) => page.getByTestId('lang-switch').getByRole('button');

async function noOverflow(page: Page, sel: string): Promise<void> {
  const bad = await page.evaluate((s) => {
    const W = document.documentElement.clientWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > W + 1) out.push(`document ${document.documentElement.scrollWidth} > ${W}`);
    for (const root of document.querySelectorAll(s))
      for (const el of [root, ...root.querySelectorAll('*')]) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || getComputedStyle(el).visibility === 'hidden') continue;
        if (el.closest('.visually-hidden')) continue;
        if (r.left < -1 || r.right > W + 1) out.push(`${el.tagName}.${el.className} ${Math.round(r.left)}..${Math.round(r.right)}`);
      }
    return out.slice(0, 8);
  }, sel);
  expect(bad, sel).toEqual([]);
}

test.describe('selettore della lingua', () => {
  for (const p of PAGES) {
    test(`presente su ${p.path}`, async ({ page }) => {
      await page.goto(p.path);
      await ready(page);
      await expect(langBtn(page)).toBeVisible();
      await expect(langBtn(page)).toContainText('Italiano');
    });
  }

  test('cambio senza ricarica, annunciato, ricordato; altri parametri conservati', async ({ page }) => {
    await page.goto('/?mode=learning');
    await ready(page);
    await page.evaluate(() => ((window as unknown as { __mark: number }).__mark = 1));
    await langBtn(page).click();
    const list = page.getByRole('listbox');
    await expect(list.getByRole('option')).toHaveCount(2);
    await expect(list.getByRole('option', { name: /Italiano/ })).toHaveAttribute('aria-selected', 'true');
    // tastiera: freccia su da Italiano (ultima) -> English, Invio
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('Enter');
    await expect(list).toHaveCount(0);
    await expect(langBtn(page)).toBeFocused();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Explore' })).toBeVisible();
    await expect(page.locator('#announcer')).toHaveText('Language: English');
    await expect(page).toHaveTitle('Home | RAVEN');
    expect(new URL(page.url()).searchParams.get('mode')).toBe('learning');
    expect(new URL(page.url()).searchParams.get('lang')).toBe('en');
    expect(await page.evaluate(() => (window as unknown as { __mark?: number }).__mark)).toBe(1); // nessuna ricarica
    expect(await page.evaluate(() => localStorage.getItem('hb.lang'))).toBe('en');
    // navigazione interna e ricarica: la scelta resta
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Explore' }).click();
    await page.getByRole('main').getByRole('link', { name: 'Analyze the link budget', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await page.goto('/licenses');
    await ready(page);
    await expect(langBtn(page)).toContainText('English');
    // e di nuovo in italiano
    await langBtn(page).click();
    await page.getByRole('option', { name: /Italiano/ }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'it');
    await expect(page.locator('#announcer')).toHaveText('Lingua: Italiano');
    expect(await page.evaluate(() => localStorage.getItem('hb.lang'))).toBe('it');
  });

  test('Esc e clic fuori chiudono; mobile: dentro il menu', async ({ page }) => {
    await page.goto('/');
    await ready(page);
    await langBtn(page).click();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('listbox')).toHaveCount(0);
    await expect(langBtn(page)).toBeFocused();
    await langBtn(page).click();
    await page.mouse.click(5, 400);
    await expect(page.getByRole('listbox')).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(langBtn(page)).toBeHidden();
    await page.getByRole('button', { name: 'Menu' }).click();
    await expect(langBtn(page)).toBeVisible();
    expect(await langBtn(page).evaluate((button) => button.clientHeight)).toBeGreaterThanOrEqual(44);
    await langBtn(page).click();
    await page.getByRole('option', { name: /English/ }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await noOverflow(page, 'header');
  });

  for (const dismiss of ['Escape', 'outside'] as const) {
    test(`menu lingua: ${dismiss} annulla anche il primo caricamento lazy`, async ({ page }) => {
      let release!: () => void;
      let requested!: () => void;
      const held = new Promise<void>((resolve) => { release = resolve; });
      const started = new Promise<void>((resolve) => { requested = resolve; });
      await page.route('**/assets/LanguageMenu-*.js', async (route) => {
        requested();
        await held;
        await route.continue();
      });
      try {
        await page.goto('/');
        await ready(page);
        await langBtn(page).click();
        await started;
        if (dismiss === 'Escape') await page.keyboard.press('Escape');
        else await page.mouse.click(5, 400);
        const loaded = page.waitForResponse((r) => /LanguageMenu-.*\.js/.test(r.url()));
        release();
        await (await loaded).finished();
        await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
        await expect(langBtn(page)).toHaveAttribute('aria-expanded', 'false');
        await expect(page.getByRole('listbox')).toHaveCount(0);
      } finally {
        release();
      }
    });
  }

  test('?lang= ha la precedenza sulla scelta salvata', async ({ page }) => {
    await page.goto('/?lang=en');
    await ready(page);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(langBtn(page)).toContainText('English');
  });

  test('?lang= malevolo o di una lingua rimossa ignorato', async ({ page }) => {
    for (const v of ['%3Cscript%3E', 'ar', 'zh', 'hi', 'ko', 'zh-Hans', 'IT']) {
      await page.goto(`/?lang=${v}`);
      await ready(page);
      await expect(page.locator('html')).toHaveAttribute('lang', 'it');
      await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    }
  });

  test('valore salvato di una lingua rimossa ignorato', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('hb.lang', 'ar'));
    await page.goto('/');
    await ready(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    await expect(page.locator('html')).toHaveAttribute('lang', /^(en|it)$/);
  });
});

test('Laboratorio tradotto al cambio di lingua senza ricarica, in entrambe le modalità', async ({ page }) => {
  await page.goto('/laboratorio?mode=learning&lang=it');
  await ready(page);
  const telemetry = page.getByTestId('lab-telemetry');
  const sims = page.getByTestId('lab-sims');
  await expect(telemetry.getByRole('link', { name: 'Apri Telemetria' })).toHaveAttribute('href', '/telemetry');
  await page.evaluate(() => ((window as unknown as { __mark: number }).__mark = 1));

  await langBtn(page).click();
  await page.getByRole('option', { name: /English/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Lab' })).toBeVisible();
  await expect(page.getByTestId('learn-line')).toContainText('tools for exploring further');
  await expect(telemetry.getByRole('link', { name: 'Open telemetry' })).toHaveAttribute('href', '/telemetry');
  await expect(sims.getByRole('link', { name: 'Open simulations' })).toHaveAttribute('href', '/sims');
  await expect(telemetry.locator('.detail')).toHaveCount(0);

  await page.getByRole('button', { name: 'Advanced' }).click();
  await expect(telemetry.locator('.detail')).toContainText('SSE stream from the backend');
  expect(await page.evaluate(() => (window as unknown as { __mark?: number }).__mark)).toBe(1);
  await noOverflow(page, '.workspace');
});

test.describe('overflow e accessibilità in entrambe le lingue', () => {
  for (const l of LANGS) {
    for (const [w, h] of [[390, 844], [1440, 900]] as const) {
      test(`?lang=${l} a ${w}: nessun overflow di barra, piè di pagina e hero`, async ({ page }) => {
        await page.setViewportSize({ width: w, height: h });
        await page.goto(`/?lang=${l}`);
        await ready(page);
        await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
        await noOverflow(page, 'header, .site-footer, .home-hero');
      });
    }
    test(`axe pulito su home e /simula in ${l}`, async ({ page }) => {
      for (const path of [`/?lang=${l}`, `/simula?lang=${l}`]) {
        await page.goto(path);
        await ready(page);
        await expect(page.locator('.hub-wait')).toHaveCount(0, { timeout: 20_000 });
        const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' ')}`), path).toEqual([]);
      }
    });
  }
});

test.describe('smoke della shell per lingua', () => {
  for (const l of LANGS) {
    test(`${l}: home e /simula`, async ({ page }) => {
      const s = SHELL[l];
      await page.goto(`/?lang=${l}`);
      await ready(page);
      await expect(page.locator('html')).toHaveAttribute('lang', s.tag);
      await expect(page).toHaveTitle(s.title);
      await expect(page.locator('header nav').getByRole('link', { name: 'Explore', exact: true })).toBeVisible();
      await expect(page.locator('header nav').getByRole('link', { name: 'Learn', exact: true })).toBeVisible();
      await expect(page.locator('.site-footer').getByRole('link', { name: s.footer })).toBeVisible();
      await expect(page.locator('.hero-actions').getByRole('link', { name: s.try })).toBeVisible();
      await expect(langBtn(page)).toContainText(s.native);
      for (const w of [834, 1024]) {
        await page.setViewportSize({ width: w, height: 900 });
        await noOverflow(page, 'header');
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.locator('header nav').getByRole('link', { name: 'Explore', exact: true }).click();
      await expect(page.locator('html')).toHaveAttribute('lang', s.tag);
      await expect(page.getByRole('main')).toBeVisible();
      await expect(page.locator('header nav a[aria-current="page"]')).toHaveText('Explore');
    });
  }
});
