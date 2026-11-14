// SPDX-License-Identifier: Apache-2.0
// Utilità condivise dai test della pagina Onda 3D (non è un file di test).
import { expect, type Page } from '@playwright/test';

export const STAGE = '.stage';
export const CANVAS = '.stage canvas';

export async function openWave(page: Page, mode: 'webgl' | 'canvas2d', path = '/wave'): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: 'Onda 3D' })).toBeVisible();
  await expect(page.getByTestId('wave-mode')).toHaveAttribute('data-mode', mode, { timeout: 20_000 });
  await expect(page.locator(CANVAS)).toHaveCount(1);
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
  await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/, { timeout: 30_000 });
  await frames(page);
}

/** Attende che il disegno si assesti (il renderer disegna solo su richiesta: contatore dei fotogrammi stabile). */
export async function frames(page: Page): Promise<void> {
  await page.waitForTimeout(150);
  let prev = -1;
  await expect
    .poll(
      async () => {
        const cur = Number((await page.locator(CANVAS).getAttribute('data-frames')) ?? 0);
        const same = cur === prev && cur > 0;
        prev = cur;
        await page.waitForTimeout(120);
        return same;
      },
      { timeout: 10_000 },
    )
    .toBe(true);
}

export interface Pixels {
  total: number;
  /** pixel diversi dallo sfondo della scena (#0b0f17) */
  lit: number;
  distinct: number;
  hash: number;
}

/** Legge i pixel del canvas dallo screenshot dell'elemento: vale per WebGL e per Canvas 2D. */
export async function pixels(page: Page): Promise<Pixels> {
  const png = await page.locator(CANVAS).screenshot();
  return page.evaluate(async (b64) => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const bmp = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const c = document.createElement('canvas');
    c.width = bmp.width;
    c.height = bmp.height;
    const ctx = c.getContext('2d')!;
    ctx.drawImage(bmp, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    const seen = new Set<number>();
    let lit = 0;
    let hash = 0;
    for (let i = 0; i < d.length; i += 4) {
      const key = ((d[i]! << 16) | (d[i + 1]! << 8) | d[i + 2]!) >>> 0;
      seen.add(key);
      if (Math.abs(d[i]! - 11) + Math.abs(d[i + 1]! - 15) + Math.abs(d[i + 2]! - 23) > 24) lit++;
      hash = (Math.imul(hash, 31) + key) | 0;
    }
    return { total: d.length / 4, lit, distinct: seen.size, hash };
  }, png.toString('base64'));
}

export const num = (s: string): number => Number(s.replace(/\s/g, '').replace('−', '-').replace(',', '.'));
