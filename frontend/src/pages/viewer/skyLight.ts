// SPDX-License-Identifier: Apache-2.0
// Luce reale del visualizzatore: client di GET /api/raven/sky/subsolar con throttle, annullamento delle richieste
// superate e cache dell'ultimo valore valido. Nessuna dipendenza dal DOM: testabile con un fetch finto.
import { isoUtc } from './simTime';
import { normalizeVec } from '../../viewports/scene';

export type SkyBody = 'earth' | 'moon' | 'mars';

export interface Light {
  /** Istante richiesto (ms UTC). */
  ms: number;
  body: SkyBody;
  lat_deg: number;
  lon_deg_east: number;
  /** Versore corpo -> Sole, spazio-oggetto, assi del viewer. */
  dir: [number, number, number];
  sun_distance_au: number;
}

export type SkyErrorKind = 'range' | 'unavailable' | 'network' | 'invalid';
export class SkyError extends Error {
  readonly kind: SkyErrorKind;
  constructor(kind: SkyErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

export const MIN_INTERVAL_MS = 250; // ~4 richieste al secondo

/** Valida la risposta del servizio. */
export function parseSubsolar(json: unknown, body: SkyBody, ms: number): Light {
  const o = json as Record<string, unknown> | null;
  const sp = o?.subsolar as Record<string, unknown> | undefined;
  const lat = sp?.lat_deg;
  const lon = sp?.lon_deg_east;
  const au = o?.sun_distance_au;
  if (typeof lat !== 'number' || typeof lon !== 'number' || !Number.isFinite(lat) || !Number.isFinite(lon)) {
    throw new SkyError('invalid', 'Risposta del servizio non valida.');
  }
  const raw = o?.sun_direction_body_fixed;
  const dir = Array.isArray(raw) ? normalizeVec(raw as number[]) : null;
  if (!dir) throw new SkyError('invalid', 'Risposta del servizio non valida.');
  return { ms, body, lat_deg: lat, lon_deg_east: lon, dir, sun_distance_au: typeof au === 'number' ? au : NaN };
}

type Fetch = typeof fetch;

export async function fetchSubsolar(body: SkyBody, ms: number, signal?: AbortSignal, f: Fetch = fetch): Promise<Light> {
  let res: Response;
  try {
    res = await f(`/api/raven/sky/subsolar?body=${body}&t=${encodeURIComponent(isoUtc(ms))}`, signal ? { signal } : {});
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new SkyError('network', 'Servizio non raggiungibile.');
  }
  if (res.status === 422) throw new SkyError('range', 'Data fuori dall’intervallo supportato.');
  if (!res.ok) throw new SkyError('unavailable', 'Calcolo della luce non disponibile.');
  let json: unknown;
  try {
    json = await res.json();
  } catch {
    throw new SkyError('invalid', 'Risposta del servizio non valida.');
  }
  return parseSubsolar(json, body, ms);
}

export interface Scheduler {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(h: unknown): void;
}
const realScheduler: Scheduler = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export interface LightClientOptions {
  fetcher?: (body: SkyBody, ms: number, signal: AbortSignal) => Promise<Light>;
  scheduler?: Scheduler;
  minIntervalMs?: number;
  onLight: (l: Light) => void;
  onError: (e: SkyError, body: SkyBody, ms: number) => void;
  onBusy?: (busy: boolean) => void;
}

/**
 * `request(body, ms)` registra l'ultimo istante voluto; al massimo una richiesta ogni `minIntervalMs`
 * (leading + trailing: l'ultimo valore vince, i valori intermedi si saltano). Una richiesta nuova annulla
 * quella in corso; le risposte superate vengono scartate. In caso d'errore `onLight` non viene chiamato:
 * chi usa il client tiene l'ultima luce valida.
 */
export class LightClient {
  private readonly fetcher: NonNullable<LightClientOptions['fetcher']>;
  private readonly sched: Scheduler;
  private readonly minMs: number;
  private readonly onLight: LightClientOptions['onLight'];
  private readonly onError: LightClientOptions['onError'];
  private readonly onBusy: ((busy: boolean) => void) | undefined;
  private want: { body: SkyBody; ms: number } | null = null;
  private timer: unknown = null;
  private lastStart = -Infinity;
  private ctl: AbortController | null = null;
  private seq = 0;
  private cache: Light | null = null;
  private disposed = false;

  constructor(o: LightClientOptions) {
    this.fetcher = o.fetcher ?? ((b, m, s) => fetchSubsolar(b, m, s));
    this.sched = o.scheduler ?? realScheduler;
    this.minMs = o.minIntervalMs ?? MIN_INTERVAL_MS;
    this.onLight = o.onLight;
    this.onError = o.onError;
    this.onBusy = o.onBusy;
  }

  get last(): Light | null {
    return this.cache;
  }

  request(body: SkyBody, ms: number): void {
    if (this.disposed) return;
    this.want = { body, ms };
    if (this.timer !== null) return; // il trailing parte da solo
    const wait = Math.max(0, this.lastStart + this.minMs - this.sched.now());
    this.timer = this.sched.setTimeout(() => {
      this.timer = null;
      this.fire();
    }, wait);
  }

  private fire(): void {
    const w = this.want;
    this.want = null;
    if (!w || this.disposed) return;
    const c = this.cache;
    if (c && c.body === w.body && c.ms === w.ms) {
      this.onLight(c); // stessa richiesta dell'ultima valida: nessuna rete
      return;
    }
    this.ctl?.abort();
    const ctl = new AbortController();
    this.ctl = ctl;
    const id = ++this.seq;
    this.lastStart = this.sched.now();
    this.onBusy?.(true);
    this.fetcher(w.body, w.ms, ctl.signal).then(
      (l) => {
        if (id !== this.seq || this.disposed) return;
        this.cache = l;
        this.onBusy?.(false);
        this.onLight(l);
      },
      (e: unknown) => {
        if (id !== this.seq || this.disposed) return;
        if (e instanceof DOMException && e.name === 'AbortError') return;
        this.onBusy?.(false);
        this.onError(e instanceof SkyError ? e : new SkyError('network', 'Servizio non raggiungibile.'), w.body, w.ms);
      },
    );
  }

  dispose(): void {
    this.disposed = true;
    this.ctl?.abort();
    if (this.timer !== null) this.sched.clearTimeout(this.timer);
    this.timer = null;
  }
}
