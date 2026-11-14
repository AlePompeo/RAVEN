// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

const next = (page: import('@playwright/test').Page) => page.getByRole('button', { name: 'Continua', exact: true }).click();

test('report: RAVEN estimates appear after the run, an accepted one is boxed in the report and the PDF, a dismissed one is not', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await page.goto('/mission-planner?mode=avanzato');
  await page.locator('#journey-name').fill('Estimate Study');
  await page.getByRole('button', { name: 'Usa questo esempio' }).click();
  await next(page);
  await page.locator('#journey-days').fill('0.15');
  await page.locator('#journey-resolution').selectOption('60');
  await next(page);
  await page.getByRole('button', { name: /Inseguimento solare ideale/ }).click();
  await next(page);
  await next(page);
  await next(page);
  await expect(page.getByTestId('planner-scene-status')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await expect(page.getByRole('heading', { name: 'Timeline della missione' })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await expect(page.getByRole('heading', { name: 'Dossier di missione', exact: true })).toBeVisible();

  // no wall of tables: one checkbox switches the RAVEN estimates on (default) or off; the mission-class slider stays
  const estimates = page.getByTestId('raven-estimates');
  await expect(estimates.locator('table')).toHaveCount(0);
  await expect(estimates.locator('input[type=checkbox]:visible')).toHaveCount(2);
  await expect(page.locator('#estimates-on')).toBeChecked();
  // the mission-class slider is keyboard accessible: End moves to the large class
  const slider = page.locator('#mission-class-range');
  await slider.focus();
  await page.keyboard.press('End');
  await expect(page.getByTestId('mission-class-name')).toHaveText('Lander grande o classe equipaggio');
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowRight');
  // the engine densities can be switched off and on again
  await page.locator('#mass-apply').uncheck();
  await page.locator('#mass-apply').check();

  await page.getByRole('button', { name: 'Prepara il report' }).click();
  // the report is English only: estimates are automatic in the cost appendix (Expert); a dismissed one is not
  const box = page.locator('[data-appendix="costs-esg"]');
  await expect(box).toHaveCount(1);
  await expect(box).toContainText('Launch and landing statistics');
  await expect(page.getByTestId('mission-lifecycle-report')).not.toContainText('Cause (result field and value)');
  // engine estimates for what no site provides: an interval with its source, unknown stays unknown, English only
  const est = page.getByTestId('report-estimates');
  await expect(est).toContainText('Quantities no site provides', { timeout: 20_000 });
  await expect(est).toContainText('Soft landing succeeds', { timeout: 20_000 });
  await expect(est).toContainText('13 attempts from 2019 to 2025');
  await expect(est).toContainText('unknown'); // roughness, component failure rates
  await expect(est).not.toContainText('Ignoto');
  // the last part: which of the two sites is better; decided by the engine, with every component in a table (no score)
  const verdict = page.getByTestId('report-site-verdict');
  await expect(verdict.locator('[data-winner]')).toBeVisible({ timeout: 20_000 });
  await expect(verdict.locator('tbody tr')).toHaveCount(5);
  await expect(verdict.getByTestId('verdict-text')).not.toBeEmpty();
  await expect(verdict).toContainText('RAVEN engine made the decision');

  await page.emulateMedia({ media: 'print' });
  await page.pdf({ path: testInfo.outputPath('estimates.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true });
  const text = execFileSync('pdftotext', ['-layout', testInfo.outputPath('estimates.pdf'), '-'], { encoding: 'utf8' });
  expect(text).toContain('Cost, schedule and sustainability');
  expect(text).toContain('Including RAVEN estimates');
  expect(text).toContain('Quantities no site provides');
  expect(text).toContain('Soft landing succeeds');
  expect(text).toContain('Which site is better?');
  expect(text).not.toContain('Cause (result field and value)');
});

test('report: the PDF waits for the written comparison of the two sites (a local model needs time)', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/raven/report/verdict', async (route) => { await gate; await route.continue(); });
  await page.goto('/mission-planner?mode=avanzato');
  await page.locator('#journey-name').fill('Verdict Wait');
  await page.getByRole('button', { name: 'Usa questo esempio' }).click();
  await next(page);
  await page.locator('#journey-days').fill('0.15');
  await page.locator('#journey-resolution').selectOption('60');
  await next(page);
  await page.getByRole('button', { name: /Inseguimento solare ideale/ }).click();
  await next(page);
  await next(page);
  await next(page);
  await expect(page.getByTestId('planner-scene-status')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Simula i due scenari' }).click();
  await expect(page.getByRole('heading', { name: 'Timeline della missione' })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await expect(page.getByRole('heading', { name: 'Dossier di missione', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Prepara il report' }).click();
  await expect(page.getByTestId('pdf-wait')).toBeVisible({ timeout: 15_000 }); // the comparison is still being written
  await expect(page.getByTestId('download-pdf')).toBeDisabled();
  release();
  await expect(page.getByTestId('report-site-verdict').getByTestId('verdict-text')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('pdf-wait')).toHaveCount(0, { timeout: 30_000 });
  // part 2: the nine map overlays are drawn as images (each one a canvas that the PDF turns into a picture), with both sites marked
  const overlays = page.getByTestId('report-overlays');
  await expect(overlays.locator('canvas[data-pdf-image]')).toHaveCount(9);
  await expect(overlays).toContainText('Longest blackout without Earth');
  await expect(overlays).toContainText('False colour: Sun, Earth, slope');
  await overlays.scrollIntoViewIfNeeded();
  await overlays.screenshot({ path: testInfo.outputPath('overlays.png') });
  // the real PDF export: the nine overlay maps travel as pictures (plus the Moon map of the sites)
  await expect(page.getByTestId('download-pdf')).toBeEnabled({ timeout: 30_000 });
  const download = page.waitForEvent('download', { timeout: 90_000 }).catch(() => null);
  await page.getByTestId('download-pdf').click();
  const file = await download;
  test.skip(!file, 'the PDF engine of the server is not available here (the page falls back to the print dialog)');
  const pdf = testInfo.outputPath('report.pdf');
  await file!.saveAs(pdf);
  const listing = execFileSync('pdfimages', ['-list', pdf], { encoding: 'utf8' });
  const pictures = listing.split('\n').slice(2).filter((l) => l.trim()).length;
  expect(pictures).toBeGreaterThanOrEqual(10);
});
