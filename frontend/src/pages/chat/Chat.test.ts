// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import Chat from './Chat.svelte';
import { resetConversation } from './conversation.svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import itCatalog from '../../i18n/it.json';
import enPages from '../../i18n/en.pages.json';

afterEach(() => {
  cleanup();
  resetConversation();
  useCatalog('it', itCatalog, enPages);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

const enc = new TextEncoder();
const ev = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
const META = ev('meta', { provider: 'assistant-extractive', mode: 'extractive', retrieved: ['fspl'], level: 'intermedio', lang: 'it' });
const CIT = ev('citations', { citations: [{ id: 'fspl', title: 'Perdita nello spazio libero', kind: 'formula', anchor: 'a', url_path: '/x' }] });
const ANSWER = [META, ev('token', { token: 'La perdita è ' }), ev('token', { token: '**210 dB** [fspl]' }), CIT, ev('done', { refused: false, followups: ['Che cos’è il dB?'], chars: 20 })].join('');
const REFUSAL = [
  ev('meta', { provider: 'assistant-extractive', mode: 'extractive', retrieved: [], level: 'intermedio', lang: 'it' }),
  ev('token', { token: 'Questa informazione non è presente nel materiale del sito.' }),
  ev('citations', { citations: [] }),
  ev('done', { refused: true, followups: [], chars: 58 }),
].join('');

function sseRes(body: string): Response {
  return new Response(new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc.encode(body)); c.close(); } }));
}

interface Net {
  status?: unknown | 'fail';
  chat?: (init: RequestInit) => Promise<Response>;
  doc?: unknown;
}
function stubNet(net: Net = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, ...(init ? { init } : {}) });
      if (url.startsWith('/api/assistant/status')) {
        if (net.status === 'fail') throw new TypeError('offline');
        return new Response(JSON.stringify(net.status ?? { provider: 'assistant-extractive', mode: 'extractive' }));
      }
      if (url.startsWith('/api/assistant/suggestions')) return new Response(JSON.stringify({ suggestions: url.includes('page=chat') ? [{ question: 'Che cos’è l’assistente?', doc_id: 'x' }] : [] }));
      if (url.startsWith('/api/assistant/knowledge/')) return new Response(JSON.stringify(net.doc ?? { id: 'fspl', title: 'Perdita nello spazio libero', kind: 'formula', summary: 's', expression: 'F = 1', variables: [{ symbol: 'd', name: 'dist', unit: 'km', range: '>0' }] }));
      if (url === '/api/assistant/chat') return net.chat ? net.chat(init!) : sseRes(ANSWER);
      return new Response('', { status: 404 });
    }),
  );
  return calls;
}

const ask = async (text: string) => {
  const input = screen.getByLabelText('La tua domanda') as HTMLTextAreaElement;
  await fireEvent.input(input, { target: { value: text } });
  await fireEvent.submit(input.form as HTMLFormElement);
  return input;
};
const WARN = /provider esterno configurato/i;

describe('Chat: stato e privacy', () => {
  it('estrattivo: badge "dal materiale del sito" e nessun avviso di servizio esterno', async () => {
    stubNet();
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    expect(screen.queryByText(WARN)).toBeNull();
    expect(await screen.findByRole('button', { name: 'Che cos’è l’assistente?' })).toBeTruthy();
  });
  it('modalità llm con provider non locale: avviso visibile', async () => {
    stubNet({ status: { provider: 'assistant-openai-compat', mode: 'llm' } });
    render(Chat);
    await screen.findByText(WARN);
    expect(screen.getByText('Risposte dal materiale del sito')).toBeTruthy();
  });
  it('llm dichiarato locale dal backend (external: false): nessun avviso di servizio esterno', async () => {
    stubNet({ status: { provider: 'ollama:llama3.1', mode: 'llm', external: false } });
    render(Chat);
    await screen.findByText(/Risposte generate da un modello \(ollama:llama3.1\)/);
    expect(screen.queryByText(WARN)).toBeNull();
  });
  it('llm con external: true: avviso', async () => {
    stubNet({ status: { provider: 'assistant-openai-compat', mode: 'llm', external: true } });
    render(Chat);
    await screen.findByText(WARN);
  });
  it('stato non raggiungibile: avviso (fail closed) e messaggio su cosa fare', async () => {
    stubNet({ status: 'fail' });
    render(Chat);
    await screen.findByText(WARN);
    expect(screen.getByTestId('assistant-unreachable').textContent).toMatch(/Controlla la connessione/);
    expect((screen.getByRole('checkbox', { name: 'Usa la SI online' }) as HTMLInputElement).disabled).toBe(true);
  });
  it('mode ignoto nello status = llm = avviso', async () => {
    stubNet({ status: { provider: '', mode: 'boh' } });
    render(Chat);
    await screen.findByText(WARN);
  });
});

