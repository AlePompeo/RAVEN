// SPDX-License-Identifier: Apache-2.0
import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';

const nav = (page: Page) => page.getByRole('navigation', { name: 'Mission planning steps' });
const prepare = (page: Page) => page.getByRole('button', { name: 'Prepare report', exact: true });

async function toDossier(page: Page, query = '') {
  await page.goto(`/mission-planner?lang=en&mp_step=period&site=malapert-massif&t=2027-04-16T00:00:00Z${query}`);
  await page.locator('#journey-days').fill('0.15');
  await nav(page).getByRole('button', { name: /Simulation/ }).click();
  await page.getByRole('button', { name: 'Simulate both scenarios', exact: true }).click();
  await expect(prepare(page)).toBeEnabled({ timeout: 60_000 });
  await prepare(page).click();
  await expect(page.getByRole('heading', { name: 'Mission dossier', exact: true })).toBeVisible();
}
const pdfText = async (page: Page, file: string) => {
  const download = page.waitForEvent('download', { timeout: 90_000 });
  await expect(page.getByTestId('download-pdf')).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId('download-pdf').click();
  await (await download).saveAs(file);
  const text = execFileSync('pdftotext', ['-layout', file, '-'], { encoding: 'utf8' });
  const pages = Number(execFileSync('pdfinfo', [file], { encoding: 'utf8' }).match(/Pages:\s+(\d+)/)?.[1]);
  const toc = text.split('\n').filter((l) => /\.{4,}\s*\d+\s*$/.test(l)).length;
  return { text, pages, toc };
};

test('report modes: Learn asks few questions and reports with one click; Expert has every field and the full report', async ({ page, request }, testInfo) => {
  test.setTimeout(240_000);
  const probe = await request.post('/api/raven/report/pdf', { data: { html: '<p>x</p>', title: 'probe', lang: 'en' } });
  const serverPdf = probe.status() !== 503;
  await toDossier(page, '&mode=learning');

  // Learn is the default for the Learning site mode
  const dossier = page.getByTestId('report-dossier');
  await expect(dossier).toHaveAttribute('data-mode', 'learn');
  await expect(page.getByRole('radio', { name: /Learn/ })).toBeChecked();
  const questions = page.getByTestId('dossier-essential').locator('input:visible, select:visible, textarea:visible');
  expect(await questions.count()).toBeGreaterThan(0);
  expect(await questions.count()).toBeLessThanOrEqual(6);
  await expect(dossier.locator('textarea:visible')).toHaveCount(0);
  await expect(page.locator('#dossier-architecture')).toHaveCount(0);
  await expect(page.locator('#dossier-currency')).toHaveCount(0);
  await expect(page.getByTestId('dossier-optional-counter')).toHaveCount(0);
  await expect(page.getByTestId('learn-hidden')).toHaveCount(0);
  await expect(page.getByTestId('dossier-progress')).toContainText('report fields are filled');
  expect((await new AxeBuilder({ page }).include('[data-testid="report-dossier"]').analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });

  // one click, nothing filled
  await page.getByTestId('generate-now').click();
  await expect(page.getByTestId('report-mode')).toHaveAttribute('data-mode', 'learn');
  // the Report step is light: one primary button, a small menu, a two-option switch, one line saying the report is English
  await expect(page.getByTestId('download-pdf')).toBeVisible();
  await expect(page.getByTestId('report-more')).toBeVisible();
  await expect(page.getByTestId('report-customise')).toHaveCount(0);
  await expect(page.locator('#journey-decision')).toHaveCount(0);
  await expect(page.getByText('The report is generated in English.')).toBeVisible();
  // Learn = parts 1-4 only: verdict sentence, four charts, formulas, limits; no contents, no appendix
  await expect(page.getByRole('heading', { name: '1. Verdict', exact: true })).toBeVisible();
  await expect(page.getByTestId('report-verdict')).toContainText('sampled hours');
  await expect(page.locator('figure.rp-chart')).toHaveCount(5);
  await expect(page.getByRole('heading', { name: '4. How it was computed', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '5. Limits and validation status', exact: true })).toBeVisible();
  await expect(page.locator('.rp-appendix')).toHaveCount(0);
  await expect(page.getByTestId('report-toc')).toHaveCount(0);
  const learnLength = (await page.locator('.report-preview').innerText()).length;
  const learnPdf = serverPdf ? await pdfText(page, testInfo.outputPath('learn.pdf')) : null;
  if (learnPdf) { expect(learnPdf.text).toContain('Which site is better'); expect(learnPdf.text).toContain('Page 1 of'); }

  // switch to Expert in the Report step: the site mode is untouched
  await page.getByRole('radio', { name: 'Expert' }).check();
  await expect(page.getByTestId('report-mode')).toHaveAttribute('data-mode', 'expert');
  await expect(page.getByTestId('report-toc')).toBeVisible();
  await expect(page.locator('.rp-appendix').first()).toBeVisible();
  await page.getByTestId('report-customise').locator('summary').click();
  await expect(page.getByTestId('report-section-picker').locator('input[type="checkbox"]:not(:checked)')).toHaveCount(0);
  expect((await page.locator('.report-preview').innerText()).length).toBeGreaterThan(learnLength);
  if (learnPdf) {
    const expertPdf = await pdfText(page, testInfo.outputPath('expert.pdf'));
    expect(expertPdf.toc).toBeGreaterThan(learnPdf.toc);
    expect(expertPdf.pages).toBeGreaterThan(learnPdf.pages);
    expect(expertPdf.text.length).toBeGreaterThan(learnPdf.text.length);
    expect(learnPdf.pages).toBeLessThanOrEqual(8);
  }

  // Expert dossier: the same questions plus the RAVEN estimates; cost, CO2e and the plan text are not typed any more
  await page.getByTestId('report-more').locator('summary').click();
  await page.getByRole('button', { name: 'Edit mission dossier', exact: true }).click();
  await expect(dossier).toHaveAttribute('data-mode', 'expert');
  for (const id of ['purpose', 'missionStatement', 'successCriteria', 'owner']) await expect(page.locator(`#dossier-${id}`)).toHaveCount(1);
  for (const id of ['architecture', 'launchPlan', 'environmentPlan', 'currency', 'year', 'cost-basis', 'contingency', 'funding']) await expect(page.locator(`#dossier-${id}`)).toHaveCount(0);
  await expect(page.locator('#cost-operations')).toHaveCount(0);
  await expect(page.locator('#carbon-boundary')).toHaveCount(0);
  await expect(page.getByTestId('dossier-group-plan')).toHaveCount(0);
  await expect(page.getByTestId('dossier-optional-counter')).toHaveCount(0);
  expect((await new AxeBuilder({ page }).include('[data-testid="report-dossier"]').analyze()).violations).toEqual([]);
});

test('report modes: Advanced site mode defaults to Expert; the choice survives a reload', async ({ page }) => {
  test.setTimeout(150_000);
  await toDossier(page, '&mode=avanzato');
  await expect(page.getByTestId('report-dossier')).toHaveAttribute('data-mode', 'expert');
  await page.getByRole('radio', { name: /Learn/ }).check();
  await expect(page.getByTestId('report-dossier')).toHaveAttribute('data-mode', 'learn');
  await page.goto('/mission-planner?lang=en&mode=avanzato&mp_step=dossier');
  await expect(page.getByTestId('report-dossier')).toHaveAttribute('data-mode', 'learn');
});
