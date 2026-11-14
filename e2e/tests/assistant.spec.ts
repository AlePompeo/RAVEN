// SPDX-License-Identifier: Apache-2.0
// Learning Assistant contro il backend REALE (provider estrattivo, base di conoscenza del repository).
// Nessun LLM reale: modalità llm, interruzioni a metà e limiti del provider NON sono coperti qui.
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = 'test-results/ui/assistant';
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const Q_FSPL = 'Come si calcola la perdita di spazio libero?';

mkdirSync(OUT, { recursive: true });
test.use({ viewport: { width: 1440, height: 900 } });

async function ask(page: Page, q: string) {
  await page.getByLabel('La tua domanda').fill(q);
  await page.getByRole('button', { name: 'Invia' }).click();
}
const status = (page: Page) => page.getByTestId('assistant-status');

test.describe('chat: risposte dal materiale del sito', () => {
  test('la risposta arriva in streaming, con chip di citazione, Fonti e pannello della formula fspl', async ({ page }) => {
    await page.goto('/chat');
    await expect(page.getByRole('heading', { level: 1, name: 'RAVEN SI', exact: true })).toBeVisible();
    await expect(page.getByTestId('assistant-mode')).toHaveText('Risposte dal materiale del sito');
    await expect(page.getByText(/provider esterno configurato/i)).toHaveCount(0);
    // domande di partenza dal backend
    await expect(page.getByRole('list', { name: 'Domande suggerite' }).getByRole('button').first()).toBeVisible();

    const reply = page.waitForResponse((r) => r.url().endsWith('/api/assistant/chat') && r.request().method() === 'POST');
    await ask(page, Q_FSPL);
    const res = await reply;
    expect(res.headers()['content-type']).toContain('text/event-stream');
    // annuncio unico a fine risposta, mai i token
    await expect(status(page)).toHaveText(/^Risposta pronta, \d+ font/, { timeout: 15_000 });
    await expect(page.getByLabel('La tua domanda')).toHaveValue('');

    const history = page.getByRole('list', { name: 'Conversazione' });
    await expect(history.locator(':scope > li').first()).toContainText(Q_FSPL);
    await expect(history.getByText('Formula', { exact: true })).toBeVisible(); // formula in blocco monospace
    await expect(history.getByRole('region', { name: 'Variabili della formula' })).toBeVisible();
    const chips = history.getByRole('button', { name: /^Fonte fspl:/ });
    await expect(chips.first()).toBeVisible();
    await expect(history.getByRole('region', { name: 'Fonti' }).getByRole('button').first()).toBeVisible();
    await expect(history.getByRole('list', { name: 'Domande di approfondimento' })).toBeVisible();

    // nessun marcatore [fspl] grezzo e nessun link generato dal testo
    await expect(history.locator('a')).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/chat-answer-1440.png` });

    // pannello fonte: tabella delle variabili, formula, esempio svolto; focus gestito
    const chip = chips.first();
    await chip.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: /Perdita nello spazio libero/ });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('FSPL_dB = 92.45 + 20*log10(d_km) + 20*log10(f_GHz)')).toBeVisible();
    const table = dialog.getByRole('table').first();
    await expect(table.getByRole('columnheader', { name: 'Unità' })).toBeVisible();
    await expect(table.getByRole('cell', { name: 'km', exact: true })).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'Esempio svolto' })).toBeVisible();
    await expect(dialog.getByRole('cell', { name: '210.994' })).toBeVisible();
    await expect(dialog.getByText(/Verificata il/)).toBeVisible();
    await expect(page.locator('main')).toHaveAttribute('inert', '');
    await expect(dialog.getByRole('button', { name: /Chiudi/ })).toBeFocused();
    await page.screenshot({ path: `${OUT}/chat-source-panel-1440.png` });
    // il focus non esce dal pannello
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'))).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(chip).toBeFocused();
    await expect(page.locator('main')).not.toHaveAttribute('inert', '');

    // nulla di ciò che si è scritto finisce nell'archiviazione del browser
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
    expect(stored).not.toContain('spazio libero');
  });

  test('domanda fuori dal materiale: scheda di rifiuto calma, nessuna fonte', async ({ page }) => {
    await page.goto('/chat');
    await ask(page, 'Qual è la ricetta della carbonara?');
    const card = page.getByTestId('refusal');
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText('Non è nel materiale del sito');
    await expect(card).toContainText('Prova a chiedere');
    await expect(page.getByRole('region', { name: 'Fonti' })).toHaveCount(0);
    await expect(status(page)).toHaveText(/non è nel materiale/);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/chat-refusal-1440.png` });
  });

  test('domanda di approfondimento, livello tecnico e nuova conversazione', async ({ page }) => {
    await page.goto('/chat');
    await page.getByLabel('Impostazioni della conversazione').click();
    await page.getByLabel('Livello della spiegazione').selectOption('tecnico');
    const body = page.waitForRequest((r) => r.url().endsWith('/api/assistant/chat'));
    await ask(page, Q_FSPL);
    expect((await body).postDataJSON()).toMatchObject({ level: 'tecnico', page_context: { page_id: 'chat' } });
    await expect(status(page)).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    const follow = page.getByRole('list', { name: 'Domande di approfondimento' }).getByRole('button').first();
    await follow.click();
    await expect(page.getByRole('list', { name: 'Conversazione' }).locator(':scope > li')).toHaveCount(4, { timeout: 15_000 });
    await page.getByRole('button', { name: 'Nuova conversazione' }).click();
    await expect(page.getByRole('list', { name: 'Conversazione' }).locator(':scope > li')).toHaveCount(0);
    await expect(page.getByLabel('La tua domanda')).toBeFocused();
  });
});

