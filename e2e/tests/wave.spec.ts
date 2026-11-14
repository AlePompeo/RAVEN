// SPDX-License-Identifier: Apache-2.0
// Onda 3D contro il backend reale: superficie WebGL, cursore e sezione, preset, errori, esportazione.
import { test, expect } from '@playwright/test';
import { defineWaveCore } from './waveSuite';
import { frames, num, openWave, pixels } from './waveHelpers';

test.describe('onda 3D (WebGL)', () => {
  defineWaveCore('webgl');

  test('la sezione al cursore coincide con la curva esatta e con la simulazione dell’API a quella distanza', async ({ page, request }) => {
    await openWave(page, 'webgl');
    await page.getByLabel(/Distanza dal crinale/).fill('1000');
    await expect(page.getByTestId('section-note')).toHaveAttribute('data-source', 'api', { timeout: 20_000 });
    await page.getByRole('tab', { name: 'Tabella' }).click();
    const rows = await page.locator('#wpanel-table tbody tr').evaluateAll((trs) =>
      trs.map((tr) => [...tr.querySelectorAll('th,td')].map((c) => c.textContent ?? '')),
    );
    expect(rows.length).toBeGreaterThanOrEqual(60);
    const api = await request.get('/api/raven/wave?frequency_ghz=8.4&radius_m=0&distance_m=1000&step_m=10&y_min_m=-40&y_max_m=40&nx=100&ny=160');
    expect(api.ok()).toBe(true);
    const sec = (await api.json()).section as { y_m: number[]; intensity: number[]; knife_edge_exact: number[]; nu: number[] };
    const stride = sec.y_m.length / rows.length;
    expect(Number.isInteger(stride)).toBe(true);
    let checked = 0;
    rows.forEach((r, k) => {
      const i = k * stride;
      expect(Math.abs(num(r[0]!) - sec.y_m[i]!)).toBeLessThan(0.06);
      expect(Math.abs(num(r[1]!) - sec.nu[i]!)).toBeLessThan(0.02);
      expect(Math.abs(num(r[2]!) - sec.intensity[i]!)).toBeLessThan(0.001);
      expect(Math.abs(num(r[3]!) - sec.knife_edge_exact[i]!)).toBeLessThan(0.001);
      checked++;
    });
    expect(checked).toBe(rows.length);
    // l'interpolazione di anteprima (prima della risposta) usa la stessa lama esatta calcolata nel browser:
    // sulla linea di vista l'intensità esatta vale 0,25 (nu = 0)
    const mid = sec.y_m.findIndex((y) => y >= 0);
    expect(sec.knife_edge_exact[mid]!).toBeGreaterThan(0.2);
    expect(sec.knife_edge_exact[mid]!).toBeLessThan(0.31);
  });

  test('preset: cresta 100 m e 400 m, lama e bande, con richieste debounced e una sola per raffica', async ({ page }) => {
    await openWave(page, 'webgl');
    const urls: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/api/raven/wave')) urls.push(r.url());
    });
    await page.getByRole('button', { name: 'Cresta 100 m' }).click();
    await expect(page.getByLabel('Raggio della cresta (m)')).toHaveValue('100');
    await expect(page.getByRole('button', { name: 'Cresta 100 m' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/, { timeout: 30_000 });
    expect(urls.filter((u) => u.includes('radius_m=100'))).toHaveLength(1);
    await page.getByRole('button', { name: 'Cresta 400 m' }).click();
    await expect.poll(() => urls.some((u) => u.includes('radius_m=400'))).toBe(true);
    await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/, { timeout: 30_000 });
    await page.getByRole('tab', { name: 'Parametri e avvisi' }).click();
    await expect(page.getByTestId('wave-meta')).toContainText('rounded');
    await page.getByRole('button', { name: 'Lama', exact: true }).click();
    await expect(page.getByLabel('Raggio della cresta (m)')).toHaveValue('0');
    await page.getByRole('button', { name: /Banda Ka/ }).click();
    await expect(page.getByLabel('Frequenza (GHz)')).toHaveValue('32');
    await expect.poll(() => urls.some((u) => u.includes('frequency_ghz=32'))).toBe(true);
    await page.getByRole('button', { name: /Banda X/ }).click();
    await expect(page.getByLabel('Frequenza (GHz)')).toHaveValue('8.4');
    await expect(page.locator('#f-freq-hint')).toHaveText('λ = 0,0357 m');

    // raffica di digitazioni: debounce, una sola richiesta nuova
    await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/, { timeout: 30_000 });
    const n0 = urls.length;
    const field = page.getByLabel('Distanza massima (m)');
    for (const v of ['2', '25', '250', '2500']) {
      await field.fill(v);
      await page.waitForTimeout(60);
    }
    await expect.poll(() => urls.length, { timeout: 10_000 }).toBeGreaterThan(n0);
    await page.waitForTimeout(800);
    expect(urls.slice(n0).filter((u) => u.includes('distance_m=2500'))).toHaveLength(1);
    expect(urls.slice(n0).some((u) => u.includes('distance_m=25&') || u.includes('distance_m=250&'))).toBe(false);
  });

  test('errori onesti: 422, 503 e rete mantengono l’ultima superficie valida', async ({ page }) => {
    await openWave(page, 'webgl');
    const before = await pixels(page);
    expect(before.lit).toBeGreaterThan(1000);
    let mode: '422' | '503' | 'net' | 'ok' = '422';
    await page.route('**/api/raven/wave?*', async (route) => {
      if (mode === '422') await route.fulfill({ status: 422, json: { detail: 'parametri non validi' } });
      else if (mode === '503') await route.fulfill({ status: 503, json: { detail: 'non disponibile' } });
      else if (mode === 'net') await route.abort();
      else await route.continue();
    });
    await page.getByRole('button', { name: 'Cresta 100 m' }).click();
    const alert = page.getByTestId('wave-error');
    await expect(alert).toContainText('Parametri non validi');
    await expect(alert).toContainText('ultima superficie valida');
    await frames(page);
    expect((await pixels(page)).lit).toBeGreaterThan(1000);
    await expect(page.getByLabel(/Distanza dal crinale/)).toBeEnabled();
    mode = '503';
    await page.getByRole('button', { name: 'Cresta 400 m' }).click();
    await expect(alert).toContainText('503');
    mode = 'net';
    await page.getByRole('button', { name: 'Riprova' }).click();
    await expect(alert).toContainText('non raggiungibile');
    mode = 'ok';
    await page.getByRole('button', { name: 'Riprova' }).click();
    await expect(alert).toBeHidden({ timeout: 30_000 });
    await expect(page.getByTestId('wave-status')).toHaveText(/Superficie aggiornata/);
  });

  test('campi non validi: messaggio vicino al campo e nessuna richiesta', async ({ page }) => {
    await openWave(page, 'webgl');
    const urls: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/api/raven/wave')) urls.push(r.url());
    });
    await page.getByLabel('Raggio della cresta (m)').fill('900');
    await expect(page.getByText('Il raggio della cresta deve essere tra 0 (lama) e 400 m.')).toBeVisible();
    await expect(page.getByLabel('Raggio della cresta (m)')).toHaveAttribute('aria-invalid', 'true');
    await page.waitForTimeout(700);
    expect(urls).toHaveLength(0);
  });

  test('animazione: nessun avvio automatico; con movimento ridotto è disattivata', async ({ page }) => {
    await openWave(page, 'webgl');
    const v0 = await page.getByTestId('cursor-value').textContent();
    await page.waitForTimeout(800);
    expect(await page.getByTestId('cursor-value').textContent()).toBe(v0);
    const play = page.getByRole('button', { name: 'Avanza lungo la distanza' });
    await play.click();
    await expect(page.getByRole('button', { name: 'Pausa' })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(async () => page.getByTestId('cursor-value').textContent()).not.toBe(v0);
    await page.getByRole('button', { name: 'Pausa' }).click();
    const v1 = await page.getByTestId('cursor-value').textContent();
    await page.waitForTimeout(500);
    expect(await page.getByTestId('cursor-value').textContent()).toBe(v1);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload();
    await expect(page.getByRole('button', { name: 'Avanza lungo la distanza' })).toBeDisabled();
    await expect(page.getByText('Animazione disattivata')).toBeVisible();
  });

  test('esportazione CSV e JSON della sezione e della griglia', async ({ page }) => {
    await openWave(page, 'webgl');
    const csv = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Scarica CSV' }).click();
    const d = await csv;
    expect(d.suggestedFilename()).toBe('onda-sezione.csv');
    const stream = await d.createReadStream();
    let text = '';
    for await (const c of stream) text += c;
    expect(text.split('\n')[0]).toBe('y_m,nu,intensity_simulated,intensity_knife_edge_exact');
    expect(text.trim().split('\n').length).toBe(401);
    await page.getByRole('tab', { name: 'Tabella' }).click();
    const grid = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Scarica JSON' }).click();
    expect((await grid).suggestedFilename()).toBe('onda-griglia.json');
  });

  test('spiegazione: ν, segno, limiti dichiarati e tavola alternativa', async ({ page }) => {
    await openWave(page, 'webgl');
    await page.getByRole('tab', { name: 'Cosa mostra' }).click();
    const panel = page.locator('#wpanel-about');
    await expect(panel).toContainText('ν = −y·√(2/(λx))');
    await expect(panel).toContainText('ν > 0 è l’ombra');
    await expect(panel).toContainText('scalare e parassiale');
    await expect(panel).toContainText('nessun regolite');
  });
});
