// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest';
import { askAssistant, sanitizeParams, trimHistory, sendsTextOutside, fetchKnowledgeDoc, parseKnowledgeDoc, fetchSuggestions, type AssistantRequest } from './assistant';
import { toAssistantEvent } from './events';

const enc = new TextEncoder();
function stream(chunks: string[], status = 200): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        for (const x of chunks) c.enqueue(enc.encode(x));
        c.close();
      },
    }),
    { status, headers: { 'content-type': 'text/event-stream' } },
  );
}
const ev = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
const FULL = [
  ev('meta', { provider: 'assistant-extractive', mode: 'extractive', retrieved: ['fspl'], level: 'intermedio', lang: 'it' }),
  ev('token', { token: 'Ciao ' }),
  ev('token', { token: '[fspl]' }),
  ev('citations', { citations: [{ id: 'fspl', title: 'FSPL', kind: 'formula', anchor: 'a', url_path: '/api/assistant/knowledge/fspl#a' }] }),
  ev('warning', { codes: ['provider_fallback'], messages: ['m'] }),
  ev('done', { refused: false, followups: ['Che cos’è il dB?'], chars: 11 }),
].join('');
const req: AssistantRequest = { messages: [{ role: 'user', content: 'ciao' }], level: 'intermedio' };

function collect() {
  const log: string[] = [];
  return {
    log,
    h: {
      onMeta: (m: { mode: string }) => log.push(`meta:${m.mode}`),
      onToken: (t: string) => log.push(`t:${t}`),
      onCitations: (c: { id: string }[]) => log.push(`c:${c.map((x) => x.id)}`),
      onWarning: (w: { codes: string[] }) => log.push(`w:${w.codes}`),
      onDone: (d: { refused: boolean; followups: string[] }) => log.push(`d:${d.refused}:${d.followups.length}`),
    },
  };
}

describe('askAssistant', () => {
  it('consegna meta, token, citazioni, avvisi e done nell’ordine, e invia il corpo atteso', async () => {
    const f = vi.fn(async () => stream([FULL]));
    const { log, h } = collect();
    const r = await askAssistant(f as unknown as typeof fetch, { ...req, page_context: { page_id: 'sims', simulation_id: 'fspl-c', params: { distance_km: 384400 } } }, new AbortController().signal, h);
    expect(r).toEqual({ status: 'done' });
    expect(log).toEqual(['meta:extractive', 't:Ciao ', 't:[fspl]', 'c:fspl', 'w:provider_fallback', 'd:false:1']);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/assistant/chat');
    expect(JSON.parse(init.body as string)).toEqual({
      messages: req.messages,
      level: 'intermedio',
      page_context: { page_id: 'sims', simulation_id: 'fspl-c', params: { distance_km: 384400 } },
    });
  });

  it('regge chunk che spezzano eventi e righe a ogni byte', async () => {
    const bytes = enc.encode(FULL);
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        for (let i = 0; i < bytes.length; i++) c.enqueue(bytes.slice(i, i + 1)); // un byte per chunk, anche dentro ai caratteri multibyte
        c.close();
      },
    });
    const { log, h } = collect();
    const r = await askAssistant((async () => new Response(body)) as unknown as typeof fetch, req, new AbortController().signal, h);
    expect(r.status).toBe('done');
    expect(log.filter((l) => l.startsWith('t:'))).toEqual(['t:Ciao ', 't:[fspl]']);
    expect(log.at(-1)).toBe('d:false:1');
  });

  it('un evento error produce un messaggio che dice cosa fare e interrompe', async () => {
    const { log, h } = collect();
    const r = await askAssistant((async () => stream([ev('token', { token: 'a' }), ev('error', { detail: 'assistente non disponibile' })])) as unknown as typeof fetch, req, new AbortController().signal, h);
    expect(r.status).toBe('error');
    expect(r.status === 'error' && r.detail).toMatch(/riprova/i);
    expect(log).toEqual(['t:a']);
  });

  it.each([
    [429, /attendi/i],
    [422, /accorciala/i],
    [503, /riprova/i],
  ])('errore HTTP %i', async (status, re) => {
    const r = await askAssistant((async () => new Response('{}', { status })) as unknown as typeof fetch, req, new AbortController().signal, {});
    expect(r.status === 'error' && r.detail).toMatch(re);
  });

  it('flusso chiuso senza done = errore', async () => {
    const r = await askAssistant((async () => stream([ev('token', { token: 'a' })])) as unknown as typeof fetch, req, new AbortController().signal, {});
    expect(r.status).toBe('error');
  });

  it('rete assente = errore con istruzioni; abort = aborted', async () => {
    const r1 = await askAssistant((async () => { throw new TypeError('fail'); }) as unknown as typeof fetch, req, new AbortController().signal, {});
    expect(r1.status === 'error' && r1.detail).toMatch(/connessione/i);
    const ac = new AbortController();
    const r2 = await askAssistant((async () => { ac.abort(); throw new DOMException('x', 'AbortError'); }) as unknown as typeof fetch, req, ac.signal, {});
    expect(r2).toEqual({ status: 'aborted' });
  });

  it('abort durante la lettura del flusso', async () => {
    const ac = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(enc.encode(ev('token', { token: 'a' })));
      },
      pull() {
        ac.abort();
        return new Promise(() => {});
      },
    });
    const f = (async (_u: string, init: RequestInit) => {
      init.signal?.addEventListener('abort', () => body.cancel().catch(() => {}));
      return new Response(body);
    }) as unknown as typeof fetch;
    const p = askAssistant(f, req, ac.signal, {});
    ac.abort();
    expect(await p).toEqual({ status: 'aborted' });
  });

  it('tetto di memoria del parser: riga enorme = errore, senza crash', async () => {
    const r = await askAssistant((async () => stream(['x'.repeat(1024 * 1024 + 10)])) as unknown as typeof fetch, req, new AbortController().signal, {});
    expect(r.status === 'error' && r.detail).toMatch(/superato il limite/i);
  });
});

