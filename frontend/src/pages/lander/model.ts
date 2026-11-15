// SPDX-License-Identifier: Apache-2.0
// Modello dei dati della Scena lander: tipi e validazione della risposta di GET /api/raven/scene, client con
// throttle e annullamento, formula della zona di Fresnel, stato del link (colore + testo), puntamento e cono
// dell'antenna, direzione locale del Sole, testo alternativo ed esportazione JSON. Nessun accesso al DOM.
import { isoUtc } from '../viewer/simTime';
import type { CustomSiteDef } from '../../shell/customSites';
import { askTerrainConfirm, type TerrainEstimate } from '../../shell/ravenApi';

export type LinkState = 'open' | 'transition' | 'blocked' | 'unknown';
export type SceneErrorKind = 'range' | 'coverage' | 'unavailable' | 'busy' | 'network' | 'invalid' | 'outside_model';

export class SceneError extends Error {
  readonly kind: SceneErrorKind;
  constructor(kind: SceneErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

export interface SceneParams {
  site: string;
  /** Sito personalizzato (definizione dallo scenario condiviso): coordinate e nome vanno nella richiesta. */
  customSite?: CustomSiteDef;
  ms: number;
  station: 'dsn34' | 'dsn18';
  gain: number;
  rate: number;
  mast: number;
}

export const DEFAULT_GAIN = 15;
export const DEFAULT_RATE = 1e5;
export const DEFAULT_MAST = 2;
export const MAST_RANGE = [0.5, 10] as const;
/** Pendenza del grafico: perdita di puntamento 12,04 (errore/HPBW)^2 dB (gaussiana esatta, API antenna). */
export const POINTING_DB_PER_X2 = 12.04;

export interface Patch {
  n: number;
  sizeM: number;
  spacingM: number;
  nativeResolutionM: number;
  heights: Float32Array; // u (m) sul piano orizzontale locale, righe n (da destra a sinistra) x colonne e
  minM: number;
  maxM: number;
  sampling: string;
}

export interface LanderScene {
  tUtc: string;
  site: { id: string | null; lat: number; lon: number };
  sky: { icrfToScene: [number[], number[], number[]] } | null;
  earth: { azDeg: number; elDeg: number; rangeKm: number; angularDiameterDeg: number; parallaxDeg: number };
  terrain: {
    source: string;
    synthetic: boolean;
    label: string;
    productId: string | null;
    nativeResolutionM: number | null;
    profileSpacingM: number;
    radiusResolved: boolean;
    coverage: string;
    patch: Patch | null;
    patchHalfM: number | null;
    profile: { e: number[]; u: number[]; arc: number[] };
  };
  antenna: {
    station: string;
    mastM: number;
    mastTag: string;
    gainDbi: number;
    diameterM: number;
    hpbwDeg: number;
    pointingDbPerX2: number;
    wavelengthM: number;
    frequencyGhz: number;
  };
  ridge: {
    e: number;
    u: number;
    arcDistanceM: number;
    heightM: number;
    d1M: number;
    d2M: number;
    heightAboveLosM: number;
    tipElevationDeg: number;
    angleAboveLosDeg: number;
    radiusM: number | null;
    radiusResolved: boolean;
    blocksLos: boolean;
    nu: number;
  };
  fresnel: { wavelengthM: number; rangeM: number; r1AtRidgeM: number; dEndM: number };
  diffraction: {
    knifeEdgeDb: number;
    correctionDb: number | null;
    correctionUncertaintyDb: number | null;
    correctionLabel: string;
    lossDb: number | null;
    multipathApplicable: boolean;
    multipathGainDb: number | null;
    multipathReason: string | null;
    totalLossDb: number | null;
  };
  link: { rateBps: number; margin: number | null; state: LinkState; stateLabel: string; geometricVisible: boolean; fsplDb: number; station: string };
  tags: Record<string, string>;
  /** Risposta dell'API come ricevuta (per l'esportazione, con i nomi dei campi del contratto). */
  raw: Record<string, unknown>;
  limits: string[];
  disclaimer: string;
}

/* ------------------------------------------------ validazione ------------------------------------------------ */

const bad = () => new SceneError('invalid', 'Risposta del servizio non valida.');
const rec = (v: unknown): Record<string, unknown> => {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw bad();
  return v as Record<string, unknown>;
};
const num = (v: unknown): number => {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw bad();
  return v;
};
const numOrNull = (v: unknown): number | null => (v === null || v === undefined ? null : num(v));
const str = (v: unknown): string => {
  if (typeof v !== 'string') throw bad();
  return v;
};
const numArr = (v: unknown, max: number): number[] => {
  if (!Array.isArray(v) || v.length < 2 || v.length > max) throw bad();
  return v.map(num);
};

export function parseScene(json: unknown): LanderScene {
  const o = rec(json);
  const model = o.model === undefined ? null : rec(o.model);
  const ear = rec(o.earth);
  const ter = rec(o.terrain);
  const ant = rec(o.antenna);
  const rid = rec(o.ridge);
  const fre = rec(o.fresnel);
  const dif = rec(o.diffraction);
  const lnk = rec(o.link);
  const st = str(model ? model.state : lnk.state);
  if (st !== 'open' && st !== 'transition' && st !== 'blocked' && st !== 'unknown') throw bad();
  const margin = st === 'unknown' ? null
    : model && 'margin_db' in model ? numOrNull(model.margin_db) : num(lnk.margin_db);
  const currentDif = { ...dif };
  if (margin === null) {
    for (const key of ['correction_db', 'correction_uncertainty_db', 'diffraction_loss_db', 'total_loss_db']) {
      currentDif[key] = null;
    }
    currentDif.multipath_applicable = false;
    currentDif.multipath_gain_db = null;
    currentDif.multipath_reason = 'RF result unavailable';
  }
  const prof = rec(ter.profile);
  const e = numArr(prof.e_m, 1000);
  const u = numArr(prof.u_m, 1000);
  const arc = numArr(prof.arc_m, 1000);
  if (e.length !== u.length || e.length !== arc.length) throw bad();
  let patch: Patch | null = null;
  if (ter.patch !== null && ter.patch !== undefined) {
    const p = rec(ter.patch);
    const n = num(p.n);
    const h = p.height_m;
    if (!Number.isInteger(n) || n < 4 || n > 256 || !Array.isArray(h) || h.length !== n * n) throw bad();
    const heights = new Float32Array(n * n);
    for (let i = 0; i < h.length; i++) heights[i] = num(h[i]);
    patch = {
      n,
      sizeM: num(p.size_m),
      spacingM: num(p.spacing_m),
      nativeResolutionM: num(p.native_resolution_m),
      heights,
      minM: num(p.min_m),
      maxM: num(p.max_m),
      sampling: str(p.sampling),
    };
  }
  const samples = fre.samples;
  const dEnd = Array.isArray(samples) && samples.length > 1 ? num((rec(samples[samples.length - 1]) as { d_m: unknown }).d_m) : num(rid.d1_m) * 1.6;
  const limits = Array.isArray(o.declared_limits) ? o.declared_limits.filter((x): x is string => typeof x === 'string') : [];
  const site = rec(o.site);
  const tags = rec(o.tags);
  let sky: LanderScene['sky'] = null;
  if (o.sky !== undefined && o.sky !== null) {
    const matrix = rec(o.sky).icrf_to_scene;
    if (!Array.isArray(matrix) || matrix.length !== 3) throw bad();
    const rows = matrix.map((row: unknown) => {
      if (!Array.isArray(row) || row.length !== 3) throw bad();
      return row.map(num);
    });
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        const dot = rows[i]!.reduce((sum: number, x: number, k: number) => sum + x * rows[j]![k]!, 0);
        if (Math.abs(dot - (i === j ? 1 : 0)) > 1e-6) throw bad();
      }
    }
    const [a, b, c] = rows;
    const det = a![0]! * (b![1]! * c![2]! - b![2]! * c![1]!)
      - a![1]! * (b![0]! * c![2]! - b![2]! * c![0]!)
      + a![2]! * (b![0]! * c![1]! - b![1]! * c![0]!);
    if (Math.abs(det - 1) > 1e-6) throw bad();
    sky = { icrfToScene: [a!, b!, c!] };
  }
  return {
    tUtc: str(o.t_utc),
    site: { id: typeof site.id === 'string' ? site.id : null, lat: num(site.lat_deg), lon: num(site.lon_deg_east) },
    sky,
    earth: {
      azDeg: num(ear.az_deg),
      elDeg: num(ear.el_deg),
      rangeKm: num(ear.range_km),
      angularDiameterDeg: num(ear.angular_diameter_deg),
      parallaxDeg: num(ear.parallax_deg),
    },
    terrain: {
      source: str(ter.source),
      synthetic: ter.synthetic === true,
      label: str(ter.label),
      productId: typeof ter.product_id === 'string' ? ter.product_id : null,
      nativeResolutionM: numOrNull(ter.native_resolution_m),
      profileSpacingM: num(ter.profile_spacing_m),
      radiusResolved: ter.radius_resolved === true,
      coverage: str(ter.coverage),
      patch,
      patchHalfM: numOrNull(ter.patch_half_size_m),
      profile: { e, u, arc },
    },
    antenna: {
      station: str(ant.station),
      mastM: num(ant.mast_height_m),
      mastTag: str(ant.mast_tag),
      gainDbi: num(ant.gain_dbi),
      diameterM: num(ant.diameter_m),
      hpbwDeg: num(ant.hpbw_deg),
      pointingDbPerX2: num(ant.pointing_db_per_hpbw2),
      wavelengthM: num(ant.wavelength_m),
      frequencyGhz: num(ant.frequency_ghz),
    },
    ridge: {
      e: num(rid.e_m),
      u: num(rid.u_m),
      arcDistanceM: num(rid.arc_distance_m),
      heightM: num(rid.height_m),
      d1M: num(rid.d1_m),
      d2M: num(rid.d2_m),
      heightAboveLosM: num(rid.height_above_los_m),
      tipElevationDeg: num(rid.tip_elevation_deg),
      angleAboveLosDeg: num(rid.angle_above_los_deg),
      radiusM: numOrNull(rid.radius_of_curvature_m),
      radiusResolved: rid.radius_resolved === true,
      blocksLos: rid.blocks_los === true,
      nu: num(rid.nu),
    },
    fresnel: { wavelengthM: num(fre.wavelength_m), rangeM: num(fre.range_m), r1AtRidgeM: num(fre.r1_at_ridge_m), dEndM: dEnd },
    diffraction: {
      knifeEdgeDb: num(dif.knife_edge_db),
      correctionDb: margin === null ? null : num(currentDif.correction_db),
      correctionUncertaintyDb: margin === null ? null : num(currentDif.correction_uncertainty_db),
      correctionLabel: str(dif.correction_label),
      lossDb: margin === null ? null : num(currentDif.diffraction_loss_db),
      multipathApplicable: currentDif.multipath_applicable === true,
      multipathGainDb: numOrNull(currentDif.multipath_gain_db),
      multipathReason: typeof currentDif.multipath_reason === 'string' ? currentDif.multipath_reason : null,
      totalLossDb: margin === null ? null : num(currentDif.total_loss_db),
    },
    link: {
      rateBps: num(lnk.rate_bps),
      margin,
      state: margin === null && st !== 'blocked' ? 'unknown' : st,
      stateLabel: str(lnk.state_label),
      geometricVisible: lnk.geometric_visible === true,
      fsplDb: num(lnk.fspl_db),
      station: str(lnk.station),
    },
    raw: { ...o, link: { ...lnk, margin_db: margin, state: margin === null && st !== 'blocked' ? 'unknown' : st }, diffraction: currentDif },
    tags: Object.fromEntries(Object.entries(tags).filter((kv): kv is [string, string] => typeof kv[1] === 'string')),
    limits,
    disclaimer: typeof o.disclaimer === 'string' ? o.disclaimer : '',
  };
}

