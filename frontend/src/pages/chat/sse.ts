// SPDX-License-Identifier: Apache-2.0
export interface SseEvent {
  event: string;
  data: string;
}

export interface SseParser {
  /** Lancia SseLimitError (e resta in errore) se si superano i limiti di memoria. */
  feed(chunk: string): SseEvent[];
}

export interface SseLimits {
  /** Massimo di caratteri di una riga non ancora terminata. */
  maxLineChars?: number;
  /** Massimo di caratteri di dati accumulati per un singolo evento. */
  maxEventChars?: number;
}

export const DEFAULT_SSE_LIMIT = 1024 * 1024; // 1 MiB di caratteri

export class SseLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SseLimitError';
  }
}

const EOL = /\r\n|\n|\r/g;

/**
 * Parser SSE incrementale: tollera chunk che spezzano righe/eventi, CRLF (anche spezzato tra chunk),
 * commenti e righe malformate. Scansione lineare del solo chunk nuovo (niente slicing quadratico).
 */
export function createSseParser(limits: SseLimits = {}): SseParser {
  const maxLine = limits.maxLineChars ?? DEFAULT_SSE_LIMIT;
  const maxEvent = limits.maxEventChars ?? DEFAULT_SSE_LIMIT;
  let cur = ''; // riga corrente non terminata
  let started = false;
  let lastCR = false;
  let failed: SseLimitError | null = null;
  let event = '';
  let data: string[] = [];
  let dataChars = 0;

  function fail(msg: string): never {
    failed = new SseLimitError(msg);
    cur = '';
    data = [];
    throw failed;
  }

  function line(l: string, out: SseEvent[]): void {
    if (l === '') {
      if (data.length > 0) out.push({ event: event || 'message', data: data.join('\n') });
      event = '';
      data = [];
      dataChars = 0;
      return;
    }
    if (l.startsWith(':')) return;
    const i = l.indexOf(':');
    if (i < 0) return; // riga malformata: ignorata
    const field = l.slice(0, i);
    let value = l.slice(i + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value.slice(0, 64);
    else if (field === 'data') {
      dataChars += value.length + 1;
      if (dataChars > maxEvent) fail('evento SSE troppo grande');
      data.push(value);
    }
  }

  return {
    feed(chunk: string): SseEvent[] {
      if (failed) throw failed;
      if (chunk === '') return []; // non altera lo stato (es. \r finale in attesa di \n)
      if (!started) {
        started = true;
        if (chunk.startsWith('﻿')) chunk = chunk.slice(1);
      }
      const out: SseEvent[] = [];
      let pos = 0;
      if (lastCR && chunk.startsWith('\n')) pos = 1;
      lastCR = false;
      EOL.lastIndex = pos;
      for (let m = EOL.exec(chunk); m !== null; m = EOL.exec(chunk)) {
        const piece = chunk.slice(pos, m.index);
        if (cur.length + piece.length > maxLine) fail('riga SSE troppo lunga');
        line(cur + piece, out);
        cur = '';
        pos = m.index + m[0].length;
        if (m[0] === '\r' && pos === chunk.length) lastCR = true; // l'eventuale '\n' arriva nel chunk dopo
      }
      const rest = chunk.slice(pos);
      if (cur.length + rest.length > maxLine) fail('riga SSE troppo lunga');
      cur += rest;
      return out;
    },
  };
}

export type ChatEvent =
  | { type: 'token'; token: string }
  | { type: 'done' }
  | { type: 'error'; detail: string }
  | { type: 'ignore' };

export function toChatEvent(ev: SseEvent): ChatEvent {
  if (ev.event === 'error') {
    try {
      const d: unknown = JSON.parse(ev.data);
      const detail = (d as { detail?: unknown } | null)?.detail;
      if (typeof detail === 'string') return { type: 'error', detail };
    } catch {
      /* fallthrough */
    }
    return { type: 'error', detail: 'errore del provider' };
  }
  if (ev.data === '[DONE]') return { type: 'done' };
  try {
    const d: unknown = JSON.parse(ev.data);
    const token = (d as { token?: unknown } | null)?.token;
    if (typeof token === 'string') return { type: 'token', token };
  } catch {
    /* ignorato */
  }
  return { type: 'ignore' };
}
