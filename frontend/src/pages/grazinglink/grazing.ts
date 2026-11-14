// SPDX-License-Identifier: Apache-2.0
// Logica pura della pagina GrazingLink: contratto di /api/raven/experiments/* (backend/api/grazing_routes.py), costruzione
// della richiesta, profilo del terreno da CSV, finestre geometrica e reale, mappa di calore, curve di diffrazione,
// esportazioni. Nessun accesso al DOM (tranne downloadText).

export type ParamStatus = 'V' | 'D' | 'I';
export type Series = (number | null)[];

export interface Site {
  id: string;
  name: string;
  lat_deg: number;
  lon_deg_east: number;
  dem_covered: boolean;
}
export interface Limits {
  days_max: number;
  step_min_min: number;
  max_profile_points: number;
  max_samples: number;
}
export interface Status {
  dem: {
    available: boolean;
    cached_tiles: number;
    mode: string;
    product: { id: string; coverage: string; coverage_north_limit_deg?: number; credit: string; url: string };
    hint: string;
  };
  ephemeris: { available: boolean; supported_range?: { start_utc: string; end_utc: string } | null };
  sites: Site[];
  limits: Limits;
  disclaimer: string;
}
export interface ParamRow {
  key: string;
  value: number | string;
  unit: string;
  min?: number | null;
  max?: number | null;
  status: ParamStatus;
  source: string;
  note?: string;
}
export interface Station {
  key: string;
  name: string;
  diameter_m: number;
  gain_dbi: number;
  gain_tag: string;
  gain_source?: string;
}
export interface Defaults {
  parameters: ParamRow[];
  stations: Station[];
  rates_bps: number[];
  k_values: number[];
  declared_limits: string[];
  disclaimer: string;
}
export interface TradeRow {
  k: number;
  backoff_db: number;
  declared_steps: number;
  outages: number;
  outage_pct: number;
  gaussian_outage_pct: number;
  scheduled_bits: number;
  delivered_bits: number;
  relative_data: number | null;
  mean_rate_bps: number;
}
export interface Gimbal {
  hpbw_deg: number;
  excursion_deg: number;
  fixed_mount_loss_db: number;
  max_loss_budget_db: number;
  max_error_for_budget_deg: number;
  gimbal_needed: boolean;
}
export interface AnalysisResult {
  label: string;
  window: { start_utc: string; days: number; step_min: number; n_steps: number };
  site: { id: string | null; lat_deg: number | null; lon_deg_east: number | null };
  series_time_unix: number[];
  series_step_min: number;
  series: Record<string, Series | Series[]>;
  rates_bps: number[];
  windows: {
    rate_bps: number;
    geometric_hours: number;
    real_hours: number;
    transition_hours: number;
    geometric_not_closing_hours: number;
    both_hours: number;
    total_hours: number;
    geometric_intervals_unix: number[][];
    real_intervals_unix: number[][];
    transition_intervals_unix: number[][];
    rule: string;
  };
  compensator: { k: number; sigma_db: number; chosen: TradeRow; tradeoff: TradeRow[]; note: string };
  antenna: {
    station: Station;
    diameter_m: number;
    rover_gain_dbi: number;
    hpbw_script_70_deg: number;
    hpbw_uniform_deg: number;
    mount: string;
    gimbal_mechanical_limit_fraction?: number | null;
    gimbal: Gimbal;
    libration_excursion_deg: number;
    pointing_loss_max_db: number;
    pointing_script_minus_gaussian_max_db: number;
    note: string;
  };
  flags: {
    terrain: { source: string; synthetic: boolean; label: string; product_id: string | null; spacing_m: number };
    geometry_source: string;
    radius_resolved: boolean;
    radius_resolved_fraction: number;
    ridge_radius_median_m: number | null;
    multipath: { applicable_fraction: number; status: string; enabled: boolean; reason_not_applicable: string };
    correction: {
      status: string;
      steps_with_radius: number;
      anomaly_steps: number;
      clamped_steps: number;
      geometry_extrapolated_steps: number;
      max_uncertainty_db: number;
      label: string;
    };
    blocked_fraction: number;
    earth_below_horizon_fraction: number;
  };
  parameters: ParamRow[];
  declared_limits: string[];
  correction_inconsistency: { text: string; status: string; table_max_db: number; p526_max_db: number; jpl226_claim_db: number; policy?: string };
}
export interface Compensation {
  nu: number[];
  radius_m: number[];
  correction_db: number[][];
  oscillation_envelope_db: number[][];
  anomaly: number[][];
  info: { version: string; status: string; file_sha256: string };
  inconsistency: { status: string; text: string };
}
export interface Dish {
  diameter_m: number;
  gain_dbi: number;
  hpbw_script_70_deg: number;
  hpbw_uniform_deg: number;
  hpbw_ratio: number;
  pointing: {
    err_deg: number;
    script_db: number;
    gaussian_hpbw70_db: number;
    gaussian_hpbw_uniform_db: number;
    airy_exact_db: number;
    constant_difference_db: number;
  }[];
  gimbal: Gimbal;
}
export interface AntennaReport {
  frequency_ghz: number;
  dishes: Dish[];
  required_gain: { rate_bps: number; required_gain_dbi: number; type: string; diameter_m: number | null; hpbw_script_deg: number | null }[];
  excursion_deg: number;
  note: string;
}

