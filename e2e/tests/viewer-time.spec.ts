// SPDX-License-Identifier: Apache-2.0
// Data e ora UTC del visualizzatore: il punto subsolare mostrato viene dal backend reale (/api/raven/sky/subsolar),
// una data fuori intervallo da' un messaggio senza perdere l'ultima luce, nessun overflow a 390px, axe pulito.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

const fmt = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(2)}° ${v >= 0 ? pos : neg}`;

async function open(page: Page, body = 'moon') {
  await page.goto(`/viewer?body=${body}`);
  await expect(page.getByTestId('sky-time')).toBeVisible();
  await expect(page.getByTestId('sky-subsolar')).toContainText('lat', { timeout: 15_000 });
}

test.describe('data e ora del visualizzatore', () => {
  test('cambiare data aggiorna il punto subsolare con il valore reale del backend', async ({ page, request }) => {
    await open(page);
    const before = await page.getByTestId('sky-subsolar').innerText();
    await page.getByLabel('Data', { exact: true }).fill('2027-03-05');
    await page.getByLabel('Ora UTC').fill('06:30:00');
    await page.getByLabel('Ora UTC').dispatchEvent('change');
    const r = await request.get('/api/raven/sky/subsolar?body=moon&t=2027-03-05T06:30:00Z');
    expect(r.status()).toBe(200);
    const j = await r.json();
    const expected = `lat ${fmt(j.subsolar.lat_deg, 'N', 'S')}, lon ${fmt(j.subsolar.lon_deg_east, 'E', 'O')}`;
    await expect(page.getByTestId('sky-subsolar')).toContainText(expected, { timeout: 10_000 });
    expect(await page.getByTestId('sky-subsolar').innerText()).not.toBe(before);
    await expect(page.getByTestId('sky-status')).toContainText('2027-03-05 06:30:00 UTC');
  });

  test('passi di un giorno e di un\'ora, e "Adesso"', async ({ page }) => {
    await open(page, 'earth');
    await page.getByLabel('Ora UTC').fill('00:30:00');
    await page.getByLabel('Ora UTC').dispatchEvent('change');
    await page.getByLabel('Data', { exact: true }).fill('2026-12-31');
    await page.getByLabel('Data', { exact: true }).dispatchEvent('change');
    await page.getByRole('button', { name: 'Un giorno avanti' }).click();
    await expect(page.getByLabel('Data', { exact: true })).toHaveValue('2027-01-01');
    await page.getByRole('button', { name: 'Un’ora indietro' }).click();
    await expect(page.getByLabel('Data', { exact: true })).toHaveValue('2026-12-31');
    await expect(page.getByLabel('Ora UTC')).toHaveValue('23:30:00');
    await page.getByRole('button', { name: 'Adesso' }).click();
    const today = new Date().toISOString().slice(0, 10);
    await expect(page.getByLabel('Data', { exact: true })).toHaveValue(today);
  });

  test('la riproduzione avanza il tempo e si ferma', async ({ page }) => {
    await open(page);
    const time = page.getByLabel('Ora UTC');
    await page.getByLabel('Velocità').selectOption('hour');
    const t0 = await time.inputValue();
    const play = page.getByRole('button', { name: /Riproduci/ });
    await play.click();
    await expect(page.getByRole('button', { name: /Ferma/ })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => time.inputValue(), { timeout: 8000 }).not.toBe(t0);
    await page.getByRole('button', { name: /Ferma/ }).click();
    const t1 = await time.inputValue();
    await page.waitForTimeout(700);
    expect(await time.inputValue()).toBe(t1);
  });

  test('data fuori intervallo: messaggio visibile, ultima luce conservata', async ({ page }) => {
    await open(page);
    const before = await page.getByTestId('sky-subsolar').innerText();
    await page.route('**/api/raven/sky/subsolar**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.continue();
    });
    await page.getByRole('button', { name: 'Un giorno avanti' }).click();
    await page.getByLabel('Data', { exact: true }).fill('1960-01-01');
    await page.getByLabel('Data', { exact: true }).dispatchEvent('change');
    const status = page.getByTestId('sky-status');
    await expect(status).toContainText('fuori dall’intervallo supportato');
    await expect(status).toHaveAttribute('data-problem', '1');
    await page.waitForTimeout(1000);
    await expect(status).toHaveAttribute('data-problem', '1');
    expect(await page.getByTestId('sky-subsolar').innerText()).toBe(before);
    await expect(page.locator('.stage canvas').first()).toBeVisible();
  });

  test('backend non disponibile (422/503/rete): messaggio e nessun crash', async ({ page }) => {
    await open(page);
    const before = await page.getByTestId('sky-subsolar').innerText();
    await page.route('**/api/raven/sky/subsolar**', (route) => route.fulfill({ status: 503, body: '{}' }));
    await page.getByRole('button', { name: 'Un giorno avanti' }).click();
    await expect(page.getByTestId('sky-status')).toContainText('non disponibile');
    expect(await page.getByTestId('sky-subsolar').innerText()).toBe(before);
    await page.unroute('**/api/raven/sky/subsolar**');
    await page.route('**/api/raven/sky/subsolar**', (route) => route.fulfill({ status: 422, body: '{}' }));
    await page.getByRole('button', { name: 'Un giorno avanti' }).click();
    await expect(page.getByTestId('sky-status')).toContainText('fuori dall’intervallo');
  });

  test('Sole e Marte non sono nel selettore: il Sole resta solo la sorgente della luce', async ({ page }) => {
    await page.goto('/viewer?body=sun');
    await expect(page.getByRole('tab', { name: 'Sole' })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Luna' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByLabel('Data', { exact: true })).toBeEnabled();
  });

  test('390px: nessun overflow orizzontale, bersagli da 44px, axe pulito', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/viewer?body=moon');
    await expect(page.getByTestId('sky-subsolar')).toContainText('lat', { timeout: 15_000 });
    await expect(page.getByLabel('Data', { exact: true })).toBeVisible();
    const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    expect(o.sw).toBeLessThanOrEqual(o.cw);
    for (const b of await page.getByTestId('sky-time').getByRole('button').all()) {
      const box = await b.boundingBox();
      expect(box!.height, await b.innerText()).toBeGreaterThanOrEqual(43.5);
      expect(box!.width).toBeGreaterThanOrEqual(43.5);
      expect(box!.x + box!.width).toBeLessThanOrEqual(390.5);
    }
    await page.screenshot({ path: 'test-results/ui/viewer-time-390.png' });
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
  });

  test('1440px: axe pulito e ordine di tabulazione coerente', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) }))).toEqual([]);
    // ordine di lettura = ordine DOM: -1 giorno, -1 h, Adesso, +1 h, +1 giorno, Riproduci
    await page.getByRole('button', { name: 'Un giorno indietro' }).focus();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Un’ora indietro' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Adesso' })).toBeFocused();
    for (let i = 0; i < 3; i++) await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: /Riproduci/ })).toBeFocused();
    await page.screenshot({ path: 'test-results/ui/viewer-time-1440.png' });
  });
});
