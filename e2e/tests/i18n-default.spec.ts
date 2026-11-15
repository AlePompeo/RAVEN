// SPDX-License-Identifier: Apache-2.0
// Progetto "en-default" (playwright.config.ts): nessuna lingua salvata, browser en-US -> il sito parte in inglese.
import { test, expect } from '@playwright/test';

test('predefinito inglese senza scelta salvata', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('main[data-route-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  await expect(page).toHaveTitle('Home | RAVEN');
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Home' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Try and learn' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Mode' })).toHaveCount(0);
  await expect(page.getByTestId('lang-switch')).toContainText('English');
  expect(await page.evaluate(() => localStorage.getItem('hb.lang'))).toBeNull();
});

test('browser in italiano senza scelta salvata -> italiano', async ({ browser, baseURL }) => {
  const ctx = await browser.newContext({ baseURL, locale: 'it-IT', storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'it', { timeout: 20_000 });
  await expect(page.getByTestId('lang-switch')).toContainText('Italiano');
  await ctx.close();
});

test('browser in una lingua non supportata (hindi) -> inglese', async ({ browser, baseURL }) => {
  const ctx = await browser.newContext({ baseURL, locale: 'hi-IN', storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en', { timeout: 20_000 });
  await ctx.close();
});
