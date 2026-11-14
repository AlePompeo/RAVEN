// SPDX-License-Identifier: Apache-2.0
// Prove comuni della pagina Onda 3D, eseguite con WebGL (wave.spec.ts) e senza (wave-no-webgl.spec.ts).
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';
import { CANVAS, frames, openWave, pixels } from './waveHelpers';

export function defineWaveCore(mode: 'webgl' | 'canvas2d'): void {
  test(`la superficie non è vuota (${mode}) e cambia con la camera da tastiera`, async ({ page }) => {
    await openWave(page, mode);
    const a = await pixels(page);
    expect(a.lit / a.total, 'quota di pixel che non sono sfondo').toBeGreaterThan(0.08);
    expect(a.distinct, 'colori distinti (colormap + luce)').toBeGreaterThan(60);

    await page.locator('.stage').focus();
    await frames(page);
    const a1 = await pixels(page); // con l'anello di focus
    for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight');
    await frames(page);
    const b = await pixels(page);
    expect(b.hash).not.toBe(a1.hash);
    expect(b.lit / b.total).toBeGreaterThan(0.08);
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('+');
    await frames(page);
    const c = await pixels(page);
    expect(c.hash).not.toBe(b.hash);
    await page.keyboard.press('0');
    await frames(page);
    if (mode === 'canvas2d') expect((await pixels(page)).hash).toBe(a1.hash); // ripristino esatto
    else expect((await pixels(page)).lit).toBeGreaterThan(0);
  });

  test(`il cursore sposta il piano della sezione (${mode}) e aggiorna il grafico`, async ({ page }) => {
    await openWave(page, mode);
    await expect(page.getByTestId('cursor-value')).toHaveText('2000');
    const a = await pixels(page);
    await page.getByLabel(/Distanza dal crinale/).fill('800');
    await expect(page.getByTestId('cursor-value')).toHaveText('800');
    await expect(page.getByRole('heading', { name: 'Sezione a 800 m' })).toBeVisible();
    await frames(page);
    expect((await pixels(page)).hash).not.toBe(a.hash);
    await expect(page.locator('.chart[data-ready="1"] canvas').first()).toBeVisible({ timeout: 15_000 });
    // passi da tastiera sulla scena: parentesi quadre
    await page.locator('.stage').focus();
    await page.keyboard.press(']');
    await expect(page.getByTestId('cursor-value')).not.toHaveText('800');
  });

  test(`nessun overflow a 390 px e axe senza violazioni (${mode})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openWave(page, mode);
    const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    expect(o.sw).toBeLessThanOrEqual(o.cw);
    await expect(page.locator(CANVAS)).toBeVisible();
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
      expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) })), scheme).toEqual([]);
    }
  });
}
