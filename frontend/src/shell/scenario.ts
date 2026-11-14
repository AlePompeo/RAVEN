// SPDX-License-Identifier: Apache-2.0
// Scenario condiviso del ramo lunare (docs/domain/grazinglink-plan.md): sito, istante UTC, stazione di terra,
// guadagno, altezza antenna, bit-rate e k del compensatore. Vive nell'URL e,
// solo come comodita', in sessionStorage (mai cookie). Ogni valore letto da URL o storage e' non fidato: chi non passa
// la validazione viene ignorato (nessun errore, nessun eco). Nessuna dipendenza dal DOM oltre a location/history.
import { MAX_MS, MIN_MS } from '../pages/viewer/simTime';
import { customSites, encodeCustom, isCustomId, parseCustom, type CustomSiteDef } from './customSites';

export type StationId = 'dsn34' | 'dsn18';
export const STATIONS: readonly StationId[] = ['dsn34', 'dsn18'];
/** Bit-rate ammessi dal motore (backend/domain/grazing/bitrate.py, DEFAULT_RATES_BPS). */
export const BITRATES: readonly number[] = [1e4, 3e4, 1e5, 3e5, 1e6, 3e6];
export const GAIN_RANGE = [-10, 45] as const; // dBi, PARAMS tx_gain_dbi
export const K_RANGE = [0, 6] as const; // PARAMS compensator_k
export const MAST_RANGE = [0.1, 100] as const; // PARAMS compensator_k
const SITE_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
const T_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?Z?$/;
export const STORAGE_KEY = 'hb.scenario';

export interface Scenario {
  site: string | null;
  /** Istante UTC "AAAA-MM-GGThh:mm:ssZ"; null = non scelto (le pagine usano l'ora attuale o il loro predefinito). */
  t: string | null;
  station: StationId;
  gain: number | null;
  bitrate: number | null;
  k: number | null;
  mast: number | null;
  /** Siti definiti dall'utente (al massimo 8): fanno parte dello scenario e quindi dell'URL (`cs=`). */
  customSites: CustomSiteDef[];
}

export const DEFAULT_SCENARIO: Readonly<Scenario> = { site: null, t: null, station: 'dsn34', gain: null, bitrate: null, k: null, mast: null, customSites: [] };
const KEYS = ['site', 't', 'station', 'gain', 'rate', 'k', 'antenna_h', 'cs'] as const;

