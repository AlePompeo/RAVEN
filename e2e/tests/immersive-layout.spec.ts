// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const scenes = [
  { name: 'Scena', url: '/simula?tab=scena', stage: '[data-testid="sim-stage"]', controls: '.stage-frame .hud' },
  { name: 'Onda', url: '/simula?tab=onda', stage: '#wave-stage', controls: '.figure .hud' },
  { name: 'Sito nel tempo', url: '/simula?tab=sito', stage: '#lander-stage', controls: '.stage-frame .hud' },
  { name: 'Globo e classifica', url: '/siti', stage: '#viewer-stage', controls: '.stage-wrap .hud-tools' },
];

test('Navigazione delle scene compatta su desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/simula?scene=site');
  await expect(page.locator('#lander-stage canvas')).toHaveCount(1, { timeout: 20_000 });
  const bar = page.locator('.subnav');
  const title = await bar.getByRole('heading', { level: 1 }).boundingBox();
  const tabs = await bar.getByRole('tablist', { name: 'Viste della simulazione' }).boundingBox();
  const choices = await bar.getByRole('group', { name: 'Scenario della scena' }).boundingBox();
  expect(title).not.toBeNull();
  expect(tabs).not.toBeNull();
  expect(choices).not.toBeNull();
  expect(Math.abs(title!.y + title!.height / 2 - (tabs!.y + tabs!.height / 2))).toBeLessThan(3);
  expect(Math.abs(title!.y + title!.height / 2 - (choices!.y + choices!.height / 2))).toBeLessThan(3);
  expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(64);
  expect(await bar.locator('.subnav-tools').evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
});

test('Navigazione delle scene compatta e utilizzabile su mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/simula?scene=site');
  await expect(page.locator('#lander-stage canvas')).toHaveCount(1, { timeout: 20_000 });
  const bar = page.locator('.subnav');
  expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(110);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const analysis = bar.getByRole('button', { name: 'Analisi radio interattiva' });
  await analysis.focus();
  await expect(analysis).toBeInViewport();
  expect((await analysis.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('simula')).toHaveAttribute('data-real', '1');
  await bar.getByRole('tab', { name: 'L’onda' }).click();
  await expect(page.locator('#wave-stage canvas')).toHaveCount(1, { timeout: 20_000 });
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  for (const scene of scenes) {
    test(`${scene.name}: pannello richiudibile (${viewport.width}px)`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(scene.url);
      const stage = page.locator(scene.stage);
      const panel = page.locator('.scene-controls');
      const toggle = panel.getByRole('button', { name: 'Controlli e impostazioni' });
      await expect(stage.locator('canvas')).toHaveCount(1, { timeout: 20_000 });
      if (viewport.width < 900) await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      else await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      const box = (await stage.boundingBox())!;
      const floating = (await page.locator(scene.controls).boundingBox())!;
      expect(box.height).toBeGreaterThanOrEqual(320);
      expect(box.height).toBeGreaterThan(viewport.height * 0.60);
      expect(box.height).toBeLessThan(viewport.height * 0.75);
      expect(floating.y).toBeGreaterThanOrEqual(box.y);
      expect(floating.y + floating.height).toBeLessThanOrEqual(box.y + box.height + 1);
      if (viewport.width >= 900) {
        const side = (await panel.boundingBox())!;
        expect(side.x).toBeGreaterThanOrEqual(box.x + box.width);
        expect(side.width).toBeGreaterThan(320);
        expect(side.width).toBeLessThanOrEqual(368);
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        await expect.poll(async () => (await stage.boundingBox())!.width).toBeGreaterThan(box.width);
        const layout = (await page.locator('.scene-layout').boundingBox())!;
        await expect.poll(async () => Math.abs((await stage.boundingBox())!.width - layout.width)).toBeLessThan(2);
      }
      await toggle.focus();
      await page.keyboard.press('Enter');
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      if (viewport.width < 900) {
        const side = (await panel.boundingBox())!;
        expect(side.x + side.width).toBeLessThanOrEqual(box.x + box.width + 1);
        expect(side.x).toBeGreaterThan(box.x);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    });
  }
}

