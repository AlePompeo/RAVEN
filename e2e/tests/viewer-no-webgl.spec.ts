// SPDX-License-Identifier: Apache-2.0
// Chromium avviato SENZA WebGL (nessuna GPU, API 3D disabilitate): il visualizzatore deve comunque
// mostrare una scena grafica, tramite il renderer Canvas 2D.
import { test, expect, type Page } from '@playwright/test';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

const STAGE_CANVAS = '.stage canvas';

/** Legge i pixel del canvas 2D della scena (stesso contesto che disegna: nessuna copia). */
async function pixels(page: Page): Promise<{ distinct: number; opaque: number; hash: number; total: number }> {
  return page.evaluate((sel) => {
    const c = document.querySelector<HTMLCanvasElement>(sel)!;
    const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    const seen = new Set<number>();
    let opaque = 0;
    let hash = 0;
    for (let i = 0; i < d.length; i += 4) {
      const a = d[i + 3]!;
      if (a === 0) continue;
      opaque++;
      const key = ((d[i]! << 16) | (d[i + 1]! << 8) | d[i + 2]!) >>> 0;
      seen.add(key);
      hash = (Math.imul(hash, 31) + key) | 0;
    }
    return { distinct: seen.size, opaque, hash, total: d.length / 4 };
  }, STAGE_CANVAS);
}

async function openViewer(page: Page): Promise<void> {
  await page.goto('/viewer');
  await expect(page.getByRole('heading', { level: 1, name: 'Siti – Globo e classifica' })).toBeVisible();
  await expect(page.getByTestId('viewer-mode')).toHaveText('Modalità compatibile (senza WebGL)', { timeout: 20_000 });
  await expect(page.locator(STAGE_CANVAS)).toHaveCount(1);
  // attende il primo frame disegnato e la scena definitiva (mappe NASA caricate, piena risoluzione)
  await expect.poll(async () => (await pixels(page)).distinct, { timeout: 10_000 }).toBeGreaterThan(50);
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 15_000 });
}

test.describe('visualizzatore senza WebGL (Chromium senza GPU)', () => {
  test('precondizione: WebGL è davvero assente in questo browser', async ({ page }) => {
    await page.goto('/viewer');
    const gl = await page.evaluate(() => {
      const c = document.createElement('canvas');
      return {
        webgl: c.getContext('webgl') === null,
        webgl2: document.createElement('canvas').getContext('webgl2') === null,
        experimental: document.createElement('canvas').getContext('experimental-webgl') === null,
      };
    });
    expect(gl).toEqual({ webgl: true, webgl2: true, experimental: true });
  });

  test('mostra una scena 2D non vuota, con sfumature, senza il messaggio di WebGL mancante', async ({ page }, info) => {
    await openViewer(page);
    await expect(page.getByText('WebGL non è supportato')).toHaveCount(0);
    await expect(page.getByRole('alert').filter({ hasText: /WebGL|visualizzazione 3D/i })).toHaveCount(0);
    await expect(page.getByTestId('viewer-mode')).toHaveAttribute('data-mode', 'canvas2d');
    const box = await page.locator(STAGE_CANVAS).boundingBox();
    expect(box!.width).toBeGreaterThan(200);
    expect(box!.height).toBeGreaterThan(200);

    const px = await pixels(page);
    expect(px.opaque / px.total).toBeGreaterThan(0.9); // sfondo e sfera coprono il canvas
    expect(px.distinct).toBeGreaterThan(500); // ombreggiatura reale, non colori piatti
    await expect(page.locator('#scene-description')).not.toBeEmpty();

    const png = await page.locator('.stage').screenshot();
    await info.attach('viewer-canvas2d', { body: png, contentType: 'image/png' });
    await page.screenshot({ path: 'test-results/viewer-no-webgl.png', fullPage: true });
  });

  test('i comandi da tastiera ruotano la vista (i pixel cambiano) e aggiornano la descrizione', async ({ page }) => {
    await openViewer(page);
    const before = await pixels(page);
    const desc = page.locator('#scene-description');
    const d0 = await desc.textContent();
    await page.getByRole('button', { name: 'Ruota a destra' }).focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    await expect.poll(async () => (await pixels(page)).hash).not.toBe(before.hash);
    await expect.poll(() => desc.textContent()).not.toBe(d0);
    await expect(page.getByTestId('viewer-mode')).toHaveText('Modalità compatibile (senza WebGL)');

    const mid = await pixels(page);
    await page.getByRole('button', { name: "Inclina verso l'alto" }).focus();
    await page.keyboard.press('Enter');
    await expect.poll(async () => (await pixels(page)).hash).not.toBe(mid.hash);
  });

  test('la rotazione automatica anima i pixel solo senza reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await openViewer(page);
    await page.getByRole('button', { name: 'Rotazione automatica' }).click();
    const a = (await pixels(page)).hash;
    await expect.poll(async () => (await pixels(page)).hash, { timeout: 5_000 }).not.toBe(a);

    // reattività: attivando "riduci movimento" l'animazione si ferma senza ricaricare
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(page.getByRole('button', { name: 'Rotazione automatica' })).toHaveCount(0);
    // dopo lo stop il renderer ridisegna una volta a piena risoluzione (il Worker impiega un tempo variabile):
    // data-ready="1" segnala la scena definitiva; da lì l'immagine deve restare ferma
    await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 10_000 });
    const frozen = (await pixels(page)).hash;
    await page.waitForTimeout(700);
    expect((await pixels(page)).hash).toBe(frozen);
  });

  test('con reduced motion già attivo al caricamento la scena resta statica', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openViewer(page);
    await expect(page.getByText('Rotazione automatica disattivata')).toBeVisible();
    // sotto carico data-ready può precedere di poco l'ultimo ridisegno (frame del Worker in volo, ResizeObserver):
    // si attende la scena assestata (due letture consecutive uguali). Un'animazione continua non si assesterebbe mai
    // e farebbe fallire questa attesa; il controllo di staticità qui sotto resta identico.
    let last = (await pixels(page)).hash;
    await expect
      .poll(
        async () => {
          await page.waitForTimeout(250);
          const h = (await pixels(page)).hash;
          const same = h === last;
          last = h;
          return same;
        },
        { timeout: 10_000 },
      )
      .toBe(true);
    const a = (await pixels(page)).hash;
    await page.waitForTimeout(800);
    expect((await pixels(page)).hash).toBe(a);
  });
});
