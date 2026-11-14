// SPDX-License-Identifier: Apache-2.0
// Client HTTP del Learning Assistant (contratto: docs/assistant.md). Nessuna persistenza dei messaggi.
import { createSseParser, SseLimitError, type SseEvent } from './sse';
import { toAssistantEvent, type AssistantEvent, type Citation, type AssistantMode } from './events';
import { isLocalProvider } from './api';
import { BASE } from '../../registry';
import { t } from '../../i18n/i18n.svelte';

export type { Citation, AssistantMode } from './events';
export type Level = 'principiante' | 'intermedio' | 'tecnico';
export const LEVELS: readonly Level[] = ['principiante', 'intermedio', 'tecnico'];
export const MAX_MESSAGE_CHARS = 2000;
export const MAX_HISTORY = 10; // messaggi inviati come storico (il server ne accetta 20)
const KIND_KEYS: Record<string, Parameters<typeof t>[0]> = {
  formula: 'si.formula', concept: 'si.concept', method: 'si.method', simulation: 'si.simulation',
  page: 'si.pageKind', glossary: 'si.glossary', problem: 'si.problem', decision: 'si.decision',
};
export function knowledgeKind(kind: string): string {
  const key = KIND_KEYS[kind];
  return key && Object.hasOwn(KIND_KEYS, kind) ? t(key) : kind;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}
export type Scalar = string | number;
export interface PageContext {
  page_id: string;
  simulation_id?: string;
  params?: Record<string, Scalar>;
}
export interface AssistantRequest {
  messages: ChatTurn[];
  page_context?: PageContext;
  level: Level;
  lang?: 'it' | 'en';
  allow_external?: boolean;
  provider?: string;
}
export interface AssistantHandlers {
  onMeta?: (e: Extract<AssistantEvent, { type: 'meta' }>) => void;
  onToken?: (t: string) => void;
  onCitations?: (c: Citation[]) => void;
  onWarning?: (e: Extract<AssistantEvent, { type: 'warning' }>) => void;
  onDone?: (e: Extract<AssistantEvent, { type: 'done' }>) => void;
}
export type AskResult = { status: 'done' } | { status: 'aborted' } | { status: 'error'; detail: string };

/** Limita i parametri a 16 scalari finiti con chiave <= 40 caratteri (limiti del server). */
export function sanitizeParams(params: Record<string, unknown>): Record<string, Scalar> {
  const out: Record<string, Scalar> = {};
  let n = 0;
  for (const [k, v] of Object.entries(params)) {
    if (n >= 16) break;
    const key = k.slice(0, 40);
    if (key === '' || key === '__proto__') continue;
    if (typeof v === 'number' && Number.isFinite(v)) out[key] = v;
    else if (typeof v === 'string') out[key] = v.slice(0, 200);
    else continue;
    n++;
  }
  return out;
}

/** Ultimi messaggi dello storico, ciascuno tagliato al massimo consentito. */
export function trimHistory(turns: ChatTurn[]): ChatTurn[] {
  return turns.slice(-MAX_HISTORY).map((t) => ({ role: t.role, content: t.content.slice(0, MAX_MESSAGE_CHARS) }));
}

function httpMessage(status: number): string {
  if (status === 429) return t('si.rateLimited');
  if (status === 422) return t('si.invalidQuestion');
  return t('si.serverError');
}

