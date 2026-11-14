// SPDX-License-Identifier: Apache-2.0
// Onda 3D in Chromium SENZA WebGL (nessuna GPU): deve mostrare una vera superficie con il renderer Canvas 2D.
import { test, expect } from '@playwright/test';
import { defineWaveCore } from './waveSuite';
import { openWave } from './waveHelpers';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

test.describe('onda 3D senza WebGL (Chromium senza GPU)', () => {
  defineWaveCore('canvas2d');

  test('etichetta di modalità compatibile e comandi della vista', async ({ page }) => {
    await openWave(page, 'canvas2d');
    await expect(page.getByTestId('wave-mode')).toHaveText('Modalità compatibile (senza WebGL)');
    await page.getByRole('button', { name: 'Ruota a destra' }).click();
    await page.getByRole('button', { name: 'Ingrandisci' }).click();
    await page.getByRole('button', { name: 'Ripristina' }).click();
  });
});
