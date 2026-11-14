// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const appOrigin = `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? 8001}`;

for (const english of [false, true]) {
  test(`reliability: real engine, thermal demand, conditional charts and report ${english ? 'app EN' : 'root IT'}`, async ({ page }, info) => {
    test.setTimeout(120_000);
    const base = english ? `${appOrigin}/app` : '';
    const nav = () => page.getByRole('navigation', { name: english ? 'Mission planning steps' : 'Passaggi della pianificazione' });
    const prepare = () => page.getByRole('button', { name: english ? 'Prepare report' : 'Prepara il report', exact: true });
    const physical: Record<string, unknown>[] = [];
    page.on('request', (r) => {
      if (r.url().endsWith('/api/raven/evaluate') && r.postDataJSON().include_windows) physical.push(r.postDataJSON());
    });
    await page.goto(`${base}/mission-planner?lang=${english ? 'en' : 'it'}&site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=period`);
    await page.locator('#journey-days').fill('0.15');
    await page.locator('#journey-resolution').selectOption('60');
    await nav().getByRole('button', { name: english ? /Energy/ : /Energia/ }).click();
    await expect(page.getByTestId('reliability-inputs')).toHaveCount(0);
    await expect(page.getByTestId('reliability-results')).toHaveCount(0);
    await nav().getByRole('button', { name: english ? /Reliability/ : /Affidabilità/ }).click();
    await expect(page.locator('#rel-enabled')).not.toBeChecked();
    await page.getByRole('button', { name: english ? 'Load illustrative assumptions — not real hardware' : 'Carica ipotesi illustrative — non hardware reale', exact: true }).click();
    await expect(page.locator('#rel-apply-power')).not.toBeChecked();
    await page.locator('#rel-apply-power').check();
    await page.locator('#rel-thermal_load_w').fill('2');
    expect((await new AxeBuilder({ page }).include('[data-testid="reliability-inputs"]').analyze()).violations).toEqual([]);
    const computer = page.getByTestId('reliability-inputs').locator('details').filter({ has: page.locator('#rel-computer-thermal_max_c') });
    await computer.locator('summary').click();
    await page.locator('#rel-computer-thermal_max_c').fill('100');
    await page.locator('#rel-computer-dose_rate_krad_h').fill('100');
    await nav().getByRole('button', { name: english ? /Simulation/ : /Simulazione/ }).click();
    const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/report/reliability') && r.status() === 200);
    await page.getByRole('button', { name: english ? 'Simulate both scenarios' : 'Simula i due scenari', exact: true }).click();
    const result = await (await response).json();
    await expect(page.getByTestId('reliability-results')).toHaveCount(0);
    await nav().getByRole('button', { name: english ? /Reliability/ : /Affidabilità/ }).click();
    expect(result.model).toBe('raven-reliability-1');
    const scenario = result.scenarios[0];
    expect(scenario.duration_hours).toBe(3);
    expect(scenario.expected_available_hours).toBeGreaterThan(0);
    expect(scenario.expected_available_hours).toBeLessThan(3);
    const cpu = scenario.components.find((c: { id: string }) => c.id === 'computer');
    expect(cpu.thermal_margin_c).toBe(-15);
    expect(cpu.dose_krad).toBe(8550);
    expect(cpu.environment_status).toBe('outside_declared_envelope');
    expect(physical).toHaveLength(2);
    for (const q of physical) expect(q.energy_overrides).toMatchObject({ survival_load_w: 12, active_load_w: 52 });
    await expect(page.getByTestId('reliability-results').locator('.chart')).toHaveCount(10);
    const comparisons = page.getByTestId('reliability-charts');
    await expect(comparisons.getByRole('figure', { name: english ? 'Protected-component temperature margin' : 'Margine termico del componente protetto', exact: true })).toContainText('-15 °C');
    await expect(comparisons.getByRole('figure', { name: english ? 'Shielded dose versus declared TID tolerance' : 'Dose schermata rispetto alla tolleranza TID dichiarata', exact: true })).toContainText(english ? '8,550 krad(Si)' : '8550 krad(Si)');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath('reliability-comparisons-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 720 });
    await expect(page.getByTestId('reliability-A')).toContainText(english ? 'WARNING:' : 'ATTENZIONE:');
    expect((await new AxeBuilder({ page }).include('[data-testid="reliability-results"]').analyze()).violations).toEqual([]);
    await expect(page.locator('#rel-apply-power')).toBeChecked();
    await nav().getByRole('button', { name: english ? /Simulation/ : /Simulazione/ }).click();
    await prepare().click();
    await expect(page.locator('#report-option-reliability')).not.toBeChecked();
    await page.locator('#report-option-reliability').check();
    await prepare().click();
    const report = page.locator('.report-preview');
    await expect(report.getByTestId('reliability-results')).toBeVisible();
    await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: english ? 'Download structured report (JSON)' : 'Scarica report strutturato (JSON)', exact: true }).click();
    const download = await downloadPromise;
    const archive = JSON.parse(await readFile((await download.path())!, 'utf8'));
    expect(archive.lifecycle.reliability.calculation).toEqual(result);
    expect(archive.lifecycle.reliability.assumptions.apply_thermal_load).toBe(true);
    expect(archive.lifecycle.reliability.qualification).toBe('not_validated');
    expect(archive.evaluations[0].parameters_used.energy.survival_load_w).toBe(12);
    const evidence = structuredClone(archive.lifecycle);
    evidence.raven_seal.blockchain_simulation = null;
    const payload = {
      format: 'raven-report-evidence-v1', calculation_created_at: archive.calculation_created_at,
      config: archive.config, requests: archive.requests, evaluations: archive.evaluations, lifecycle: evidence,
    };
    const canonical = JSON.stringify(payload, (_key, value) =>
      value && typeof value === 'object' && !Array.isArray(value)
        ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);
    expect(archive.lifecycle.raven_seal.blockchain_simulation.payload_sha256).toBe(createHash('sha256').update(canonical).digest('hex'));
    const print = page.getByRole('button', { name: english ? 'Print / save PDF' : 'Stampa / salva PDF', exact: true });
    await expect(print).toBeEnabled();
    await page.emulateMedia({ media: 'print' });
    await page.pdf({ path: info.outputPath('reliability-report.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true });
    await expect(report.getByTestId('reliability-results')).toBeVisible();
    await expect(page.getByTestId('report-final-seal')).toContainText('DEMO-');
    await page.emulateMedia({ media: 'screen' });
    // Reliability is controlled from the Dossier and remains off in both report modes by default.
    await page.getByRole('radio', { name: /Learn/ }).check();
    await expect(report.getByTestId('reliability-results')).toHaveCount(0);
    await page.getByRole('radio', { name: /Expert/ }).check();
    await expect(report.getByTestId('reliability-results')).toHaveCount(0);
    await page.reload();
    await expect(report.getByTestId('reliability-results')).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath('reliability-mobile.png'), fullPage: true });
    expect(physical).toHaveLength(2);
  });
}