/* --------------------------------------------------- richieste --------------------------------------------------- */

export function sceneUrl(p: SceneParams, allowDownload = false): string {
  const q = new URLSearchParams({
    site: p.site,
    t: isoUtc(p.ms),
    station: p.station,
    gain_dbi: String(p.gain),
    rate_bps: String(p.rate),
    antenna_height_m: String(p.mast),
  });
  if (p.customSite) {
    q.set('lat_deg', String(p.customSite.lat_deg));
    q.set('lon_deg_east', String(p.customSite.lon_deg_east));
    q.set('name', p.customSite.name);
  }
  if (allowDownload) q.set('allow_download', 'true');
  return `/api/raven/scene?${q.toString()}`;
}

type Fetch = typeof fetch;

export async function fetchScene(p: SceneParams, signal?: AbortSignal, f: Fetch = fetch): Promise<LanderScene> {
  let res: Response;
  try {
    res = await f(sceneUrl(p), signal ? { signal } : {});
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new SceneError('network', 'Servizio non raggiungibile.');
  }
  if (res.status === 409) {
    // terreno di un sito personalizzato da scaricare: serve la conferma dell'utente (stima nel corpo)
    let estimate: TerrainEstimate | undefined;
    try {
      estimate = ((await res.json()) as { estimate?: TerrainEstimate }).estimate;
    } catch {
      /* corpo non JSON */
    }
    const yes = estimate ? await askTerrainConfirm(estimate) : false;
    if (!yes) throw new SceneError('unavailable', 'Dati del terreno di questo sito non scaricati.');
    try {
      res = await f(sceneUrl(p, true), signal ? { signal } : {});
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') throw e;
      throw new SceneError('network', 'Servizio non raggiungibile.');
    }
  }
  if (res.status === 413) throw new SceneError('range', 'Dati del terreno oltre il tetto per questo sito.');
  if (res.status === 422) {
    let detail = '';
    try {
      detail = String(((await res.json()) as { detail?: unknown }).detail ?? '');
    } catch {
      /* corpo non JSON */
    }
    if (detail.includes('DEM')) throw new SceneError('coverage', 'Sito fuori copertura DEM: il terreno LOLA non esiste qui e non viene inventato.');
    throw new SceneError('range', 'Istante o parametri non validi per il servizio.');
  }
  if (res.status === 503 || res.status === 429) {
    let detail = '';
    try {
      detail = String(((await res.json()) as { detail?: unknown }).detail ?? '');
    } catch {
      /* corpo non JSON */
    }
    if (detail.includes('troppe') || res.status === 429) throw new SceneError('busy', 'Servizio occupato: nuovo tentativo tra poco.');
    throw new SceneError('unavailable', 'Dati del terreno o effemeridi non disponibili in questo momento.');
  }
  if (!res.ok) throw new SceneError('unavailable', 'Scena non disponibile.');
  let json: unknown;
  try {
    json = await res.json();
  } catch {
    throw bad();
  }
  return parseScene(json);
}

