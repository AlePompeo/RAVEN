// SPDX-License-Identifier: Apache-2.0
// Scena lander contro il backend reale con le tile LOLA in cache: terreno, HUD, sezione laterale, camera.
import { test, expect } from '@playwright/test';
import { defineLanderCore } from './landerSuite';
import { apiScene, frames, openLander, pixels, SITE, T0 } from './landerHelpers';

declare global {
  interface Window {
    __webglResizeChecks: { active: boolean; frames: boolean[] };
  }
}

for (const [path, selector, ready] of [
  [`/lander?site=${SITE}&t=${T0}`, '#lander-stage canvas', '.stage[data-ready="1"]'],
  ['/wave', '.stage canvas', '.stage[data-ready="1"]'],
  ['/viewer', '.stage canvas', '.stage[data-ready="1"]'],
  ['/simula', '.stage canvas', '.stage canvas[data-camera]'],
] as const) {
  test(`WebGL repaints before the resize is composited: ${path}`, async ({ page }) => {
    await page.addInitScript((selector) => {
      window.__webglResizeChecks = { active: false, frames: [] };
      const Native = window.ResizeObserver;
      window.ResizeObserver = class extends Native {
        constructor(callback: ResizeObserverCallback) {
          super((entries, observer) => {
            const canvas = document.querySelector<HTMLCanvasElement>(selector);
            const width = canvas?.width;
            const height = canvas?.height;
            callback(entries, observer);
            if (!window.__webglResizeChecks.active || !canvas || (width === canvas.width && height === canvas.height)) return;
            const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl');
            if (!gl) throw new Error('Expected a live WebGL context');
            const data = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
            gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, data);
            window.__webglResizeChecks.frames.push(data.some((value, i) => i % 4 !== 3 && value !== 0));
          });
        }
      };
    }, selector);
    await page.goto(path);
    await expect(page.locator(ready)).toHaveCount(1, { timeout: 40_000 });
    const canvas = await page.locator(selector).elementHandle();
    await page.evaluate(() => { window.__webglResizeChecks.active = true; });
    for (const width of [1000, 834, 390]) {
      const before = await page.evaluate(() => window.__webglResizeChecks.frames.length);
      await page.setViewportSize({ width, height: 900 });
      await expect.poll(() => page.evaluate(() => window.__webglResizeChecks.frames.length)).toBeGreaterThan(before);
    }
    expect(await page.evaluate(() => window.__webglResizeChecks.frames.every(Boolean))).toBe(true);
    expect(await canvas!.evaluate((el, s) => el === document.querySelector(s), selector)).toBe(true);
    await canvas?.dispose();
  });
}

test.describe('scena lander (WebGL)', () => {
  defineLanderCore('webgl');

  test('usa la mappa stellare NASA e ne dichiara i limiti', async ({ page }, testInfo) => {
    await openLander(page, 'webgl');
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-sky', 'nasa');
    await expect(page.getByTestId('lander-visual-credit')).toContainText('NASA Scientific Visualization Studio');
    await expect(page.getByTestId('lander-visual-credit')).toContainText("orientata per il sito e l'istante");
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-sky-orientation', 'site-time');
    const height = (await page.locator('#lander-stage').boundingBox())!.height;
    const cinematic = page.getByRole('button', { name: 'Vista cinematografica' });
    await cinematic.click();
    await expect(cinematic).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-overlays', 'hidden');
    expect((await page.locator('#lander-stage').boundingBox())!.height).toBeGreaterThan(height);
    await expect(page.getByTestId('hud-margin')).toBeVisible();
    await page.locator('#lander-stage').screenshot({ path: testInfo.outputPath('lander.png') });
    await cinematic.click();
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-overlays', 'visible');
  });

  test('se la mappa stellare non si carica la scena resta utilizzabile e lo segnala', async ({ page }) => {
    await page.route('**/stars-*.webp', (route) => route.abort());
    await openLander(page, 'webgl');
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-sky', 'unavailable');
    await expect(page.getByTestId('lander-sky-error')).toBeVisible();
    await expect(page.getByTestId('lander-hud')).toBeVisible();
  });

  test('senza matrice astronomica dichiara il cielo illustrativo', async ({ page }) => {
    await page.route('**/api/raven/scene*', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      delete body.sky;
      await route.fulfill({ response, json: body });
    });
    await openLander(page, 'webgl');
    await expect(page.locator('#lander-stage canvas')).toHaveAttribute('data-sky-orientation', 'illustrative');
    await expect(page.getByTestId('lander-visual-credit')).toContainText('orientamento del cielo è illustrativo');
  });

  test('la camera cambia da tastiera e con i preset, il ripristino torna alla vista scelta', async ({ page }) => {
    await openLander(page, 'webgl');
    await page.locator('#lander-stage').focus();
    await frames(page);
    const a = await pixels(page);
    for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight');
    await frames(page);
    const b = await pixels(page);
    expect(b.hash).not.toBe(a.hash);
    await page.keyboard.press('2');
    await frames(page);
    const c = await pixels(page);
    expect(c.hash).not.toBe(b.hash);
    await expect(page.getByRole('button', { name: 'Laterale' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: "Dall'alto" }).click();
    await frames(page);
    expect((await pixels(page)).hash).not.toBe(c.hash);
    await page.getByRole('button', { name: 'Ingrandisci' }).click();
    await frames(page);
    await page.keyboard.press('1');
    await frames(page);
    expect((await pixels(page)).lit).toBeGreaterThan(0);
  });

  test('la scheda Sezione laterale mostra il canvas 2D non vuoto e i controlli 3D restano', async ({ page }) => {
    await openLander(page, 'webgl');
    await page.getByRole('tab', { name: 'Sezione laterale' }).click();
    const box = page.getByTestId('section-canvas');
    await expect(box.locator('canvas')).toHaveCount(1);
    await frames(page, '[data-testid="section-canvas"] canvas');
    const p = await pixels(page, '[data-testid="section-canvas"] canvas');
    expect(p.lit / p.total).toBeGreaterThan(0.08);
    expect(p.distinct).toBeGreaterThan(12);
    await expect(page.getByRole('button', { name: 'Dal lander' })).toBeVisible();
  });

  test('la vista dal lander cambia con l’altezza del palo e l’API riceve il valore', async ({ page, request }) => {
    await openLander(page, 'webgl');
    const changed = page.waitForRequest((r) =>
      new URL(r.url()).pathname === '/api/raven/scene' && new URL(r.url()).searchParams.get('antenna_height_m') === '6');
    await page.locator('#l-mast').fill('6');
    await expect(page.getByTestId('hud-antenna')).toContainText('palo 6,0 m', { timeout: 20_000 });
    expect(new URL((await changed).url()).searchParams.get('antenna_height_m')).toBe('6');
    const api = await apiScene(request, SITE, T0, 6);
    expect(api.antenna.mast_height_m).toBe(6);
  });
});
