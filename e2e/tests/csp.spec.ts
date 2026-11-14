// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { PAGES } from './pages';

// La CSP `default-src 'self'` del backend deve essere compatibile con Vite, three.js e uPlot in un browser reale.
test('nessuna violazione CSP ne errore di console su nessuna pagina', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  for (const p of PAGES) {
    const snapshot = p.path.startsWith('/siti')
      ? page.waitForResponse((response) => response.url().includes('/api/raven/snapshot'))
      : null;
    await page.goto(p.path);
    await expect(page.getByRole('heading', { level: 1, name: p.h1 })).toBeVisible();
    if (p.path === '/telemetry') await expect(page.locator('.chart canvas').first()).toBeVisible();
    if (p.path === '/simula?tab=onda') await expect(page.locator('.stage canvas')).toHaveCount(1, { timeout: 20_000 });
    if (snapshot) {
      await expect(page.locator('.stage canvas').or(page.getByRole('alert')).first()).toBeVisible({ timeout: 20_000 });
      await (await snapshot).finished();
    }
  }
  expect(problems).toEqual([]);
});

test('header di sicurezza presenti sulla pagina HTML servita', async ({ request }) => {
  const res = await request.get('/');
  const h = res.headers();
  expect(h['content-security-policy']).toContain("default-src 'self'");
  expect(h['x-content-type-options']).toBe('nosniff');
  expect(h['set-cookie']).toBeUndefined();
});