test('RAVEN SI English chat and source controls use the selected language', async ({ page }) => {
  await page.goto('/chat?lang=en');
  await expect(page.getByRole('heading', { name: 'RAVEN SI', level: 1, exact: true })).toBeVisible();
  await page.getByLabel('Your question').fill('How is free space path loss calculated?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(status(page)).toHaveText(/^Answer ready/, { timeout: 15_000 });
  await page.getByRole('region', { name: 'Sources', exact: true }).getByRole('button').first().click();
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Close source panel' })).toBeVisible();
});

test.describe('chat: backend non disponibile', () => {
  test('backend irraggiungibile: lo dice, spiega cosa fare e non nasconde l’avviso di privacy', async ({ page }) => {
    await page.route('**/api/assistant/**', (r) => r.abort('connectionrefused'));
    await page.goto('/chat');
    await expect(page.getByTestId('assistant-unreachable')).toContainText('Controlla la connessione');
    await expect(page.getByText(/provider esterno configurato/i)).toBeVisible(); // fail closed
    await ask(page, 'ciao');
    await expect(page.getByRole('alert')).toContainText('Controlla la connessione');
    await expect(page.getByLabel('La tua domanda')).toHaveValue('ciao'); // il testo non si perde
  });

  test('errore 503 sulla chat: un solo messaggio con cosa fare', async ({ page }) => {
    await page.route('**/api/assistant/chat', (r) => r.fulfill({ status: 503, body: 'x' }));
    await page.goto('/chat');
    await ask(page, 'ciao');
    await expect(page.getByRole('alert')).toHaveCount(1);
    await expect(page.getByRole('alert')).toContainText('Riprova');
    await expect(page.getByLabel('La tua domanda')).toHaveValue('ciao');
  });

  test('fonte non più presente: il pannello lo dice onestamente', async ({ page }) => {
    await page.goto('/chat');
    await ask(page, Q_FSPL);
    await expect(status(page)).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    await page.route('**/api/assistant/knowledge/**', (r) => r.fulfill({ status: 404, body: '{}' }));
    await page.getByRole('region', { name: 'Fonti' }).getByRole('button').first().click();
    await expect(page.getByRole('dialog').getByRole('alert')).toContainText('non è più nel materiale');
    await page.keyboard.press('Escape');
  });
});

test.describe('RAVEN SI', () => {
  test('su /sims invia page_context con simulazione, valori e ultimo risultato', async ({ page }) => {
    await page.goto('/sims');
    await expect(page.getByLabel('Simulazione')).toBeVisible();
    await page.getByLabel('Simulazione').selectOption('fspl-c');
    await page.getByLabel('Nome ingresso 1').fill('distance_km');
    await page.getByLabel('Valore 1').fill('384400');
    await page.getByRole('button', { name: 'Aggiungi ingresso' }).click();
    await page.getByLabel('Nome ingresso 2').fill('freq_ghz');
    await page.getByLabel('Valore 2').fill('2.2');
    await page.getByRole('button', { name: 'Esegui' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Simulazione completata.' })).toBeVisible();

    const bodies: unknown[] = [];
    await page.route('**/api/assistant/chat', async (route) => {
      bodies.push(route.request().postDataJSON());
      await route.continue();
    });
    const btn = page.getByRole('button', { name: 'RAVEN SI', exact: true });
    await btn.click();
    const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(sheet).toBeVisible();
    await sheet.getByLabel('Impostazioni della conversazione').click();
    await sheet.getByRole('checkbox', { name: 'Includi i parametri tecnici visibili' }).check();
    await expect(sheet.getByTestId('explain-context')).toContainText('distance_km = 384400');
    const suggestions = sheet.getByRole('list', { name: 'Domande suggerite' }).getByRole('button');
    await expect(suggestions.first()).toBeVisible();
    await sheet.getByLabel('La tua domanda').fill('Come si legge questo risultato?');
    await sheet.getByRole('button', { name: 'Invia' }).click();
    await expect(sheet.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });

    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({
      messages: [{ role: 'user', content: 'Come si legge questo risultato?' }],
      page_context: { page_id: 'sims', simulation_id: 'fspl-c', params: { distance_km: 384400, freq_ghz: 2.2 } },
    });
    const ctx = (bodies[0] as { page_context: { params: Record<string, number> } }).page_context.params;
    expect(Object.keys(ctx).some((k) => k.startsWith('risultato_'))).toBe(true);
    await page.screenshot({ path: `${OUT}/sims-explain-sheet-1440.png` });

    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    await expect(btn).toBeFocused();
  });

  test('su /viewer invia il corpo selezionato', async ({ page }) => {
    await page.goto('/viewer?body=earth');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const req = page.waitForRequest((r) => r.url().endsWith('/api/assistant/chat'));
    await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
    await page.getByLabel('Impostazioni della conversazione').click();
    await page.getByRole('checkbox', { name: 'Includi i parametri tecnici visibili' }).check();
    await page.getByLabel('La tua domanda').fill('Che cosa vedo?');
    await page.getByRole('button', { name: 'Invia' }).click();
    const ctx = (await req).postDataJSON().page_context;
    expect(ctx.page_id).toBe('siti'); // /viewer porta a Siti (scheda Globo)
    expect(ctx.params.body).toBeTruthy();
  });

  test('resta disponibile su /chat e altrove senza spostare il layout (CLS)', async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __cls: number }).__cls = 0;
      new PerformanceObserver((l) => {
        for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) (window as unknown as { __cls: number }).__cls += e.value;
      }).observe({ type: 'layout-shift', buffered: true });
    });
    await page.goto('/chat');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('button', { name: 'RAVEN SI', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
    await expect(page.getByLabel('La tua domanda')).toBeFocused();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore' }).click();
    await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible();
    const btn = page.getByRole('button', { name: 'RAVEN SI', exact: true });
    await expect(btn).toBeVisible();
    await expect(btn.locator('..')).toHaveCSS('position', 'fixed'); // fuori dal flusso: non sposta nulla
    const box = await btn.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(43.5);
    expect(await page.evaluate(() => (window as unknown as { __cls: number }).__cls)).toBeLessThan(0.1);
    // nav intatta
    await expect(page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Learn' })).toBeVisible();
  });

  test('scorciatoie: Alt+A apre; "?" solo se attivato nel foglio e mai mentre si scrive', async ({ page }) => {
    await page.goto('/telemetry');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.keyboard.press('?');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.keyboard.press('Alt+A');
    const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(sheet).toBeVisible();
    await sheet.getByLabel('Impostazioni della conversazione').click();
    await sheet.getByRole('checkbox', { name: 'Apri anche con il tasto ?' }).check();
    await expect(sheet.getByRole('checkbox', { name: 'Apri anche con il tasto ?' })).toBeChecked();
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    await page.keyboard.press('?');
    await expect(sheet).toBeVisible();
    // nel campo di testo il punto interrogativo si scrive e basta
    await sheet.getByLabel('La tua domanda').fill('');
    await sheet.getByLabel('La tua domanda').press('?');
    await expect(sheet.getByLabel('La tua domanda')).toHaveValue('?');
  });

  test('telefono: il foglio sale dal basso, senza overflow, bersagli >= 44px', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, reducedMotion: 'reduce', locale: 'it-IT' });
    const page = await ctx.newPage();
    await page.addInitScript(() => localStorage.setItem('hb.lang', 'it'));
    await page.goto('/sims');
    await expect(page.getByLabel('Simulazione')).toBeVisible();
    await page.getByRole('button', { name: 'RAVEN SI', exact: true }).tap();
    const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(sheet).toBeVisible();
    const box = (await sheet.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(389);
    expect(box.y + box.height).toBeGreaterThanOrEqual(843);
    expect(box.y).toBeLessThanOrEqual(1);
    await expect(sheet.getByLabel('La tua domanda')).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    const small = await sheet.locator('button, input, a[href]').evaluateAll((els) =>
      els.filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && !(e as HTMLInputElement).type?.match(/checkbox/) && Math.min(r.width, r.height) < 43.5; }).map((e) => e.textContent?.trim()),
    );
    expect(small).toEqual([]);
    await page.screenshot({ path: `${OUT}/sims-explain-sheet-390.png` });
    await ctx.close();
  });
});

