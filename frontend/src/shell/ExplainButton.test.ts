// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import ExplainButton from './ExplainButton.svelte';
import { setPageContext, clearPageContext, explainPrefs, pageIdFor } from './pageContext.svelte';
import { resetConversation } from '../pages/chat/conversation.svelte';

afterEach(() => {
  cleanup();
  resetConversation();
  vi.unstubAllGlobals();
  clearPageContext();
  explainPrefs.questionKey = false;
  document.body.innerHTML = '';
});

const enc = new TextEncoder();
const ev = (n: string, d: unknown) => `event: ${n}\ndata: ${JSON.stringify(d)}\n\n`;
const ANSWER = ev('meta', { provider: 'assistant-extractive', mode: 'extractive', retrieved: ['fspl'], level: 'intermedio', lang: 'it' }) + ev('token', { token: 'Risposta [fspl]' }) + ev('citations', { citations: [{ id: 'fspl', title: 'FSPL', kind: 'formula', anchor: '', url_path: '' }] }) + ev('done', { refused: false, followups: [], chars: 5 });

function stub() {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/assistant/status')) return new Response(JSON.stringify({ provider: 'assistant-extractive', mode: 'extractive' }));
      if (url.startsWith('/api/assistant/suggestions')) return new Response(JSON.stringify({ suggestions: [{ question: 'Cosa fa fspl-c?', doc_id: 'sim-fspl-c' }] }));
      if (url === '/api/assistant/chat') {
        bodies.push(JSON.parse(init!.body as string));
        return new Response(new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc.encode(ANSWER)); c.close(); } }));
      }
      return new Response('', { status: 404 });
    }),
  );
  return bodies;
}

describe('ExplainButton', () => {
  it('apre il foglio, mostra le domande suggerite della pagina e invia page_context con simulazione e valori', async () => {
    const bodies = stub();
    setPageContext({ simulation_id: 'fspl-c', params: { distance_km: 384400, risultato_fspl_db: 210.99 } });
    render(ExplainButton, { pageId: 'sims' });
    const btn = screen.getByRole('button', { name: 'RAVEN SI' });
    expect(btn.getAttribute('aria-keyshortcuts')).toBe('Alt+A');
    await fireEvent.click(btn);
    const dlg = await screen.findByRole('dialog', { name: 'RAVEN SI' });
    expect(dlg).toBeTruthy();
    await fireEvent.click(screen.getByLabelText('Impostazioni della conversazione'));
    await fireEvent.click(screen.getByLabelText('Includi i parametri tecnici visibili'));
    expect(screen.getByTestId('explain-context').textContent).toMatch(/distance_km = 384400/);
    await fireEvent.click(await screen.findByRole('button', { name: 'Cosa fa fspl-c?' }));
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta, 1 fonte.'));
    expect(bodies[0]).toMatchObject({
      messages: [{ role: 'user', content: 'Cosa fa fspl-c?' }],
      page_context: { page_id: 'sims', simulation_id: 'fspl-c', params: { distance_km: 384400, risultato_fspl_db: 210.99 } },
    });
  });

  it('domanda libera senza contesto: solo page_id', async () => {
    const bodies = stub();
    render(ExplainButton, { pageId: 'telemetry' });
    await fireEvent.click(screen.getByRole('button', { name: 'RAVEN SI' }));
    const field = await screen.findByLabelText('La tua domanda');
    await fireEvent.input(field, { target: { value: 'Che grafico è?' } });
    await fireEvent.submit((field as HTMLInputElement).form!);
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect((bodies[0] as { page_context: unknown }).page_context).toEqual({ page_id: 'telemetry' });
  });

  it('mostra tutti e soli i parametri trasmessi nell’anteprima', async () => {
    const bodies = stub();
    const params = Object.fromEntries(Array.from({ length: 17 }, (_, i) => [`valore_${i}`, i]));
    setPageContext({ params });
    render(ExplainButton, { pageId: 'telemetry' });
    await fireEvent.click(screen.getByRole('button', { name: 'RAVEN SI' }));
    await screen.findByTestId('raven-si');
    await fireEvent.click(screen.getByLabelText('Impostazioni della conversazione'));
    await fireEvent.click(screen.getByLabelText('Includi i parametri tecnici visibili'));
    const preview = (await screen.findByTestId('explain-context')).textContent ?? '';
    const field = await screen.findByLabelText('La tua domanda');
    await fireEvent.input(field, { target: { value: 'Che grafico è?' } });
    await fireEvent.submit((field as HTMLInputElement).form!);
    await waitFor(() => expect(bodies).toHaveLength(1));
    const sent = (bodies[0] as { page_context: { params: Record<string, number> } }).page_context.params;
    expect(Object.keys(sent)).toHaveLength(16);
    for (const [key, value] of Object.entries(sent)) expect(preview).toContain(`${key} = ${value}`);
    expect(preview).not.toContain('valore_16 =');
  });

  it('Esc chiude il foglio e il focus torna al pulsante', async () => {
    stub();
    render(ExplainButton, { pageId: 'home' });
    const btn = screen.getByRole('button', { name: 'RAVEN SI' });
    btn.focus();
    await fireEvent.click(btn);
    const dlg = await screen.findByRole('dialog');
    await fireEvent.keyDown(dlg, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(btn);
  });

  it('Alt+A apre; "?" no finché non è attivato, e mai mentre si scrive in un campo', async () => {
    stub();
    render(ExplainButton, { pageId: 'home' });
    await fireEvent.keyDown(document.body, { key: '?' });
    expect(screen.queryByRole('dialog')).toBeNull();
    explainPrefs.questionKey = true;
    const input = document.createElement('input');
    document.body.appendChild(input);
    await fireEvent.keyDown(input, { key: '?' });
    expect(screen.queryByRole('dialog')).toBeNull();
    await fireEvent.keyDown(document.body, { key: '?' });
    await screen.findByRole('dialog');
    cleanup();
    explainPrefs.questionKey = false;
    render(ExplainButton, { pageId: 'home' });
    await fireEvent.keyDown(document.body, { key: 'å', code: 'KeyA', altKey: true });
    await screen.findByRole('dialog');
  });

  it('backend non raggiungibile: il foglio lo dice e spiega cosa fare', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
    render(ExplainButton, { pageId: 'home' });
    await fireEvent.click(screen.getByRole('button', { name: 'RAVEN SI' }));
    expect((await screen.findByTestId('assistant-unreachable')).textContent).toMatch(/Controlla la connessione/);
    expect(screen.getByText(/provider esterno configurato/i)).toBeTruthy();
  });

  it('inert: nessuna scorciatoia mentre il menu è aperto', async () => {
    stub();
    render(ExplainButton, { pageId: 'home', inert: true });
    await fireEvent.keyDown(document.body, { key: 'a', code: 'KeyA', altKey: true });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('pageIdFor', () => {
  it('nome della cartella della pagina', () => {
    expect(pageIdFor('/')).toBe('home');
    expect(pageIdFor('/sims')).toBe('sims');
    expect(pageIdFor('/viewer/')).toBe('viewer');
  });
});