test('Scena unificata: scelta e vecchi collegamenti conservano sito e ora', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/lander?site=shackleton&t=2027-04-07T00:00:00Z&gain=18');
  await expect(page.locator('#lander-stage canvas')).toHaveCount(1, { timeout: 20_000 });
  await expect(page.getByRole('button', { name: 'Sito reale nel tempo' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#l-site')).toHaveValue('shackleton');
  await expect(page.getByRole('tab', { name: 'Sito nel tempo' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Scenario didattico', exact: true }).click();
  await expect(page.getByTestId('sim-stage')).toBeVisible();
  await page.getByRole('button', { name: 'Sito reale nel tempo' }).click();
  await expect(page.locator('#l-site')).toHaveValue('shackleton');
  await expect(page).toHaveURL(/scene=site/);
  await page.reload();
  await expect(page.locator('#lander-stage canvas')).toHaveCount(1, { timeout: 20_000 });
  await expect(page.locator('#l-site')).toHaveValue('shackleton');
  await expect(page).toHaveURL(/t=2027-04-07T00/);
  await page.getByRole('button', { name: 'Analisi radio interattiva' }).click();
  await expect(page.getByTestId('simula')).toHaveAttribute('data-real', '1');
  await expect(page.getByTestId('sim-site')).toHaveValue('shackleton');
  await expect(page.getByTestId('ctl-hours')).toBeVisible();
  await page.locator('#sim-hours').fill('2');
  await expect.poll(() => page.evaluate(() => new URLSearchParams(location.search).get('t'))).toBe('2027-04-07T02:00:00Z');
  await page.getByRole('button', { name: 'Tempo e illuminazione' }).click();
  await expect(page.locator('#l-gain')).toHaveValue('18');
  await expect(page.locator('#sky-time')).toHaveValue('02:00:00');
  await page.getByRole('button', { name: 'Analisi radio interattiva' }).click();
  await page.reload();
  await expect(page.getByTestId('simula')).toHaveAttribute('data-real', '1');
  await page.goto('/simula?real=1&site=shackleton&t=2027-04-07T00:00:00Z&dia=0.5');
  await expect(page.getByTestId('simula')).toHaveAttribute('data-real', '1');
  await expect(page.getByTestId('ctl-dia-num')).toHaveValue('0.5');
  await page.getByRole('button', { name: 'Tempo e illuminazione' }).click();
  await page.getByRole('button', { name: 'Analisi radio interattiva' }).click();
  await expect(page.getByTestId('ctl-dia-num')).toHaveValue('0.5');
});

for (const url of ['/siti?tab=globo', '/siti?tab=classifica', '/viewer', '/compare']) {
  test(`Siti unificati: ${url}`, async ({ page }) => {
    await page.goto(url);
    await expect(page.getByTestId('siti-combined')).toBeVisible();
    await expect(page.locator('#viewer-stage canvas')).toHaveCount(1, { timeout: 20_000 });
    await expect(page.locator('.ranking')).toBeVisible();
    await expect(page.getByRole('tablist', { name: 'Viste dei siti' })).toHaveCount(0);
  });
}

test('Globo: controlli accessibili anche a schermo intero', async ({ page }) => {
  await page.goto('/siti');
  const fullscreen = page.getByRole('button', { name: 'Schermo intero', exact: true });
  await fullscreen.click();
  await expect(page.getByRole('button', { name: 'Esci da schermo intero' })).toBeVisible();
  const left = page.getByRole('button', { name: 'Ruota a sinistra' });
  await left.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('button', { name: 'Ruota a destra' })).toBeFocused();
  await page.getByRole('button', { name: 'Esci da schermo intero' }).click();
  await expect(fullscreen).toBeVisible();
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`Globo: ora sotto e comandi a sinistra (${viewport.width}px)`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/siti?t=2027-04-07T00:00:00Z');
    await expect(page.locator('#viewer-stage canvas')).toHaveCount(1, { timeout: 20_000 });
    const drawer = page.getByRole('button', { name: 'Controlli e impostazioni' });
    if (await drawer.getAttribute('aria-expanded') === 'true') await drawer.click();
    const stage = page.locator('.stage-wrap');
    const stageBox = (await stage.boundingBox())!;
    const timeBox = (await page.getByTestId('sky-time').boundingBox())!;
    expect(timeBox.y).toBeGreaterThanOrEqual(stageBox.y + stageBox.height);
    await expect(page.locator('.hud-bar .live-pill')).toBeVisible();
    await expect(page.getByLabel('Data', { exact: true })).toBeVisible();
    const zoomIn = (await stage.getByRole('button', { name: 'Ingrandisci' }).boundingBox())!;
    const zoomOut = (await stage.getByRole('button', { name: 'Riduci' }).boundingBox())!;
    expect(zoomIn.x).toBeGreaterThanOrEqual(stageBox.x);
    expect(zoomIn.x + zoomIn.width).toBeLessThan(stageBox.x + stageBox.width / 2);
    expect(Math.abs(zoomIn.x - zoomOut.x)).toBeLessThan(1);
    expect(zoomOut.y).toBeGreaterThanOrEqual(zoomIn.y + zoomIn.height);
    await expect(page.getByRole('toolbar', { name: 'Controlli della vista' })).toHaveAttribute('aria-orientation', 'vertical');
    await page.getByRole('button', { name: 'Un’ora avanti' }).click();
    await expect(page.getByLabel('Ora UTC')).toHaveValue('01:00:00');
    await expect(drawer).toHaveAttribute('aria-expanded', 'false');
  });
}

for (const scene of [scenes[0]!, scenes[3]!]) {
  test(`${scene.name}: pannello mobile aperto accessibile`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(scene.url);
    await expect(page.locator(`${scene.stage} canvas`)).toHaveCount(1, { timeout: 20_000 });
    await page.getByRole('button', { name: 'Controlli e impostazioni' }).click();
    const report = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    expect(report.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
  });
}