/* ---------------------------------- profilo da CSV ---------------------------------- */

export const MAX_PROFILE_BYTES = 60_000; // il corpo massimo dell'API e' 64 KiB
export const MAX_PROFILE_POINTS = 1500;

export interface Profile {
  distance_m: number[];
  height_m: number[];
}
export type ProfileParse = { ok: true; profile: Profile } | { ok: false; error: string };

/** CSV `distanza_m,quota_m` (separatori , ; tab o spazio; intestazione e righe # ignorate). Regole come l'API. */
export function parseProfileCsv(text: string, maxPoints = MAX_PROFILE_POINTS): ProfileParse {
  if (text.length > MAX_PROFILE_BYTES) return { ok: false, error: `File troppo grande (massimo ${MAX_PROFILE_BYTES / 1000} kB).` };
  const d: number[] = [];
  const h: number[] = [];
  let header = true;
  const lines = text.replace(/^﻿/, '').split(/\r\n|\n|\r/);
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] ?? '').trim();
    if (line === '' || line.startsWith('#')) continue;
    const cells = line.split(/[,;\t ]+/).filter((c) => c !== '');
    const nums = cells.map(Number);
    if (cells.length !== 2 || nums.some((v) => !Number.isFinite(v))) {
      if (header && d.length === 0) {
        header = false; // la prima riga non numerica e' l'intestazione
        continue;
      }
      return { ok: false, error: `Riga ${i + 1}: servono due numeri (distanza in m, quota in m).` };
    }
    header = false;
    const [x, z] = nums as [number, number];
    if (d.length === 0 && x !== 0) return { ok: false, error: `Riga ${i + 1}: la prima distanza deve essere 0.` };
    const prev = d[d.length - 1];
    if (prev !== undefined && x <= prev) return { ok: false, error: `Riga ${i + 1}: le distanze devono crescere.` };
    if (x > 100_000) return { ok: false, error: `Riga ${i + 1}: distanza oltre 100 km.` };
    if (z < -20_000 || z > 20_000) return { ok: false, error: `Riga ${i + 1}: quota fuori da ±20 km.` };
    if (d.length >= maxPoints) return { ok: false, error: `Troppi punti (massimo ${maxPoints}).` };
    d.push(x);
    h.push(z);
  }
  if (d.length < 2) return { ok: false, error: 'Servono almeno due punti.' };
  return { ok: true, profile: { distance_m: d, height_m: h } };
}

/** Crinale parabolico di prova (SOLO per provare la pagina): terreno piano a 0 m, cresta a 500 m alta 12 m, R = 100 m. */
export function syntheticRidgeCsv(): string {
  const rows = ['distance_m,height_m'];
  for (let x = 0; x <= 1000; x += 10) rows.push(`${x},${Math.max(12 - (x - 500) ** 2 / 200, 0).toFixed(3)}`);
  return rows.join('\n') + '\n';
}

/* ------------------------------------ richiesta ------------------------------------ */

export const DEFAULT_START = '2027-04-07T00:00';
export const RATE_DEFAULT = 1e5;
export const MAIN_KEYS = ['tx_power_dbw', 'tx_gain_dbi', 'rate_bps', 'compensator_k'] as const;
/** Chiavi che il modulo gestisce a parte (non vanno nell'elenco degli altri parametri). */
const OWN_KEYS = new Set<string>([...MAIN_KEYS, 'window_days', 'window_step_min']);

