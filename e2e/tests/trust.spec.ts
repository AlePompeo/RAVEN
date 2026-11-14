// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.use({ storageState: { cookies: [], origins: [] } });

for (const language of ['en', 'it'] as const) {
  test(`privacy, storage and usage conditions in ${language}`, async ({ page }) => {
    await page.goto(`/privacy?lang=${language}`);
    await expect(page.getByRole('heading', { name: language === 'en' ? 'Legal information is not complete' : 'Informazioni legali non complete' })).toBeVisible();
    await page.getByRole('link', { name: language === 'en' ? 'Storage, consent and local-data guidance' : 'Archiviazione, consenso e gestione dei dati locali', exact: true }).click();
    await expect(page.getByText('hb.planner-journey.history.v1')).toBeVisible();
    const box = page.getByRole('checkbox', { name: language === 'en' ? 'Usage analytics' : 'Statistiche di utilizzo' });
    await expect(box).not.toBeChecked();
    await box.check();
    await expect(page.getByRole('status').filter({ hasText: language === 'en' ? 'Choice saved.' : 'Scelta salvata.' })).toBeVisible();
    await page.getByRole('navigation', { name: language === 'en' ? 'Legal' : 'Note legali' }).getByRole('link', { name: language === 'en' ? 'Terms of use' : "Condizioni d'uso" }).click();
    await expect(page.getByRole('heading', { name: language === 'en' ? 'Terms of use' : "Condizioni d'uso", level: 1 })).toBeVisible();
    await expect(page.getByText(language === 'en' ? /not an approved commercial service contract/ : /Non sono un contratto commerciale approvato/)).toBeVisible();
  });
}

test('removed Contacts sections stay absent and legal links work under the /app/ deployment prefix', async ({ page }) => {
  const proxy = `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? 8001}`;
  await page.goto(`${proxy}/app/contacts?lang=en`);
  await expect(page.getByRole('heading', { name: 'The team', level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Help and support' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Team information to complete' })).toHaveCount(0);
  await expect(page.getByText(/No verified public support address/)).toHaveCount(0);
  await page.getByRole('navigation', { name: 'Legal' }).getByRole('link', { name: 'Cookies', exact: true }).click();
  await expect(page).toHaveURL(/\/app\/cookies/);
  await page.getByRole('navigation', { name: 'Legal' }).getByRole('link', { name: 'Terms of use' }).click();
  await expect(page).toHaveURL(/\/app\/terms/);
});

test('legal information is accessible on mobile and linked from Plans', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of ['/privacy', '/cookies', '/terms']) {
    await page.goto(`${route}?lang=en`);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(audit.violations.map((violation) => violation.id)).toEqual([]);
  }
  await page.goto('/pricing?lang=en');
  await page.locator('main').getByRole('link', { name: 'Terms of use', exact: true }).click();
  await expect(page).toHaveURL(/\/terms/);
});
