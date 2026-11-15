// SPDX-License-Identifier: Apache-2.0
import { expect, type Page } from '@playwright/test';

export async function openSimulationDetails(page: Page): Promise<void> {
  const details = page.getByTestId('simulation-disclosure');
  await expect(details).toBeVisible({ timeout: 90_000 });
  if (!(await details.evaluate((el) => (el as HTMLDetailsElement).open))) {
    await details.locator('summary').click();
  }
}
