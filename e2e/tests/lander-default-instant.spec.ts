// SPDX-License-Identifier: Apache-2.0
// Istante predefinito della Scena lander: senza t nello scenario si sceglie, nel mese successivo all'ora attuale, un
// istante con Sole radente (1-3 gradi) calcolato con il Sole vero; con t esplicito non si cambia nulla.
import { test, expect } from '@playwright/test';
import { SITE, T0 } from './landerHelpers';

test.use({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark', reducedMotion: 'reduce' });

test('senza t: istante scelto con il Sole radente, detto in pagina, visibile e modificabile', async ({ page }) => {
  const series: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/raven/sky/series')) series.push(r.url());
  });
  await page.goto(`/lander?site=${SITE}`);
  const note = page.getByTestId('instant-note');
  await expect(note).toBeVisible({ timeout: 30_000 });
  expect(series).toHaveLength(1);
  expect(series[0]).toContain('body=moon');
  const kind = await note.getAttribute('data-kind');
  await expect(page.getByTestId('lander-status')).toHaveText(/Scena aggiornata/, { timeout: 40_000 });
  const sun = (await page.getByTestId('sun-note').textContent()) ?? '';
  if (kind === 'grazing') {
    await expect(note).toContainText('Istante scelto perché il Sole è radente');
    const m = /Sole reale a (-?\d+,\d+)°/.exec(sun);
    expect(m, sun).not.toBeNull();
    const el = Number(m![1]!.replace(',', '.'));
    expect(el).toBeGreaterThanOrEqual(0.95);
    expect(el).toBeLessThanOrEqual(3.05);
  } else {
    await expect(note).toContainText('Nessun istante con Sole radente');
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: 'test-results/ui/lander-default-1440-dark.png', fullPage: true });
  // l'istante e' nel pannello della data e nello scenario (URL) e si puo' cambiare
  await expect(page.locator('.toggle .num')).toContainText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
  await expect(page).toHaveURL(/[?&]t=\d{4}-\d{2}-\d{2}T/, { timeout: 5_000 });
  if (await page.locator('.toggle').isVisible()) await page.locator('.toggle').click(); // a schermo largo il pannello e' sempre aperto
  await page.getByLabel('Data', { exact: true }).fill('2027-04-07');
  await page.getByLabel('Data', { exact: true }).press('Enter');
  await expect(note).toHaveCount(0); // l'utente ha scelto un altro istante: la nota non vale piu'
});

test('con t esplicito nessuna ricerca e nessuna nota', async ({ page }) => {
  let calls = 0;
  page.on('request', (r) => {
    if (r.url().includes('/api/raven/sky/series')) calls++;
  });
  await page.goto(`/lander?site=${SITE}&t=${T0}`);
  await expect(page.getByTestId('lander-status')).toHaveText(/Scena aggiornata/, { timeout: 40_000 });
  await expect(page.getByTestId('instant-note')).toHaveCount(0);
  expect(calls).toBe(0);
});

test('serie non disponibile: resta l ora attuale, senza nota e senza luce inventata', async ({ page }) => {
  await page.route('**/api/raven/sky/series**', (route) => route.fulfill({ status: 503, json: { detail: 'efemeridi non disponibili' } }));
  await page.goto(`/lander?site=${SITE}`);
  await expect(page.locator('.toggle .num')).toContainText(/\d{4}-\d{2}-\d{2}/, { timeout: 30_000 });
  await expect(page.getByTestId('instant-note')).toHaveCount(0);
});