/** Istante UTC valido (formato stretto, data reale, intervallo supportato) normalizzato; altrimenti null. */
export function normalizeT(raw: unknown): string | null {
  if (typeof raw !== 'string' || raw.length > 25) return null;
  const m = T_RE.exec(raw);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = [m[1], m[2], m[3], m[4], m[5], m[6] ?? '0'].map(Number) as [number, number, number, number, number, number];
  const ms = Date.UTC(y, mo - 1, d, h, mi, s);
  const dt = new Date(ms);
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) return null;
  if (ms < MIN_MS || ms > MAX_MS) return null;
  return dt.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function tToMs(t: string | null): number | null {
  const n = normalizeT(t);
  return n === null ? null : Date.parse(n);
}
export function msToT(ms: number): string | null {
  return Number.isFinite(ms) ? normalizeT(new Date(Math.floor(ms / 1000) * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')) : null;
}

function num(raw: string | null, lo: number, hi: number): number | null {
  if (raw === null || raw === '' || raw.length > 24 || !/^-?\d+(\.\d+)?(e[+-]?\d+)?$/i.test(raw)) return null;
  const v = Number(raw);
  return Number.isFinite(v) && v >= lo && v <= hi ? v : null;
}

/** Legge lo scenario da una query string; i valori non validi sono ignorati (restano al predefinito). */
export function parseScenario(search: string): Scenario {
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(search);
  } catch {
    return { ...DEFAULT_SCENARIO };
  }
  const site = p.get('site');
  const station = p.get('station');
  const rate = num(p.get('rate'), 1, 1e10);
  const cs = parseCustom(p.get('cs'));
  return {
    // un sito personalizzato e' valido solo se definito nello stesso scenario
    site: site !== null && SITE_RE.test(site) && (!isCustomId(site) || cs.some((c) => c.id === site)) ? site : null,
    t: normalizeT(p.get('t')),
    station: STATIONS.includes(station as StationId) ? (station as StationId) : 'dsn34',
    gain: num(p.get('gain'), GAIN_RANGE[0], GAIN_RANGE[1]),
    bitrate: rate !== null && BITRATES.includes(rate) ? rate : null,
    k: num(p.get('k'), K_RANGE[0], K_RANGE[1]),
    mast: num(p.get('antenna_h'), MAST_RANGE[0], MAST_RANGE[1]),
    customSites: cs,
  };
}

/** Parametri dello scenario (solo i non predefiniti), aggiunti a `into` senza toccare gli altri. */
export function writeScenarioParams(s: Scenario, into: URLSearchParams = new URLSearchParams()): URLSearchParams {
  for (const k of KEYS) into.delete(k);
  const cs = encodeCustom(s.customSites);
  if (s.site && (!isCustomId(s.site) || s.customSites.some((c) => c.id === s.site))) into.set('site', s.site);
  if (cs) into.set('cs', cs);
  if (s.t) into.set('t', s.t);
  if (s.station !== 'dsn34') into.set('station', s.station);
  if (s.gain !== null) into.set('gain', String(s.gain));
  if (s.bitrate !== null) into.set('rate', String(s.bitrate));
  if (s.k !== null) into.set('k', String(s.k));
  if (s.mast !== null) into.set('antenna_h', String(s.mast));
  return into;
}

/** "?site=...&t=..." (vuota se lo scenario e' predefinito). */
export function scenarioQuery(s: Scenario): string {
  const q = writeScenarioParams(s).toString();
  return q ? `?${q}` : '';
}

/** Percorso interno con lo scenario nella query (passare poi da `withBase` per l'href). */
export function withScenario(path: string, s: Scenario): string {
  const [pathname, search = ''] = path.split('?', 2);
  const params = writeScenarioParams(s, new URLSearchParams(search));
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ''}`;
}

type Listener = (s: Scenario) => void;
interface Env {
  loc: Pick<Location, 'pathname' | 'search' | 'hash'>;
  hist: Pick<History, 'replaceState' | 'state'> | null;
  store: Pick<Storage, 'getItem' | 'setItem'> | null;
}

function sessionStore(): Env['store'] {
  try {
    return typeof sessionStorage !== 'undefined' ? sessionStorage : null;
  } catch {
    return null;
  }
}

export const URL_WRITE_MS = 1000;

/** Store minimo: get/set/subscribe. La scrittura nell'URL e' in coda (al massimo una al secondo, replaceState). */
export class ScenarioStore {
  private s: Scenario;
  private readonly subs = new Set<Listener>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly env: Env;

  constructor(env?: Partial<Env>) {
    this.env = {
      loc: env?.loc ?? (typeof location !== 'undefined' ? location : { pathname: '/', search: '', hash: '' }),
      hist: env && 'hist' in env ? (env.hist ?? null) : typeof history !== 'undefined' ? history : null,
      store: env && 'store' in env ? (env.store ?? null) : sessionStore(),
    };
    this.s = this.initial();
    customSites.set(this.s.customSites);
  }

  private initial(): Scenario {
    const fromUrl = parseScenario(this.env.loc.search);
    const hasUrl = KEYS.some((k) => new URLSearchParams(this.env.loc.search).has(k));
    if (hasUrl) return fromUrl;
    try {
      const raw = this.env.store?.getItem(STORAGE_KEY);
      if (typeof raw === 'string' && raw.length < 1500) return parseScenario(raw);
    } catch {
      /* archiviazione non disponibile */
    }
    return { ...DEFAULT_SCENARIO };
  }

  get(): Scenario {
    return { ...this.s };
  }

  /** Dopo una navigazione: se l'URL porta uno scenario vince; altrimenti resta quello in memoria. */
  reload(): Scenario {
    if (KEYS.some((k) => new URLSearchParams(this.env.loc.search).has(k))) {
      this.s = parseScenario(this.env.loc.search);
      this.emit();
    }
    return this.get();
  }

  set(patch: Partial<Scenario>): void {
    const next = { ...this.s, ...patch };
    // rivalida: una pagina non puo' introdurre valori fuori dominio
    const checked = parseScenario(writeScenarioParams(next).toString());
    for (const key of Object.keys(patch) as (keyof Scenario)[]) {
      const v = patch[key];
      if (key === 'customSites') continue;
      // un campo non valido viene ignorato: resta il valore precedente
      if (v !== null && v !== undefined && (checked[key] === null || (key === 'station' && checked.station !== v))) {
        (checked as unknown as Record<string, unknown>)[key] = this.s[key];
      }
    }
    if (JSON.stringify(checked) === JSON.stringify(this.s)) return;
    this.s = checked;
    this.emit();
    this.queueWrite();
  }

  subscribe(fn: Listener): () => void {
    this.subs.add(fn);
    fn(this.get());
    return () => this.subs.delete(fn);
  }

  private emit(): void {
    customSites.set(this.s.customSites);
    for (const f of this.subs) f(this.get());
  }

  private queueWrite(): void {
    if (this.timer !== null) return;
    this.timer = setTimeout(() => this.flush(), URL_WRITE_MS);
  }

  /** Scrive subito URL e sessionStorage con lo stato corrente. */
  flush(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    const params = writeScenarioParams(this.s, new URLSearchParams(this.env.loc.search));
    const qs = params.toString();
    try {
      this.env.hist?.replaceState(this.env.hist.state, '', `${this.env.loc.pathname}${qs ? `?${qs}` : ''}${this.env.loc.hash}`);
    } catch {
      /* ambiente senza History API */
    }
    try {
      this.env.store?.setItem(STORAGE_KEY, scenarioQuery(this.s));
    } catch {
      /* archiviazione non disponibile */
    }
  }

  dispose(): void {
    if (this.timer !== null) {
      this.flush();
    }
  }
}

let shared: ScenarioStore | null = null;
/** Store condiviso dell'applicazione (creato al primo uso). */
export function scenarioStore(): ScenarioStore {
  shared ??= new ScenarioStore();
  return shared;
}