describe('Chat: conversazione', () => {
  it('conserva la conversazione in memoria dopo minimizzazione e cambio pagina', async () => {
    const calls = stubNet();
    const view = render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('Prima domanda locale');
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta'));
    view.unmount();
    render(Chat, { pageId: 'learn' });
    expect(screen.getByRole('list', { name: 'Conversazione' }).textContent).toContain('Prima domanda locale');
    await ask('Seconda domanda');
    await waitFor(() => expect(calls.filter((call) => call.url === '/api/assistant/chat')).toHaveLength(2));
    const last = calls.filter((call) => call.url === '/api/assistant/chat').at(-1)!;
    expect(JSON.parse(last.init!.body as string)).toMatchObject({
      page_context: { page_id: 'learn' },
      messages: [{ role: 'user', content: 'Prima domanda locale' }, { role: 'assistant' }, { role: 'user', content: 'Seconda domanda' }],
    });
  });

  it('richiede consenso online e cancella lo storico locale prima di condividerlo', async () => {
    const calls = stubNet({ status: { provider: 'groq', mode: 'llm', external: true, cloud_available: true } });
    render(Chat);
    const checkbox = await screen.findByRole('checkbox', { name: 'Usa la SI online' });
    await waitFor(() => expect((checkbox as HTMLInputElement).disabled).toBe(false));
    await ask('Solo locale: non condividere');
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta'));
    const local = calls.find((call) => call.url === '/api/assistant/chat')!;
    expect(JSON.parse(local.init!.body as string).allow_external).not.toBe(true);
    await fireEvent.click(checkbox);
    expect(screen.queryByText('Solo locale: non condividere')).toBeNull();
    await ask('Spiega il Mission Planner online');
    const online = calls.filter((call) => call.url === '/api/assistant/chat').at(-1)!;
    expect(JSON.parse(online.init!.body as string)).toMatchObject({
      allow_external: true, provider: 'groq',
      messages: [{ role: 'user', content: 'Spiega il Mission Planner online' }],
    });
    expect(online.init!.body).not.toContain('Solo locale');
  });

  it('risposta: citazioni come chip, Fonti, follow-up, annuncio unico a fine risposta, nessuna persistenza', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const calls = stubNet();
    const { container } = render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    const input = await ask('Come si calcola la perdita?');
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta, 1 fonte.'));
    const chat = calls.find((c) => c.url === '/api/assistant/chat')!;
    expect(JSON.parse(chat.init!.body as string)).toEqual({ messages: [{ role: 'user', content: 'Come si calcola la perdita?' }], level: 'intermedio', lang: 'it', page_context: { page_id: 'chat' } });
    expect(screen.getByText('210 dB').tagName).toBe('STRONG');
    const chips = screen.getAllByRole('button', { name: /^Fonte fspl:/ });
    expect(chips).toHaveLength(1);
    expect(screen.getByRole('region', { name: 'Fonti' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Che cos’è il dB?' })).toBeTruthy();
    await waitFor(() => expect(input.value).toBe(''));
    // una sola regione live (role=status) e nessun aria-live esplicito sul testo
    expect(container.querySelectorAll('[aria-live]').length).toBe(0);
    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });

  it('uses the current site language unless a chat language is selected', async () => {
    const calls = stubNet();
    useCatalog('en', {}, enPages);
    render(Chat, { embedded: true });
    const send = async (text: string) => {
      const input = screen.getByRole('textbox') as HTMLTextAreaElement;
      await fireEvent.input(input, { target: { value: text } });
      await fireEvent.submit(input.form as HTMLFormElement);
      await waitFor(() => expect(input.value).toBe(''));
    };
    await send('What is link margin?');
    let chatCalls = calls.filter((call) => call.url === '/api/assistant/chat');
    expect(JSON.parse(chatCalls.at(-1)!.init!.body as string).lang).toBe('en');
    useCatalog('it', itCatalog, enPages);
    await send('Che cos’è il margine?');
    chatCalls = calls.filter((call) => call.url === '/api/assistant/chat');
    expect(JSON.parse(chatCalls.at(-1)!.init!.body as string).lang).toBe('it');
    await fireEvent.change(screen.getByLabelText('Lingua'), { target: { value: 'en' } });
    await send('Spiega il margine');
    chatCalls = calls.filter((call) => call.url === '/api/assistant/chat');
    expect(JSON.parse(chatCalls.at(-1)!.init!.body as string).lang).toBe('en');
  });

  it('il testo in streaming non finisce nella regione live prima della fine', async () => {
    let release: (() => void) | undefined;
    stubNet({
      chat: async () =>
        new Response(
          new ReadableStream<Uint8Array>({
            async start(c) {
              c.enqueue(enc.encode(META + ev('token', { token: 'parziale ' })));
              await new Promise<void>((r) => (release = r));
              c.enqueue(enc.encode(ev('token', { token: 'finale' }) + CIT + ev('done', { refused: false, followups: [], chars: 1 })));
              c.close();
            },
          }),
        ),
    });
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('ciao');
    await waitFor(() => expect(screen.getByText(/parziale/)).toBeTruthy());
    expect(screen.getByTestId('assistant-status').textContent).toBe('');
    expect(screen.getByRole('button', { name: 'Interrompi' })).toBeTruthy();
    release!();
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta'));
  });

  it('rifiuto: scheda calma con cosa provare, nessuna fonte', async () => {
    stubNet({ chat: async () => sseRes(REFUSAL) });
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('ricetta della carbonara');
    const card = await screen.findByTestId('refusal');
    expect(card.textContent).toMatch(/Non è nel materiale del sito/);
    expect(card.textContent).toMatch(/Prova a chiedere/);
    expect(screen.queryByRole('region', { name: 'Fonti' })).toBeNull();
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toMatch(/non è nel materiale/));
  });

  it('avvisi: provider_fallback tradotto in una frase che dice cosa è successo', async () => {
    stubNet({ chat: async () => sseRes(META + ev('token', { token: 'ok' }) + ev('warning', { codes: ['provider_fallback'], messages: ['x'] }) + ev('done', { refused: false, followups: [], chars: 2 })) });
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('ciao');
    const list = await screen.findByRole('list', { name: 'Avvisi su questa risposta' });
    expect(list.textContent).toMatch(/Il modello richiesto non è disponibile/);
  });

  it('warns explicitly when a model answer has no citations', async () => {
    stubNet({ chat: async () => sseRes(META + ev('token', { token: 'answer' }) + ev('warning', { codes: ['no_citation'], messages: [] }) + ev('done', { refused: false, followups: [], chars: 6 })) });
    useCatalog('en', {}, enPages);
    render(Chat);
    const input = screen.getByRole('textbox') as HTMLTextAreaElement;
    await fireEvent.input(input, { target: { value: 'Question' } });
    await fireEvent.submit(input.form as HTMLFormElement);
    expect((await screen.findByText(/does not cite the retrieved sources/)).textContent).toMatch(/may be incorrect/);
  });

  it('errore del server: un solo alert che dice cosa fare e il testo resta nel campo', async () => {
    stubNet({ chat: async () => new Response('x', { status: 503 }) });
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    const input = await ask('domanda');
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1));
    expect(screen.getByRole('alert').textContent).toMatch(/riprova/i);
    expect(input.value).toBe('domanda');
    expect(screen.queryByTestId('refusal')).toBeNull();
  });

  it('Interrompi annulla la richiesta (AbortController) e annuncia l’interruzione', async () => {
    let signal: AbortSignal | null | undefined;
    stubNet({
      chat: async (init) => {
        signal = init.signal;
        return new Response(new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc.encode(META + ev('token', { token: 'inizio ' }))); init.signal?.addEventListener('abort', () => c.error(new DOMException('abort', 'AbortError'))); } }));
      },
    });
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    const input = await ask('domanda lunga');
    await waitFor(() => expect(screen.getByText(/inizio/)).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: 'Interrompi' }));
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toBe('Risposta interrotta.'));
    expect(signal?.aborted).toBe(true);
    expect(screen.getByText(/Risposta interrotta: il testo qui sopra è parziale/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(input.value).toBe('domanda lunga');
    expect(screen.getByRole('button', { name: 'Invia' })).toBeTruthy();
  });

  it('Nuova conversazione svuota la cronologia e rimette il focus sul campo', async () => {
    stubNet();
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('uno');
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta'));
    await fireEvent.click(screen.getByRole('button', { name: 'Nuova conversazione' }));
    expect(screen.queryByRole('list', { name: 'Conversazione' })?.children.length ?? 0).toBe(0);
    expect(document.activeElement).toBe(screen.getByLabelText('La tua domanda'));
    expect(screen.getByTestId('assistant-status').textContent).toBe('Nuova conversazione.');
  });

  it('livello e lingua finiscono nella richiesta', async () => {
    const calls = stubNet();
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await fireEvent.change(screen.getByLabelText('Livello della spiegazione'), { target: { value: 'tecnico' } });
    await fireEvent.change(screen.getByLabelText('Lingua'), { target: { value: 'en' } });
    await ask('what is fspl');
    await waitFor(() => expect(screen.getByTestId('assistant-status').textContent).toContain('Risposta pronta'));
    const body = JSON.parse(calls.find((c) => c.url === '/api/assistant/chat')!.init!.body as string);
    expect(body).toMatchObject({ level: 'tecnico', lang: 'en' });
  });

  it('un chip di citazione apre il pannello fonte; Esc lo chiude e il focus torna al chip', async () => {
    stubNet();
    render(Chat);
    await screen.findByText('Risposte dal materiale del sito');
    await ask('q');
    const chip = await screen.findByRole('button', { name: /^Fonte fspl:/ });
    chip.focus();
    await fireEvent.click(chip);
    const dlg = await screen.findByRole('dialog');
    await screen.findByText('F = 1');
    await fireEvent.keyDown(dlg, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(chip);
  });
});