export const SCENE_MIN_INTERVAL_MS = 500;
const CACHE_MAX = 24;

export interface SceneClientOptions {
  fetcher?: (p: SceneParams, signal: AbortSignal) => Promise<LanderScene>;
  minIntervalMs?: number;
  onScene: (s: LanderScene, p: SceneParams) => void;
  onError: (e: SceneError, p: SceneParams) => void;
  onBusy?: (busy: boolean) => void;
}

const keyOf = (p: SceneParams) => `${Math.floor(p.ms / 1000)}|${p.site}|${p.station}|${p.gain}|${p.rate}|${p.mast}|${JSON.stringify(p.customSite ?? null)}`;

/**
 * L'ultimo scenario voluto vince (leading + trailing, al massimo una richiesta ogni `minIntervalMs`); una richiesta
 * nuova annulla quella in corso e le risposte superate sono scartate; uno scenario gia' calcolato esce dalla cache.
 */
export class SceneClient {
  private readonly fetcher: NonNullable<SceneClientOptions['fetcher']>;
  private readonly minMs: number;
  private want: SceneParams | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private lastStart = -Infinity;
  private ctl: AbortController | null = null;
  private seq = 0;
  private readonly cache = new Map<string, LanderScene>();
  private disposed = false;
  fetches = 0;

