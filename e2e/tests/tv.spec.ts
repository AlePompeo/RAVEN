// SPDX-License-Identifier: Apache-2.0
// Modalità TV: solo frecce, Invio ed Esc (telecomando). Il focus si muove in modo prevedibile
// nav -> CTA del palco -> capitoli -> comandi del visualizzatore; Invio attiva; Esc chiude il foglio.
import { test, expect, type Page } from '@playwright/test';

test.use({ viewport: { width: 1920, height: 1080 }, reducedMotion: 'reduce' });

const focused = (page: Page) => page.evaluate(() => (document.activeElement?.getAttribute('aria-label') ?? document.activeElement?.textContent ?? '').trim());

test('home: frecce nella nav, giù fino alla CTA del palco, poi all’interruttore di modalità, Invio apre', async ({ page }) => {
  await page.goto('/?tv=1');
  await expect(page.locator('html')).toHaveAttribute('data-tv', '1');
  await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Home' }).focus();
  await page.keyboard.press('ArrowRight');
  expect(await focused(page)).toBe('Mission Planner');
  // dalla barra verso il basso: la CTA, prima di tutto il resto (mai il pulsante fluttuante "Spiega")
  await page.keyboard.press('ArrowDown');
  expect(await focused(page)).toBe('Prova tu');
  await page.keyboard.press('ArrowRight');
  expect(await focused(page)).toBe('Come funziona');
  await page.keyboard.press('ArrowLeft');
  expect(await focused(page)).toBe('Prova tu');
  // l'interruttore Learning | Avanzato sta sotto le CTA: raggiungibile con le frecce, Invio sceglie
  await page.keyboard.press('ArrowDown');
  expect(await focused(page)).toBe('Demo guidata');
  await page.keyboard.press('ArrowDown');
  expect(await focused(page)).toBe('Learning');
  await page.keyboard.press('ArrowRight');
  expect(await focused(page)).toBe('Avanzato');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Avanzato' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('link', { name: 'Prova tu' }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/simula/);
});

test('visualizzatore: frecce tra schede e comandi, la scena non ruota per sbaglio', async ({ page }) => {
  await page.goto('/viewer?tv=1');
  await expect(page.locator('.stage[data-ready="1"]')).toHaveCount(1, { timeout: 20_000 });
  const desc = page.locator('#scene-description');
  const before = await desc.textContent();
  await page.getByRole('tab', { name: 'Luna' }).focus();
  await page.keyboard.press('ArrowRight'); // dentro la tablist: cambia corpo
  await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowDown'); // esce dalla tablist verso i comandi
  const f1 = await focused(page);
  expect(f1.length).toBeGreaterThan(0);
  expect(f1).not.toBe('Terra');
  // fino al pulsante "Ruota a destra" con le frecce e Invio: la descrizione cambia
  await page.getByRole('button', { name: 'Ruota a destra' }).focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => desc.textContent()).not.toBe(before);
  // la scena con il focus non mangia le frecce in TV: si esce verso un altro controllo
  await page.locator('.stage').focus();
  const d0 = await desc.textContent();
  await page.keyboard.press('ArrowRight');
  expect(await page.evaluate(() => document.activeElement?.classList.contains('stage'))).toBe(false);
  expect(await desc.textContent()).toBe(d0);
});

test.describe('telefono in modalità TV forzata: Esc chiude il foglio', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('Esc', async ({ page }) => {
    await page.goto('/viewer?tv=0');
    await page.getByRole('button', { name: 'Controlli e impostazioni' }).click();
    const toggle = page.getByRole('button', { name: /Luoghi e dati di Luna/ });
    await toggle.click();
    await expect(page.getByRole('button', { name: 'Chiudi' })).toHaveAttribute('aria-expanded', 'true');
    await page.getByRole('searchbox', { name: 'Cerca un luogo' }).focus();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: /Luoghi e dati di Luna/ })).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByRole('button', { name: /Luoghi e dati di Luna/ })).toBeFocused();
  });
});

test.describe('assistente in modalità TV', () => {
  test('RAVEN SI: nascosto finché il telecomando non lo raggiunge, poi foglio navigabile con le frecce', async ({ page }) => {
    await page.goto('/telemetry?tv=1');
    await expect(page.getByRole('heading', { level: 1, name: 'Telemetria' })).toBeVisible();
    const btn = page.getByRole('button', { name: 'RAVEN SI', exact: true });
    await expect(btn).toHaveCSS('opacity', '0'); // nessun elemento fluttuante a 3 metri
    // raggiungibile con le sole frecce (dal contenuto verso il basso/destra)
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Home' }).focus();
    let reached = false;
    for (let i = 0; i < 40 && !reached; i++) {
      await page.keyboard.press(i % 4 === 3 ? 'ArrowRight' : 'ArrowDown');
      reached = (await focused(page)) === 'RAVEN SI';
    }
    expect(reached, 'il pulsante è raggiungibile con le frecce').toBe(true);
    await expect(btn).toHaveCSS('opacity', '1'); // compare quando ha il focus
    await page.keyboard.press('Enter');
    const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole('list', { name: 'Domande suggerite' })).toBeVisible();
    // le frecce restano dentro il foglio
    for (const k of ['ArrowDown', 'ArrowDown', 'ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft']) {
      await page.keyboard.press(k);
      expect(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')), `dopo ${k}`).toBe(true);
    }
    // tasto Indietro del telecomando = Esc
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'GoBack', bubbles: true, cancelable: true })));
    await expect(sheet).toHaveCount(0);
    await expect(btn).toBeFocused();
  });

  test('chat: invio dal telecomando, chip di citazione e pannello fonte; Indietro chiude e riporta al chip', async ({ page }) => {
    await page.goto('/chat?tv=1');
    await expect(page.getByTestId('assistant-mode')).toHaveText('Risposte dal materiale del sito');
    await expect(page.getByRole('button', { name: 'RAVEN SI', exact: true })).toHaveCSS('opacity', '0'); // on the chat page it only focuses the input, and is not shown on a TV
    const input = page.getByLabel('La tua domanda');
    await input.fill('Come si calcola la perdita di spazio libero?');
    await input.press('Enter');
    await expect(page.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    const chip = page.getByRole('region', { name: 'Fonti' }).getByRole('button').first();
    await chip.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: /Chiudi/ })).toBeFocused();
    for (const k of ['ArrowDown', 'ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight']) {
      await page.keyboard.press(k);
      expect(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')), `dopo ${k}`).toBe(true);
    }
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'GoBack', bubbles: true, cancelable: true })));
    await expect(dialog).toHaveCount(0);
    await expect(chip).toBeFocused();
  });
});
