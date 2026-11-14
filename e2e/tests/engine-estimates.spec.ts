// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Quantities no site provides, estimated by the engine: an interval, its source and tag; unknown stays unknown.
test('model page: engine estimates with intervals, sources and unknowns', async ({ page }) => {
  await page.goto('/model?lang=en');
  const box = page.getByTestId('engine-estimates');
  await expect(box).toBeVisible({ timeout: 30_000 });
  await expect(box).toContainText('Regolith permittivity (real part)');
  await expect(box).toContainText('NTRS 19780005009');
  await expect(box).toContainText('Surface roughness, rms (m)');
  await expect(box.locator('dd', { hasText: 'Unknown' }).first()).toBeVisible(); // roughness and component failure rates
  await expect(box).toContainText('ambiguous');
  await expect(box).toContainText('Tag I');
  expect((await new AxeBuilder({ page }).include('[data-testid="engine-estimates"]').analyze()).violations).toEqual([]);
});