export interface Form {
  siteId: string;
  start: string;
  days: number | null;
  stepMin: number | null;
  station: 'dsn34' | 'dsn18';
  mount?: 'tracking' | 'fixed' | 'gimbal';
  rate: number;
  profile: Profile | null;
  sweep: boolean;
  elStart: number | null;
  elEnd: number | null;
  /** valori dei parametri numerici (chiave -> valore); null = campo vuoto */
  values: Record<string, number | null>;
}
export interface AnalyzeRequest {
  site_id?: string;
  start_utc: string;
  days: number;
  step_min: number;
  overrides: Record<string, number | string>;
  profile?: Profile;
  earth_sweep?: { el_start_deg: number; el_end_deg: number };
}
export interface FormErrors {
  [field: string]: string | undefined;
}

export const extraParams = (rows: ParamRow[]): ParamRow[] =>
  rows.filter((r) => r.status === 'I' && typeof r.value === 'number' && !OWN_KEYS.has(r.key));
export const initialValues = (rows: ParamRow[]): Record<string, number | null> =>
  Object.fromEntries(rows.filter((r) => typeof r.value === 'number').map((r) => [r.key, r.value as number]));

/** Data e ora UTC con secondi facoltativi -> ISO UTC con secondi; null se non valida. */
export function toStartUtc(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local);
  if (!m) return null;
  const [y, mo, d, h, mi] = [1, 2, 3, 4, 5].map((i) => Number(m[i]));
  const seconds = Number(m[6] ?? '0');
  const t = new Date(Date.UTC(y!, mo! - 1, d!, h!, mi!));
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo! - 1 || t.getUTCDate() !== d || h! > 23 || mi! > 59 || seconds > 59) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] ?? '00'}Z`;
}

export function validateForm(f: Form, rows: ParamRow[], st: Pick<Status, 'sites' | 'limits'>): FormErrors {
  const e: FormErrors = {};
  if (toStartUtc(f.start) === null) e.start = 'Data e ora UTC non valide.';
  const dmax = st.limits.days_max;
  if (f.days === null || !Number.isFinite(f.days) || f.days <= 0 || f.days > dmax) e.days = `Durata tra 0 (escluso) e ${dmax} giorni.`;
  if (f.stepMin === null || !Number.isFinite(f.stepMin) || f.stepMin < st.limits.step_min_min || f.stepMin > 1440)
    e.step = `Passo tra ${st.limits.step_min_min} e 1440 minuti.`;
  if (f.days !== null && f.stepMin !== null && !e.days && !e.step && (f.days * 1440) / f.stepMin > st.limits.max_samples)
    e.step = `Troppi istanti (massimo ${st.limits.max_samples}): aumenta il passo o riduci la durata.`;
  if (f.sweep) {
    if (!f.profile) e.profile = 'Lo spazzolamento della Terra richiede un profilo del terreno.';
    for (const [k, v] of [['elStart', f.elStart], ['elEnd', f.elEnd]] as const)
      if (v === null || !Number.isFinite(v) || v < -30 || v > 60) e[k] = 'Elevazione tra -30 e 60 gradi.';
  } else {
    const s = st.sites.find((x) => x.id === f.siteId);
    if (!s) e.site = 'Scegli un sito.';
    else if (!s.dem_covered && !f.profile) e.site = 'Sito fuori copertura DEM: carica un profilo del terreno o scegli un sito coperto.';
  }
  for (const r of rows) {
    if (r.status !== 'I' || typeof r.value !== 'number') continue;
    const v = f.values[r.key];
    if (v === null || v === undefined || !Number.isFinite(v)) e[`p-${r.key}`] = 'Inserisci un numero.';
    else if (r.min != null && v < r.min) e[`p-${r.key}`] = `Minimo ${r.min}.`;
    else if (r.max != null && v > r.max) e[`p-${r.key}`] = `Massimo ${r.max}.`;
  }
  return e;
}

export function buildRequest(f: Form, rows: ParamRow[]): AnalyzeRequest {
  const start = toStartUtc(f.start);
  if (start === null || f.days === null || f.stepMin === null) throw new Error('modulo non valido');
  const overrides: Record<string, number | string> = { station: f.station, rate_bps: f.rate };
  if (f.mount && f.mount !== 'tracking') overrides.mount = f.mount;
  for (const r of rows) {
    const v = f.values[r.key];
    if (r.status === 'I' && typeof r.value === 'number' && r.key !== 'rate_bps' && v !== null && v !== undefined && v !== r.value) overrides[r.key] = v;
  }
  const req: AnalyzeRequest = { start_utc: start, days: f.days, step_min: f.stepMin, overrides };
  if (f.sweep) req.earth_sweep = { el_start_deg: f.elStart ?? 0, el_end_deg: f.elEnd ?? 0 };
  else req.site_id = f.siteId;
  if (f.profile) req.profile = f.profile;
  return req;
}

/** Elenco di numeri da testo ("1e3, 1e4 ; 1e5"); null se vuoto, troppo lungo o non numerico. */
export function parseNumberList(text: string, lo: number, hi: number, maxLen = 12): number[] | null {
  const parts = text.split(/[\s,;]+/).filter((p) => p !== '');
  if (parts.length === 0 || parts.length > maxLen) return null;
  const nums = parts.map(Number);
  return nums.every((v) => Number.isFinite(v) && v >= lo && v <= hi) ? nums : null;
}

export interface AntennaRequest {
  station: string;
  frequency_ghz: number;
  eta: number;
  rates_bps: number[];
  diameters_m: number[];
  tx_power_dbw: number;
  tsys_k: number;
  ebn0_db: number;
  losses_db: number;
  distance_km: number;
  excursion_deg: number;
}
/** Richiesta /antenna coerente con l'analisi (stessi parametri usati, escursione dalla librazione calcolata). */
export function antennaRequest(res: AnalysisResult, station: string, rates: number[], diameters: number[]): AntennaRequest {
  const p = (k: string, d: number): number => {
    const v = res.parameters.find((x) => x.key === k)?.value;
    return typeof v === 'number' ? v : d;
  };
  const range = res.series.range_km as Series | undefined;
  const mid = (range ?? []).filter((v): v is number => v !== null && v >= 300_000 && v <= 450_000);
  return {
    station,
    frequency_ghz: p('frequency_ghz', 8.4),
    eta: p('antenna_eta', 0.55),
    rates_bps: rates,
    diameters_m: diameters,
    tx_power_dbw: p('tx_power_dbw', 10),
    tsys_k: p('tsys_k', 30),
    ebn0_db: p('ebn0_db', 2.5),
    losses_db: p('misc_loss_db', 3),
    distance_km: mid.length ? Math.round(mid.reduce((a, b) => a + b, 0) / mid.length) : 384_400,
    excursion_deg: Math.min(90, Math.max(0, Number(res.antenna.libration_excursion_deg.toFixed(3)))),
  };
}

/* ------------------------------------- rete ------------------------------------- */

export type ApiFailure = 'dem' | 'ephemeris' | 'gimbal' | 'busy' | 'coverage' | 'invalid' | 'server' | 'network';
export type ApiResult<T> = { ok: true; data: T } | { ok: false; kind: ApiFailure; message: string };

export const FAILURE_TEXT: Record<ApiFailure, string> = {
  dem: 'Dati LOLA non disponibili sul server: il terreno non si può calcolare e nessun risultato è stato inventato. Per scaricarli esegui «make grazing-dem» (tile in build/lola), oppure carica un tuo profilo del terreno.',
  ephemeris: 'Le efemeridi (kernel JPL) non sono disponibili sul server: l’analisi non si può calcolare. Riprova più tardi.',
  gimbal: 'Il simulatore gimbal C non è disponibile o non ha completato il calcolo. Controlla il server e compila con «make build-servo».',
  busy: 'Il server sta già eseguendo altre analisi. Attendi qualche secondo e riprova.',
  coverage: 'Sito fuori copertura DEM (il prodotto LOLA copre latitudini <= -85 gradi): scegli un sito coperto o carica un profilo.',
  invalid: 'Parametri non validi, oppure la data è fuori dall’intervallo coperto dalle efemeridi. Controlla i campi e riprova.',
  server: 'Errore interno del server durante il calcolo. Riprova con una finestra più breve.',
  network: 'Server non raggiungibile. Controlla la connessione e riprova.',
};

export async function classify(res: Response): Promise<ApiFailure> {
  let detail = '';
  try {
    const b = (await res.json()) as { detail?: unknown };
    if (typeof b.detail === 'string') detail = b.detail;
  } catch {
    /* corpo non JSON */
  }
  if (res.status === 503) return detail.includes('DEM') ? 'dem' : detail.includes('gimbal') ? 'gimbal' : detail.includes('troppe') ? 'busy' : 'ephemeris';
  if (res.status === 422) return detail.includes('copertura DEM') ? 'coverage' : 'invalid';
  if (res.status === 429) return 'busy';
  return 'server';
}

async function call<T>(f: typeof fetch, url: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await f(url, init);
  } catch {
    return { ok: false, kind: 'network', message: FAILURE_TEXT.network };
  }
  if (!res.ok) {
    const kind = await classify(res);
    return { ok: false, kind, message: FAILURE_TEXT[kind] };
  }
  try {
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, kind: 'server', message: FAILURE_TEXT.server };
  }
}
const post = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
  ...(signal ? { signal } : {}),
});
export const fetchStatus = (f: typeof fetch) => call<Status>(f, '/api/raven/experiments/status');
export const fetchDefaults = (f: typeof fetch) => call<Defaults>(f, '/api/raven/experiments/defaults');
export const fetchCompensation = (f: typeof fetch) => call<Compensation>(f, '/api/raven/compensation');
export const runAnalysis = (f: typeof fetch, r: AnalyzeRequest, s?: AbortSignal) => call<AnalysisResult>(f, '/api/raven/experiments/analyze', post(r, s));
export const runAntenna = (f: typeof fetch, r: AntennaRequest, s?: AbortSignal) => call<AntennaReport>(f, '/api/raven/experiments/antenna', post(r, s));

/* ----------------------------- finestre geometrica / reale ----------------------------- */

export interface WindowStats {
  total: number;
  geometric: number;
  real: number;
  transition: number;
  both: number;
  notClosing: number;
  /** ore in cui ne' la geometria ne' il link aprono */
  closed: number;
  geometricPct: number;
  realPct: number;
  transitionPct: number;
  /** le due barre: segmenti in percentuale del totale (somma 100) */
  geometricBar: { both: number; notClosing: number; blocked: number };
  realBar: { both: number; transition: number; closed: number };
}
const pc = (x: number, total: number) => (total > 0 ? (100 * x) / total : 0);

export function windowStats(w: AnalysisResult['windows']): WindowStats {
  const total = w.total_hours;
  const closedGeom = Math.max(total - w.geometric_hours, 0);
  const closedReal = Math.max(total - w.real_hours, 0);
  return {
    total,
    geometric: w.geometric_hours,
    real: w.real_hours,
    transition: w.transition_hours,
    both: w.both_hours,
    notClosing: w.geometric_not_closing_hours,
    closed: Math.max(total - w.both_hours - w.geometric_not_closing_hours - w.transition_hours, 0),
    geometricPct: pc(w.geometric_hours, total),
    realPct: pc(w.real_hours, total),
    transitionPct: pc(w.transition_hours, total),
    geometricBar: { both: pc(w.both_hours, total), notClosing: pc(w.geometric_not_closing_hours, total), blocked: pc(closedGeom, total) },
    realBar: { both: pc(w.both_hours, total), transition: pc(w.transition_hours, total), closed: pc(closedReal, total) },
  };
}

/** Intervalli [t0,t1] (unix) come posizione e larghezza in percentuale della finestra [a, b]. */
export function intervalSegments(iv: number[][], a: number, b: number): { left: number; width: number }[] {
  const span = b - a;
  if (!(span > 0)) return [];
  return iv.map(([s, e]) => {
    const l = Math.min(Math.max(((s ?? a) - a) / span, 0), 1);
    const r = Math.min(Math.max(((e ?? a) - a) / span, 0), 1);
    return { left: 100 * l, width: Math.max(100 * (r - l), 0.3) };
  });
}

export const hoursText = (h: number): string => `${h.toFixed(1).replace('.', ',')} h`;
export const pctText = (p: number): string => `${p.toFixed(1).replace('.', ',')} %`;

/* ----------------------------------- serie nel tempo ----------------------------------- */

const col = (a: Series | undefined, n: number): Float64Array => Float64Array.from({ length: n }, (_, i) => a?.[i] ?? NaN);
const flat = (v: Series | Series[] | undefined): Series | undefined => (Array.isArray(v) && Array.isArray(v[0]) ? undefined : (v as Series | undefined));

export interface TimeData {
  time: Float64Array;
  earthEl: Float64Array;
  ridgeEl: Float64Array;
  margins: Float64Array[];
  zero: Float64Array;
}
/** Elevazione della cresta vista dall'antenna = elevazione della Terra + angolo della cresta sopra la linea di vista. */
export function timeData(res: AnalysisResult): TimeData {
  const n = res.series_time_unix.length;
  const earth = col(flat(res.series.earth_el_deg), n);
  const above = col(flat(res.series.ridge_angle_above_los_deg), n);
  const by = (res.series.margin_by_rate_db ?? []) as Series[];
  return {
    time: Float64Array.from(res.series_time_unix),
    earthEl: earth,
    ridgeEl: earth.map((e, i) => e + (above[i] ?? NaN)),
    margins: res.rates_bps.map((_, j) => col(by[j], n)),
    zero: new Float64Array(n),
  };
}
export const rateLabel = (bps: number): string => (bps >= 1e6 ? `${bps / 1e6} Mbit/s` : `${bps / 1e3} kbit/s`);

/* -------------------------------------- diffrazione -------------------------------------- */

const HALF_PI = Math.PI / 2;
/**
 * Integrali di Fresnel C(x), S(x) (definizione di scipy.special.fresnel: argomento pi t^2 / 2). Serie di potenze per
 * |x| <= 1,5 e frazione continua di Lentz oltre (Numerical Recipes, 6.9), precisione ~1e-12 in doppia: sostituisce
 * l'integrazione di Simpson a passo fisso, imprecisa per |x| grande (l'integrando oscilla a frequenza pi x).
 */
export function fresnelCS(x: number): [number, number] {
  const ax = Math.abs(x);
  let c: number;
  let s: number;
  if (!Number.isFinite(ax)) return Number.isNaN(x) ? [NaN, NaN] : [Math.sign(x) * 0.5, Math.sign(x) * 0.5];
  if (ax < 1e-15) {
    c = ax;
    s = 0;
  } else if (ax <= 1.5) {
    let sum = 0;
    let sums = 0;
    let sumc = ax;
    let sign = 1;
    const fact = HALF_PI * ax * ax;
    let odd = true;
    let term = ax;
    let n = 3;
    for (let k = 1; k <= 200; k++) {
      term *= fact / k;
      sum += (sign * term) / n;
      const test = Math.abs(sum) * 1e-16;
      if (odd) {
        sign = -sign;
        sums = sum;
        sum = sumc;
      } else {
        sumc = sum;
        sum = sums;
      }
      if (term < test) break;
      odd = !odd;
      n += 2;
    }
    s = sums;
    c = sumc;
  } else {
    const pix2 = Math.PI * ax * ax;
    // numeri complessi come coppie [re, im]
    let br = 1;
    let bi = -pix2;
    let ccr = 1e300;
    let cci = 0;
    let den = br * br + bi * bi;
    let dr = br / den;
    let di = -bi / den;
    let hr = dr;
    let hi = di;
    let n = -1;
    for (let k = 2; k <= 300; k++) {
      n += 2;
      const a = -n * (n + 1);
      br += 4;
      // d = 1 / (a d + b)
      const xr = a * dr + br;
      const xi = a * di + bi;
      den = xr * xr + xi * xi;
      dr = xr / den;
      di = -xi / den;
      // cc = b + a / cc
      den = ccr * ccr + cci * cci;
      ccr = br + (a * ccr) / den;
      cci = bi - (a * cci) / den;
      const delr = ccr * dr - cci * di;
      const deli = ccr * di + cci * dr;
      const nhr = hr * delr - hi * deli;
      hi = hr * deli + hi * delr;
      hr = nhr;
      if (Math.abs(delr - 1) + Math.abs(deli) < 1e-15) break;
    }
    // h = (ax - j ax) h ; cs = (1+j)/2 (1 - e^{j pix2/2} h)
    const h2r = ax * hr + ax * hi;
    const h2i = ax * hi - ax * hr;
    const er = Math.cos(0.5 * pix2);
    const ei = Math.sin(0.5 * pix2);
    const tr = 1 - (er * h2r - ei * h2i);
    const ti = -(er * h2i + ei * h2r);
    c = 0.5 * (tr - ti);
    s = 0.5 * (ti + tr);
  }
  return x < 0 ? [-c, -s] : [c, s];
}
/** Perdita esatta del bordo a lama J(nu) in dB (positiva = attenuazione), come backend/domain/grazing/diffraction.py. */
export function knifeEdgeDb(nu: number): number {
  const [c, s] = fresnelCS(nu);
  const re = 0.5 - c;
  const im = -(0.5 - s);
  // (1+j)/2 * (re + j im)
  const mr = (re - im) / 2;
  const mi = (re + im) / 2;
  return -20 * Math.log10(Math.hypot(mr, mi));
}
/** P.526-9 eq. (27) per nu > -0,78; sotto tale soglia 0 è una scelta del codice. */
export function ituDb(nu: number): number {
  if (nu <= -0.78) return 0;
  const x = nu - 0.1;
  return 6.9 + 20 * Math.log10(Math.sqrt(x * x + 1) + x);
}

export interface DiffractionCurve {
  nu: Float64Array;
  exact: Float64Array;
  itu: Float64Array;
  /** punti di funzionamento: J esatto negli nu dell'analisi (NaN altrove) */
  points: Float64Array;
}
/** Curva su una griglia regolare unita agli nu di funzionamento (decimati a `maxPoints`). */
export function diffractionCurve(opNu: (number | null)[], lo = -2, hi = 4, step = 0.05, maxPoints = 120): DiffractionCurve {
  const clean = opNu.filter((v): v is number => v !== null && Number.isFinite(v));
  const stride = Math.max(1, Math.ceil(clean.length / maxPoints));
  const ops = clean.filter((_, i) => i % stride === 0);
  const lo2 = Math.min(lo, ...ops, hi);
  const hi2 = Math.max(hi, ...ops, lo);
  const grid = new Set<number>();
  for (let v = lo2; v <= hi2 + 1e-9; v += step) grid.add(Number(v.toFixed(4)));
  for (const v of ops) grid.add(Number(v.toFixed(4)));
  const xs = Float64Array.from([...grid].sort((a, b) => a - b));
  const opSet = new Set(ops.map((v) => Number(v.toFixed(4))));
  const exact = xs.map(knifeEdgeDb);
  return {
    nu: xs,
    exact,
    itu: xs.map(ituDb),
    points: exact.map((j, i) => (opSet.has(xs[i] as number) ? j : NaN)),
  };
}

/* --------------------------- mappa di calore della compensazione --------------------------- */

export interface HeatCell {
  ri: number;
  ni: number;
  nu: number;
  radius: number;
  value: number;
  envelope: number;
  anomaly: boolean;
  /** 0..1 rispetto al massimo della tabella */
  t: number;
}
export interface Heat {
  nu: number[];
  radius: number[];
  cells: HeatCell[];
  max: number;
  anomalies: number;
}
export function heatmap(c: Compensation): Heat {
  const max = Math.max(1e-9, ...c.correction_db.flat());
  const cells: HeatCell[] = [];
  c.radius_m.forEach((radius, ri) =>
    c.nu.forEach((nu, ni) => {
      const value = c.correction_db[ri]?.[ni] ?? NaN;
      cells.push({
        ri,
        ni,
        nu,
        radius,
        value,
        envelope: c.oscillation_envelope_db[ri]?.[ni] ?? 0,
        anomaly: (c.anomaly[ri]?.[ni] ?? 0) === 1,
        t: Math.min(Math.max(value / max, 0), 1),
      });
    }),
  );
  return { nu: c.nu, radius: c.radius_m, cells, max, anomalies: cells.filter((x) => x.anomaly).length };
}
/** Colonna della tabella piu' vicina a nu (per sottolineare la zona di funzionamento). */
export function nearestIndex(xs: number[], v: number): number {
  let best = 0;
  xs.forEach((x, i) => {
    if (Math.abs(x - v) < Math.abs((xs[best] ?? 0) - v)) best = i;
  });
  return best;
}
export function finiteRange(a: (number | null)[] | undefined): [number, number] | null {
  const v = (a ?? []).filter((x): x is number => x !== null && Number.isFinite(x));
  return v.length ? [Math.min(...v), Math.max(...v)] : null;
}

/* ---------------------------------------- compensatore ---------------------------------------- */

export interface TradeData {
  k: Float64Array;
  outage: Float64Array;
  data: Float64Array;
}
export function tradeData(rows: TradeRow[]): TradeData {
  const s = [...rows].sort((a, b) => a.k - b.k);
  return {
    k: Float64Array.from(s.map((r) => r.k)),
    outage: Float64Array.from(s.map((r) => r.outage_pct)),
    data: Float64Array.from(s.map((r) => (r.relative_data === null ? NaN : 100 * r.relative_data))),
  };
}
export function chosenRateData(res: AnalysisResult): { time: Float64Array; kbps: Float64Array } {
  const n = res.series_time_unix.length;
  return { time: Float64Array.from(res.series_time_unix), kbps: col(flat(res.series.chosen_rate_bps), n).map((v) => v / 1e3) };
}

/* ---------------------------------------- esportazione ---------------------------------------- */

const cell = (v: string | number | boolean | null | undefined): string => {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : '';
  let s = String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`; // difesa dalle formule dei fogli di calcolo
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export function toCsv(header: string[], rows: (string | number | boolean | null | undefined)[][]): string {
  return [header.join(','), ...rows.map((r) => r.map(cell).join(','))].join('\n') + '\n';
}

