// SPDX-License-Identifier: Apache-2.0
// Istantanea GrazingLink del visualizzatore: client di GET /api/raven/snapshot (throttle, cache, annullamento
// delle richieste superate), validazione della risposta e testi (angolo della Terra, perdita in spazio libero).
// Nessuna dipendenza dal DOM: testabile con un fetch finto. Nessun valore inventato: tutto viene dal servizio.
import { customSites, encodeCustom, snapshotParam } from '../../shell/customSites';
import { isoUtc } from './simTime';
import type { Scheduler } from './skyLight';

export type LinkState = 'open' | 'transition' | 'blocked' | 'out_of_coverage' | 'unavailable' | 'needs_download' | 'unknown';
const STATES: readonly LinkState[] = ['open', 'transition', 'blocked', 'out_of_coverage', 'unavailable', 'needs_download', 'unknown'];

/** Testo mostrato accanto al colore (il colore non e' mai l'unico segnale). */
export const STATE_LABEL: Record<LinkState, string> = {
  open: 'aperto',
  transition: 'transizione',
  blocked: 'bloccato',
  out_of_coverage: 'fuori copertura DEM',
  unavailable: 'dati DEM non disponibili',
  needs_download: 'terreno da scaricare',
  unknown: 'sconosciuto',
};
export const STATE_HELP: Record<LinkState, string> = {
  open: 'margine >= 0 e centro della Terra sopra il crinale',
  transition: 'margine >= 0 ma il crinale blocca la linea di vista geometrica: il link chiude per diffrazione',
  blocked: 'margine < 0 al bit-rate scelto',
  out_of_coverage: 'il DEM LOLA copre latitudini <= -85 gradi: nessun valore stimato',
  unavailable: 'tile del DEM non disponibili sul server',
  needs_download: 'i dati di terreno vicini vanno scaricati (con la tua conferma, o all\'installazione) prima del calcolo; fino ad allora il margine e\' ignoto',
  unknown: 'un dato manca o il terreno lontano e\' fuori dal modello: il margine e\' ignoto, non un orizzonte piatto',
};

export interface SnapSite {
  id: string;
  name: string;
  lat: number;
  lon: number;
  demCovered: boolean;
  earthAz: number;
  earthEl: number;
  rangeKm: number;
  fsplDeltaDb: number;
  state: LinkState;
  marginDb: number | null;
  ridgeEl: number | null;
}

export interface SnapAntenna {
  id: 'dsn34' | 'dsn18';
  name: string;
  diameterM: number;
  verified: boolean;
}
export interface SnapComplex {
  complex: string;
  lat: number;
  lon: number;
  moonAz: number;
  moonEl: number;
  sees: boolean;
  antennas: SnapAntenna[];
}

export interface Snapshot {
  tUtc: string;
  rateBps: number;
  station: string;
  rangeKm: number;
  referenceKm: number;
  fsplDeltaDb: number;
  sites: SnapSite[];
  complexes: SnapComplex[];
  bestComplex: string | null;
  minElevationDeg: number;
  source: { document: string; url: string };
  limits: string[];
}

