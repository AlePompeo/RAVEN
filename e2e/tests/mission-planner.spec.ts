// SPDX-License-Identifier: Apache-2.0
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { frames, pixels } from './landerHelpers';
import type { RavenEvaluation } from '../../frontend/src/shell/ravenApi';
import { openSimulationDetails } from './plannerHelpers';
const appOrigin = `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? 8001}`;

const next = (page: Page) => page.getByRole('button', { name: 'Continua', exact: true }).click();
const navigation = (page: Page) => page.getByRole('navigation', { name: 'Passaggi della pianificazione' });
async function openComparison(page: Page) {
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=period&mode=avanzato');
  await expect(page.getByRole('heading', { name: 'Periodo', exact: true })).toBeVisible();
  await page.locator('#journey-days').fill('0.15');
  await page.locator('#journey-resolution').selectOption('60');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
}

for (const base of ['', `${appOrigin}/app`]) {
  test(`planner: supported UTC dates constrain both scenarios and duration ${base || 'root'}`, async ({ page }) => {
    await page.goto(`${base}/mission-planner?mp_step=period`);
    await expect(page.getByRole('heading', { name: 'Periodo', exact: true })).toBeVisible();
    const start = page.locator('#journey-start');
    await expect(start).toHaveAttribute('min', '1972-01-01T00:00');
    await start.fill('1971-12-31T23:59');
    await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeDisabled();
    await expect(page.getByText("L'intera missione deve rientrare nell'intervallo di date supportato dalle efemeridi.", { exact: true })).toBeVisible();
    await start.fill('2001-01-01T00:00');
    await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeEnabled();
    const latest = await start.getAttribute('max');
    expect(latest).toBeTruthy();
    await start.fill(latest!);
    await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeEnabled();
    await page.locator('#journey-days').fill('8');
    await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeDisabled();
    await start.fill('2001-01-01T00:00');
    await navigation(page).getByRole('button', { name: /Missione/ }).click();
    await page.getByRole('button', { name: 'Due date, stesso sito', exact: true }).click();
    await navigation(page).getByRole('button', { name: /Periodo/ }).click();
    await page.locator('#journey-start-b').fill('1971-12-31T23:59');
    await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeDisabled();
  });
}