  constructor(private readonly o: SceneClientOptions) {
    this.fetcher = o.fetcher ?? ((p, sig) => fetchScene(p, sig));
    this.minMs = o.minIntervalMs ?? SCENE_MIN_INTERVAL_MS;
  }

  request(p: SceneParams): void {
    if (this.disposed || !Number.isFinite(p.ms)) return;
    if (this.ctl !== null) {
      this.ctl.abort();
      this.ctl = null;
      this.seq++;
      this.o.onBusy?.(false);
    }
    this.want = p;
    const hit = this.cache.get(keyOf(p));
    if (hit) {
      this.seq++;
      if (this.timer !== null) clearTimeout(this.timer);
      this.timer = null;
      this.want = null;
      this.o.onBusy?.(false);
      this.o.onScene(hit, p);
      return;
    }
    if (this.timer !== null) return;
    const wait = Math.max(0, this.lastStart + this.minMs - Date.now());
    this.timer = setTimeout(() => {
      this.timer = null;
      this.fire();
    }, wait);
  }

  private fire(): void {
    const p = this.want;
    this.want = null;
    if (!p || this.disposed) return;
    this.ctl?.abort();
    const ctl = new AbortController();
    this.ctl = ctl;
    const my = ++this.seq;
    this.lastStart = Date.now();
    this.fetches++;
    this.o.onBusy?.(true);
    this.fetcher(p, ctl.signal).then(
      (s) => {
        if (this.disposed || my !== this.seq) return;
        this.ctl = null;
        this.cache.set(keyOf(p), s);
        if (this.cache.size > CACHE_MAX) this.cache.delete(this.cache.keys().next().value as string);
        this.o.onBusy?.(false);
        this.o.onScene(s, p);
      },
      (e: unknown) => {
        if (this.disposed || my !== this.seq) return;
        this.ctl = null;
        this.o.onBusy?.(false);
        if (e instanceof DOMException && e.name === 'AbortError') return;
        this.o.onError(e instanceof SceneError ? e : new SceneError('unavailable', 'Scena non disponibile.'), p);
      },
    );
  }

