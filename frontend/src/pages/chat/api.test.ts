// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest';
import { streamChat, isLocalProvider, isVerifiedLocal, type ChatMessage } from './api';

function sseResponse(chunks: string[], status = 200): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
  return new Response(body, { status, headers: { 'content-type': 'text/event-stream' } });
}
const msgs: ChatMessage[] = [{ role: 'user', content: 'ciao' }];
const run = (f: unknown, signal = new AbortController().signal, onToken: (t: string) => void = () => {}) =>
  streamChat(f as typeof fetch, msgs, 'echo-llm', signal, onToken);

describe('streamChat', () => {
  it('inoltra i token, termina su [DONE] e invia il body atteso', async () => {
    const f = vi.fn(async () => sseResponse(['data: {"tok', 'en":"a"}\n\ndata: {"token":"b"}\n\n', 'data: [DONE]\n\n']));
    const tokens: string[] = [];
    const r = await run(f, undefined, (t) => tokens.push(t));
    expect(tokens).toEqual(['a', 'b']);
    expect(r).toEqual({ status: 'done' });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/chat');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ messages: msgs, provider: 'echo-llm' });
  });
  it('gestisce event: error', async () => {
    const r = await run(async () =>
      sseResponse(['data: {"token":"a"}\n\n', 'event: error\ndata: {"detail":"provider non disponibile"}\n\n']),
    );
    expect(r).toEqual({ status: 'error', detail: 'provider non disponibile' });
  });
  it('errore HTTP', async () => {
    const r = await run(async () => new Response('{}', { status: 404 }));
    expect(r.status).toBe('error');
  });
  it('flusso chiuso senza [DONE] e un errore', async () => {
    const r = await run(async () => sseResponse(['data: {"token":"a"}\n\n']));
    expect(r.status).toBe('error');
  });
  it('abort restituisce aborted senza errore', async () => {
    const ac = new AbortController();
    const r = await run(async () => {
      ac.abort();
      throw new DOMException('abort', 'AbortError');
    }, ac.signal);
    expect(r).toEqual({ status: 'aborted' });
  });
});

describe('isVerifiedLocal (fail closed)', () => {
  it('locale solo se elenco caricato e provider noto e locale', () => {
    expect(isVerifiedLocal('echo-llm', ['echo-llm'])).toBe(true);
    expect(isVerifiedLocal('echo-llm', null)).toBe(false);
    expect(isVerifiedLocal('echo-llm', [])).toBe(false);
    expect(isVerifiedLocal('altro', ['altro'])).toBe(false);
  });
});

describe('limiti SSE', () => {
  it('riga enorme senza newline -> errore', async () => {
    const r = await run(async () => sseResponse(['x'.repeat(1024 * 1024 + 10)]));
    expect(r.status).toBe('error');
  });
});

describe('isLocalProvider', () => {
  it('solo gli stub locali noti', () => {
    expect(isLocalProvider('echo-llm')).toBe(true);
    expect(isLocalProvider('openai')).toBe(false);
  });
});
