// SPDX-License-Identifier: Apache-2.0
// Utilità condivise dai test della Scena lander (non è un file di test).
import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const SITE = 'de-gerlache';
export const T0 = '2027-04-07T00:00:00Z';
export const STAGE_CANVAS = '.stage canvas';

export async function openLander(page: Page, mode: 'webgl' | 'canvas2d', query = `?site=${SITE}&t=${T0}`): Promise<void> {
  await page.goto(`/lander${query}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Scena lander' })).toBeVisible();
  await expect(page.getByTestId('lander-mode')).toHaveAttribute('data-mode', mode, { timeout: 20_000 });
  await expect(page.locator(STAGE_CANVAS)).toHaveCount(1);
  await expect(page.getByTestId('lander-status')).toHaveText(/Scena aggiornata/, { timeout: 40_000 });
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 30_000 });
  await frames(page);
}

/** Attende che il disegno si assesti (il renderer disegna solo su richiesta: contatore dei fotogrammi stabile). */
export async function frames(page: Page, sel = STAGE_CANVAS): Promise<void> {
  await page.waitForTimeout(150);
  let prev = -1;
  await expect
    .poll(
      async () => {
        const cur = Number((await page.locator(sel).first().getAttribute('data-frames')) ?? 0);
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
  /** pixel lontani dallo sfondo della scena (#05070b) */
  lit: number;
  distinct: number;
  hash: number;
}

export async function pixels(page: Page, sel = STAGE_CANVAS): Promise<Pixels> {
  const png = await page.locator(sel).first().screenshot();
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
      if (Math.abs(d[i]! - 5) + Math.abs(d[i + 1]! - 7) + Math.abs(d[i + 2]! - 11) > 60) lit++;
      hash = (Math.imul(hash, 31) + key) | 0;
    }
    return { total: d.length / 4, lit, distinct: seen.size, hash };
  }, png.toString('base64'));
}

export const num = (s: string): number => Number(s.replace(/\s/g, '').replace('−', '-').replace('+', '').replace(',', '.'));

export interface ApiScene {
  earth: { el_deg: number; az_deg: number; range_km: number };
  ridge: { nu: number; d1_m: number; arc_distance_m: number; height_above_los_m: number };
  fresnel: { r1_at_ridge_m: number };
  diffraction: { knife_edge_db: number; correction_db: number | null; diffraction_loss_db: number | null; multipath_applicable: boolean; total_loss_db: number | null };
  link: { margin_db: number | null; state: string; state_label: string };
  antenna: { hpbw_deg: number; mast_height_m: number };
  terrain: { patch: { n: number; height_m: number[] } | null; source: string };
}

export async function apiScene(request: APIRequestContext, site: string, t: string, antennaHeight = 2): Promise<ApiScene> {
  const r = await request.get(`/api/raven/scene?site=${site}&t=${encodeURIComponent(t)}&station=dsn34&gain_dbi=15&rate_bps=100000&antenna_height_m=${antennaHeight}`);
  expect(r.ok()).toBe(true);
  return (await r.json()) as ApiScene;
}