  cancel(): void {
    this.ctl?.abort();
    this.ctl = null;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.want = null;
    this.seq++;
  }

  dispose(): void {
    this.cancel();
    this.disposed = true;
  }
}

/* ------------------------------------------------- geometria ------------------------------------------------- */

/** Raggio della n-esima zona di Fresnel, CB79 sez. 2.3 eq. (2): sqrt(n lambda d1 d2 / (d1 + d2)). */
export function fresnelRadius(n: number, wavelengthM: number, d1M: number, d2M: number): number {
  if (!(d1M > 0) || !(d2M > 0) || !(wavelengthM > 0) || n < 1) return 0;
  return Math.sqrt((n * wavelengthM * d1M * d2M) / (d1M + d2M));
}

/** Raggio della prima zona alla distanza `dM` dall'antenna sulla linea di vista (Terra a `rangeM`). */
export function fresnelAt(s: Pick<LanderScene, 'fresnel'>, dM: number): number {
  return fresnelRadius(1, s.fresnel.wavelengthM, dM, s.fresnel.rangeM - dM);
}

export interface StateInfo {
  state: LinkState;
  label: string;
  /** Colore del disegno (verde/ambra/rosso) e simbolo: lo stato e' sempre scritto, mai solo colore. */
  color: string;
  rgb: [number, number, number];
  symbol: string;
  help: string;
}

export const STATE_INFO: Record<LinkState, StateInfo> = {
  open: { state: 'open', label: 'Aperto', color: '#30d158', rgb: [0.19, 0.82, 0.35], symbol: '●', help: 'margine >= 0 e centro della Terra sopra il crinale' },
  transition: { state: 'transition', label: 'Transizione', color: '#ffb340', rgb: [1, 0.7, 0.25], symbol: '◐', help: 'margine >= 0 ma il crinale blocca la linea di vista geometrica: il link chiude per diffrazione' },
  blocked: { state: 'blocked', label: 'Bloccato', color: '#ff6961', rgb: [1, 0.41, 0.38], symbol: '✕', help: 'margine < 0 al bit-rate scelto, oppure terreno lontano che blocca il link' },
  unknown: { state: 'unknown', label: 'Ignoto', color: '#a1a1aa', rgb: [0.63, 0.63, 0.67], symbol: '?', help: 'margine non calcolabile nel modello corrente' },
};

