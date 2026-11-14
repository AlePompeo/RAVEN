// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('plans disclose proposed prices and do not offer an unconfigured purchase', async ({ page }) => {
  await page.goto('/pricing');
  await expect(page).toHaveTitle('Piani | RAVEN');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Una nuova prospettiva sulle missioni lunari.');
  await expect(page.locator('.plan h3')).toHaveText(['Free', 'Premium', 'Enterprise']);
  await expect(page.getByText('Acquisto non ancora disponibile')).toHaveCount(2);
  await expect(page.getByRole('link', { name: 'Apri checkout esterno' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Apri Mission Planner' })).toHaveAttribute('href', '/mission-planner');
  await expect(page.getByText(/non attiva automaticamente/)).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  expect(result.violations.map((v) => v.id)).toEqual([]);
});

for (const mode of ['learning', 'avanzato']) {
  test(`tabella di confronto: spunte e croci con testo, righe prevista (${mode})`, async ({ page }) => {
    await page.goto(`/pricing?mode=${mode}`);
    const region = page.getByRole('region', { name: /Tabella di confronto dei piani/ });
    await expect(region).toHaveAttribute('tabindex', '0');
    const table = region.getByRole('table');
    await expect(table.locator('thead').getByRole('columnheader')).toHaveText(['Funzionalità', 'Free', 'Premium', 'Enterprise']);
    for (const g of ['Analisi', 'Dati, terreno e apprendimento', 'Report ed esportazione', 'Supporto e licenza']) {
      await expect(table.getByRole('columnheader', { name: g })).toBeVisible();
    }
    const rf = table.getByRole('row', { name: /Analisi RF avanzata/ });
    await expect(rf.getByRole('cell')).toHaveText([/✕\s*Non incluso/, /✓\s*Incluso/, /✓\s*Incluso/]);
    const pdf = table.getByRole('row', { name: /Report PDF strutturato/ });
    await expect(pdf.getByRole('rowheader')).toContainText('Prevista');
    await expect(table.getByRole('row', { name: /Geometria di Sole e Terra/ }).getByRole('rowheader')).not.toContainText('Prevista');
    await expect(table.getByText('Non incluso').first()).toBeAttached();
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
}

test('tabella a 390px: nessun overflow di pagina, scorrimento nella regione con tastiera', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/pricing');
  const region = page.getByRole('region', { name: /Tabella di confronto dei piani/ });
  await region.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await region.focus();
  await expect(region).toBeFocused();
  expect(await region.evaluate((el) => el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight)).toBe(true);
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => region.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const head = page.getByRole('columnheader', { name: 'Premium' });
  const y = (await head.boundingBox())!.y;
  const top = (await region.boundingBox())!.y;
  expect(Math.abs(y - top)).toBeLessThan(4);
});

for (const width of [834, 390]) {
  test(`navigation reaches plans without overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    if (width < 834) await page.getByRole('button', { name: 'Menu' }).click();
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Piani' }).click();
    await expect(page).toHaveURL(/\/pricing$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
