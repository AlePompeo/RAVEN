// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

const FALLBACK = 'Impossibile caricare la visualizzazione 3D. Usa la descrizione testuale.';

test.describe('visualizzatore 3D', () => {
  test('canvas WebGL reale oppure fallback testuale (mai pagina vuota)', async ({ page }, info) => {
    await page.goto('/viewer');
    await expect(page.getByRole('heading', { level: 1, name: 'Siti – Globo e classifica' })).toBeVisible();
    const canvas = page.locator('.stage canvas');
    const fallback = page.getByRole('alert').filter({ hasText: FALLBACK });
    // attende l'uno o l'altro esito del caricamento pigro di three.js
    await expect(canvas.or(fallback).first()).toBeVisible({ timeout: 20_000 });

    const webgl = await page.evaluate(() => {
      const c = document.createElement('canvas');
      return !!(c.getContext('webgl2') ?? c.getContext('webgl'));
    });
    info.annotations.push({ type: 'webgl', description: webgl ? 'disponibile (software GL)' : 'NON disponibile' });
    if (webgl) {
      await expect(canvas).toHaveCount(1);
      await expect(fallback).toHaveCount(0);
      const box = await canvas.boundingBox();
      expect(box!.width).toBeGreaterThan(100);
      expect(box!.height).toBeGreaterThan(100);
    } else {
      await expect(fallback).toBeVisible();
    }
    if (webgl) {
      await expect(page.getByTestId('viewer-mode')).toHaveText('Accelerazione WebGL attiva');
      await page.waitForTimeout(500);
      const png = await page.locator('.stage').screenshot();
      await info.attach('viewer-webgl', { body: png, contentType: 'image/png' });
      await page.screenshot({ path: 'test-results/viewer-webgl.png', fullPage: true });
    }
    // in entrambi i casi la descrizione testuale equivalente e presente
    await expect(page.locator('#scene-description')).not.toBeEmpty();
  });

  test('i controlli da tastiera aggiornano la descrizione della scena', async ({ page }) => {
    await page.goto('/viewer');
    const desc = page.locator('#scene-description');
    const before = await desc.textContent();
    const btn = page.getByRole('button', { name: 'Ruota a destra' });
    await btn.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => desc.textContent()).not.toBe(before);
    await expect(page.locator('[role=status][aria-live=polite]').last()).toContainText('Vista aggiornata', { timeout: 5_000 });
  });

  test('senza preferenza di riduzione del movimento: rotazione automatica attivabile', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/viewer');
    const toggle = page.getByRole('button', { name: 'Rotazione automatica' });
    await expect(toggle).toBeVisible();
    const initial = await toggle.getAttribute('aria-pressed');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', initial === 'true' ? 'false' : 'true');
  });

  test('prefers-reduced-motion: reduce rimuove il comando di rotazione automatica', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/viewer');
    await expect(page.getByRole('button', { name: 'Rotazione automatica' })).toHaveCount(0);
    await expect(page.getByText('Rotazione automatica disattivata')).toBeVisible();
    // reattivita': tornando a no-preference il comando ricompare senza ricaricare
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(page.getByRole('button', { name: 'Rotazione automatica' })).toBeVisible();
  });
});