export async function askAssistant(fetchFn: typeof fetch, req: AssistantRequest, signal: AbortSignal, h: AssistantHandlers): Promise<AskResult> {
  try {
    const res = await fetchFn(`${BASE}api/assistant/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
    });
    if (!res.ok || !res.body) return { status: 'error', detail: httpMessage(res.status) };
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    const parser = createSseParser();
    for (;;) {
      const { done, value } = await reader.read();
      let events: SseEvent[];
      try {
        events = parser.feed(done ? dec.decode() : dec.decode(value, { stream: true }));
      } catch (err) {
        await reader.cancel().catch(() => {});
        throw err;
      }
      for (const raw of events) {
        const ev = toAssistantEvent(raw);
        if (ev.type === 'meta') h.onMeta?.(ev);
        else if (ev.type === 'token') h.onToken?.(ev.token);
        else if (ev.type === 'citations') h.onCitations?.(ev.citations);
        else if (ev.type === 'warning') h.onWarning?.(ev);
        else if (ev.type === 'error') {
          await reader.cancel().catch(() => {});
          return { status: 'error', detail: t('si.serverError') };
        } else if (ev.type === 'done') {
          h.onDone?.(ev);
          await reader.cancel().catch(() => {});
          return { status: 'done' };
        }
      }
      if (done && signal.aborted) return { status: 'aborted' };
      if (done) return { status: 'error', detail: t('si.incomplete') };
    }
  } catch (e) {
    if (signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return { status: 'aborted' };
    if (e instanceof SseLimitError) return { status: 'error', detail: t('si.tooLarge') };
    return { status: 'error', detail: t('si.network') };
  }
}

export interface Suggestion {
  question: string;
  doc_id: string;
}
export async function fetchSuggestions(fetchFn: typeof fetch, page: string, lang: string, signal?: AbortSignal): Promise<Suggestion[]> {
  const q = new URLSearchParams({ page, lang });
  const res = await fetchFn(`${BASE}api/assistant/suggestions?${q}`, signal ? { signal } : {});
  if (!res.ok) throw new Error(String(res.status));
  const d = (await res.json()) as { suggestions?: unknown };
  const out: Suggestion[] = [];
  for (const s of Array.isArray(d.suggestions) ? d.suggestions : []) {
    const o = s as { question?: unknown; doc_id?: unknown } | null;
    if (o && typeof o.question === 'string') out.push({ question: o.question, doc_id: typeof o.doc_id === 'string' ? o.doc_id : '' });
  }
  return out.slice(0, 6);
}

export interface StatusInfo {
  provider: string;
  mode: AssistantMode;
  /** Il backend dichiara se il testo esce dal computer; null = campo assente (non si assume nulla). */
  external: boolean | null;
  cloudAvailable: boolean;
}
export async function fetchStatus(fetchFn: typeof fetch, signal?: AbortSignal): Promise<StatusInfo> {
  const res = await fetchFn(`${BASE}api/assistant/status`, signal ? { signal } : {});
  if (!res.ok) throw new Error(String(res.status));
  const d = (await res.json()) as { provider?: unknown; mode?: unknown; external?: unknown; cloud_available?: unknown };
  return {
    provider: typeof d.provider === 'string' ? d.provider : '',
    mode: d.mode === 'extractive' ? 'extractive' : 'llm',
    external: typeof d.external === 'boolean' ? d.external : null,
    cloudAvailable: d.cloud_available === true,
  };
}

/**
 * Il testo lascia il computer? Solo la modalità estrattiva (nessuna rete) e un provider locale noto lo
 * escludono. Ogni altro caso, compreso "non so" (modalità o provider ignoti), vale come servizio esterno.
 */
export function sendsTextOutside(mode: AssistantMode | null, provider: string, external: boolean | null = null): boolean {
  if (mode === 'extractive') return false;
  if (external === false) return false; // il backend dichiara esplicitamente un provider locale
  return !(mode === 'llm' && isLocalProvider(provider));
}

// --- documento di conoscenza per il pannello fonte ---
export interface KnowledgeVariable {
  symbol: string;
  name: string;
  unit: string;
  range: string;
}
export interface KnowledgeSource {
  ref: string;
  supports: string;
}
export interface KnowledgeDoc {
  id: string;
  title: string;
  kind: string;
  summary: string;
  body: string;
  level: string;
  last_verified: string;
  origin: string;
  sources: KnowledgeSource[];
  expression: string;
  variables: KnowledgeVariable[];
  assumptions: string[];
  limits: string[];
  worked_example: { inputs: Record<string, Scalar>; outputs: Record<string, Scalar>; note: string } | null;
  derivation: string[];
  anchors: { anchor: string; heading: string }[];
}

const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '');
const strList = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter((s) => s !== '') : []);
const asRec = (v: unknown): Record<string, unknown> => (v !== null && typeof v === 'object' ? (v as Record<string, unknown>) : {});
const scalars = (v: unknown): Record<string, Scalar> => {
  const out: Record<string, Scalar> = {};
  for (const [k, x] of Object.entries(asRec(v))) if (typeof x === 'number' || typeof x === 'string') out[k] = x;
  return out;
};

export function parseKnowledgeDoc(raw: unknown): KnowledgeDoc {
  const d = asRec(raw);
  const we = d.worked_example !== null && typeof d.worked_example === 'object' ? asRec(d.worked_example) : null;
  const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
  return {
    id: str(d.id),
    title: str(d.title),
    kind: str(d.kind),
    summary: str(d.summary),
    body: str(d.body),
    level: str(d.level),
    last_verified: str(d.last_verified),
    origin: str(d.origin),
    sources: list(d.sources)
      .map((s) => ({ ref: str(asRec(s).ref), supports: str(asRec(s).supports) }))
      .filter((s) => s.ref !== ''),
    expression: str(d.expression),
    variables: list(d.variables).map((v) => ({ symbol: str(asRec(v).symbol), name: str(asRec(v).name), unit: str(asRec(v).unit), range: str(asRec(v).range) })),
    assumptions: strList(d.assumptions),
    limits: strList(d.limits),
    worked_example: we ? { inputs: scalars(we.inputs), outputs: scalars(we.outputs), note: str(we.note) } : null,
    derivation: strList(d.derivation),
    anchors: list(d.anchors).map((a) => ({ anchor: str(asRec(a).anchor), heading: str(asRec(a).heading) })),
  };
}

export type DocResult = { ok: true; doc: KnowledgeDoc } | { ok: false; reason: 'not-found' | 'error' | 'aborted'; message: string };

export async function fetchKnowledgeDoc(fetchFn: typeof fetch, id: string, signal?: AbortSignal): Promise<DocResult> {
  try {
    const res = await fetchFn(`${BASE}api/assistant/knowledge/${encodeURIComponent(id)}`, signal ? { signal } : {});
    if (res.status === 404) return { ok: false, reason: 'not-found', message: t('si.sourceMissing') };
    if (!res.ok) return { ok: false, reason: 'error', message: t('si.sourceError') };
    return { ok: true, doc: parseKnowledgeDoc(await res.json()) };
  } catch {
    if (signal?.aborted) return { ok: false, reason: 'aborted', message: '' };
    return { ok: false, reason: 'error', message: t('si.network') };
  }
}