export interface Pointing {
  errorDeg: number;
  lossDb: number;
  /** Errore oltre meta' HPBW: il cono diventa rosso. */
  beyond: boolean;
  /** Margine del link con la perdita di puntamento aggiunta (l'API calcola con errore 0). */
  marginDb: number | null;
  state: LinkState;
}

export function pointing(s: LanderScene, errorDeg: number): Pointing {
  const err = Math.max(0, errorDeg);
  const ratio = s.antenna.hpbwDeg > 0 ? err / s.antenna.hpbwDeg : 0;
  const loss = s.antenna.pointingDbPerX2 * ratio * ratio;
  const margin = s.link.margin === null ? null : s.link.margin - loss;
  const state: LinkState = margin === null ? s.link.state
    : margin < 0 ? 'blocked' : s.link.geometricVisible ? 'open' : 'transition';
  return { errorDeg: err, lossDb: loss, beyond: err > s.antenna.hpbwDeg / 2, marginDb: margin, state };
}

/** Direzione (e, u) dell'asse del fascio: la direzione della Terra ruotata verso l'alto di `errorDeg`. */
export function beamDirection(earthElDeg: number, errorDeg: number): [number, number] {
  const a = ((earthElDeg + errorDeg) * Math.PI) / 180;
  return [Math.cos(a), Math.sin(a)];
}

/** Frazione della prima zona di Fresnel occupata dal crinale: h/r1 (h sopra la linea di vista); > 1 = oltre il raggio. */
export function ridgeObstruction(s: LanderScene): number {
  const r1 = s.fresnel.r1AtRidgeM;
  return r1 > 0 ? s.ridge.heightAboveLosM / r1 : 0;
}

/* ------------------------------------------------- luce del Sole ------------------------------------------------- */

export interface SunLocal {
  elDeg: number;
  /** Azimut da Nord in senso orario. */
  azDeg: number;
  /** Versore verso il Sole nel riferimento della scena (e avanti verso la Terra, n a sinistra, u in alto). */
  dir: [number, number, number];
}

/**
 * Direzione del Sole al sito. `bodyDir` e' il versore corpo -> Sole negli assi del visualizzatore (x verso 90 Est, y
 * Nord, z verso lon 0, vedi `localDirToBody`); `earthAzDeg` orienta l'asse e della scena.
 */
export function sunLocal(latDeg: number, lonDeg: number, bodyDir: readonly [number, number, number], earthAzDeg: number): SunLocal {
  const la = (latDeg * Math.PI) / 180;
  const lo = (lonDeg * Math.PI) / 180;
  const east = [Math.cos(lo), 0, -Math.sin(lo)];
  const north = [-Math.sin(la) * Math.sin(lo), Math.cos(la), -Math.sin(la) * Math.cos(lo)];
  const up = [Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)];
  const dot = (v: number[]) => v[0]! * bodyDir[0] + v[1]! * bodyDir[1] + v[2]! * bodyDir[2];
  const de = dot(east);
  const dn = dot(north);
  const du = dot(up);
  const az = Math.atan2(de, dn);
  const rel = az - (earthAzDeg * Math.PI) / 180; // oraria dalla direzione della Terra
  const h = Math.hypot(de, dn);
  const dir: [number, number, number] = [h * Math.cos(rel), -h * Math.sin(rel), du];
  return { elDeg: (Math.asin(Math.max(-1, Math.min(1, du))) * 180) / Math.PI, azDeg: (((az * 180) / Math.PI) % 360 + 360) % 360, dir };
}

/** Luce di ripiego: Sole basso (1,5 gradi) dietro l'osservatore: dichiarata in pagina come non reale. */
export const FALLBACK_SUN: SunLocal = { elDeg: 1.5, azDeg: NaN, dir: [Math.cos((1.5 * Math.PI) / 180) * Math.cos(0.9), -Math.cos((1.5 * Math.PI) / 180) * Math.sin(0.9), Math.sin((1.5 * Math.PI) / 180)] };

/* ---------------------------------------------- testo ed esportazione ---------------------------------------------- */

const f = (v: number | null, d = 2) => v === null ? '?' : v.toFixed(d).replace('.', ',');

export function rateText(bps: number): string {
  return bps >= 1e6 ? `${f(bps / 1e6, bps % 1e6 ? 1 : 0)} Mbit/s` : `${f(bps / 1e3, 0)} kbit/s`;
}

