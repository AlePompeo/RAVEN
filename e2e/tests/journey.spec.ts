// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
const appOrigin = `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? 8001}`;

test('hub, scenario e cronologia collegano le viste esistenti', async ({ page }) => {
  await page.goto('/?site=haworth&t=2026-01-01T12%3A00%3A00Z&station=dsn18&gain=12&rate=100000&k=2');
  await page.getByRole('main').getByRole('link', { name: 'Inizia il Mission Planner' }).click();
  await expect(page).toHaveURL(/\/mission-planner\?/);
  expect(new URL(page.url()).searchParams.get('site')).toBe('haworth');
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeFocused();
  const main = page.getByRole('main');
  for (const [name, path] of [['Simula la scena', '/simula'], ['Simula l’onda', '/simula'], ['Analizza il link budget', '/analizza'], ['Analizza i siti in 3D', '/siti']] as const) {
    const url = new URL((await main.getByRole('link', { name, exact: true }).getAttribute('href'))!, page.url());
    expect(url.pathname).toBe(path);
    expect(url.searchParams.get('site')).toBe('haworth');
    expect(url.searchParams.get('station')).toBe('dsn18');
  }
  const wave = new URL((await main.getByRole('link', { name: 'Simula l’onda' }).getAttribute('href'))!, page.url());
  expect(wave.searchParams.get('tab')).toBe('onda');
  expect(wave.searchParams.get('t')).toBe('2026-01-01T12:00:00Z');
  await main.getByRole('link', { name: 'Simula l’onda' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Simula – Onda 3D' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' })).toHaveAttribute('aria-current', 'page');
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { level: 1, name: 'Simula – Onda 3D' })).toBeVisible();
});

test('Learn replaces tool cards with one progressive lesson and a knowledge check', async ({ page }) => {
  await page.goto('/learn?site=haworth');
  const main = page.getByRole('main');
  const practice = new URL((await main.getByRole('link', { name: 'Apri il passo corrispondente del Planner' }).getAttribute('href'))!, page.url());
  expect(practice.pathname).toBe('/mission-planner');
  expect(practice.searchParams.get('site')).toBe('haworth');
  expect(practice.searchParams.get('mp_step')).toBe('mission');
  await expect(main.locator('.cards')).toHaveCount(0);
  await expect(main.getByRole('heading', { name: "Missione: definisci l'obiettivo" })).toBeVisible();
  await expect(main.getByRole('radio')).toHaveCount(3);
  await expect(page.getByTestId('learn-lessons').locator('nav button')).toHaveCount(15);
});

test('pagine interne scure e titolo display, senza modificare il tema della home', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/mission-planner');
  const intro = page.locator('.step-heading h2');
  await expect(intro).toBeVisible();
  await expect(intro).toHaveCSS('color', 'rgb(245, 245, 247)');
  await expect(page.locator('.journey-header h1')).toHaveCSS('font-family', /Orbitron/);
  await expect.poll(() => page.evaluate(() => document.fonts.check('16px Orbitron'))).toBe(true);
  await page.locator('.brand').click();
  await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
  await expect(page.locator('main')).not.toHaveClass(/interior/);
});

for (const path of ['/explore', '/learn']) {
  test(`${path}: accessibile e senza overflow su mobile`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });
}

test('Learn: knowledge checks gate progression, explain evidence and keep the scenario', async ({ page }) => {
  await page.goto('/learn?site=haworth');
  const lessons = page.getByTestId('learn-lessons');
  await expect(lessons.getByRole('button', { name: 'Lezione successiva' })).toBeDisabled();
  await lessons.getByRole('radio', { name: 'Aumenta automaticamente la potenza del trasmettitore.' }).check();
  await lessons.getByRole('button', { name: 'Verifica la risposta' }).click();
  await expect(lessons.getByText(/Non ancora/)).toBeVisible();
  await expect(lessons.getByRole('button', { name: 'Lezione successiva' })).toBeDisabled();
  for (const answer of [
    'Cambia il requisito con cui valutare il risultato.',
    'No, il bordo richiede una propria posizione e analisi del terreno.',
    'Un passo più breve, entro il limite dei punti.',
    '200 Wh.',
    'Un progetto compatibile di puntamento e montaggio.',
    'Come stato della batteria ignoto.',
    'Requisiti, ipotesi, intervalli ignoti ed evidenze.',
    "Un'ipotesi illustrativa, non una misura.",
    "No, occorre confrontare disco e orizzonte del terreno.",
    'Lasciare ignote le quantità che dipendono dal terreno.',
    'No, contano ancora frazione del disco e orientamento.',
    'No, gli stati successivi della batteria restano ignoti.',
    'Riduce il margine di 10 dB.',
    'No, pianificazione e operazioni non sono modellate.',
    'Che quelle ore campionate soddisfano le regole operative del modello.',
  ]) {
    await lessons.getByRole('radio', { name: answer, exact: true }).check();
    await lessons.getByRole('button', { name: 'Verifica la risposta' }).click();
    const nextLesson = lessons.getByRole('button', { name: 'Lezione successiva' });
    if (await nextLesson.count()) await nextLesson.click();
  }
  await expect(lessons.getByRole('heading', { name: 'Percorso di apprendimento completato' })).toBeVisible();
  await expect(lessons.getByRole('link', { name: 'Metti in pratica le lezioni' })).toHaveAttribute('href', '/mission-planner?site=haworth');
});

