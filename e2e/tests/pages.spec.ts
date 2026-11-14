// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('percorso sconosciuto: pagina 404 con titolo, h1 e link alla home', async ({ page }) => {
  const res = await page.goto('/percorso/che/non-esiste');
  // il server statico serve l'app (html=True) o risponde 404; la pagina deve comunque mostrare il 404 dell'app
  expect(res).not.toBeNull();
  await expect(page).toHaveTitle('Pagina non trovata | RAVEN');
  await expect(page.getByRole('heading', { level: 1, name: 'Pagina non trovata' })).toBeVisible();
  const home = page.getByRole('main').getByRole('link', { name: 'Torna alla home' });
  await expect(home).toBeVisible();
  await home.click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
});

test('navigazione client-side verso un percorso sconosciuto: focus su h1 e annuncio', async ({ page }) => {
  await page.goto('/');
  // il primo rendering della rotta non sposta il focus né annuncia: si attende che sia concluso (data-route-ready)
  await expect(page.locator('main[data-route-ready]')).toHaveCount(1);
  await page.evaluate(() => {
    history.pushState({}, '', '/nulla');
    dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.getByRole('heading', { level: 1, name: 'Pagina non trovata' })).toBeFocused();
  await expect(page).toHaveTitle('Pagina non trovata | RAVEN');
  await expect(page.locator('#announcer')).toHaveText('Pagina Pagina non trovata');
});