export type SnapshotErrorKind = 'range' | 'unavailable' | 'network' | 'invalid';
export class SnapshotError extends Error {
  readonly kind: SnapshotErrorKind;
  constructor(kind: SnapshotErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const bad = () => new SnapshotError('invalid', 'Risposta del servizio non valida.');

/** Valida la risposta: campi mancanti o non finiti la rifiutano (nessun valore di ripiego). */
export function parseSnapshot(json: unknown): Snapshot {
  if (!isObj(json) || !Array.isArray(json.sites) || !isObj(json.dsn)) throw bad();
  if (!fin(json.earth_moon_range_km) || !fin(json.fspl_delta_db) || !fin(json.reference_range_km)) throw bad();
  const sites: SnapSite[] = json.sites.map((r: unknown) => {
    if (!isObj(r)) throw bad();
    const state = r.state;
    if (typeof r.id !== 'string' || typeof r.name !== 'string' || !STATES.includes(state as LinkState)) throw bad();
    if (![r.lat_deg, r.lon_deg_east, r.earth_az_deg, r.earth_el_deg, r.earth_range_km, r.fspl_delta_db].every(fin)) throw bad();
    const margin = r.margin_db;
    const ridge = r.ridge_el_deg;
    if ((margin !== null && margin !== undefined && !fin(margin)) || (ridge !== null && ridge !== undefined && !fin(ridge))) throw bad();
    return {
      id: r.id,
      name: r.name,
      lat: r.lat_deg as number,
      lon: r.lon_deg_east as number,
      demCovered: r.dem_covered === true,
      earthAz: r.earth_az_deg as number,
      earthEl: r.earth_el_deg as number,
      rangeKm: r.earth_range_km as number,
      fsplDeltaDb: r.fspl_delta_db as number,
      state: state as LinkState,
      marginDb: fin(margin) ? margin : null,
      ridgeEl: fin(ridge) ? ridge : null,
    };
  });
  const d = json.dsn;
  if (!Array.isArray(d.complexes) || !isObj(d.source) || typeof d.source.document !== 'string' || !fin(d.min_elevation_deg)) throw bad();
  const complexes: SnapComplex[] = d.complexes.map((c: unknown) => {
    if (!isObj(c) || typeof c.complex !== 'string' || !Array.isArray(c.antennas)) throw bad();
    if (![c.lat_deg, c.lon_deg_east, c.moon_az_deg, c.moon_el_deg].every(fin)) throw bad();
    return {
      complex: c.complex,
      lat: c.lat_deg as number,
      lon: wrapLon(c.lon_deg_east as number),
      moonAz: c.moon_az_deg as number,
      moonEl: c.moon_el_deg as number,
      sees: c.sees_moon === true,
      antennas: (c.antennas as unknown[]).flatMap((a): SnapAntenna[] =>
        isObj(a) && (a.id === 'dsn34' || a.id === 'dsn18') && typeof a.name === 'string' && fin(a.diameter_m)
          ? [{ id: a.id, name: a.name, diameterM: a.diameter_m, verified: a.coordinates_verified === true }]
          : [],
      ),
    };
  });
  return {
    tUtc: typeof json.t_utc === 'string' ? json.t_utc : '',
    rateBps: fin(json.rate_bps) ? json.rate_bps : NaN,
    station: typeof json.station === 'string' ? json.station : 'dsn34',
    rangeKm: json.earth_moon_range_km,
    referenceKm: json.reference_range_km,
    fsplDeltaDb: json.fspl_delta_db,
    sites,
    complexes,
    bestComplex: typeof d.best_complex === 'string' ? d.best_complex : null,
    minElevationDeg: d.min_elevation_deg,
    source: { document: d.source.document, url: typeof d.source.url === 'string' ? d.source.url : '' },
    limits: Array.isArray(json.limits) ? json.limits.filter((x): x is string => typeof x === 'string') : [],
  };
}

/** Longitudine Est in [0, 360) -> [-180, 180). */
export function wrapLon(lon: number): number {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

/* ---------------------------------- testi ---------------------------------- */

const dec = (v: number, d: number) => v.toFixed(d).replace('.', ',');

/** "Terra a 0,9° sull'orizzonte" / "Terra a 1,2° sotto l'orizzonte". */
export function earthAngleText(elDeg: number): string {
  const a = Math.abs(elDeg);
  return `Terra a ${dec(a, 1)}° ${elDeg < 0 ? 'sotto l’orizzonte' : 'sull’orizzonte'}`;
}

/** Variazione della perdita in spazio libero rispetto a 384.400 km, con segno vero ("-0,49 dB"). */
export function fsplDeltaText(deltaDb: number): string {
  const s = dec(Math.abs(deltaDb), 2);
  return `${deltaDb < 0 ? '−' : deltaDb > 0 ? '+' : ''}${s} dB`;
}

export function rangeText(km: number): string {
  return `${Math.round(km).toLocaleString('it-IT')} km`;
}

/** Limite di copertura del DEM LOLA usato dal servizio (prodotto LDEM_85S, dem.lock.json): latitudine <= -85. */
export const DEM_MAX_LAT = -85;

export interface PlaceLink {
  state: LinkState | 'pending';
  label: string;
  site: SnapSite | null;
}

/**
 * Stato del link di un luogo: dal servizio se il sito e' nell'istantanea; senza istantanea ancora 'in calcolo' per i
 * siti dell'analisi; un luogo fuori dal registro e fuori dalla copertura DEM e' 'fuori copertura DEM' (mai un valore stimato).
 */
export function placeState(siteId: string | undefined, lat: number, snap: Snapshot | null): PlaceLink {
  const site = siteId ? (snap?.sites.find((s) => s.id === siteId) ?? null) : null;
  if (site) return { state: site.state, label: STATE_LABEL[site.state], site };
  if (!snap) return { state: 'pending', label: 'in calcolo', site: null }; // the snapshot has not arrived: nothing is known yet
  if (lat > DEM_MAX_LAT) return { state: 'out_of_coverage', label: STATE_LABEL.out_of_coverage, site: null }; // not in the registry and no terrain product known
  return { state: 'pending', label: 'senza stato', site: null };
}

/** Complesso DSN evidenziato: quello con la Luna piu' alta, se almeno uno la vede. */
export function highlightedComplex(s: Pick<Snapshot, 'complexes' | 'bestComplex'>): string | null {
  if (s.bestComplex && s.complexes.some((c) => c.complex === s.bestComplex)) return s.bestComplex;
  return null;
}

export function moonSeenText(c: SnapComplex, minEl: number): string {
  const el = dec(Math.abs(c.moonEl), 0);
  return c.sees
    ? `${c.complex}: Luna a ${el}° sull’orizzonte (sopra il minimo di ${dec(minEl, 0)}°)`
    : c.moonEl < 0
      ? `${c.complex}: Luna sotto l’orizzonte (${el}°)`
      : `${c.complex}: Luna a ${el}° sull’orizzonte, sotto il minimo di ${dec(minEl, 0)}°`;
}

/* --------------------------- direzione sul disco --------------------------- */

/**
 * Direzione locale (azimut da Nord orario, elevazione) di un punto lat/lon -> vettore nel riferimento del corpo
 * (stesse assi di `latLonToBody`: x verso 90 Est, y verso Nord, z verso lon 0). Sfera: il calcolo e' schematico.
 */
export function localDirToBody(latDeg: number, lonDeg: number, azDeg: number, elDeg: number): [number, number, number] {
  const la = (latDeg * Math.PI) / 180;
  const lo = (lonDeg * Math.PI) / 180;
  const az = (azDeg * Math.PI) / 180;
  const el = (elDeg * Math.PI) / 180;
  const east = [Math.cos(lo), 0, -Math.sin(lo)];
  const north = [-Math.sin(la) * Math.sin(lo), Math.cos(la), -Math.sin(la) * Math.cos(lo)];
  const up = [Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)];
  const ce = Math.cos(el);
  const e = ce * Math.sin(az);
  const n = ce * Math.cos(az);
  const u = Math.sin(el);
  return [0, 1, 2].map((i) => e * east[i]! + n * north[i]! + u * up[i]!) as [number, number, number];
}

/* ----------------------------- client con throttle ----------------------------- */

export const SNAPSHOT_MIN_INTERVAL_MS = 1000; // al massimo una richiesta al secondo, anche in riproduzione veloce
const CACHE_MAX = 48;

type Fetch = typeof fetch;

export async function fetchSnapshot(ms: number, rateBps: number, station: string, signal?: AbortSignal, f: Fetch = fetch, gain: number | null = null): Promise<Snapshot> {
  const q = new URLSearchParams({ t: isoUtc(ms), rate_bps: String(rateBps), station });
  if (gain !== null) q.set('gain_dbi', String(gain));
  const custom = snapshotParam(customSites.get());
  if (custom) q.set('custom', custom);
  let res: Response;
  try {
    res = await f(`/api/raven/snapshot?${q.toString()}`, signal ? { signal } : {});
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new SnapshotError('network', 'Servizio non raggiungibile.');
  }
  if (res.status === 422) throw new SnapshotError('range', 'Istante o parametri non validi per il servizio.');
  if (!res.ok) throw new SnapshotError('unavailable', 'Analisi del link non disponibile.');
  let json: unknown;
  try {
    json = await res.json();
  } catch {
    throw bad();
  }
  return parseSnapshot(json);
}

export interface SnapshotClientOptions {
  fetcher?: (ms: number, rateBps: number, station: string, signal: AbortSignal, gain: number | null) => Promise<Snapshot>;
  scheduler?: Scheduler;
  minIntervalMs?: number;
  onSnapshot: (s: Snapshot, ms: number) => void;
  onError: (e: SnapshotError) => void;
  onBusy?: (busy: boolean) => void;
}

const realScheduler: Scheduler = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

/**
 * `request(ms, rate, station)`: l'ultimo istante voluto vince (leading + trailing, al massimo una richiesta al
 * secondo); un istante gia' calcolato esce dalla cache senza rete. Un solo calcolo in corso:
 * gli aggiornamenti vengono accorpati e le risposte superate sono scartate, senza abbandonare
 * thread che il server deve comunque completare. In errore `onSnapshot` non viene chiamato.
 */
export class SnapshotClient {
  private readonly fetcher: NonNullable<SnapshotClientOptions['fetcher']>;
  private readonly sched: Scheduler;
  private readonly minMs: number;
  private want: { sec: number; rate: number; station: string; gain: number | null } | null = null;
  private timer: unknown = null;
  private lastStart = -Infinity;
  private ctl: AbortController | null = null;
  private inflightKey: string | null = null;
  private wantedKey: string | null = null;
  private seq = 0;
  private readonly cache = new Map<string, Snapshot>();
  private disposed = false;
  fetches = 0;

  constructor(private readonly o: SnapshotClientOptions) {
    this.fetcher = o.fetcher ?? ((m, r, s, sig, gain) => fetchSnapshot(m, r, s, sig, fetch, gain));
    this.sched = o.scheduler ?? realScheduler;
    this.minMs = o.minIntervalMs ?? SNAPSHOT_MIN_INTERVAL_MS;
  }

  private static key(sec: number, rate: number, station: string, gain: number | null): string {
    return `${sec}|${rate}|${station}|${gain}|${encodeCustom(customSites.get())}`;
  }

  request(ms: number, rateBps: number, station: string, gain: number | null = null): void {
    if (this.disposed || !Number.isFinite(ms)) return;
    const w = { sec: Math.floor(ms / 1000), rate: rateBps, station, gain };
    const key = SnapshotClient.key(w.sec, w.rate, w.station, w.gain);
    this.wantedKey = key;
    if (this.inflightKey === key) {
      if (this.timer !== null) this.sched.clearTimeout(this.timer);
      this.timer = null;
      this.want = null;
      this.o.onBusy?.(true);
      return;
    }
    this.want = w;
    const hit = this.cache.get(key);
    if (hit) {
      // Il risultato richiesto e' pronto; un eventuale thread obsoleto finisce senza aggiornare la vista.
      if (this.timer !== null) this.sched.clearTimeout(this.timer);
      this.timer = null;
      this.want = null;
      this.o.onBusy?.(false);
      this.o.onSnapshot(hit, w.sec * 1000);
      return;
    }
    this.o.onBusy?.(true);
    this.schedule();
  }

  private schedule(): void {
    if (this.disposed || !this.want || this.inflightKey !== null || this.timer !== null) return;
    const wait = Math.max(0, this.lastStart + this.minMs - this.sched.now());
    this.timer = this.sched.setTimeout(() => {
      this.timer = null;
      this.fire();
    }, wait);
  }

  private fire(): void {
    if (this.inflightKey !== null) return;
    const w = this.want;
    this.want = null;
    if (!w || this.disposed) return;
    const ctl = new AbortController();
    this.ctl = ctl;
    const key = SnapshotClient.key(w.sec, w.rate, w.station, w.gain);
    this.inflightKey = key;
    const id = ++this.seq;
    this.lastStart = this.sched.now();
    this.fetches++;
    this.o.onBusy?.(true);
    this.fetcher(w.sec * 1000, w.rate, w.station, ctl.signal, w.gain).then(
      (s) => {
        if (id !== this.seq || this.disposed) return;
        this.cache.set(key, s);
        while (this.cache.size > CACHE_MAX) this.cache.delete(this.cache.keys().next().value as string);
        if (key === this.wantedKey) this.o.onSnapshot(s, w.sec * 1000);
      },
      (e: unknown) => {
        if (id !== this.seq || this.disposed) return;
        if (e instanceof DOMException && e.name === 'AbortError') return;
        if (key === this.wantedKey) {
          this.o.onError(e instanceof SnapshotError ? e : new SnapshotError('network', 'Servizio non raggiungibile.'));
        }
      },
    ).finally(() => {
      if (id !== this.seq || this.disposed) return;
      this.ctl = null;
      this.inflightKey = null;
      if (!this.want) this.o.onBusy?.(false);
      this.schedule();
    });
  }

  dispose(): void {
    this.disposed = true;
    this.ctl?.abort();
    if (this.timer !== null) this.sched.clearTimeout(this.timer);
    this.timer = null;
  }
}
