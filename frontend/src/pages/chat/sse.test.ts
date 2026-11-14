// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { createSseParser, toChatEvent, SseLimitError } from './sse';

const feedAll = (chunks: string[]) => {
  const p = createSseParser();
  return chunks.flatMap((c) => p.feed(c));
};

describe('SSE parser', () => {
  it('analizza eventi completi', () => {
    const ev = feedAll(['data: {"token":"a"}\n\ndata: [DONE]\n\n']);
    expect(ev).toEqual([
      { event: 'message', data: '{"token":"a"}' },
      { event: 'message', data: '[DONE]' },
    ]);
  });
  it('gestisce un evento spezzato a meta riga e tra i separatori', () => {
    expect(feedAll(['da', 'ta: {"tok', 'en":"x"}\n', '\n'])).toEqual([{ event: 'message', data: '{"token":"x"}' }]);
    expect(feedAll(['data: 1\r', '\n\r\ndata: 2\r\n\r\n']).map((e) => e.data)).toEqual(['1', '2']);
  });
  it('legge event: error e ignora commenti e righe malformate', () => {
    const ev = feedAll([': keepalive\n\n', 'garbage\nevent: error\ndata: {"detail":"x"}\n\n']);
    expect(ev).toEqual([{ event: 'error', data: '{"detail":"x"}' }]);
  });
  it('unisce piu righe data e non emette eventi senza dati', () => {
    expect(feedAll(['data: a\ndata: b\n\n', 'event: x\n\n'])).toEqual([{ event: 'message', data: 'a\nb' }]);
  });
  it('ignora il BOM iniziale e un evento incompleto a fine flusso', () => {
    expect(feedAll(['﻿data: 1\n\n', 'data: 2'])).toEqual([{ event: 'message', data: '1' }]);
  });
});

describe('CRLF e chunk vuoti', () => {
  it('un chunk vuoto tra \\r e \\n non rompe il CRLF', () => {
    expect(feedAll(['data: 1\r', '', '\n\r\n']).map((e) => e.data)).toEqual(['1']);
  });
});

describe('limiti', () => {
  it('flood senza newline lancia e resta in errore', () => {
    const p = createSseParser({ maxLineChars: 100 });
    expect(() => {
      for (let i = 0; i < 50; i++) p.feed('x'.repeat(10));
    }).toThrow(SseLimitError);
    expect(() => p.feed('data: 1\n\n')).toThrow(SseLimitError);
  });
  it('evento con troppi dati (molte righe data) lancia', () => {
    const p = createSseParser({ maxEventChars: 50 });
    expect(() => p.feed('data: aaaaaaaaaaaaaaaaaaaa\n'.repeat(5))).toThrow(SseLimitError);
  });
  it('eventi grandi ma sotto il limite passano; il limite e per evento', () => {
    const p = createSseParser({ maxEventChars: 50 });
    const out = p.feed('data: aaaaaaaaaaaaaaaaaaaa\n\n'.repeat(5));
    expect(out).toHaveLength(5);
  });
  it('input di molti MB in piccoli chunk resta lineare', () => {
    const p = createSseParser();
    let n = 0;
    const t = Date.now();
    for (let i = 0; i < 20000; i++) n += p.feed('data: {"token":"' + 'a'.repeat(100) + '"}\n\n').length;
    expect(n).toBe(20000);
    expect(Date.now() - t).toBeLessThan(2000);
  });
});

describe('toChatEvent', () => {
  it('token, done, error, malformati', () => {
    expect(toChatEvent({ event: 'message', data: '{"token":"ciao"}' })).toEqual({ type: 'token', token: 'ciao' });
    expect(toChatEvent({ event: 'message', data: '[DONE]' })).toEqual({ type: 'done' });
    expect(toChatEvent({ event: 'error', data: '{"detail":"giu"}' })).toEqual({ type: 'error', detail: 'giu' });
    expect(toChatEvent({ event: 'error', data: 'non json' })).toEqual({ type: 'error', detail: 'errore del provider' });
    expect(toChatEvent({ event: 'message', data: 'non json' })).toEqual({ type: 'ignore' });
    expect(toChatEvent({ event: 'message', data: '{"token":3}' })).toEqual({ type: 'ignore' });
  });
});
