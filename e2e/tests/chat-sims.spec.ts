// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

// La chat (Learning Assistant) è in assistant.spec.ts.

test.describe('simulazioni', () => {
  test('RAVEN usa un profilo sintetico e confronta la perdita con il plugin C', async ({ page }) => {
    await page.goto('/sims');
    await page.getByLabel('Simulazione').selectOption('grazinglink-link');
    await expect(page.getByLabel('Nome ingresso 1')).toHaveValue('earth_el_deg');
    await expect(page.getByLabel('Nome ingresso 2')).toHaveValue('ridge_radius_m');
    await page.getByRole('button', { name: 'Esegui' }).click();
    await expect(page.getByText('Profilo sintetico di prova', { exact: false })).toBeVisible();
    await expect(page.getByText('Perdita nello spazio libero: Python', { exact: false })).toContainText('C − Python');
    await expect(page.getByRole('row', { name: /^profile_synthetic\b/ }).getByRole('cell')).toHaveText('1');
  });

  test('example-sim con x=3 restituisce y=9', async ({ page }) => {
    await page.goto('/sims');
    await expect(page.getByLabel('Simulazione')).toBeVisible();
    await page.getByLabel('Simulazione').selectOption('example-sim');
    await page.getByLabel('Nome ingresso 1').fill('x');
    await page.getByLabel('Valore 1').fill('3');
    await page.getByRole('button', { name: 'Esegui' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Simulazione completata.' })).toBeVisible();
    const row = page.getByRole('row', { name: /^y\b/ });
    await expect(row.getByRole('cell')).toHaveText('9');
  });

  test('ingresso non numerico: errore di campo, focus sul campo e nessuna chiamata al server', async ({ page }) => {
    let posted = false;
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/run')) posted = true;
    });
    await page.goto('/sims');
    await page.getByLabel('Nome ingresso 1').fill('x');
    await page.getByLabel('Valore 1').fill('abc');
    await page.getByRole('button', { name: 'Esegui' }).click();
    await expect(page.getByLabel('Valore 1')).toBeFocused();
    await expect(page.getByLabel('Valore 1')).toHaveAttribute('aria-invalid', 'true');
    expect(posted).toBe(false);
  });
});
