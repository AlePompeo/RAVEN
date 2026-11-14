// SPDX-License-Identifier: Apache-2.0
// Scena lander in Chromium SENZA WebGL: la sezione laterale in Canvas 2D e' il ripiego, non vuota, con testo equivalente.
import { test, expect } from '@playwright/test';
import { defineLanderCore } from './landerSuite';
import { openLander, pixels } from './landerHelpers';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

test.describe('scena lander senza WebGL (Chromium senza GPU)', () => {
  defineLanderCore('canvas2d');

  test('etichetta della modalita compatibile, nessun comando 3D, sezione con tutte le etichette', async ({ page }) => {
    await openLander(page, 'canvas2d');
    await expect(page.getByTestId('lander-mode')).toContainText('senza WebGL');
    await expect(page.getByRole('button', { name: 'Ruota a destra' })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Sezione laterale' })).toHaveCount(0);
    const p = await pixels(page);
    expect(p.lit / p.total).toBeGreaterThan(0.1);
    // il canvas e' nascosto agli assistivi: il gruppo porta il nome e il testo e' nella scheda
    await expect(page.locator('#lander-stage')).toHaveAttribute('aria-roledescription', 'sezione');
    await page.getByRole('tab', { name: 'Descrizione testuale' }).click();
    await expect(page.getByTestId('lander-text')).toContainText('prima zona di Fresnel');
  });
});
