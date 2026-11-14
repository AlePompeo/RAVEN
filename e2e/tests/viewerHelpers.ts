// SPDX-License-Identifier: Apache-2.0
// Utilità condivise dai test del visualizzatore (non è un file di test).
import { expect, type Page } from '@playwright/test';

export const BODIES = [
  { id: 'moon', name: 'Luna' },
  { id: 'earth', name: 'Terra' },
] as const;
export const OUT = 'test-results/ui/bodies';

export async function ready(page: Page): Promise<void> {
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
}

export async function shootAll(page: Page, w: number, tag: 'webgl' | 'nogl'): Promise<void> {
  await page.setViewportSize({ width: w, height: w === 1440 ? 900 : 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const b of BODIES) {
    await page.goto(`/viewer?body=${b.id}`);
    await ready(page);
    await expect(page.getByTestId('viewer-mode')).toHaveAttribute('data-mode', tag === 'nogl' ? 'canvas2d' : /webgl|canvas2d/);
    await page.screenshot({ path: `${OUT}/${b.id}-${w}-${tag}.png` });
  }
}

