import { test } from '@playwright/test';
test('diag', async ({ page }) => {
  const t0 = Date.now();
  page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text().slice(0, 200)));
  page.on('pageerror', (e) => console.log('PAGEERR', String(e).slice(0, 300)));
  page.on('response', (r) => r.url().includes('/api/') && console.log('RESP', Date.now() - t0, r.status(), r.url().slice(-80)));
  page.on('requestfailed', (r) => console.log('FAILED', r.url().slice(-80)));
  await page.goto('/viewer?body=moon&t=2027-04-07T00%3A00%3A00Z&mode=avanzato');
  await page.locator('.stage[data-ready="1"]').waitFor({ timeout: 60000 });
  console.log('READY', Date.now() - t0);
  await page.getByTestId('fspl-delta').waitFor({ timeout: 60000 });
  console.log('FSPL', Date.now() - t0);
});
