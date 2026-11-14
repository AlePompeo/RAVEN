// SPDX-License-Identifier: Apache-2.0
// Scelta del corpo celeste nel visualizzatore del ramo lunare (solo Luna e Terra): mouse, tastiera, tocco,
// link diretto, reduced motion, memoria dopo 20 cambi e screenshot di ogni corpo (1440 e 390, con e senza WebGL).
import { test, expect } from '@playwright/test';
import { ready, shootAll } from './viewerHelpers';

test.describe('scelta del corpo celeste', () => {
  test('il selettore ha solo Luna e Terra; Sole e Marte non ci sono', async ({ page }) => {
    await page.goto('/viewer');
    const tabs = page.getByRole('tablist', { name: 'Corpo celeste' });
    await expect(tabs.getByRole('tab')).toHaveCount(2);
    await expect(tabs.getByRole('tab', { name: 'Luna' })).toBeVisible();
    await expect(tabs.getByRole('tab', { name: 'Terra' })).toBeVisible();
    await expect(tabs.getByRole('tab', { name: 'Sole' })).toHaveCount(0);
    await expect(tabs.getByRole('tab', { name: 'Marte' })).toHaveCount(0);
  });

  test('con il mouse: la scheda cambia, il titolo segue, il link si aggiorna', async ({ page }) => {
    await page.goto('/viewer');
    const tabs = page.getByRole('tablist', { name: 'Corpo celeste' });
    await tabs.getByRole('tab', { name: 'Terra' }).click();
    await expect(tabs.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('.hud-h')).toContainText('Terra'); // dentro Siti il titolo del corpo è un h2
    await expect(page).toHaveURL(/body=earth/);
    // la telemetria compare solo con la Luna
    await expect(page.getByText('La telemetria riguarda il sito lunare')).toBeVisible();
    await tabs.getByRole('tab', { name: 'Luna' }).click();
    await expect(page.locator('.hud-h')).toContainText('Luna');
    await expect(page).not.toHaveURL(/body=/);
  });

  test('da tastiera: frecce, Home e Fine spostano la selezione (pattern tablist)', async ({ page }) => {
    await page.goto('/viewer');
    const moon = page.getByRole('tab', { name: 'Luna' });
    await moon.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Terra' })).toBeFocused();
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('ArrowRight'); // si richiude sulla Luna
    await expect(moon).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('End');
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('Home');
    await expect(moon).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('[role=status][aria-live=polite]').last()).toContainText('Luna selezionata');
  });

  test('link diretto e scelta ricordata (localStorage); Sole e Marte tornano alla Luna', async ({ page }) => {
    await page.goto('/viewer?body=earth');
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('tab', { name: 'Luna' }).click();
    await page.getByRole('tab', { name: 'Terra' }).click(); // la scelta viene ricordata
    await page.goto('/viewer');
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await page.goto('/viewer?body=pluto'); // non valido: vale la scelta salvata
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('tab', { name: 'Luna' }).click(); // ora la scelta salvata e' la Luna
    for (const gone of ['mars', 'sun']) {
      await page.goto(`/viewer?body=${gone}`);
      await expect(page.getByRole('tab', { name: 'Luna' })).toHaveAttribute('aria-selected', 'true');
    }
  });

  test('i marcatori sono pulsanti con nome accessibile e portano il luogo al centro', async ({ page }) => {
    await page.goto('/viewer');
    await page.getByRole('button', { name: /^Apollo 11,/ }).click();
    await expect(page.locator('[role=status][aria-live=polite]').last()).toContainText('Apollo 11 al centro', { timeout: 5_000 });
    await expect(page.locator('#scene-description')).toContainText('rotazione orizzontale di -23°');
  });

  test('ricerca e filtri: stato vuoto con indicazione', async ({ page }) => {
    await page.goto('/viewer');
    await page.getByRole('searchbox', { name: 'Cerca un luogo' }).fill('zzz');
    await expect(page.getByText('Nessun luogo corrisponde')).toBeVisible();
    await page.getByRole('searchbox', { name: 'Cerca un luogo' }).fill('');
    await page.getByRole('button', { name: 'Crateri', exact: true }).click();
    await expect(page.locator('.places li')).toHaveCount(2);
  });

  test('memoria: 20 cambi di corpo non accumulano mappe', async ({ page }) => {
    // il verdetto è il contatore di mappe (data-textures), non il tempo: a macchina carica i 20 cambi durano di più
    test.setTimeout(120_000);
    await page.goto('/viewer');
    await ready(page);
    const order = ['earth', 'moon'];
    for (let i = 0; i < 20; i++) {
      await page.locator(`[role=tab][data-body=${order[i % 2]}]`).click();
      await page.waitForTimeout(120);
    }
    await ready(page);
    const n = Number(await page.locator('.stage').getAttribute('data-textures'));
    expect(n).toBeLessThanOrEqual(4); // cielo + colore + rilievo (+ eventuale anteprima)
  });
});

test.describe('tocco', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test('un tocco sulla scheda cambia corpo e il foglio Esplora si apre', async ({ page }) => {
    await page.goto('/viewer');
    await page.getByRole('button', { name: 'Controlli e impostazioni' }).tap();
    await page.getByRole('tab', { name: 'Terra' }).tap();
    await expect(page.getByRole('tab', { name: 'Terra' })).toHaveAttribute('aria-selected', 'true');
    const toggle = page.getByRole('button', { name: /Luoghi e dati di Terra/ });
    await toggle.tap();
    await expect(page.getByRole('button', { name: 'Chiudi' })).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('heading', { name: 'Perché RAVEN' })).toBeVisible();
  });
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });
  test('cambio istantaneo, niente riproduzione della luce', async ({ page }) => {
    await page.goto('/viewer');
    await expect(page.getByRole('button', { name: /ciclo della luce/ })).toHaveCount(0);
    await page.getByRole('tab', { name: 'Terra' }).click();
    await ready(page); // nessuna dissolvenza da attendere
  });
});

test.describe('screenshot dei corpi (WebGL)', () => {
  for (const w of [1440, 390]) {
    test(`${w}px`, async ({ page }) => {
      await shootAll(page, w, 'webgl');
    });
  }
});