test('reliability: partial assumptions and failed API remain explicit and block incomplete report generation', async ({ page }) => {
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=period');
  await page.locator('#journey-days').fill('0.15');
  await page.locator('#journey-resolution').selectOption('60');
  const nav = page.getByRole('navigation', { name: 'Passaggi della pianificazione' });
  await nav.getByRole('button', { name: /Affidabilità/ }).click();
  await page.getByRole('button', { name: 'Carica ipotesi illustrative — non hardware reale', exact: true }).click();
  const cpu = page.getByTestId('reliability-inputs').locator('details').filter({ has: page.locator('#rel-computer-failure_rate_per_hour') });
  await cpu.locator('summary').click();
  await page.locator('#rel-computer-failure_rate_per_hour').fill('');
  await nav.getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await nav.getByRole('button', { name: /Affidabilità/ }).click();
  await expect(page.getByTestId('reliability-A')).toContainText('Ipotesi incomplete');
  await nav.getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Prepara il report', exact: true }).click();
  await nav.getByRole('button', { name: /Affidabilità/ }).click();
  await page.route('**/api/raven/report/reliability', (route) => route.fulfill({ status: 503, json: { detail: 'test_unavailable' } }));
  const dossierCpu = page.getByTestId('reliability-inputs').locator('details').filter({ has: page.locator('#rel-computer-failure_rate_per_hour') });
  await dossierCpu.locator('summary').click();
  await page.locator('#rel-computer-failure_rate_per_hour').fill('0');
  await expect(page.getByRole('alert')).toContainText('Calcolo di affidabilità non riuscito');
  await nav.getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Prepara il report', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Calcolo di affidabilità non riuscito');
  await expect(page.getByRole('button', { name: 'Prepara il report', exact: true })).toBeDisabled();
  await page.unroute('**/api/raven/report/reliability');
  await page.getByRole('button', { name: "Ricalcola l'affidabilità", exact: true }).click();
  await expect(page.getByRole('button', { name: 'Prepara il report', exact: true })).toBeEnabled();
  await nav.getByRole('button', { name: /Affidabilità/ }).click();
  await expect(page.getByTestId('reliability-A')).not.toContainText('Ipotesi incomplete');
});