/** Descrizione testuale completa (alternativa alla grafica): tutti i numeri della scena. */
export function textAlternative(s: LanderScene, p: Pointing, sun: SunLocal | null, sunReal: boolean, language: 'it' | 'en' = 'it'): string {
  if (language === 'en') {
    const f = (value: number | null, digits = 2) => value === null ? '?' : value.toFixed(digits);
    const above = (value: number) => value >= 0 ? 'above' : 'below';
    const states = { open: 'open', transition: 'transition', blocked: 'blocked', unknown: 'unknown' } as const;
    const parts = [
      `Lander scene at site ${s.site.id ?? 'selected'} on ${s.tUtc.replace('T', ' ').replace('Z', ' UTC')}.`,
      `Earth is at ${f(s.earth.elDeg, 2)} degrees relative to the horizon, azimuth ${f(s.earth.azDeg, 1)} degrees, distance ${Math.round(s.earth.rangeKm).toLocaleString('en-US')} km.`,
      `The dominant ridge is ${f(s.ridge.arcDistanceM, 0)} m from the antenna along the ground, ${f(Math.abs(s.ridge.heightAboveLosM), 1)} m ${above(s.ridge.heightAboveLosM)} the line of sight; its top appears at ${f(s.ridge.tipElevationDeg, 2)} degrees, ${f(Math.abs(s.ridge.angleAboveLosDeg), 2)} degrees ${above(s.ridge.angleAboveLosDeg)} Earth. Parameter nu ${f(s.ridge.nu, 2)}.`,
      `The first Fresnel zone radius at the ridge is ${f(s.fresnel.r1AtRidgeM, 2)} m (wavelength ${f(s.fresnel.wavelengthM * 100, 2)} cm); the ridge occupies ${f(ridgeObstruction(s) * 100, 0)} percent of that radius.`,
      `Diffraction loss: knife edge ${f(s.diffraction.knifeEdgeDb, 2)} dB, ridge correction ${f(s.diffraction.correctionDb, 2)} dB (${s.diffraction.correctionLabel}), total ${f(s.diffraction.lossDb, 2)} dB.`,
      s.diffraction.multipathApplicable ? `Multipath term ${f(s.diffraction.multipathGainDb ?? 0, 2)} dB.` : `Multipath term not applicable${s.diffraction.multipathReason ? `: ${s.diffraction.multipathReason}` : ''}.`,
      `Link margin at ${s.link.rateBps >= 1e6 ? `${f(s.link.rateBps / 1e6, s.link.rateBps % 1e6 ? 1 : 0)} Mbit/s` : `${f(s.link.rateBps / 1e3, 0)} kbit/s`}: ${f(s.link.margin, 2)} dB, state ${states[s.link.state]}.`,
      `Antenna height ${f(s.antenna.mastM, 1)} m (tag ${s.antenna.mastTag}), gain ${f(s.antenna.gainDbi, 1)} dBi, HPBW ${f(s.antenna.hpbwDeg, 1)} degrees; pointing error ${f(p.errorDeg, 1)} degrees, loss ${f(p.lossDb, 2)} dB, ${p.beyond ? 'beyond' : 'within'} half HPBW; pointing margin ${f(p.marginDb, 2)} dB.`,
    ];
    if (sun) parts.push(sunReal ? `Sun ${f(sun.elDeg, 2)} degrees above the horizon (actual illumination).` : `Fallback grazing light at ${f(sun.elDeg, 1)} degrees, not the actual Sun.`);
    parts.push(`Terrain: ${s.terrain.label}${s.terrain.synthetic ? ' (synthetic test profile)' : ''}.`);
    return parts.join(' ');
  }
  const parts = [
    `Scena del lander al sito ${s.site.id ?? 'scelto'} il ${s.tUtc.replace('T', ' ').replace('Z', ' UTC')}.`,
    `La Terra e' a ${f(s.earth.elDeg, 2)} gradi sull'orizzonte, azimut ${f(s.earth.azDeg, 1)} gradi, distanza ${Math.round(s.earth.rangeKm).toLocaleString('it-IT')} km.`,
    `Il crinale dominante e' a ${f(s.ridge.arcDistanceM, 0)} m dall'antenna lungo il terreno, ${f(s.ridge.heightAboveLosM, 1)} m ${s.ridge.heightAboveLosM >= 0 ? 'sopra' : 'sotto'} la linea di vista; la cima appare a ${f(s.ridge.tipElevationDeg, 2)} gradi, ${f(Math.abs(s.ridge.angleAboveLosDeg), 2)} gradi ${s.ridge.angleAboveLosDeg >= 0 ? 'sopra' : 'sotto'} la Terra. Parametro nu ${f(s.ridge.nu, 2)}.`,
    `Raggio della prima zona di Fresnel al crinale ${f(s.fresnel.r1AtRidgeM, 2)} m (lunghezza d'onda ${f(s.fresnel.wavelengthM * 100, 2)} cm); il crinale occupa ${f(ridgeObstruction(s) * 100, 0)} per cento di quel raggio.`,
    `Perdita di diffrazione: bordo a lama ${f(s.diffraction.knifeEdgeDb, 2)} dB, correzione della cresta ${f(s.diffraction.correctionDb, 2)} dB (${s.diffraction.correctionLabel}), totale ${f(s.diffraction.lossDb, 2)} dB.`,
    s.diffraction.multipathApplicable ? `Termine multipath ${f(s.diffraction.multipathGainDb ?? 0, 2)} dB.` : `Termine multipath non applicabile${s.diffraction.multipathReason ? `: ${s.diffraction.multipathReason}` : ''}.`,
    `Margine di link a ${rateText(s.link.rateBps)}: ${f(s.link.margin, 2)} dB, stato ${STATE_INFO[s.link.state].label.toLowerCase()}.`,
    `Antenna a ${f(s.antenna.mastM, 1)} m di altezza (tag ${s.antenna.mastTag}), guadagno ${f(s.antenna.gainDbi, 1)} dBi, HPBW ${f(s.antenna.hpbwDeg, 1)} gradi; errore di puntamento ${f(p.errorDeg, 1)} gradi, perdita ${f(p.lossDb, 2)} dB, ${p.beyond ? 'oltre' : 'entro'} meta' HPBW; margine con puntamento ${f(p.marginDb, 2)} dB.`,
  ];
  if (sun) parts.push(sunReal ? `Sole a ${f(sun.elDeg, 2)} gradi sull'orizzonte (luce reale).` : `Luce radente di ripiego a ${f(sun.elDeg, 1)} gradi, non il Sole reale.`);
  parts.push(`Terreno: ${s.terrain.label}${s.terrain.synthetic ? ' (profilo sintetico di prova)' : ''}.`);
  return parts.join(' ');
}