test('planner: RAVEN SI online proposals retain provenance but never persist cloud consent', async ({ page }) => {
  await page.route('**/api/assistant/status', (route) => route.fulfill({
    json: { provider: 'groq', mode: 'llm', external: true, cloud_available: true },
  }));
  await page.route('**/api/raven/report/narrative', (route) => {
    expect(route.request().postDataJSON().allow_external).toBe(true);
    return route.fulfill({ json: {
      sections: Object.fromEntries(['0', 'A', 'B', 'C', 'D', 'E', 'F'].map((phase) => [phase, `Mock unreviewed proposal ${phase}`])),
      model: 'openai/gpt-oss-20b', provider: 'groq', local: false,
      data_scope: 'anonymous_technical_profile', generated_at: '2026-11-09T10:00:00Z',
      context_sha256: 'b'.repeat(64), status: 'unreviewed_si_proposal', lang: 'it',
    } });
  });
  await openComparison(page);
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  await expect(page.getByTestId('mission-statistics').locator('.composition-chart')).toHaveCount(2);
  await expect(page.getByTestId('mission-statistics').getByRole('figure', { name: 'Totali energetici A/B', exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('[data-testid="mission-statistics"]').analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  const consent = page.getByTestId('report-cloud-consent');
  await expect(consent).toBeEnabled();
  await expect(consent).not.toBeChecked();
  await consent.check();
  await page.getByRole('button', { name: 'Genera proposte RAVEN SI', exact: true }).click();
  await expect(page.getByTestId('report-dossier')).toContainText('openai/gpt-oss-20b');
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await expect(page.getByTestId('mission-assistance').first()).toContainText('Source: Groq online');
  await expect(page.locator('[data-phase="A"] .si-proposal')).toContainText('Mock unreviewed proposal A');
  await page.reload();
  await navigation(page).getByRole('button', { name: /Dossier/ }).click();
  await expect(consent).toBeEnabled();
  await expect(consent).not.toBeChecked();
});

test('planner: nine-step journey completes a traceable dossier and coherent report, restores and invalidates results', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const bodies: Record<string, unknown>[] = [];
  page.on('request', (request) => {
    if (request.url().endsWith('/api/raven/evaluate') && request.postDataJSON().include_windows) bodies.push(request.postDataJSON());
  });
  await page.goto('/mission-planner?mode=avanzato');
  await expect(page.getByRole('heading', { name: 'Missione', exact: true })).toBeVisible();
  await page.locator('#journey-name').fill('South Pole Study');
  await page.getByRole('button', { name: 'Usa questo esempio' }).click();
  await expect(page.getByRole('heading', { name: 'Siti', exact: true })).toBeVisible();
  await next(page);
  await page.locator('#journey-days').fill('0.15');
  await page.locator('#journey-resolution').selectOption('60');
  await next(page);
  await page.getByRole('button', { name: /Inseguimento solare ideale/ }).click();
  await page.locator('#journey-efficiency').fill('0.3');
  await page.locator('#journey-area').fill('2');
  await next(page);
  await expect(page.getByRole('heading', { name: 'Affidabilità', exact: true })).toBeVisible();
  await next(page);
  await page.locator('#journey-gain').fill('22');
  await page.getByText('Impostazioni avanzate del modello', { exact: true }).click();
  await page.locator('#journey-k').fill('1.7');
  await next(page);
  await expect(page.getByTestId('planner-scene-status')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  expect(bodies).toHaveLength(2);
  for (const body of bodies) {
    expect(body).toMatchObject({
      start_utc: '2027-04-16T00:00:00Z', days: .15, step_min: 60,
      energy_overrides: { orientation: 'tracking', array_area_m2: 2, cell_efficiency: .3 },
      rf_overrides: { tx_gain_dbi: 22, compensator_k: 1.7 },
    });
  }
  await page.locator('#journey-time').fill('1');
  await expect(page.locator('label[for="journey-time"]')).toContainText('01:00:00 UTC');
  await page.getByRole('button', { name: /^Esplora scenario B/ }).click();
  await expect(page.locator('label[for="journey-time"]')).toContainText('01:00:00 UTC');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.screenshot({ path: testInfo.outputPath('comparison.png'), fullPage: true });
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await expect(page.getByRole('heading', { name: 'Dossier di missione', exact: true })).toBeVisible();
  await expect(page.getByTestId('report-mode')).toHaveAttribute('data-mode', 'expert');
  await page.locator('#dossier-purpose').selectOption('scientific');
  await expect(page.locator('#dossier-missionStatement')).toHaveCount(0);
  await page.locator('#report-option-parameters').check();
  await expect(page.getByTestId('report-cloud-consent')).toBeDisabled();
  await page.getByRole('button', { name: 'Genera proposte RAVEN SI', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Nessun modello SI configurato disponibile', { timeout: 15000 });
  await expect(page.locator('#journey-decision')).toHaveCount(0);
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  expect(await page.locator('.report-preview').innerText()).not.toMatch(/\uFFFD|\\u[0-9a-f]{4}/i);
  await expect(page.getByTestId('report-bar')).toBeVisible();
  await expect(page.getByText('Il report viene generato in inglese.')).toBeVisible();
  await expect(page.locator('.report-preview .rp-meta')).toContainText('South Pole Study');
  await expect(page.locator('.report-preview .rp-meta')).toContainText('2027-04-16');
  await expect(page.getByTestId('report-decision')).toHaveCount(0);
  await expect(page.getByTestId('report-digital-savings')).toContainText('estimated');
  await expect(page.getByTestId('report-final-seal')).toContainText('DEMO-');
  const downloadPromise = page.waitForEvent('download');
  await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
  await page.getByRole('button', { name: 'Scarica report strutturato (JSON)' }).click();
  const download = await downloadPromise;
  const report = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(report.config.name).toBe('South Pole Study');
  expect(report.config.panel.array_area_m2).toBe(2);
  expect(report.evaluations).toHaveLength(2);
  expect(report.parameter_registry.registry_sha256).toBe(report.evaluations[0].registry_sha256);
  expect(report.parameter_registry.parameters.find((p: { key: string }) => p.key === 'cell_efficiency').source).toBeTruthy();
  expect(report.parameter_registry.source_parameters.find((p: { key: string }) => p.key === 'grazing.regolith_eps_real').source).toBeTruthy();
  await expect(page.locator('.rp-params tr', { hasText: 'rf.regolith_eps_real' }).first()).not.toContainText('not in the registry');
  const flat: (readonly [string, unknown])[][] = report.evaluations.map((e: RavenEvaluation) =>
    Object.entries(e.parameters_used!).flatMap(([g, v]) => Object.entries(v).map(([k, x]) => [`${g}.${k}`, x] as const)));
  // one table, one row per parameter of either scenario; rows that differ are marked
  await expect(page.locator('.rp-params tbody tr')).toHaveCount(new Set(flat.flatMap((rows) => rows.map(([k]) => k))).size);
  expect(report.config.decision).toBe('');
  expect(report.evaluations[0].parameters_used.rf.compensator_k).toBe(1.7);
  expect(report.evaluations[0].steps.gen_w.some((v: number | null) => v !== null && v > 0)).toBe(true);
  expect(report.schema_version).toBe(5);
  expect(report.lifecycle.phases.map((phase: { id: string }) => phase.id)).toEqual(['0', 'A', 'B', 'C', 'D', 'E', 'F']);
  expect(report.lifecycle.completion_audit).toMatchObject({ total_fields: 35, verified_deliverables: 0 });
  expect(report.lifecycle.completion_audit.proposed_or_missing).toContain('qualification_tests');
  expect(report.lifecycle.phases.flatMap((phase: { deliverables: { input_dependencies: string[] }[] }) => phase.deliverables)
    .every((item: { input_dependencies: string[] }) => item.input_dependencies.length > 0)).toBe(true);
  expect(report.lifecycle.planning_objectives.mission_statement).toBeNull();
  expect(report.lifecycle.assistance.mission_specific_si_generated).toBe(false);
  expect(report.lifecycle.sustainability).toMatchObject({ perspective: 'ESG', esg_score: null, conformity_claim: false });
  expect(report.lifecycle.sustainability.document_paper_estimate).toMatchObject({ paper_factor_id: '19_506_5164_15_1', sides_per_sheet: 1 });
  expect(report.lifecycle.sustainability.document_paper_estimate.not_printing_avoided_kg_co2e).toBeGreaterThan(0);
  expect(report.lifecycle.liability_disclaimer.notice).toContain('Preliminary study produced by software');
  const lifecycle = page.getByTestId('mission-lifecycle-report');
  await expect(lifecycle.locator('section.phase')).toHaveCount(7);
  await expect(lifecycle.locator('.rp-verdict-page .rp-kpi')).toHaveCount(1);
  await expect(lifecycle.locator('> section:last-child')).toHaveAttribute('data-testid', 'report-final-seal');
  await expect(lifecycle.locator('> section:nth-last-child(2)')).toHaveAttribute('data-testid', 'report-digital-savings');
  await expect(page.getByTestId('mission-liability')).toContainText(report.evaluations[0].registry_sha256);
  expect(report.lifecycle.raven_seal.cryptographic_signature).toBeNull();
  const certificate = report.lifecycle.raven_seal.blockchain_simulation;
  expect(certificate).toMatchObject({ status: 'simulation_only_not_broadcast', broadcast: false, network: null, cryptographic_signature: null });
  const lifecycleEvidence = structuredClone(report.lifecycle);
  lifecycleEvidence.raven_seal.blockchain_simulation = null;
  const payload = {
    format: 'raven-report-evidence-v1', calculation_created_at: report.calculation_created_at,
    config: report.config, requests: report.requests, evaluations: report.evaluations, lifecycle: lifecycleEvidence,
  };
  const canonical = JSON.stringify(payload, (_key, value) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);
  expect(certificate.payload_sha256).toBe(createHash('sha256').update(canonical).digest('hex'));
  await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
  await expect(page.getByRole('button', { name: 'Stampa / salva PDF', exact: true })).toBeEnabled();
  const certificateBeforePrint = await page.getByTestId('report-final-seal').innerText();
  const paperBeforePrint = await page.getByTestId('report-digital-savings').innerText();
  await page.emulateMedia({ media: 'print' });
  await expect(lifecycle.getByRole('heading', { name: '5. Limits and validation status', exact: true })).toBeVisible();
  await expect(page.getByTestId('mission-liability')).toBeVisible();
  await expect(lifecycle.locator('.raven-seal-mark img')).toBeVisible();
  await expect(page.locator('.report-options')).toBeHidden();
  await expect(page.locator('.report-bar')).toBeHidden();
  const pdf = await page.pdf({ path: testInfo.outputPath('mission-report.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true });
  const pdfPages = pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)?.length ?? 0;
  expect(pdfPages).toBeGreaterThan(0);
  expect(pdfPages).toBeLessThanOrEqual(20); // verdict page, charts, formulas, limits and appendices
  const pdfText = execFileSync('pdftotext', ['-layout', testInfo.outputPath('mission-report.pdf'), '-'], { encoding: 'utf8' });
  expect(pdfText).not.toContain('127.0.0.1');
  expect(pdfText).not.toContain('http://');
  expect(pdfText).not.toContain('Mission Planner | RAVEN');
  await expect(page.getByTestId('report-final-seal')).toHaveText(certificateBeforePrint, { useInnerText: true });
  await expect(page.getByTestId('report-digital-savings')).toHaveText(paperBeforePrint, { useInnerText: true });
  await page.emulateMedia({ media: 'screen' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.screenshot({ path: testInfo.outputPath('report.png'), fullPage: true });
  await page.getByRole('radio', { name: 'Learn' }).check();
  await expect(lifecycle.locator('.rp-appendix')).toHaveCount(0);
  await expect(lifecycle.locator('section.phase')).toHaveCount(0);
  await expect(lifecycle.locator('figure.rp-chart')).toHaveCount(5);
  await expect(page.getByTestId('report-essential-limits')).toBeVisible();
  await expect(page.getByTestId('mission-signature')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Stampa / salva PDF', exact: true })).toBeEnabled();
  await page.emulateMedia({ media: 'print' });
  const briefPdf = await page.pdf({ path: testInfo.outputPath('mission-report-brief.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true });
  const briefPages = briefPdf.toString('latin1').match(/\/Type\s*\/Page\b/g)?.length ?? 0;
  expect(briefPages).toBeGreaterThan(0);
  expect(briefPages).toBeLessThan(pdfPages);
  expect(briefPages).toBeLessThanOrEqual(9); // Learn = parts 1-4, with the nine overlay maps (one page) and the Sun and Earth against the horizon
  await page.emulateMedia({ media: 'screen' });
  const briefDownloadPromise = page.waitForEvent('download');
  await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
  await page.getByRole('button', { name: 'Scarica report strutturato (JSON)' }).click();
  const briefDownload = await briefDownloadPromise;
  const briefArchive = JSON.parse(await readFile((await briefDownload.path())!, 'utf8'));
  expect(briefArchive.lifecycle.presentation).toMatchObject({
    json_contains_complete_data: true, sections: { summary: true, charts: false, provenance: false },
  });
  expect(briefArchive.evaluations[0].steps.gen_w).toEqual(report.evaluations[0].steps.gen_w);
  expect(briefArchive.lifecycle.phases).toHaveLength(7);
  await page.reload();
  await expect(page.getByTestId('report-mode')).toHaveAttribute('data-mode', 'learn');
  await page.getByRole('radio', { name: 'Expert' }).check();
  await page.getByTestId('report-customise').locator('summary').click();
  await page.locator('#report-section-parameters').uncheck();
  await expect(page.locator('.report-preview [data-appendix="parameters"]')).toHaveCount(0);
  await page.locator('#report-section-parameters').check();
  await expect(page.locator('.report-preview [data-appendix="parameters"]')).toHaveCount(1);
  await expect(page.locator('.report-preview figure.rp-chart')).toHaveCount(5);
  expect(bodies).toHaveLength(2);
  await page.goto(`${appOrigin}/app/mission-planner?lang=en&mode=avanzato&mp_step=period&site=malapert-massif&t=2027-04-16T00:00:00Z`);
  await page.locator('#journey-days').fill('0.15');
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Prepare report', exact: true })).toBeEnabled({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Mission dossier', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  await expect(page.getByRole('heading', { name: '1. Verdict', exact: true })).toBeVisible();
  await expect(page.getByTestId('report-digital-savings')).toContainText('estimated');
  await expect(page.getByTestId('report-final-seal')).toContainText('DEMO-');
  await expect(page.locator('.rp-kicker')).toContainText('Preliminary');
  const appDownloadPromise = page.waitForEvent('download');
  await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
  await page.getByRole('button', { name: 'Download structured report (JSON)', exact: true }).click();
  const appDownload = await appDownloadPromise;
  const appReport = JSON.parse(await readFile((await appDownload.path())!, 'utf8'));
  expect(appReport.lifecycle.phases).toHaveLength(7);
  expect(appReport.lifecycle.economics.currency).toBeNull();
  expect(appReport.lifecycle.sustainability.carbon_indicator.total_kg_co2e).toBeNull();
  expect(appReport.lifecycle.liability_disclaimer.notice).toContain('Preliminary study produced by software');
  await expect(page.getByRole('button', { name: 'Print / save PDF', exact: true })).toBeEnabled();
  const appCertificateBeforePrint = await page.getByTestId('report-final-seal').innerText();
  const appPaperBeforePrint = await page.getByTestId('report-digital-savings').innerText();
  await page.emulateMedia({ media: 'print' });
  const appPdf = await page.pdf({ path: testInfo.outputPath('mission-report-app.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true });
  const appPdfPages = appPdf.toString('latin1').match(/\/Type\s*\/Page\b/g)?.length ?? 0;
  expect(appPdfPages).toBeGreaterThan(0);
  expect(appPdfPages).toBeLessThanOrEqual(20);
  await expect(page.getByTestId('report-final-seal')).toHaveText(appCertificateBeforePrint, { useInnerText: true });
  await expect(page.getByTestId('report-digital-savings')).toHaveText(appPaperBeforePrint, { useInnerText: true });
  await page.emulateMedia({ media: 'screen' });
  await page.getByRole('radio', { name: 'Learn' }).check();
  await expect(page.locator('.report-preview .rp-appendix')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Print / save PDF', exact: true })).toBeEnabled();
  await page.emulateMedia({ media: 'print' });
  const appBriefPdf = await page.pdf({ path: testInfo.outputPath('mission-report-app-brief.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true });
  const appBriefPages = appBriefPdf.toString('latin1').match(/\/Type\s*\/Page\b/g)?.length ?? 0;
  expect(appBriefPages).toBeGreaterThan(0);
  expect(appBriefPages).toBeLessThan(appPdfPages);
  expect(appBriefPages).toBeLessThanOrEqual(9);
  await page.emulateMedia({ media: 'screen' });
  await page.goto('/mission-planner?mp_step=report');
  await page.reload();
  await expect(page.getByTestId('report-more')).toBeVisible();
  await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
  await page.getByRole('button', { name: 'Modifica dossier di missione', exact: true }).click();
  await expect(page.locator('#journey-decision')).toHaveCount(0);
  await expect(page.locator('#dossier-missionStatement')).toHaveCount(0);
  await expect(page.locator('#dossier-purpose')).toHaveValue('scientific');
  expect(bodies).toHaveLength(4);
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await navigation(page).getByRole('button', { name: /Energia/ }).click();
  await page.locator('#journey-area').fill('3');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
  await expect(page.getByText(/Questi sono i risultati del calcolo precedente/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prepara il report' })).toBeDisabled();
  expect(bodies).toHaveLength(4); // two root and two app evaluations; editing never starts another full calculation
});

for (const prefixed of [false, true]) {
  test(`planner: dark week preserves real zeros, energy coverage and unknown RF without empty charts${prefixed ? ' (/app/)' : ''}`, async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    await page.goto(`${prefixed ? `${appOrigin}/app` : ''}/mission-planner?site=malapert-massif&t=2027-04-07T00:00:00Z&mp_step=sites`);
    await page.getByRole('group', { name: 'Assegna la selezione a uno scenario' }).getByRole('button', { name: 'Sito B', exact: true }).click();
    await page.getByRole('button', { name: /^Haworth \(/ }).click();
    await next(page);
    await page.locator('#journey-days').fill('7');
    await page.locator('#journey-resolution').selectOption('60');
    await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
    await page.getByRole('button', { name: 'Simula i due scenari' }).click();
    await openSimulationDetails(page);
    await page.getByRole('button', { name: 'Prepara il report' }).click();
    await page.getByRole('button', { name: 'Prepara il report' }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByTestId('report-more').evaluate((el) => { (el as HTMLDetailsElement).open = true; });
    await page.getByRole('button', { name: 'Scarica report strutturato (JSON)' }).click();
    const download = await downloadPromise;
    await download.saveAs(testInfo.outputPath('dark-week-report.json'));
    const report: { evaluations: RavenEvaluation[] } = JSON.parse(await readFile((await download.path())!, 'utf8'));
    const haworth = report.evaluations.find((e) => e.site.id === 'haworth')!;
    const unknownRfHours = haworth.steps!.rf_closes.filter((v) => v === null).length * haworth.window.step_min / 60;
    expect(haworth.metrics.unknown_hours).toBe(146);
    expect(unknownRfHours).toBeLessThan(haworth.metrics.unknown_hours);
    // the verdict says what is known and what is not: the dark week gives A its useful hours, B is unknown from the radio link
    const verdict = page.getByTestId('report-verdict');
    await expect(verdict).toContainText('B: 0 confirmed, 146 h unknown because the radio link is outside the model');
    await expect(verdict).toContainText('A is the only site with confirmed useful time');
    await expect(page.getByTestId('report-means')).toContainText('Do not rank B on this run');
    await expect(page.locator('figure.rp-chart[data-chart="rf"]')).toContainText('B: no values (unknown)');
    const battery = page.locator('figure.rp-chart[data-chart="battery"]');
    await expect(battery.locator('svg text').first()).toHaveText('0');
    await expect(battery).toContainText('Does the battery last?');
    await page.screenshot({ path: testInfo.outputPath('dark-week-report.png'), fullPage: true });
  });
}

test('planner: energy edits recalculate preview in place and change the engine output', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=energy');
  const charts = page.getByTestId('journey-preview-charts');
  await charts.locator('figure').first().waitFor({ timeout: 45_000 });
  const trackingResponse = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate') &&
    r.request().postDataJSON().site_id === 'malapert-massif' &&
    r.request().postDataJSON().energy_overrides.orientation === 'tracking', { timeout: 15_000 });
  await page.getByRole('button', { name: /Inseguimento solare ideale/ }).click();
  const tracking: RavenEvaluation = await (await trackingResponse).json();
  await charts.locator('figure').first().waitFor({ timeout: 30_000 });
  const areaResponse = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate') &&
    r.request().postDataJSON().site_id === 'malapert-massif' &&
    r.request().postDataJSON().energy_overrides.array_area_m2 === 1.5, { timeout: 15_000 });
  await page.locator('#journey-area').fill('1.5');
  const enlarged: RavenEvaluation = await (await areaResponse).json();
  expect(enlarged.steps!.gen_w[0]).toBeCloseTo(tracking.steps!.gen_w[0]! * 1.5, 6);
  await charts.locator('figure').first().waitFor({ timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Energia', exact: true })).toBeVisible();
  const smallResponse = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate') &&
    r.request().postDataJSON().site_id === 'malapert-massif' &&
    r.request().postDataJSON().energy_overrides.array_area_m2 === .01, { timeout: 15_000 });
  await page.locator('#journey-area').fill('0.01');
  const small: RavenEvaluation = await (await smallResponse).json();
  expect(small.metrics.min_soc).toBeLessThan(.9);
  expect(small.steps!.soc.at(-1)).toBeLessThan(small.steps!.soc[0]!);
  await charts.locator('figure').first().waitFor({ timeout: 30_000 });
});

test('planner: a failed automatic preview stays explicit and retries only after changed input', async ({ page }) => {
  let calls = 0;
  await page.clock.install();
  await page.route('**/api/raven/evaluate', async (route) => {
    calls++;
    await route.fulfill({ status: 503, json: { detail: 'busy' } });
  });
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=energy');
  await page.getByRole('alert').first().waitFor({ timeout: 15_000 });
  await page.clock.runFor(1000);
  expect(calls).toBe(1);
  const changedResponse = page.waitForResponse((r) => r.url().endsWith('/api/raven/evaluate'));
  await page.locator('#journey-area').fill('1.5');
  await page.clock.runFor(500);
  await changedResponse;
  expect(calls).toBe(2);
  await page.clock.runFor(1000);
  expect(calls).toBe(2);
  await expect(page.getByRole('alert').first()).toBeVisible();
});

test('planner: invalid period and numeric controls block progress without clamping', async ({ page }) => {
  await page.goto('/mission-planner?mp_step=period');
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await page.locator('#journey-days').fill('366');
  await page.locator('#journey-resolution').selectOption('10');
  await expect(page.getByRole('alert')).toContainText(/campioni|punti|passo|finestra/i);
  await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeDisabled();
  await page.locator('#journey-days').fill('1');
  await next(page);
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await page.locator('#journey-efficiency').fill('4');
  await expect(page.locator('#journey-efficiency')).toHaveValue('4');
  await expect(page.getByRole('button', { name: 'Continua', exact: true })).toBeDisabled();
});

test('planner: browser history, reload and language preserve the current draft', async ({ page }) => {
  await page.goto('/mission-planner');
  await page.locator('#journey-name').fill('Draft history');
  await next(page);
  await next(page);
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Siti', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'Periodo', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Periodo', exact: true })).toBeVisible();
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await page.goto('/mission-planner?lang=en&mp_step=period');
  await expect(page.getByRole('heading', { name: 'Period', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible();
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
});

test('planner: two-date comparison evaluates the same site in different windows', async ({ page }) => {
  test.setTimeout(90_000);
  const bodies: Record<string, unknown>[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/raven/evaluate') && r.postDataJSON().include_windows) bodies.push(r.postDataJSON()); });
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z');
  await page.getByRole('button', { name: 'Due date, stesso sito', exact: true }).click();
  await navigation(page).getByRole('button', { name: /Periodo/ }).click();
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await page.locator('#journey-days').fill('0.05');
  await page.locator('#journey-start-b').fill('2027-04-17T00:00');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  expect(bodies.map((r) => r.site_id)).toEqual(['malapert-massif', 'malapert-massif']);
  expect(bodies.map((r) => r.start_utc)).toEqual(['2027-04-16T00:00:00Z', '2027-04-17T00:00:00Z']);
});

test('planner: custom terrain download is explicit and refusal leaves report unavailable', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/mission-planner?mp_step=sites');
  await page.getByText('Inserisci coordinate personalizzate precise', { exact: true }).click();
  await page.getByTestId('custom-toggle').click();
  await page.locator('#cs-name').fill('Equatore prova');
  await page.locator('#cs-lat').fill('0');
  await page.locator('#cs-lon').fill('30');
  await page.getByTestId('custom-add').click();
  await navigation(page).getByRole('button', { name: /Periodo/ }).click();
  await page.locator('#journey-days').fill('0.05');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await expect(page.getByTestId('terrain-prompt')).toBeVisible();
  await page.getByTestId('terrain-cancel').click();
  await expect(page.getByRole('alert')).toContainText('Download del terreno necessario rifiutato');
  await expect(page.getByRole('button', { name: 'Prepara il report' })).toBeDisabled();
});

test('planner: API failure is visible and can be retried', async ({ page }) => {
  await page.route('**/api/raven/evaluate', (route) => route.fulfill({ status: 503, body: '{}' }));
  await openComparison(page);
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await expect(page.getByRole('alert')).toContainText('Efemeridi non disponibili o server occupato');
  await expect(page.getByRole('button', { name: 'Simula i due scenari' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Prepara il report' })).toBeDisabled();
});

test('planner: default temporal preview is interactive and does not unlock the report', async ({ page }) => {
  const bodies: Record<string, unknown>[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/raven/evaluate')) bodies.push(r.postDataJSON()); });
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=energy');
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('journey-preview-charts').locator('svg')).toHaveCount(2);
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toMatchObject({ days: 7, step_min: 60, include_windows: false });
  await page.getByTestId('journey-preview-charts').getByRole('slider').first().fill('1');
  await expect(page.getByTestId('journey-preview-charts').getByRole('slider').nth(1)).toHaveValue('1');
  await page.locator('#journey-area').fill('4');
  await expect(page.getByTestId('journey-preview-charts')).toHaveCount(0);
  await expect(navigation(page).getByRole('button', { name: /Report/ })).toBeDisabled();
});

test('planner: library restores custom coordinates and radio across browser sessions', async ({ page }) => {
  await page.goto('/mission-planner?mp_step=sites');
  await page.getByText('Inserisci coordinate personalizzate precise', { exact: true }).click();
  await page.getByTestId('custom-toggle').click();
  await page.locator('#cs-name').fill('Saved ridge');
  await page.locator('#cs-lat').fill('-88.5');
  await page.locator('#cs-lon').fill('42');
  await page.getByTestId('custom-add').click();
  await navigation(page).getByRole('button', { name: /Comunicazioni/ }).click();
  await page.locator('#journey-gain').fill('21');
  await navigation(page).getByRole('button', { name: /Missione/ }).click();
  await page.locator('#journey-name').fill('Saved lunar mission');
  await page.getByText('Missioni salvate ed esempi', { exact: true }).click();
  await page.getByRole('button', { name: 'Salva configurazione', exact: true }).click();
  await expect(page.getByText('Missione salvata nella libreria del browser.')).toBeVisible();
  await page.evaluate(() => sessionStorage.clear());
  await page.goto('/mission-planner');
  await page.getByText('Missioni salvate ed esempi', { exact: true }).click();
  await page.getByRole('button', { name: 'Apri', exact: true }).click();
  await expect(page.locator('#journey-name')).toHaveValue('Saved lunar mission');
  await navigation(page).getByRole('button', { name: /Comunicazioni/ }).click();
  await expect(page.locator('#journey-gain')).toHaveValue('21');
});

test('planner: default lander follows the comparison timeline and wave stays embedded', async ({ page }) => {
  test.setTimeout(60_000);
  await openComparison(page);
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  await expect(page.getByTestId('planner-scene-status')).toContainText('2027-04-16 00:00:00 UTC', { timeout: 20_000 });
  await page.locator('#journey-time').fill('1');
  await expect(page.getByTestId('planner-scene-status')).toContainText('2027-04-16 01:00:00 UTC');
  await navigation(page).getByRole('button', { name: /Comunicazioni/ }).click();
  await page.getByText("Esplora la diffrazione dell'onda (facoltativo)", { exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Scenario', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Sezioni' })).toHaveCount(0);
  await expect(page).toHaveURL(/mission-planner/);
});

test('planner: replay updates keep the rover camera and last WebGL frame, including slow and failed calculations', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1200 }); // the stage is wide now: keep it fully in view so screenshots are not stitched
  test.setTimeout(90_000);
  await openComparison(page);
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  const canvas = page.locator('#lander-stage canvas');
  await expect(page.getByTestId('planner-scene-status')).toContainText('2027-04-16 00:00:00 UTC', { timeout: 20_000 });
  await expect(canvas).toHaveAttribute('data-sky', 'nasa');
  await page.locator('#lander-stage').focus();
  await page.keyboard.press('1');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowUp');
  await page.locator('#journey-time').focus(); // keep the focus outline identical in the frame comparisons
  await frames(page, '#lander-stage canvas');
  const camera = await canvas.getAttribute('data-camera');
  expect(camera).toBeTruthy();
  const element = await canvas.elementHandle();
  await expect(page.locator('[data-testid="section-canvas"] canvas')).toBeVisible();
  await page.waitForTimeout(500);
  const before = await pixels(page, '#lander-stage canvas');
  expect(before.distinct).toBeGreaterThan(40);
  let release = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let calls = 0;
  let fail = false;
  await page.route('**/api/raven/scene*', async (route) => {
    calls++;
    if (fail) await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"dati DEM non disponibili"}' });
    else { await gate; await route.continue(); }
  });
  try {
    await page.locator('#journey-time').fill('1');
    await expect.poll(() => calls).toBe(1);
    await expect(page.getByTestId('planner-scene-status')).toContainText('ultima scena calcolata');
    await expect(page.locator('.stage-cover')).toHaveCount(0);
    for (let i = 0; i < 3; i++) {
      await expect(canvas).toHaveAttribute('data-camera', camera!);
      const held = await pixels(page, '#lander-stage canvas');
      expect(held.hash).toBe(before.hash);
    }
    expect(calls).toBe(1); // no recalculation loop for an unchanged timeline instant
    release();
    await expect(page.getByTestId('planner-scene-status')).toContainText('2027-04-16 01:00:00 UTC', { timeout: 20_000 });
    await frames(page, '#lander-stage canvas');
    await expect(canvas).toHaveAttribute('data-camera', camera!);
    expect(await element!.evaluate((el) => el === document.querySelector('#lander-stage canvas'))).toBe(true);
    fail = true;
    await page.locator('#journey-time').fill('2');
    await expect(page.getByRole('alert').filter({ hasText: /non disponibili/ })).toBeVisible();
    await expect(canvas).toHaveAttribute('data-camera', camera!);
    await expect(page.locator('.stage-cover')).toHaveCount(0);
    await expect(page.getByTestId('planner-scene-status')).toContainText('ultima scena calcolata');
  } finally {
    release();
    await element?.dispose();
    await page.unroute('**/api/raven/scene*');
  }
});

test('planner: mobile layout and initial controls are accessible', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/mission-planner');
  await expect(page.getByRole('heading', { name: 'Missione', exact: true })).toBeVisible();
  const audit = await new AxeBuilder({ page }).include('[data-testid="mission-journey"]').analyze();
  expect(audit.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Continua', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Siti', exact: true })).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath('sites-mobile.png'), fullPage: true });
});

test('planner: period charts and communications scene appear without opening a panel', async ({ page }) => {
  await page.goto('/mission-planner?site=malapert-massif&t=2027-04-16T00:00:00Z&mp_step=period&mode=avanzato');
  await expect(page.getByTestId('journey-preview-charts')).toBeVisible({ timeout: 30_000 });
  const visual = page.locator('.visual-stage');
  expect((await visual.boundingBox())!.y).toBeLessThan(720);
  await expect(visual.getByRole('slider')).toHaveCount(2);
  await navigation(page).getByRole('button', { name: /Comunicazioni/ }).click();
  await expect(page.getByTestId('planner-scene-status')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('img', { name: "Elevazione dell'orizzonte campionato per azimut" })).toBeVisible();
  // the lateral section is in the foreground; there is no tabbed details menu and no credit or light notes
  await expect(page.getByTestId('lander-section-panel')).toBeVisible();
  await expect(page.getByTestId('section-canvas')).toBeVisible();
  await expect(page.getByTestId('hud-antenna')).toHaveCount(0);
  await expect(page.getByTestId('lander-visual-credit')).toHaveCount(0);
  await expect(page.getByTestId('sun-note')).toHaveCount(0);
});

test('dashboard: shared calculation, timeline, stale warning and no extra mission calculation', async ({ page }) => {
  await openComparison(page);
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  const dashboardCalculations: string[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/raven/evaluate')) dashboardCalculations.push(r.url()); });
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Dashboard' }).click();
  await expect(page.getByTestId('mission-dashboard')).toBeVisible();
  await openSimulationDetails(page);
  await page.locator('#journey-time').fill('1');
  await expect(page.locator('label[for="journey-time"]')).toContainText('01:00:00 UTC');
  await expect(page.getByRole('slider', { name: 'Sole', exact: true })).toHaveValue('1');
  const archive = await page.evaluate(() => sessionStorage.getItem('hb.planner-journey.run.v1'));
  await page.reload();
  await openSimulationDetails(page);
  expect(await page.evaluate(() => sessionStorage.getItem('hb.planner-journey.run.v1'))).toBe(archive);
  expect(dashboardCalculations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).include('[data-testid="mission-dashboard"]').analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole('link', { name: 'Simulazione', exact: true }).click();
  await navigation(page).getByRole('button', { name: /Energia/ }).click();
  await page.locator('#journey-area').fill('3');
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Dashboard' }).click();
  await expect(page.getByText(/Questi sono i risultati del calcolo precedente/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Prepara il report' })).toHaveCount(0);
  await page.evaluate(() => {
    const run = JSON.parse(sessionStorage.getItem('hb.planner-journey.run.v1')!);
    run.evaluations[0].registry_sha256 = 'invalid';
    sessionStorage.setItem('hb.planner-journey.run.v1', JSON.stringify(run));
  });
  await page.reload();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Timeline della missione' })).toHaveCount(0);
});

test('dashboard: empty state is honest and accessible on mobile and subpath', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appOrigin}/app/dashboard`);
  await expect(page.getByRole('heading', { name: 'Il controllo della missione inizia qui' })).toBeVisible();
  await expect(page.getByTestId('mission-dashboard').getByRole('link', { name: 'Mission Planner' })).toHaveAttribute('href', '/app/mission-planner?mp_step=mission');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).include('[data-testid="mission-dashboard"]').analyze()).violations).toEqual([]);
});

test('dashboard history: two final calculations survive the tab, stay read-only and reset cursors', async ({ page }) => {
  test.setTimeout(120_000);
  expect((await (await page.request.get('/api/raven/model')).json()).model_version).toBe('raven-core-1.4');
  await openComparison(page);
  await navigation(page).getByRole('button', { name: /Missione/ }).click();
  await page.locator('#journey-name').fill('Archive A');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await openSimulationDetails(page);
  await expect(page.getByText('Calcolo definitivo salvato nella cronologia locale.')).toBeVisible();
  await navigation(page).getByRole('button', { name: /Missione/ }).click();
  await page.locator('#journey-name').fill('Archive B');
  await navigation(page).getByRole('button', { name: /Energia/ }).click();
  await page.locator('#journey-area').fill('2');
  await navigation(page).getByRole('button', { name: /Simulazione/ }).click();
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await expect(page.getByRole('button', { name: 'Simula i due scenari', exact: true })).toBeEnabled();
  await openSimulationDetails(page);
  const entries = await page.evaluate(() => JSON.parse(localStorage.getItem('hb.planner-journey.history.v1')!).entries as { id: string; name: string }[]);
  expect(entries.map((e) => e.name)).toEqual(['Archive B', 'Archive A']);
  const draft = await page.evaluate(() => sessionStorage.getItem('hb.planner-journey.v1'));
  let calculations = 0;
  page.on('request', (r) => { if (r.url().endsWith('/api/raven/evaluate')) calculations++; });
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Dashboard' }).click();
  await page.locator('#history-selection').selectOption(entries[1]!.id);
  await expect(page.getByRole('heading', { name: 'Archive A', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Prepara il report' })).toHaveCount(0);
  await page.locator('#journey-time').fill('2');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: "Scarica l'istantanea del calcolo (JSON)" }).click();
  const file = await downloaded;
  const snapshot = JSON.parse(await readFile((await file.path())!, 'utf8'));
  expect(snapshot.config.name).toBe('Archive A');
  expect(snapshot.config.panel.array_area_m2).toBe(1);
  await page.locator('#history-selection').selectOption(entries[0]!.id);
  await expect(page.locator('#journey-time')).toHaveValue('0');
  expect(await page.evaluate(() => sessionStorage.getItem('hb.planner-journey.v1'))).toBe(draft);
  await page.evaluate(() => sessionStorage.removeItem('hb.planner-journey.run.v1'));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Archive B', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).include('[data-testid="mission-dashboard"]').analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Elimina il calcolo salvato selezionato' }).click();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('hb.planner-journey.history.v1')!).entries.length)).toBe(1);
  await page.getByRole('checkbox', { name: "Confermo l'eliminazione dell'intera cronologia locale dei calcoli" }).check();
  await page.getByRole('button', { name: 'Svuota la cronologia dei calcoli' }).click();
  await page.reload();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('hb.planner-journey.history.v1')!).entries)).toEqual([]);
  expect(calculations).toBe(0);
});

test('dashboard history: corruption is explicit and clearing requires consent', async ({ page }) => {
  await page.goto('/dashboard');
  await page.evaluate(() => localStorage.setItem('hb.planner-journey.history.v1', '{broken'));
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('La cronologia dei calcoli è illeggibile');
  await expect(page.getByRole('button', { name: 'Svuota la cronologia dei calcoli' })).toBeDisabled();
  expect(await page.evaluate(() => localStorage.getItem('hb.planner-journey.history.v1'))).toBe('{broken');
  await page.getByRole('checkbox', { name: "Confermo l'eliminazione dell'intera cronologia locale dei calcoli" }).check();
  await page.getByRole('button', { name: 'Svuota la cronologia dei calcoli' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('planner: Download PDF is rendered by the server with page numbers and no local address', async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
  const probe = await request.post('/api/raven/report/pdf', { data: { html: '<p>x</p>', title: 'probe', lang: 'en' } });
  test.skip(probe.status() === 503, 'server PDF engine not installed (extra pdf / Pango missing)');
  await page.goto('/mission-planner?lang=en&mp_step=period&site=malapert-massif&t=2027-04-16T00:00:00Z&mode=avanzato');
  await page.locator('#journey-days').fill('0.15');
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Prepare report', exact: true })).toBeEnabled({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  await page.getByRole('button', { name: 'Prepare report', exact: true }).click();
  await expect(page.getByTestId('report-toc')).toHaveCount(0);
  const download = page.waitForEvent('download', { timeout: 90_000 });
  await page.getByTestId('download-pdf').click();
  const file = testInfo.outputPath('server-report.pdf');
  await (await download).saveAs(file);
  const info = execFileSync('pdfinfo', [file], { encoding: 'utf8' });
  expect(info).toMatch(/Title:\s+\S/);
  expect(info).toMatch(/Tagged:\s+yes/);
  const pages = Number(info.match(/Pages:\s+(\d+)/)?.[1]);
  expect(pages).toBeGreaterThan(2);
  const text = (n: number) => execFileSync('pdftotext', ['-f', String(n), '-l', String(n), '-layout', file, '-'], { encoding: 'utf8' });
  const all = execFileSync('pdftotext', ['-layout', file, '-'], { encoding: 'utf8' });
  expect(all).not.toContain('127.0.0.1');
  expect(all).not.toContain('localhost');
  const tocPage = [1, 2].find((n) => text(n).includes('Contents'))!; // the short contents follow the verdict (page 1 or 2)
  expect(tocPage).toBeDefined();
  expect(text(tocPage)).toMatch(/Page \d of \d+/);
  // every table-of-contents line ends with a page number that is a real page of the document
  const lines = text(tocPage).split('\n').filter((l) => /\.{4,}\s*\d+\s*$/.test(l));
  expect(lines.length).toBeGreaterThan(4);
  for (const line of lines) {
    const [, title, n] = line.match(/^\s*(.+?)\s*\.{4,}\s*(\d+)\s*$/)!;
    const pageNo = Number(n);
    expect(pageNo).toBeGreaterThanOrEqual(1);
    expect(pageNo).toBeLessThanOrEqual(pages);
    expect(text(pageNo).replace(/\s+/g, ' ')).toContain(title!.replace(/\s+/g, ' ').slice(0, 30));
  }
});