describe('toAssistantEvent', () => {
  it('dati malformati o eventi ignoti non lanciano', () => {
    expect(toAssistantEvent({ event: 'token', data: '{rotto' })).toEqual({ type: 'ignore' });
    expect(toAssistantEvent({ event: 'altro', data: '{}' })).toEqual({ type: 'ignore' });
    expect(toAssistantEvent({ event: 'meta', data: '[]' })).toEqual({ type: 'ignore' });
  });
  it('modalità ignota = llm (fail closed); citazioni senza id scartate', () => {
    const m = toAssistantEvent({ event: 'meta', data: JSON.stringify({ provider: 'x', mode: '???' }) });
    expect(m).toMatchObject({ type: 'meta', mode: 'llm' });
    const c = toAssistantEvent({ event: 'citations', data: JSON.stringify({ citations: [{ title: 'senza id' }, { id: 'a' }] }) });
    expect(c).toMatchObject({ type: 'citations', citations: [{ id: 'a', title: 'a' }] });
  });
});

describe('helper', () => {
  it('sanitizeParams: max 16 scalari finiti, chiavi corte, niente __proto__', () => {
    const many = Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`k${i}`, i]));
    expect(Object.keys(sanitizeParams(many))).toHaveLength(16);
    expect(sanitizeParams({ a: NaN, b: Infinity, c: { x: 1 }, d: 'ok', e: true })).toEqual({ d: 'ok' });
    expect(Object.keys(sanitizeParams({ ['k'.repeat(60)]: 1 })[0] ?? {}).length).toBe(0);
    expect(Object.keys(sanitizeParams({ ['k'.repeat(60)]: 1 }))[0]).toHaveLength(40);
  });
  it('trimHistory: ultimi 10 messaggi, 2000 caratteri', () => {
    const t = Array.from({ length: 14 }, (_, i) => ({ role: 'user' as const, content: 'x'.repeat(i === 13 ? 3000 : 5) }));
    const out = trimHistory(t);
    expect(out).toHaveLength(10);
    expect(out.at(-1)?.content).toHaveLength(2000);
  });
  it('sendsTextOutside: fail closed', () => {
    expect(sendsTextOutside('extractive', 'assistant-extractive')).toBe(false);
    expect(sendsTextOutside('llm', 'assistant-openai-compat')).toBe(true);
    expect(sendsTextOutside('llm', '')).toBe(true);
    expect(sendsTextOutside(null, 'assistant-extractive')).toBe(true);
    expect(sendsTextOutside('llm', 'echo-llm')).toBe(false);
    // il backend dichiara il provider locale: nessun avviso; dichiarato esterno o assente: avviso
    expect(sendsTextOutside('llm', 'ollama:llama3.1', false)).toBe(false);
    expect(sendsTextOutside('llm', 'ollama:llama3.1', true)).toBe(true);
    expect(sendsTextOutside('llm', 'ollama:llama3.1', null)).toBe(true);
  });
  it('fetchKnowledgeDoc: 404, errore e rete', async () => {
    const r404 = await fetchKnowledgeDoc((async () => new Response('', { status: 404 })) as unknown as typeof fetch, 'x');
    expect(r404).toMatchObject({ ok: false, reason: 'not-found' });
    const r500 = await fetchKnowledgeDoc((async () => new Response('', { status: 500 })) as unknown as typeof fetch, 'x');
    expect(r500).toMatchObject({ ok: false, reason: 'error' });
    const rn = await fetchKnowledgeDoc((async () => { throw new TypeError('x'); }) as unknown as typeof fetch, 'x');
    expect(rn).toMatchObject({ ok: false, reason: 'error' });
  });
  it('parseKnowledgeDoc tollera campi mancanti o di tipo errato', () => {
    const d = parseKnowledgeDoc({ id: 'a', variables: 5, worked_example: 'no', sources: [{ ref: 1 }, null] });
    expect(d.variables).toEqual([]);
    expect(d.worked_example).toBeNull();
    expect(d.sources).toEqual([{ ref: '1', supports: '' }]);
  });
  it('fetchSuggestions limita a 6 e ignora voci malformate', async () => {
    const s = Array.from({ length: 9 }, (_, i) => ({ question: `q${i}`, doc_id: 'd' }));
    const r = await fetchSuggestions((async () => new Response(JSON.stringify({ suggestions: [null, ...s] }))) as unknown as typeof fetch, 'sims', 'it');
    expect(r).toHaveLength(6);
  });
});
