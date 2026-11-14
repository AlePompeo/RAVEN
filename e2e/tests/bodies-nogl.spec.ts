// SPDX-License-Identifier: Apache-2.0
// Screenshot di ogni corpo con Chromium SENZA WebGL (renderer Canvas 2D software), 1440 e 390 px.
import { test } from '@playwright/test';
import { shootAll } from './viewerHelpers';

test.use({ launchOptions: { args: ['--disable-3d-apis', '--disable-gpu', '--disable-gpu-compositing'] } });

for (const w of [1440, 390]) {
  test(`corpi senza WebGL a ${w}px`, async ({ page }) => {
    await shootAll(page, w, 'nogl');
  });
}