for (const base of ['', `http://127.0.0.1:${process.env.E2E_PROXY_PORT ?? '8001'}/app`]) {
  test(`RAVEN SI conserva la conversazione tra minimizzazione e pagine ${base ? '/app/' : 'root'}`, async ({ page }) => {
    await page.goto(`${base}/learn`);
    const launcher = page.getByTestId('raven-si-launcher');
    await launcher.click();
    const dialog = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
    await expect(dialog.getByRole('checkbox', { name: 'Usa la SI online' })).toBeDisabled();
    await dialog.getByLabel('La tua domanda').fill(Q_FSPL);
    await dialog.getByRole('button', { name: 'Invia', exact: true }).click();
    await expect(dialog.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    await dialog.getByRole('button', { name: 'Riduci RAVEN SI' }).click();
    await expect(launcher).toBeFocused();
    await page.getByRole('navigation', { name: 'Principale' }).getByRole('link', { name: 'Explore', exact: true }).click();
    await launcher.click();
    await expect(dialog.getByRole('list', { name: 'Conversazione' })).toContainText(Q_FSPL);
    await page.emulateMedia({ media: 'print' });
    await expect(launcher).toBeHidden();
    await expect(dialog).toBeHidden();
    await page.emulateMedia({ media: 'screen' });
    await page.locator('.overlay > .scrim').click({ position: { x: 2, y: 2 } });
    await expect(dialog).toHaveCount(0);
    await expect(launcher).toBeFocused();
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
    expect(stored).not.toContain(Q_FSPL);
    await page.reload();
    await launcher.click();
    await expect(dialog.getByRole('list', { name: 'Conversazione' }).locator(':scope > li')).toHaveCount(0);
  });
}

test.describe('chat su telefono', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test('risposta, pannello fonte come foglio dal basso', async ({ page }) => {
    await page.goto('/chat');
    await ask(page, Q_FSPL);
    await expect(status(page)).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `${OUT}/chat-answer-390.png` });
    await page.getByRole('region', { name: 'Fonti' }).getByRole('button').first().tap();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/^FSPL_dB =/)).toBeVisible();
    const box = (await dialog.locator('.panel-wrap').boundingBox())!;
    expect(box.y + box.height).toBeGreaterThanOrEqual(843);
    expect(box.y).toBeGreaterThan(50);
    await page.screenshot({ path: `${OUT}/chat-source-panel-390.png` });
  });
});