test('Learn: English lessons remain accessible on mobile under the app prefix', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appOrigin}/app/learn?lang=en&site=haworth`);
  const lessons = page.getByTestId('learn-lessons');
  await expect(lessons.getByRole('heading', { name: 'Lunar planning, step by step' })).toBeVisible();
  const practice = new URL((await lessons.getByRole('link', { name: 'Open the corresponding Planner step' }).getAttribute('href'))!, page.url());
  expect(practice.pathname).toBe('/app/mission-planner');
  expect(practice.searchParams.get('site')).toBe('haworth');
  expect(practice.searchParams.get('mp_step')).toBe('mission');
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const base of ['', `${appOrigin}/app`]) {
  test(`educational library, antenna guide, disclosure and pricing ${base || 'root'}`, async ({ page }) => {
    await page.goto(`${base}/mission-planner?mp_step=sites`);
    const library = page.getByTestId('planner-sites-library');
    await library.locator('summary').click();
    const catalogue = ((await (await page.request.get('/api/raven/sites')).json()) as { sites: unknown[] }).sites.length;
    await expect(library.locator('article')).toHaveCount(catalogue); // one card per catalogue site
    await expect(library).toContainText('Le descrizioni non dipendono da date, batteria o risultati radio');
    await expect(library).toContainText('Fondo e bordo di un cratere hanno orizzonti diversi');
    await expect(library).not.toContainText('Energia generata');
    await page.goto(`${base}/mission-planner?mp_step=radio`);
    await expect(page.getByRole('heading', { name: 'Comunicazioni', exact: true })).toBeVisible();
    await expect(page.getByTestId('antenna-guide')).toHaveCount(0);
    await page.goto(`${base}/explore`);
    await expect(page.locator('.cards > li')).toHaveCount(4);
    await expect(page.getByRole('heading', { name: 'Link budget', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Analisi 3D dei siti', exact: true })).toBeVisible();
    await expect(page.locator('main a[href*="/laboratorio"]')).toHaveCount(0);
    await expect(page.getByTestId('antenna-guide')).toHaveCount(0);
    await page.getByRole('main').getByRole('link', { name: 'Analizza il link budget', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Link budget', level: 1, exact: true })).toBeVisible();
    const antenna = page.getByTestId('antenna-guide');
    await antenna.locator('summary').click();
    await expect(antenna).toContainText('guadagno');
    await expect(antenna).toContainText('puntamento');
    await page.goto(`${base}/analizza?lang=en`);
    await expect(page.getByTestId('antenna-guide').locator('summary')).toHaveText('Which antenna should a mission use?');
    await page.goto(`${base}/about?lang=en`);
    await expect(page.locator('main')).toContainText('Not affiliated with NASA.');
    await expect(page.locator('main')).toContainText('governments of Russia or China');
    await expect(page.locator('#transparency')).toContainText('RAVEN adopts it voluntarily');
    await expect(page.locator('#transparency')).toContainText('GitHub Copilot');
    await expect(page.locator('#references dl dt')).toHaveCount(14);
    await expect(page.locator('main')).not.toContainText('From GrazingLink to RAVEN');
    await expect(page.locator('a[href*="/roadmap"]')).toHaveCount(0);
    await page.goto(`${base}/pricing?lang=it`);
    await expect(page.locator('.plan').filter({ has: page.getByRole('heading', { name: 'Enterprise', exact: true }) }).locator('.price')).toHaveText('Chiedi un preventivo');
  });
}
