// SPDX-License-Identifier: Apache-2.0
// Eventi SSE del Learning Assistant (docs/assistant.md): meta/token/citations/warning/done/error.
// Il parser incrementale con i tetti di memoria resta quello di sse.ts.
import type { SseEvent } from './sse';

export type AssistantMode = 'extractive' | 'llm';

export interface Citation {
  id: string;
  title: string;
  kind: string;
  anchor: string;
  url_path: string;
}

export type AssistantEvent =
  | { type: 'meta'; provider: string; mode: AssistantMode; retrieved: string[]; level: string; lang: string; model: string; external: boolean | null }
  | { type: 'token'; token: string }
  | { type: 'citations'; citations: Citation[] }
  | { type: 'warning'; codes: string[]; messages: string[] }
  | { type: 'done'; refused: boolean; followups: string[]; chars: number }
  | { type: 'error'; detail: string }
  | { type: 'ignore' };

const isStr = (v: unknown): v is string => typeof v === 'string';
const strArr = (v: unknown): string[] => (Array.isArray(v) ? v.filter(isStr) : []);

/** Traduce un evento SSE grezzo; dati malformati o eventi ignoti diventano 'ignore' (mai un'eccezione). */
export function toAssistantEvent(ev: SseEvent): AssistantEvent {
  let d: Record<string, unknown> | null = null;
  try {
    const p: unknown = JSON.parse(ev.data);
    d = p !== null && typeof p === 'object' ? (p as Record<string, unknown>) : null;
  } catch {
    d = null;
  }
  switch (ev.event) {
    case 'meta':
      if (!d || !isStr(d.provider)) return { type: 'ignore' };
      return {
        type: 'meta',
        provider: d.provider,
        mode: d.mode === 'extractive' ? 'extractive' : 'llm', // fail closed: modalità ignota = llm
        retrieved: strArr(d.retrieved),
        model: isStr(d.model) ? d.model : '',
        external: typeof d.external === 'boolean' ? d.external : null,
        level: isStr(d.level) ? d.level : '',
        lang: isStr(d.lang) ? d.lang : '',
      };
    case 'token':
      return d && isStr(d.token) ? { type: 'token', token: d.token } : { type: 'ignore' };
    case 'citations': {
      const raw = d && Array.isArray(d.citations) ? (d.citations as unknown[]) : [];
      const citations: Citation[] = [];
      for (const c of raw) {
        if (c === null || typeof c !== 'object') continue;
        const o = c as Record<string, unknown>;
        if (!isStr(o.id)) continue;
        citations.push({
          id: o.id,
          title: isStr(o.title) ? o.title : o.id,
          kind: isStr(o.kind) ? o.kind : '',
          anchor: isStr(o.anchor) ? o.anchor : '',
          url_path: isStr(o.url_path) ? o.url_path : '',
        });
      }
      return { type: 'citations', citations };
    }
    case 'warning':
      return { type: 'warning', codes: strArr(d?.codes), messages: strArr(d?.messages) };
    case 'done':
      return {
        type: 'done',
        refused: d?.refused === true,
        followups: strArr(d?.followups).slice(0, 6),
        chars: typeof d?.chars === 'number' ? d.chars : 0,
      };
    case 'error':
      return { type: 'error', detail: isStr(d?.detail) ? d.detail : 'errore dell’assistente' };
    default:
      return { type: 'ignore' };
  }
}
