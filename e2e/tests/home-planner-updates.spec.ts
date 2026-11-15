// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('duration presets adjust the sampling step and simulation has no educational map', async ({ page }) => {
  await page.goto('/mission-planner?lang=en&mp_step=period&mode=avanzato&site=malapert-massif&t=2027-04-07T00:00:00Z');
  await expect(page.locator('#journey-days')).toBeVisible();
  await page.locator('#journey-resolution').selectOption('10');
  await page.getByRole('button', { name: '28 days', exact: true }).click();
  await expect(page.locator('#journey-days')).toHaveValue('28');
  await expect(page.locator('#journey-resolution')).toHaveValue('30');
  await expect(page.getByTestId('auto-step')).toContainText('raised to 30 min');
  await page.getByRole('button', { name: '365 days', exact: true }).click();
  await expect(page.locator('#journey-days')).toHaveValue('365');
  await expect(page.locator('#journey-resolution')).toHaveValue('360');
  await expect(page.getByTestId('auto-step')).toContainText('raised to 360 min');
  await page.getByRole('navigation', { name: 'Mission planning steps' }).getByRole('button', { name: /Simulation/ }).click();
  await expect(page.getByRole('button', { name: 'Simulate both scenarios', exact: true })).toBeVisible();
  await expect(page.getByTestId('planner-link-preview')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Interactive link model' })).toHaveCount(0);
});

test('home restores the interactive story without restoring removed hero controls', async ({ page }) => {
  await page.goto('/?lang=en');
  const hero = page.getByRole('region', { name: 'RAVEN', exact: true });
  await expect(hero.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about');
  await expect(hero.getByRole('link', { name: 'How it works' })).toHaveCount(0);
  await expect(hero).not.toContainText('Moon from NASA LRO maps');
  for (const id of ['step-horizon', 'step-ridge', 'step-compute', 'step-mission']) {
    await expect(page.getByTestId(id)).toBeAttached();
  }
  await page.getByTestId('step-compute').scrollIntoViewIfNeeded();
  const slider = page.getByTestId('mini-el').locator('input[type="range"]');
  await expect(slider).toBeVisible();
  const link = page.getByRole('link', { name: 'Open in the full simulator' });
  const before = await link.getAttribute('href');
  await slider.fill('3');
  await expect(link).not.toHaveAttribute('href', before!);
});