for (const scheme of ['dark', 'light'] as const) {
  test.describe(`axe ${scheme}`, () => {
    test.use({ colorScheme: scheme, reducedMotion: 'reduce' }); // axe non misura il contrasto a metà di una dissolvenza
    const axe = async (page: Page, label: string) => {
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) })), label).toEqual([]);
    };
    test('chat con risposta, pannello fonte e foglio Spiega', async ({ page }) => {
      await page.goto('/chat');
      await ask(page, Q_FSPL);
      await expect(status(page)).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
      await axe(page, `chat con risposta ${scheme}`);
      await page.getByRole('region', { name: 'Fonti' }).getByRole('button').first().click();
      await expect(page.getByRole('dialog').getByText(/^FSPL_dB =/)).toBeVisible();
      await axe(page, `pannello fonte ${scheme}`);
      await page.screenshot({ path: `${OUT}/chat-source-panel-${scheme}.png` });
      await page.keyboard.press('Escape');

      await page.goto('/chat');
      await ask(page, 'ricetta carbonara');
      await expect(page.getByTestId('refusal')).toBeVisible({ timeout: 15_000 });
      await axe(page, `rifiuto ${scheme}`);

      await page.goto('/sims');
      await expect(page.getByLabel('Simulazione')).toBeVisible();
      await page.getByRole('button', { name: 'RAVEN SI', exact: true }).click();
      const sheet = page.getByRole('dialog', { name: 'RAVEN SI', exact: true });
      await expect(sheet.getByRole('list', { name: 'Domande suggerite' })).toBeVisible();
      await axe(page, `foglio Spiega ${scheme}`);
      await sheet.getByRole('list', { name: 'Domande suggerite' }).getByRole('button').first().click();
      await expect(sheet.getByTestId('assistant-status')).toHaveText(/^Risposta pronta/, { timeout: 15_000 });
      await axe(page, `foglio Spiega con risposta ${scheme}`);
      await page.screenshot({ path: `${OUT}/sims-explain-answer-${scheme}.png` });
    });
  });
}
