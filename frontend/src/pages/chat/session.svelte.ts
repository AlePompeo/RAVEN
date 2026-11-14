// SPDX-License-Identifier: Apache-2.0
// Sessione di conversazione con l'assistente, SOLO in memoria (nessun localStorage/sessionStorage: privacy).
// Shared by /chat and the RAVEN SI overlay.
import {
  askAssistant,
  trimHistory,
  MAX_MESSAGE_CHARS,
  type AssistantMode,
  type ChatTurn,
  type Citation,
  type Level,
  type PageContext,
} from './assistant';
import { t } from '../../i18n/i18n.svelte';

export interface WarningNote {
  code: string;
  text: string;
}

export interface Turn {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  /** Solo assistente */
  streaming: boolean;
  interrupted: boolean;
  refused: boolean;
  retrieved: string[];
  citations: Citation[] | null;
  warnings: WarningNote[];
  followups: string[];
}

/** Messaggi per l'utente: dicono cosa è successo e cosa fare (le frasi del server restano un ripiego). */
export function warningNotes(codes: string[], _messages: string[]): WarningNote[] {
  return codes.map((code) => ({ code, text: t(code === 'provider_fallback' || code === 'all_candidates_failed' || code === 'provider_unhealthy' ? 'si.fallback' :
    code === 'llm_rate_limited' ? 'si.rateLimited' : code === 'llm_interrupted' ? 'si.partial' : 'si.verify') }));
}

export function completionMessage(turn: Pick<Turn, 'refused' | 'citations' | 'retrieved'>): string {
  if (turn.refused) return t('si.refusedStatus');
  const n = turn.citations?.length ?? 0;
  return n === 1 ? t('si.completeOne') : t('si.complete', { count: n });
}

export interface SessionOptions {
  getContext: () => PageContext | undefined;
  getLevel: () => Level;
  getLang: () => 'it' | 'en' | undefined;
  fetchFn?: typeof fetch;
  getAllowExternal?: () => boolean;
  getProvider?: () => string | undefined;
}

export class Session {
  turns = $state<Turn[]>([]);
  busy = $state(false);
  error = $state('');
  /** Testo della regione live: cambia solo a fine risposta (mai a ogni token). */
  status = $state('');
  mode = $state<AssistantMode | null>(null);
  provider = $state('');
  model = $state('');
  external = $state<boolean | null>(null);

  #opts: SessionOptions;
  #ctrl: AbortController | null = null;
  #pending = '';
  #raf: number | null = null;
  #seq = 0;
  #gen = 0; // cambia a ogni reset: una risposta annullata non tocca la conversazione nuova

  constructor(opts: SessionOptions) {
    this.#opts = opts;
  }

  /** Invia una domanda. Ritorna true se la risposta è arrivata (il campo di testo si può svuotare). */
  async send(text: string): Promise<boolean> {
    const q = text.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!q || this.busy) return false;
    this.error = '';
    this.status = '';
    const history: ChatTurn[] = trimHistory([...this.turns.filter((t) => !t.streaming && !t.refused && t.content !== '').map((t) => ({ role: t.role, content: t.content })), { role: 'user', content: q }]);
    const user: Turn = this.#blank('user', q);
    const asst: Turn = this.#blank('assistant', '');
    asst.streaming = true;
    this.turns.push(user, asst);
    const cur = this.turns[this.turns.length - 1]!; // proxy reattivo
    this.busy = true;
    const gen = this.#gen;
    this.#ctrl = new AbortController();
    const lang = this.#opts.getLang();
    const ctx = this.#opts.getContext();
    const res = await askAssistant(
      this.#opts.fetchFn ?? fetch,
      { messages: history, level: this.#opts.getLevel(), ...(lang ? { lang } : {}), ...(ctx ? { page_context: ctx } : {}),
        ...(this.#opts.getAllowExternal?.() ? { allow_external: true } : {}),
        ...(this.#opts.getProvider?.() ? { provider: this.#opts.getProvider!() } : {}) },
      this.#ctrl.signal,
      {
        onMeta: (m) => {
          cur.retrieved = m.retrieved;
          this.mode = m.mode;
          this.provider = m.provider;
          this.model = m.model;
          this.external = m.external;
        },
        onToken: (t) => {
          this.#pending += t;
          this.#schedule(cur);
        },
        onCitations: (c) => {
          cur.citations = c;
        },
        onWarning: (w) => {
          cur.warnings = warningNotes(w.codes, w.messages);
        },
        onDone: (d) => {
          cur.refused = d.refused;
          cur.followups = d.followups;
        },
      },
    );
    if (gen !== this.#gen) return false;
    this.#flush(cur);
    cur.streaming = false;
    this.busy = false;
    this.#ctrl = null;
    if (res.status === 'done') {
      this.status = completionMessage(cur);
      return true;
    }
    if (res.status === 'aborted') {
      cur.interrupted = true;
      this.status = t('si.stopped');
      if (cur.content === '') this.#dropLast(2);
      return false;
    }
    this.error = res.detail;
    if (cur.content === '') this.#dropLast(2);
    else cur.interrupted = true;
    return false;
  }

  stop(): void {
    this.#ctrl?.abort();
  }

  /** Nuova conversazione: annulla l'eventuale risposta in corso e svuota tutto. */
  reset(): void {
    this.#gen++;
    this.#ctrl?.abort();
    if (this.#raf !== null) cancelAnimationFrame(this.#raf);
    this.#raf = null;
    this.#pending = '';
    this.turns = [];
    this.error = '';
    this.status = t('si.fresh');
    this.busy = false;
    this.mode = null;
    this.provider = '';
    this.model = '';
    this.external = null;
  }

  destroy(): void {
    this.#ctrl?.abort();
    if (this.#raf !== null) cancelAnimationFrame(this.#raf);
  }

  #blank(role: 'user' | 'assistant', content: string): Turn {
    return { id: ++this.#seq, role, content, streaming: false, interrupted: false, refused: false, retrieved: [], citations: null, warnings: [], followups: [] };
  }

  #dropLast(n: number): void {
    this.turns.splice(this.turns.length - n, n);
  }

  // I token si accumulano e si riversano nel DOM al massimo una volta per fotogramma.
  #schedule(t: Turn): void {
    if (this.#raf !== null) return;
    const run = () => {
      this.#raf = null;
      this.#flush(t);
    };
    this.#raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame(run) : (setTimeout(run, 16) as unknown as number);
  }
  #flush(t: Turn): void {
    if (this.#raf !== null && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(this.#raf);
    this.#raf = null;
    if (this.#pending) {
      t.content += this.#pending;
      this.#pending = '';
    }
  }
}
