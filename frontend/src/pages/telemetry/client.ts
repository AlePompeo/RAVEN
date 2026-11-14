// SPDX-License-Identifier: Apache-2.0
import type { AzEl, Telemetry } from '../../contracts/telemetry';

export type ConnectionStatus =
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'reconnecting'; attempt: number; delayMs: number }
  | { kind: 'closed' };

/** Sottoinsieme di EventSource usato dal client (facilita il fake nei test). */
export interface SourceLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  close(): void;
}

export interface TelemetryClientOptions {
  url?: string;
  onSample: (s: Telemetry) => void;
  onStatus: (s: ConnectionStatus) => void;
  createSource?: (url: string) => SourceLike;
  baseDelayMs?: number;
  maxDelayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
  /** Sorgente di casualità per il jitter (default Math.random). */
  random?: () => number;
}

export interface TelemetryClient {
  start(): void;
  /** Idempotente: chiude la sorgente e annulla i retry. */
  stop(): void;
}

const TOP_KEYS = ['schema_version', 't_utc', 'site_id', 'power_w', 'link_margin_db', 'sun', 'earth'] as const;

// stesso pattern di contracts/telemetry.schema.json (verificato da test)
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

const RFC3339 = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:[Zz]|[+-](\d{2}):(\d{2}))$/;

/** JSON Schema `format: date-time` (RFC 3339): fuso orario obbligatorio, intervalli validi. */
export function isRfc3339(v: string): boolean {
  const m = RFC3339.exec(v);
  if (!m) return false;
  const [y, mo, d, h, mi, se, oh, om] = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => (m[i] === undefined ? 0 : Number(m[i])));
  if (mo! < 1 || mo! > 12 || d! < 1 || h! > 23 || mi! > 59 || se! > 60 || oh! > 23 || om! > 59) return false;
  return d! <= new Date(Date.UTC(y!, mo!, 0)).getUTCDate();
}

function onlyKeys(o: Record<string, unknown>, allowed: readonly string[]): boolean {
  return Object.keys(o).every((k) => allowed.includes(k));
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function isAzEl(v: unknown): v is AzEl {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  return onlyKeys(o, ['az_deg', 'el_deg']) && isNum(o.az_deg) && isNum(o.el_deg);
}

/** Valida un messaggio SSE secondo il contratto Telemetry (contracts/telemetry.schema.json). */
export function parseSample(data: unknown): Telemetry | null {
  if (typeof data !== 'string') return null;
  let o: unknown;
  try {
    o = JSON.parse(data);
  } catch {
    return null;
  }
  if (typeof o !== 'object' || o === null || Array.isArray(o)) return null;
  const r = o as Record<string, unknown>;
  if (!onlyKeys(r, TOP_KEYS)) return null;
  if (typeof r.schema_version !== 'string' || !SEMVER.test(r.schema_version)) return null;
  if (typeof r.t_utc !== 'string' || !isRfc3339(r.t_utc)) return null;
  if (typeof r.site_id !== 'string' || r.site_id.length < 1) return null;
  if (!isNum(r.power_w)) return null;
  if (r.link_margin_db !== undefined && !isNum(r.link_margin_db)) return null;
  if (r.sun !== undefined && !isAzEl(r.sun)) return null;
  if (r.earth !== undefined && !isAzEl(r.earth)) return null;
  return r as unknown as Telemetry;
}

export function createTelemetryClient(opts: TelemetryClientOptions): TelemetryClient {
  const url = opts.url ?? '/api/telemetry/stream';
  const create = opts.createSource ?? ((u: string) => new EventSource(u) as unknown as SourceLike);
  const base = opts.baseDelayMs ?? 1000;
  const max = opts.maxDelayMs ?? 30000;
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
  const rnd = opts.random ?? Math.random;
  const clearT = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));

  let src: SourceLike | null = null;
  let timer: unknown = null;
  let attempt = 0;
  let stopped = true;

  function detach(): void {
    if (!src) return;
    src.onopen = src.onmessage = src.onerror = null;
    src.close();
    src = null;
  }

  function connect(): void {
    timer = null;
    if (stopped) return;
    opts.onStatus(attempt === 0 ? { kind: 'connecting' } : { kind: 'reconnecting', attempt, delayMs: 0 });
    const s = create(url);
    src = s;
    s.onopen = () => {
      if (stopped || src !== s) return;
      attempt = 0;
      opts.onStatus({ kind: 'open' });
    };
    s.onmessage = (ev) => {
      if (stopped || src !== s) return;
      const sample = parseSample(ev.data);
      if (sample) opts.onSample(sample);
    };
    s.onerror = () => {
      if (stopped || src !== s) return;
      detach(); // il retry è nostro: dopo un 503 EventSource non riproverebbe
      attempt += 1;
      const cap = Math.min(max, base * 2 ** (attempt - 1));
      const delayMs = Math.round(cap / 2 + (cap / 2) * rnd()); // jitter: tra metà e pieno ritardo
      opts.onStatus({ kind: 'reconnecting', attempt, delayMs });
      timer = setT(connect, delayMs);
    };
  }

  return {
    start() {
      if (!stopped) return;
      stopped = false;
      attempt = 0;
      connect();
    },
    stop() {
      if (stopped) return;
      stopped = true;
      if (timer !== null) clearT(timer);
      timer = null;
      detach(); // niente onStatus: il chiamante sta distruggendo lo stato
    },
  };
}

export function statusText(s: ConnectionStatus): string {
  switch (s.kind) {
    case 'connecting':
      return 'Connessione al flusso di telemetria in corso.';
    case 'open':
      return 'Connesso: ricezione telemetria in tempo reale.';
    case 'reconnecting':
      return 'Connessione persa. Riconnessione in corso.'; // testo costante: un solo annuncio per interruzione
    case 'closed':
      return 'Disconnesso.';
  }
}
