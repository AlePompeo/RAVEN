// SPDX-License-Identifier: Apache-2.0
// Prove comuni della Scena lander, con WebGL (lander.spec.ts) e senza (lander-no-webgl.spec.ts).
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';
import { apiScene, frames, num, openLander, pixels, SITE, T0 } from './landerHelpers';

export function defineLanderCore(mode: 'webgl' | 'canvas2d'): void {
  test(`la scena non e' vuota (${mode}) e i numeri del HUD coincidono con l'API`, async ({ page, request }) => {
    await openLander(page, mode);
    const a = await pixels(page);
    expect(a.lit / a.total, 'quota di pixel che non sono sfondo').toBeGreaterThan(mode === 'webgl' ? 0.1 : 0.05);
    expect(a.distinct, 'colori distinti').toBeGreaterThan(mode === 'webgl' ? 40 : 12);
    const api = await apiScene(request, SITE, T0);
    const hud = page.getByTestId('lander-hud');
    await expect(hud).toBeVisible();
    const earth = (await page.getByTestId('hud-earth').textContent()) ?? '';
    expect(num(/elevazione ([\d,−-]+)°/.exec(earth)![1]!)).toBeCloseTo(api.earth.el_deg, 1);
    expect(num(/azimut ([\d,−-]+)°/.exec(earth)![1]!)).toBeCloseTo(api.earth.az_deg, 0);
    expect(num((await page.getByTestId('hud-nu').textContent()) ?? '')).toBeCloseTo(api.ridge.nu, 1);
    const fr = (await page.getByTestId('hud-fresnel').textContent()) ?? '';
    expect(num(/raggio al crinale ([\d,]+) m/.exec(fr)![1]!)).toBeCloseTo(api.fresnel.r1_at_ridge_m, 1);
    const dif = (await page.getByTestId('hud-diffraction').textContent()) ?? '';
    if (api.diffraction.diffraction_loss_db === null) expect(dif).toContain('= ? dB');
    else expect(num(/= ([\d,−-]+) dB/.exec(dif)![1]!)).toBeCloseTo(api.diffraction.diffraction_loss_db, 1);
    const mg = (await page.getByTestId('hud-margin').textContent()) ?? '';
    if (api.link.margin_db === null) {
      expect(mg).toContain('? dB');
      await expect(page.getByTestId('lander-error')).toHaveAttribute('data-kind', 'outside_model');
      await expect(page.getByTestId('hud-pointing')).toContainText('margine con puntamento ? dB');
    } else expect(num(/^([\d,−-]+) dB/.exec(mg)![1]!)).toBeCloseTo(api.link.margin_db, 1);
    // lo stato e' scritto, non solo colorato
    await expect(page.getByTestId('hud-state')).toContainText(/Aperto|Transizione|Bloccato|Ignoto/);
    await expect(page.getByTestId('hud-state')).toHaveAttribute('data-state', api.link.state);
    const mp = (await page.getByTestId('hud-multipath').textContent()) ?? '';
    if (!api.diffraction.multipath_applicable) expect(mp).toContain('non applicabile');
    await expect(page.getByTestId('lander-text')).toHaveCount(0);
    await page.getByRole('tab', { name: 'Descrizione testuale' }).click();
    await expect(page.getByTestId('lander-text')).toContainText('Il crinale dominante');
  });

  test(`cambiare l'ora aggiorna la scena (${mode})`, async ({ page, request }) => {
    await openLander(page, mode);
    const before = (await page.getByTestId('hud-earth').textContent()) ?? '';
    await page.getByRole('button', { name: 'Un’ora avanti' }).click();
    await expect(page.getByTestId('lander-status')).toHaveText(/01:00:00 UTC/, { timeout: 30_000 });
    const api = await apiScene(request, SITE, '2027-04-07T01:00:00Z');
    await expect.poll(async () => (await page.getByTestId('hud-earth').textContent()) ?? '', { timeout: 15_000 }).not.toBe(before);
    const earth = (await page.getByTestId('hud-earth').textContent()) ?? '';
    expect(num(/elevazione ([\d,−-]+)°/.exec(earth)![1]!)).toBeCloseTo(api.earth.el_deg, 1);
    expect(num((await page.getByTestId('hud-nu').textContent()) ?? '')).toBeCloseTo(api.ridge.nu, 1);
  });

  test(`i siti fuori copertura DEM sono disabilitati (${mode})`, async ({ page }) => {
    await openLander(page, mode);
    const opt = page.locator('#l-site option', { hasText: 'fuori copertura DEM' });
    expect(await opt.count()).toBeGreaterThan(0);
    for (const o of await opt.all()) await expect(o).toBeDisabled();
    await expect(page.locator('#l-site option:not([disabled])').first()).toBeEnabled();
  });

  test(`503 e 422 dell'API mostrano un avviso e nessun numero inventato (${mode})`, async ({ page }) => {
    for (const [status, body, re] of [
      [503, { detail: 'dati DEM non disponibili' }, /non disponibili/],
      [422, { detail: 'parametri non validi' }, /non validi/],
    ] as const) {
      await page.route('**/api/raven/scene*', (r) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }));
      await page.goto(`/lander?site=${SITE}&t=${T0}`);
      await expect(page.getByTestId('lander-error')).toBeVisible({ timeout: 20_000 });
      await expect(page.getByTestId('lander-error')).toContainText(re);
      await expect(page.getByTestId('lander-hud')).toHaveCount(0);
      await page.unroute('**/api/raven/scene*');
    }
  });

  test(`l'errore di puntamento mostra la perdita e porta il fascio in rosso oltre HPBW/2 (${mode})`, async ({ page, request }) => {
    await openLander(page, mode);
    const api = await apiScene(request, SITE, T0);
    const hp = api.antenna.hpbw_deg;
    await expect(page.getByTestId('hud-pointing')).toContainText('entro HPBW/2');
    const inside = hp * 0.3;
    const outside = hp * 0.8;
    await page.locator('#l-err').fill(String(Math.round(inside * 10) / 10));
    await expect(page.getByTestId('hud-pointing')).toContainText('entro HPBW/2');
    await page.locator('#l-err').fill(String(Math.round(outside * 10) / 10));
    await expect(page.getByTestId('hud-pointing')).toContainText('OLTRE HPBW/2');
    const loss = /perdita ([\d,]+) dB/.exec((await page.getByTestId('hud-pointing').textContent()) ?? '');
    expect(num(loss![1]!)).toBeGreaterThan(0.5);
  });

  test(`esporta i numeri della scena in JSON (${mode})`, async ({ page, request }) => {
    await openLander(page, mode);
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('export-json').click()]);
    const path = await dl.path();
    const fs = await import('node:fs');
    const j = JSON.parse(fs.readFileSync(path, 'utf8'));
    const api = await apiScene(request, SITE, T0);
    if (api.link.margin_db === null) expect(j.link.margin_db).toBeNull();
    else expect(j.link.margin_db).toBeCloseTo(api.link.margin_db, 2);
    expect(j.ridge.nu).toBeCloseTo(api.ridge.nu, 2);
    expect(j.declared_limits.length).toBeGreaterThan(3);
    expect(j.terrain.patch.heights).toBeUndefined();
  });

  test(`nessun overflow a 390 px e axe senza violazioni (${mode})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openLander(page, mode);
    if (mode === 'webgl') await page.getByRole('button', { name: 'Vista cinematografica' }).click();
    const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    expect(o.sw).toBeLessThanOrEqual(o.cw);
    for (const t of ['Numeri', 'Descrizione testuale', 'Limiti dichiarati'] as const) {
      await page.getByRole('tab', { name: t }).click();
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
      expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`), t).toEqual([]);
    }
  });

  test(`le schede si usano da tastiera (${mode})`, async ({ page }) => {
    await openLander(page, mode);
    await page.getByRole('tab', { name: 'Numeri' }).focus();
    await page.keyboard.press('End');
    await expect(page.getByRole('tab', { name: 'Limiti dichiarati' })).toBeFocused();
    await expect(page.getByTestId('lander-limits')).toContainText('Ostacolo singolo');
    await expect(page.getByTestId('lander-limits')).toContainText('P.526');
    await expect(page.getByTestId('lander-limits')).toContainText('Risoluzione del terreno 20 m');
    await frames(page);
  });
}
