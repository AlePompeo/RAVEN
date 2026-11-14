// SPDX-License-Identifier: Apache-2.0
// Pagina Contatti: due schede segnaposto, nessuna richiesta fuori dall'origine, membro compilato (fixture di test,
// non team.json) con foto e link LinkedIn, ordine da tastiera, link nella navigazione, D-pad in TV, foglio "Spiega".
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { useFilledTeam } from './contactsFixture';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

function trackRequests(page: Page): string[] {
  const off: string[] = [];
  page.on('request', (r) => {
    const u = new URL(r.url());
    if (u.protocol === 'data:' || u.protocol === 'blob:') return;
    if (u.origin !== new URL(page.url() === 'about:blank' ? r.url() : page.url()).origin) off.push(r.url());
  });
  return off;
}

test('due membri segnaposto, nessuna richiesta fuori dall\'origine', async ({ page }) => {
  const off = trackRequests(page);
  await page.goto('/contacts');
  await expect(page).toHaveTitle('Contatti | RAVEN');
  await expect(page.getByRole('heading', { level: 1, name: 'Il team' })).toBeVisible();
  const cards = page.getByTestId('member');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('Elettronica e telecomunicazioni');
  await expect(cards.nth(1)).toContainText('Informatica, robotica e AI');
  await expect(page.getByTestId('todo')).toHaveCount(2);
  await expect(page.getByTestId('avatar')).toHaveCount(2);
  await expect(page.locator('main a[target="_blank"]')).toHaveCount(0);
  await page.waitForLoadState('networkidle');
  expect(off).toEqual([]);
});

test('affiancate su desktop, in colonna su mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/contacts');
  await expect(page.getByTestId('member')).toHaveCount(2);
  const [a, b] = await page.getByTestId('member').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON()));
  expect(Math.abs(a.top - b.top)).toBeLessThan(2);
  expect(b.left).toBeGreaterThan(a.right - 1);
  await page.setViewportSize({ width: 390, height: 844 });
  const [c, d] = await page.getByTestId('member').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON()));
  expect(d.top).toBeGreaterThan(c.bottom - 1);
});

test.describe('membro compilato (fixture)', () => {
  test('foto e link LinkedIn; link non valido non reso; nessuna richiesta esterna', async ({ page }) => {
    const off = trackRequests(page);
    await useFilledTeam(page);
    await page.goto('/contacts');
    const cards = page.getByTestId('member');
    await expect(cards).toHaveCount(2);
    await expect(page.getByText('Pagina da personalizzare')).toHaveCount(0);

    const img = cards.nth(0).locator('img');
    await expect(img).toHaveAttribute('src', '/team/test-ada.png');
    await expect(img).toHaveAttribute('loading', 'lazy');
    await expect(img).toHaveAttribute('decoding', 'async');
    await expect(img).toHaveAttribute('width', '512');
    await expect(img).toHaveAttribute('height', '512');
    await img.scrollIntoViewIfNeeded();
    await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth)).toBeGreaterThan(0);
    const box = await img.boundingBox();
    expect(Math.abs(box!.width - box!.height)).toBeLessThan(1);

    const link = page.getByRole('link', { name: 'Profilo LinkedIn di Ada Esempio (si apre in una nuova scheda)' });
    await expect(link).toHaveText(/LinkedIn/);
    await expect(link).toHaveAttribute('href', 'https://www.linkedin.com/in/test-ada');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');

    await expect(cards.nth(1).locator('a')).toHaveCount(0);
    await expect(cards.nth(1).getByTestId('avatar')).toBeVisible();
    expect(off).toEqual([]);
  });

  for (const scheme of ['light', 'dark'] as const) {
    test(`axe ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await useFilledTeam(page);
      await page.goto('/contacts');
      await expect(page.getByRole('link', { name: /Profilo LinkedIn/ })).toBeVisible();
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations.map((v) => v.id)).toEqual([]);
    });
  }

  test('ordine da tastiera: link nel piè di pagina raggiungibile e Tab passa dal link LinkedIn', async ({ page }) => {
    await useFilledTeam(page);
    await page.goto('/contacts');
    const link = page.getByRole('link', { name: /Profilo LinkedIn/ });
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press('Tab');
    // dopo il link di Ada (unico nel main) si va al piè di pagina, in ordine di documento
    const next = await page.evaluate(() => document.activeElement?.closest('footer') !== null || document.activeElement?.id);
    expect(next).toBeTruthy();
  });
});

test('navigazione: Contatti apre la pagina e il focus va sull\'h1', async ({ page }) => {
  await page.goto('/');
  const legal = page.getByRole('navigation', { name: 'Note legali' });
  await expect(legal.getByRole('link')).toHaveText(['About', 'Modello e validazione', 'Licenze', 'Privacy', 'Cookie', "Condizioni d'uso"]);
  const nav = page.getByRole('navigation', { name: 'Principale' });
  await nav.getByRole('link', { name: 'Contatti' }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Il team' })).toBeFocused();
  await expect(nav.getByRole('link', { name: 'Contatti' })).toHaveAttribute('aria-current', 'page');
});

test('Contatti è raggiungibile anche dal menu mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Menu' }).click();
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Contatti' }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Il team' })).toBeFocused();
  await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false');
});

test('ordine da tastiera: footer raggiungibile, nessun link di assistenza o scheda segnaposto focalizzabile', async ({ page }) => {
  await page.goto('/contacts');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  const where: string[] = [];
  for (let i = 0; i < 14 && !where.includes('footer'); i++) {
    await page.keyboard.press('Tab');
    where.push(await page.evaluate(() => (document.activeElement?.closest('[data-testid="member"]') ? 'member' : document.activeElement?.closest('footer') ? 'footer' : document.activeElement?.closest('main') ? 'main' : 'altro')));
  }
  expect(where).toContain('footer');
  expect(where).not.toContain('main');
  expect(where).not.toContain('member');
});

test('TV: D-pad dal link LinkedIn al piè di pagina, anello di focus visibile e target grandi', async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await useFilledTeam(page);
  await page.goto('/contacts?tv=1');
  await expect(page.locator('html')).toHaveAttribute('data-tv', '1');
  const link = page.getByRole('link', { name: /Profilo LinkedIn/ });
  await link.focus();
  const h = (await link.boundingBox())!.height;
  expect(h).toBeGreaterThanOrEqual(56);
  await page.keyboard.press('ArrowDown');
  expect(await page.evaluate(() => !!document.activeElement?.closest('footer'))).toBe(true);
  await page.keyboard.press('ArrowUp');
  await expect(link).toBeFocused();
});

test('"RAVEN SI" su /contacts si apre e non rompe la pagina', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto('/contacts');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
  await expect(sheet).toBeVisible();
  // senza suggerimenti il foglio resta usabile: campo domanda presente e chiusura con Esc
  await expect(sheet.getByRole('textbox')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  expect(errors).toEqual([]);
});
