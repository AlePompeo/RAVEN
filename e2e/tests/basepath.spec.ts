// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

// Frontend compilato con `vite build --base=/app/` (e2e/scripts/build-app.sh) dietro un reverse proxy che
// espone l'app sotto /app/ e toglie il prefisso (e2e/scripts/prefix-proxy.mjs, porta 8001 -> backend 8002).
test.use({ baseURL: 'http://127.0.0.1:8001' });

test.describe('base path /app/', () => {
  test('home, link di navigazione e cambio rotta rispettano la base', async ({ page }) => {
    const failed: string[] = [];
    page.on('response', (r) => {
      if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`);
    });
    await page.goto('/app/');
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
    const logos = page.locator('.brand img, #home-title img');
    await expect(logos).toHaveCount(3);
    await expect.poll(() => logos.evaluateAll((items) =>
      items.every((item) => item instanceof HTMLImageElement && item.complete && item.naturalWidth > 0),
    )).toBe(true);
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/app/favicon.png');
    expect((await page.request.get('/app/favicon.png')).ok()).toBe(true);
    const nav = page.getByRole('navigation', { name: 'Principale' });
    await expect(nav.getByRole('link', { name: 'Contatti' })).toHaveAttribute('href', '/app/contacts');
    await expect(nav.getByRole('link', { name: 'Explore' })).toHaveAttribute('href', '/app/explore');
    await nav.getByRole('link', { name: 'Explore' }).click();
    await expect(page.getByRole('main').getByRole('link', { name: 'Analizza il link budget', exact: true })).toHaveAttribute('href', '/app/analizza');
    await page.getByRole('main').getByRole('link', { name: 'Analizza il link budget', exact: true }).click();
    await expect(page).toHaveURL(/\/app\/analizza$/);
    await expect(page).toHaveTitle('Link budget | RAVEN');
    await expect(page.getByRole('heading', { level: 1, name: 'Link budget' })).toBeFocused();
    expect(failed).toEqual([]);
  });

  test('una vecchia rotta sotto la base porta alla nuova, query conservata', async ({ page }) => {
    await page.goto('/app/wave?mode=avanzato');
    await expect(page).toHaveURL(/\/app\/simula\?mode=avanzato&tab=onda$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Simula – Onda 3D' })).toBeVisible();
  });

  test('ricaricamento diretto di una sotto-rotta e 404 interno sotto la base', async ({ page }) => {
    await page.goto('/app/privacy');
    await expect(page.getByRole('heading', { level: 1, name: 'Informativa sulla privacy' })).toBeVisible();
    await page.goto('/app/nulla');
    await expect(page.getByRole('heading', { level: 1, name: 'Pagina non trovata' })).toBeVisible();
  });

  test('la licenza del carattere display è disponibile sotto la base', async ({ page }) => {
    await page.goto('/app/licenses');
    const license = page.getByRole('row', { name: /Carattere Orbitron/ }).getByRole('link');
    await expect(license).toHaveAttribute('href', '/app/fonts/orbitron-OFL.txt');
    const response = await page.request.get('/app/fonts/orbitron-OFL.txt');
    expect(response.ok()).toBe(true);
    expect(await response.text()).toContain('The Orbitron Project Authors');
  });

  test('il link "Torna alla home" del 404 resta sotto la base /app/', async ({ page }) => {
    await page.goto('/app/nulla');
    const link = page.getByRole('main').getByRole('link', { name: 'Torna alla home' });
    await expect(link).toHaveAttribute('href', '/app/');
    await link.click();
    await expect(page).toHaveURL(/\/app\/$/);
  });

  test('le API (percorso assoluto /api) funzionano dalla pagina sotto /app/', async ({ page }) => {
    await page.goto('/app/sims');
    await expect(page.getByLabel('Simulazione')).toBeVisible();
    await expect(page.getByLabel('Simulazione').locator('option', { hasText: 'example-sim' })).toHaveCount(1);
  });
});
