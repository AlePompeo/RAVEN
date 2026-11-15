// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

for (const language of ['en', 'it'] as const) {
  test(`planner results collapse and dossier is simplified (${language})`, async ({ page }) => {
    const en = language === 'en';
    await page.goto(`/mission-planner?lang=${language}&mode=avanzato&mp_step=period&site=malapert-massif&t=2027-04-16T00:00:00Z`);
    const nav = page.getByRole('navigation', { name: en ? 'Mission planning steps' : 'Passaggi della pianificazione' });
    await page.locator('#journey-days').fill('0.15');
    await page.locator('#journey-resolution').selectOption('60');
    await nav.getByRole('button', { name: en ? /Reliability/ : /Affidabilità/ }).click();
    const inputs = page.getByTestId('reliability-inputs');
    await page.getByRole('button', { name: en ? 'Load illustrative assumptions — not real hardware' : 'Carica ipotesi illustrative — non hardware reale', exact: true }).click();
    await expect(inputs.getByText(en ? /Optional incremental demand/ : /domanda aggiuntiva facoltativa/i)).toHaveCount(0);
    await expect(inputs.getByText(en ? /Protect electronics before interpreting/ : /Proteggi l’elettronica/i)).toHaveCount(0);
    await expect(inputs.getByText(en ? /Use mission-specific dose analysis/ : /analisi della dose specifica/i)).toHaveCount(0);
    await expect(inputs.getByText(en ? /Preliminary RAVEN engine arithmetic/ : /calcolo preliminare/i)).toHaveCount(0);
    await expect(page.locator('#rel-apply-power')).toBeVisible();
    await nav.getByRole('button', { name: en ? /Simulation/ : /Simulazione/ }).click();
    const response = page.waitForResponse((r) => r.url().endsWith('/api/raven/report/reliability') && r.ok());
    await page.getByRole('button', { name: en ? 'Simulate both scenarios' : 'Simula i due scenari', exact: true }).click();
    await response;
    const simulation = page.getByTestId('simulation-disclosure');
    await expect(simulation).toBeVisible({ timeout: 60_000 });
    await expect(simulation).not.toHaveAttribute('open', '');
    await expect(page.getByTestId('mission-statistics')).toBeHidden();
    await simulation.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('mission-statistics')).toBeVisible();
    await expect(page.locator('#journey-time')).toBeVisible();
    await simulation.locator('summary').click();
    await expect(page.getByTestId('mission-statistics')).toBeHidden();
    await nav.getByRole('button', { name: en ? /Reliability/ : /Affidabilità/ }).click();
    const reliability = page.getByTestId('reliability-disclosure');
    await expect(reliability).toBeVisible();
    await expect(page.getByTestId('reliability-results')).toBeHidden();
    await reliability.locator('summary').click();
    await expect(page.getByTestId('reliability-charts')).toBeVisible();
    await expect(page.getByTestId('reliability-results')).toContainText('raven-reliability-1');
    await reliability.locator('summary').click();
    await expect(page.getByTestId('reliability-results')).toBeHidden();
    await nav.getByRole('button', { name: en ? /Simulation/ : /Simulazione/ }).click();
    await page.getByRole('button', { name: en ? 'Prepare report' : 'Prepara il report', exact: true }).click();
    const dossier = page.getByTestId('report-dossier');
    await expect(dossier).toBeVisible();
    await expect(page.getByTestId('dossier-progress')).toHaveCount(0);
    for (const id of ['dossier-missionStatement', 'dossier-successCriteria', 'dossier-owner', 'journey-decision']) {
      await expect(page.locator(`#${id}`)).toHaveCount(0);
    }
    await expect(page.locator('#dossier-purpose')).toBeVisible();
    await expect(page.getByText(en ? 'Essential questions' : 'Domande essenziali', { exact: true })).toHaveCount(0);
    await expect(page.getByText(en ? /Complete the mission-specific assumptions/ : /Completa le ipotesi specifiche/)).toHaveCount(0);
    await page.getByRole('button', { name: en ? 'Prepare report' : 'Prepara il report', exact: true }).click();
    await expect(page.getByTestId('report-bar')).toBeVisible();
    await expect(page.getByTestId('mission-liability')).toBeVisible();
  });
}