export interface ExportExtras {
  pointingErrorDeg: number;
  verticalExaggeration: number;
  tubeScale: number;
  sunReal: boolean;
  sunElevationDeg: number | null;
}

/** Numeri della scena (senza il campo di quote completo: solo le sue dimensioni) per l'esportazione JSON. */
export function sceneJson(s: LanderScene, extras: ExportExtras): string {
  const p = pointing(s, extras.pointingErrorDeg);
  const rawTerrain = rec(s.raw.terrain);
  const rawPatch = rawTerrain.patch === null || rawTerrain.patch === undefined ? null : rec(rawTerrain.patch);
  let patch: Record<string, unknown> | null = null;
  if (rawPatch) {
    const { height_m: _heights, ...rest } = rawPatch;
    patch = { ...rest, posts: s.terrain.patch ? s.terrain.patch.n * s.terrain.patch.n : 0 };
  }
  const out = {
    ...s.raw,
    terrain: { ...rawTerrain, patch },
    fresnel: { ...rec(s.raw.fresnel), obstruction_h_over_r1: ridgeObstruction(s) },
    pointing: { error_deg: p.errorDeg, loss_db: p.lossDb, beyond_half_hpbw: p.beyond, margin_with_pointing_db: p.marginDb, state: p.state },
    drawing: { vertical_exaggeration: extras.verticalExaggeration, fresnel_tube_scale: extras.tubeScale, sun_real: extras.sunReal, sun_elevation_deg: extras.sunElevationDeg },
  };
  return JSON.stringify(out, null, 2);
}
