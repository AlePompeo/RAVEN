// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { PAGES } from './pages';

// WCAG 2.2 AA: axe-core copre solo una parte dei criteri (le verifiche manuali restano necessarie).
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** Esclusioni motivate (nessuna al momento). Formato: { selector, regola, motivo }. */
const EXCLUSIONS: { selector: string; rule: string; reason: string }[] = [];

async function settle(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  if (path === '/telemetry') {
    await expect(page.getByRole('region', { name: 'Ultimi campioni' }).locator('tbody tr').first()).toBeVisible({ timeout: 15_000 }); // tabella popolata
    await expect(page.locator('.chart canvas').first()).toBeVisible();
  }
  if (path === '/siti') {
    await expect(page.locator('.stage canvas').or(page.getByRole('alert')).first()).toBeVisible({ timeout: 20_000 });
  }
  if (path === '/simula?tab=onda') await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
  if (path === '/sims') await expect(page.getByLabel('Simulazione')).toBeVisible();
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`axe, tema ${scheme}`, () => {
    test.use({ colorScheme: scheme });
    for (const p of PAGES) {
      test(`${p.path} senza violazioni`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await settle(page, p.path);
        expect(await page.evaluate(() => matchMedia('(prefers-color-scheme: dark)').matches)).toBe(scheme === 'dark');
        let b = new AxeBuilder({ page }).withTags(TAGS);
        for (const e of EXCLUSIONS) b = b.exclude(e.selector);
        const r = await b.analyze();
        const summary = r.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })),
        }));
        expect(summary, JSON.stringify(summary, null, 2)).toEqual([]);
        expect(r.passes.length).toBeGreaterThan(0); // la scansione ha davvero valutato qualcosa
      });
    }
  });
}

test('axe: pagina 404 (percorso sconosciuto)', async ({ page }) => {
  await page.goto('/non-esiste');
  await expect(page.getByRole('heading', { level: 1, name: 'Pagina non trovata' })).toBeVisible();
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(r.violations.map((v) => v.id)).toEqual([]);
});
