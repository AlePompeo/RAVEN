// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test.describe('navigazione solo tastiera', () => {
  test('il primo Tab raggiunge lo skip link e Invio porta il focus su <main>', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
    await page.keyboard.press('Tab');
    const skip = page.getByRole('link', { name: 'Salta al contenuto' });
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page.locator('main#main')).toBeFocused();
    expect(new URL(page.url()).hash).toBe('#main');
  });

  // Barra globale: strumenti nell'ordine del registro; le pagine legali stanno nel piè di pagina ("Note legali").
  test('i link di navigazione sono raggiungibili con Tab dopo lo skip link (ciascuno una volta, in ordine)', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
    await page.keyboard.press('Tab'); // skip link
    const names: string[] = [];
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab');
      names.push(await page.evaluate(() => document.activeElement?.textContent?.trim() ?? ''));
    }
    expect(names).toEqual([
      'RAVEN', // marchio, collegamento alla home
      'Home',
      'Mission Planner',
      'Dashboard',
      'Explore',
      'Learn',
      'Piani', // pagina Piani (pricing, order 25)
      'Contatti',
    ]);
  });

  test('il piè di pagina ha Modello e validazione, Licenze, Privacy, Cookie in questo ordine', async ({ page }) => {
    await page.goto('/');
    const legal = page.getByRole('navigation', { name: 'Note legali' });
    await expect(legal.getByRole('link')).toHaveText(['About', 'Modello e validazione', 'Licenze', 'Privacy', 'Cookie', "Condizioni d'uso"]);
  });

  test('navigando verso una pagina con schede (Simula) il focus arriva sull\'h1 della scheda caricata', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' }).click();
    const link = page.getByRole('main').getByRole('link', { name: 'Simula la scena' });
    await link.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/simula\?tab=scena$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Simulatore' })).toBeFocused();
    await expect(page.getByRole('tab', { name: 'Scena' })).toHaveAttribute('aria-selected', 'true');
  });

  test('le pagine legali sono nel piè di pagina e raggiungibili da tastiera', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main[data-route-ready="1"]')).toBeVisible();
    const legal = page.getByRole('navigation', { name: 'Note legali' });
    for (const name of ['Licenze', 'Privacy', 'Cookie']) {
      const link = legal.getByRole('link', { name });
      await link.focus();
      await expect(link).toBeFocused();
    }
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/cookies$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Cookie e archiviazione locale' })).toBeFocused();
  });

  test('cambio rotta con tastiera: focus sull\'h1 e document.title aggiornato', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Home | RAVEN');
    const link = page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' });
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeFocused();
    await page.getByRole('main').getByRole('link', { name: 'Analizza il link budget', exact: true }).click();
    await expect(page).toHaveTitle('Link budget | RAVEN');
    const h1 = page.getByRole('heading', { level: 1, name: 'Link budget' });
    await expect(h1).toBeFocused();
    await expect(link).toHaveAttribute('aria-current', 'page');
    // il cambio di pagina viene annunciato alle tecnologie assistive
    await expect(page.locator('#announcer')).toHaveText('Pagina Link budget');
  });
});