export function timeCsv(res: AnalysisResult): string {
  const t = timeData(res);
  const header = ['time_unix', 'earth_el_deg', 'ridge_el_deg', ...res.rates_bps.map((r) => `margin_db_${r}bps`)];
  const rows = Array.from(t.time, (u, i) => [u, t.earthEl[i], t.ridgeEl[i], ...t.margins.map((m) => m[i])]);
  return toCsv(header, rows);
}
export function windowsCsv(w: AnalysisResult['windows']): string {
  const s = windowStats(w);
  return toCsv(
    ['quantity', 'hours', 'percent_of_window'],
    [
      ['geometric_window', s.geometric, s.geometricPct],
      ['real_window', s.real, s.realPct],
      ['transition_geometry_blocked_link_closes', s.transition, s.transitionPct],
      ['geometric_visible_link_not_closing', s.notClosing, pc(s.notClosing, s.total)],
      ['both', s.both, pc(s.both, s.total)],
      ['total', s.total, 100],
    ],
  );
}
export function diffractionCsv(c: DiffractionCurve): string {
  return toCsv(['nu', 'knife_edge_exact_db', 'itu_p526_approx_db', 'operating_point_db'], Array.from(c.nu, (v, i) => [v, c.exact[i], c.itu[i], c.points[i]]));
}
export function heatCsv(h: Heat): string {
  return toCsv(
    ['radius_m', 'nu', 'correction_db', 'oscillation_envelope_db', 'anomaly'],
    h.cells.map((x) => [x.radius, x.nu, x.value, x.envelope, x.anomaly]),
  );
}
export function dishesCsv(a: AntennaReport): string {
  return toCsv(
    ['diameter_m', 'gain_dbi', 'hpbw_script_70_deg', 'hpbw_uniform_deg', 'hpbw_ratio', 'fixed_mount_loss_db', 'gimbal_needed'],
    a.dishes.map((d) => [d.diameter_m, d.gain_dbi, d.hpbw_script_70_deg, d.hpbw_uniform_deg, d.hpbw_ratio, d.gimbal.fixed_mount_loss_db, d.gimbal.gimbal_needed]),
  );
}
export function pointingCsv(a: AntennaReport): string {
  return toCsv(
    ['diameter_m', 'err_deg', 'script_db', 'gaussian_hpbw70_db', 'gaussian_hpbw_uniform_db', 'airy_exact_db', 'gaussian_minus_script_db'],
    a.dishes.flatMap((d) => d.pointing.map((p) => [d.diameter_m, p.err_deg, p.script_db, p.gaussian_hpbw70_db, p.gaussian_hpbw_uniform_db, p.airy_exact_db, p.constant_difference_db])),
  );
}
export function tradeCsv(rows: TradeRow[]): string {
  return toCsv(
    ['k', 'backoff_db', 'declared_steps', 'outages', 'outage_pct', 'gaussian_outage_pct', 'scheduled_bits', 'delivered_bits', 'relative_data', 'mean_rate_bps'],
    rows.map((r) => [r.k, r.backoff_db, r.declared_steps, r.outages, r.outage_pct, r.gaussian_outage_pct, r.scheduled_bits, r.delivered_bits, r.relative_data, r.mean_rate_bps]),
  );
}
export function paramsCsv(rows: ParamRow[]): string {
  return toCsv(['key', 'value', 'unit', 'status', 'source'], rows.map((r) => [r.key, r.value, r.unit, r.status, r.source]));
}
export const toJson = (v: unknown): string => JSON.stringify(v, null, 2);

/** Salva un testo come file (Blob + collegamento temporaneo, nessuna rete). */
export function downloadText(name: string, mime: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
