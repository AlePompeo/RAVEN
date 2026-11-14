// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { PAGES } from './pages';

// archivio vuoto (come un visitatore nuovo): niente hb.mode preimpostato dalla configurazione
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('privacy e consenso', () => {
  test('nessun cookie impostato dopo aver visitato tutte le pagine; nessun Set-Cookie', async ({ page, context }) => {
    const setCookie: string[] = [];
    page.on('response', (r) => {
      const h = r.headers()['set-cookie'];
      if (h) setCookie.push(`${r.url()} -> ${h}`);
    });
    for (const p of PAGES) {
      const res = await page.goto(p.path);
      expect(res!.headers()['set-cookie']).toBeUndefined();
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    }
    await page.request.get('/api/plugins');
    expect(setCookie).toEqual([]);
    expect(await context.cookies()).toEqual([]);
    expect(await page.evaluate(() => document.cookie)).toBe('');
  });

  test('consenso: tutto disattivato di default e nessuna scrittura in localStorage', async ({ page }) => {
    await page.goto('/cookies');
    const boxes = page.getByRole('group', { name: /Preferenze di consenso/ }).getByRole('checkbox');
    await expect(boxes).toHaveCount(2);
    for (const b of await boxes.all()) await expect(b).not.toBeChecked();
    expect(await page.evaluate(() => localStorage.getItem('consent.v1'))).toBeNull();
    expect(await page.evaluate(() => localStorage.length)).toBe(0);
  });

  test('concedere il consenso lo salva in localStorage e lo conserva dopo il ricaricamento', async ({ page }) => {
    await page.goto('/cookies');
    const box = page.getByRole('checkbox', { name: 'Statistiche di utilizzo' });
    await box.check();
    await expect(page.getByRole('status').filter({ hasText: 'Scelta salvata.' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('consent.v1'))).toContain('analytics');
    await page.reload();
    await expect(page.getByRole('checkbox', { name: 'Statistiche di utilizzo' })).toBeChecked();
    await expect(page.getByRole('checkbox', { name: 'Contenuti incorporati di terze parti' })).not.toBeChecked();
  });

  test('localStorage che lancia eccezioni: l\'app funziona, consenso non attivo, messaggio onesto', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.addInitScript(() => {
      const boom = () => {
        throw new DOMException('blocked', 'SecurityError');
      };
      Object.defineProperty(window, 'localStorage', { get: boom, configurable: true });
    });
    await page.goto('/cookies');
    await expect(page.getByRole('heading', { level: 1, name: 'Cookie e archiviazione locale' })).toBeVisible();
    const box = page.getByRole('checkbox', { name: 'Statistiche di utilizzo' });
    await expect(box).not.toBeChecked();
    await box.click();
    await expect(box).not.toBeChecked(); // lo stato mostrato e quello reale: non attivo
    await expect(page.getByRole('status').filter({ hasText: 'Non e stato possibile salvare la scelta' })).toBeVisible();
    // le altre pagine restano utilizzabili
    await page.locator('a.brand').click();
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
