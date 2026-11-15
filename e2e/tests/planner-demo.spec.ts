// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

for (const language of ['en', 'it'] as const) {
  test(`ready-to-run planner demo is repeatable and uses RAVEN (${language})`, async ({ page }) => {
    test.setTimeout(120_000);
    const en = language === 'en';
    const next = () => page.getByRole('button', { name: en ? 'Continue' : 'Continua', exact: true }).click();
    const navigation = page.getByRole('navigation', { name: en ? 'Mission planning steps' : 'Passaggi della pianificazione' });
    const demo = page.getByRole('button', { name: en ? 'Start a demo' : 'Avvia una demo', exact: true });
    const guide = page.getByTestId('demo-guide');
    await page.goto(`/mission-planner?lang=${language}&mode=avanzato`);
    await expect(guide).toHaveCount(0);
    await page.locator('#journey-name').fill('Previous draft');
    await demo.click();
    await expect(page.locator('#journey-name')).toHaveValue(en ? 'South Pole demo' : 'Demo Polo Sud');
    await next();
    await next();
    await page.locator('#journey-days').fill('9');
    await navigation.getByRole('button', { name: en ? /^01 Mission$/ : /^01 Missione$/ }).click();
    await demo.click();
    await page.reload();
    await expect(page.locator('#journey-name')).toHaveValue(en ? 'South Pole demo' : 'Demo Polo Sud');
    await expect(guide).toContainText(en ? 'Step 1 of 7' : 'Passaggio 1 di 7');
    await expect(guide).toContainText('50%');
    const draft = await page.evaluate(() => JSON.parse(sessionStorage.getItem('hb.planner-journey.v1')!));
    expect(draft.input).toMatchObject({ mode: 'sites', siteA: 'malapert-massif', siteB: 'haworth',
      start: '2027-04-16T00:00', days: 3, stepMin: 60 });
    expect(draft.panel).toMatchObject({ array_area_m2: 1, cell_efficiency: .295, orientation: 'horizontal' });
    expect(draft.radio).toMatchObject({ station: 'dsn34', gain: 15, rate: 100000, mast: 2, k: 2.33 });
    expect(draft.objectives).toMatchObject({ priority: 'balanced', minSunPercent: 50, minRfPercent: 50 });
    expect(draft.planning.reliability).toMatchObject({ enabled: true, apply_thermal_load: false });
    expect(draft.planning.reliability.basis).not.toBe('');
    await next();
    await expect(guide).toContainText('Malapert');
    await expect(guide).toContainText('Haworth');
    await next();
    await expect(guide).toContainText(en ? 'hourly' : 'ogni ora');
    await expect(page.locator('#journey-days')).toHaveValue('3');
    await expect(page.locator('#journey-start')).toHaveValue('2027-04-16T00:00');
    await next();
    await expect(guide).toContainText('1 m²');
    await expect(page.locator('#journey-area')).toHaveValue('1');
    await next();
    await expect(guide).toContainText(en ? 'synthetic' : 'sintetiche');
    await expect(page.locator('#rel-enabled')).toBeChecked();
    await next();
    await expect(guide).toContainText('100 kbit/s');
    await expect(page.locator('#journey-gain')).toHaveValue('15');
    await next();
    await expect(guide).toContainText(en ? 'Select Simulate both scenarios' : 'Seleziona Simula i due scenari');
    await expect(page.getByTestId('simulation-disclosure')).toHaveCount(0);
    const results: { site: { id: string }; metrics: { useful_hours: number; unknown_hours: number } }[] = [];
    page.on('response', async (response) => {
      if (response.url().endsWith('/api/raven/evaluate') && response.request().postDataJSON().include_windows && response.ok()) {
        results.push(await response.json());
      }
    });
    await page.getByRole('button', { name: en ? 'Simulate both scenarios' : 'Simula i due scenari', exact: true }).click();
    await expect(page.getByTestId('simulation-disclosure')).toBeVisible({ timeout: 60_000 });
    await expect(guide).toContainText(en ? 'Unknown data is not zero' : 'I dati ignoti non sono zero');
    await expect.poll(() => results.length).toBe(2);
    expect(results.map((result) => result.site.id)).toEqual(['malapert-massif', 'haworth']);
    expect(results.every((result) => result.metrics.unknown_hours === 0)).toBe(true);
    expect(results[0]!.metrics.useful_hours).toBeGreaterThan(results[1]!.metrics.useful_hours);

    await navigation.getByRole('button', { name: en ? /^01 Mission$/ : /^01 Missione$/ }).click();
    await demo.click();
    await page.reload();
    await navigation.getByRole('button', { name: en ? /Simulation/ : /Simulazione/ }).click();
    await expect(page.getByTestId('simulation-disclosure')).toHaveCount(0);
  });
}
