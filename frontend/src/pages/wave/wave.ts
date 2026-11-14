// SPDX-License-Identifier: Apache-2.0
// Logica pura della pagina Onda 3D: contratto di /api/raven/wave (backend/api/grazing_routes.py), costruzione e
// validazione della richiesta, richiedente con debounce e annullamento, sezione a una distanza qualsiasi, curva
// esatta del bordo a lama, avvisi in italiano, esportazioni. Nessun accesso al DOM.
import { knifeEdgeDb, toCsv } from '../grazinglink/grazing';

export const C_LIGHT = 299_792_458;

export interface WaveSection {
  x_m: number;
  y_m: number[];
  nu: number[];
  intensity: number[];
  knife_edge_exact: number[];
  max_abs_diff_vs_knife: number;
  rms_diff_vs_knife: number;
}
export interface WaveMeta {
  model: string;
  wavelength_m: number;
  frequency_ghz: number;
  radius_m: number;
  ridge: string;
  fft_size: number;
  dy_m: number;
  window_m: number;
  grid_shape: [number, number];
  steps: number;
  ridge_steps: number;
  step_m_requested: number;
  step_m_effective: number;
  x_start_m: number;
  kernel_dz_max_m: number;
  kernel_dz_limit_m: number;
  free_field_reference: number;
  nu_convention: string;
  warnings: string[];
}
export interface WaveResult {
  x_m: number[];
  y_m: number[];
  intensity: number[][];
  section: WaveSection;
  meta: WaveMeta;
  disclaimer: string;
}

/* ------------------------------------ modulo e richiesta ------------------------------------ */

export type Spec = 'frequency' | 'wavelength';
export interface WaveForm {
  spec: Spec;
  frequencyGhz: number | null;
  wavelengthM: number | null;
  radiusM: number | null;
  distanceM: number | null;
  /** semi-finestra verticale (m): y da -h a +h */
  halfWindowM: number | null;
}
export interface Resolution {
  nx: number;
  ny: number;
}
export const RES_HI: Resolution = { nx: 100, ny: 160 };
export const RES_LO: Resolution = { nx: 60, ny: 80 };

export const BANDS = [
  { id: 'S', label: 'Banda S (2,2 GHz)', ghz: 2.2 },
  { id: 'X', label: 'Banda X (8,4 GHz)', ghz: 8.4 },
  { id: 'Ka', label: 'Banda Ka (32 GHz)', ghz: 32 },
] as const;
/** La banda X coincide con la lunghezza d'onda della bozza: 0,0357 m. */
export const X_BAND_LAMBDA_M = 0.0357;

export const DEFAULT_FORM: WaveForm = {
  spec: 'frequency',
  frequencyGhz: 8.4,
  wavelengthM: X_BAND_LAMBDA_M,
  radiusM: 0,
  distanceM: 2000,
  halfWindowM: 40,
};
export const PRESETS = [
  { id: 'lama', label: 'Lama', radiusM: 0 },
  { id: 'cresta100', label: 'Cresta 100 m', radiusM: 100 },
  { id: 'cresta400', label: 'Cresta 400 m', radiusM: 400 },
] as const;

export const lambdaOf = (ghz: number): number => C_LIGHT / (ghz * 1e9);

/**
 * Valori iniziali: i predefiniti, oppure frequenza, raggio e distanza passati dalla scena di Simula (portati negli
 * intervalli del modulo; la distanza minima per il raggio come in `validateForm`). Valori non finiti: ignorati.
 */
export function initialForm(h: { frequencyGhz: number; radiusM: number; distanceM: number } | null): WaveForm {
  const f: WaveForm = { ...DEFAULT_FORM };
  if (!h) return f;
  const ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  if (ok(h.frequencyGhz)) f.frequencyGhz = Math.round(clamp(h.frequencyGhz, 0.3, 60) * 1000) / 1000;
  if (ok(h.radiusM)) f.radiusM = Math.round(clamp(h.radiusM, 0, 400) * 10) / 10;
  if (ok(h.distanceM)) {
    const r = f.radiusM ?? 0;
    const min = r > 0 ? Math.ceil(Math.sqrt(2 * r * 20) + 23) : 100;
    f.distanceM = Math.round(clamp(h.distanceM, Math.max(100, min), 5000));
  }
  return f;
}

export type FormErrors = Partial<Record<keyof WaveForm, string>>;
const inRange = (v: number | null, lo: number, hi: number): v is number => v !== null && Number.isFinite(v) && v >= lo && v <= hi;

export function validateForm(f: WaveForm): FormErrors {
  const e: FormErrors = {};
  if (f.spec === 'frequency') {
    if (!inRange(f.frequencyGhz, 0.3, 60)) e.frequencyGhz = 'La frequenza deve essere tra 0,3 e 60 GHz.';
  } else if (!inRange(f.wavelengthM, 0.005, 1)) e.wavelengthM = 'La lunghezza d’onda deve essere tra 0,005 e 1 m.';
  if (!inRange(f.radiusM, 0, 400)) e.radiusM = 'Il raggio della cresta deve essere tra 0 (lama) e 400 m.';
  if (!inRange(f.distanceM, 100, 5000)) e.distanceM = 'La distanza deve essere tra 100 e 5000 m.';
  else if (inRange(f.radiusM, 0, 400) && f.radiusM > 0 && f.distanceM <= Math.sqrt(2 * f.radiusM * 20) + 2 + 20)
    e.distanceM = 'La distanza è troppo corta per questo raggio: aumentala.';
  if (!inRange(f.halfWindowM, 1, 200)) e.halfWindowM = 'La finestra verticale deve essere tra 1 e 200 m (da -h a +h).';
  return e;
}

/** Parametri della richiesta (stringhe per l'URL): ingressi quantizzati come fa il server, passo adattato alla distanza. */
export function buildParams(f: WaveForm, res: Resolution): Record<string, string> {
  const dist = Math.round(f.distanceM ?? DEFAULT_FORM.distanceM!);
  const half = f.halfWindowM ?? DEFAULT_FORM.halfWindowM!;
  const step = Math.min(1000, Math.max(0.5, Math.round((dist / res.nx) * 10) / 10));
  const p: Record<string, string> = {};
  if (f.spec === 'frequency') p.frequency_ghz = String(Math.round((f.frequencyGhz ?? 8.4) * 1000) / 1000);
  else p.wavelength_m = String(Math.round((f.wavelengthM ?? X_BAND_LAMBDA_M) * 1e5) / 1e5);
  p.radius_m = String(Math.round((f.radiusM ?? 0) * 10) / 10);
  p.distance_m = String(dist);
  p.step_m = String(step);
  p.y_min_m = String(-Math.round(half * 10) / 10);
  p.y_max_m = String(Math.round(half * 10) / 10);
  p.nx = String(res.nx);
  p.ny = String(res.ny);
  return p;
}
export function buildUrl(f: WaveForm, res: Resolution): string {
  return `/api/raven/wave?${new URLSearchParams(buildParams(f, res)).toString()}`;
}

/* ------------------------------------------ rete ------------------------------------------ */

export type WaveFailure = 'invalid' | 'busy' | 'unavailable' | 'server' | 'network';
export type WaveOutcome = { ok: true; data: WaveResult } | { ok: false; kind: WaveFailure; message: string };
export const FAILURE_TEXT: Record<WaveFailure, string> = {
  invalid: 'Parametri non validi per il simulatore (per esempio la distanza è troppo corta per questo raggio). Correggi i campi: resta visibile l’ultima superficie valida.',
  busy: 'Il server sta eseguendo altre simulazioni. Riprovo tra poco o ripremi un preset: resta visibile l’ultima superficie valida.',
  unavailable: 'Il servizio di simulazione non è disponibile in questo momento (503). Riprova più tardi: resta visibile l’ultima superficie valida.',
  server: 'Errore interno del server durante il calcolo. Prova con una finestra o una distanza minori: resta visibile l’ultima superficie valida.',
  network: 'Server non raggiungibile. Controlla la connessione: resta visibile l’ultima superficie valida.',
};
const fail = (kind: WaveFailure): WaveOutcome => ({ ok: false, kind, message: FAILURE_TEXT[kind] });

export function isWaveResult(v: unknown): v is WaveResult {
  const r = v as Partial<WaveResult> | null;
  return (
    !!r &&
    Array.isArray(r.x_m) &&
    Array.isArray(r.y_m) &&
    Array.isArray(r.intensity) &&
    r.intensity.length === r.x_m.length &&
    r.intensity.every((row) => Array.isArray(row) && row.length === (r.y_m as number[]).length) &&
    r.x_m.length >= 2 &&
    r.y_m.length >= 2 &&
    !!r.section &&
    !!r.meta
  );
}

export async function fetchWave(f: typeof fetch, url: string, signal?: AbortSignal): Promise<WaveOutcome> {
  let res: Response;
  try {
    res = await f(url, signal ? { signal } : undefined);
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    return fail('network');
  }
  if (!res.ok) return fail(res.status === 422 ? 'invalid' : res.status === 429 ? 'busy' : res.status === 503 ? (await isBusy(res)) ? 'busy' : 'unavailable' : 'server');
  try {
    const data: unknown = await res.json();
    return isWaveResult(data) ? { ok: true, data } : fail('server');
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    return fail('server');
  }
}
async function isBusy(res: Response): Promise<boolean> {
  try {
    const b = (await res.json()) as { detail?: unknown };
    return typeof b.detail === 'string' && b.detail.includes('troppe');
  } catch {
    return false;
  }
}

export interface Requester {
  /** Richiesta dopo `delay` ms dall'ultima chiamata (le precedenti in attesa decadono). */
  schedule(url: string): void;
  /** Subito (preset): annulla la richiesta in corso e quella in attesa. */
  now(url: string): void;
  cancel(): void;
}
/**
 * Debounce + annullamento delle richieste superate: un `AbortController` per richiesta, e una risposta che
 * arriva dopo una più recente viene scartata anche se il fetch non fosse annullabile.
 */
export function createRequester(
  f: typeof fetch,
  hooks: { onStart(): void; onResult(o: WaveOutcome): void },
  delay = 350,
): Requester {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ctrl: AbortController | null = null;
  let seq = 0;
  const cancel = () => {
    clearTimeout(timer);
    timer = undefined;
    ctrl?.abort();
    ctrl = null;
    seq++;
  };
  const run = (url: string) => {
    cancel();
    const my = seq;
    const c = new AbortController();
    ctrl = c;
    hooks.onStart();
    fetchWave(f, url, c.signal).then(
      (o) => {
        if (my === seq) {
          ctrl = null;
          hooks.onResult(o);
        }
      },
      () => {
        /* annullata: nessun risultato */
      },
    );
  };
  return {
    schedule(url) {
      clearTimeout(timer);
      timer = setTimeout(() => run(url), delay);
    },
    now: run,
    cancel,
  };
}

/* ---------------------------------- sezione alla distanza del cursore ---------------------------------- */

/** Righe vicine al cursore e peso dell'interpolazione lineare (x_m crescente). */
export function rowAt(xs: ArrayLike<number>, x: number): { k: number; t: number } {
  const n = xs.length;
  if (n < 2 || x <= xs[0]!) return { k: 0, t: 0 };
  if (x >= xs[n - 1]!) return { k: n - 2, t: 1 };
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid]! <= x) lo = mid;
    else hi = mid;
  }
  const span = xs[hi]! - xs[lo]!;
  return { k: lo, t: span > 0 ? (x - xs[lo]!) / span : 0 };
}

/** Distanza minima del cursore: la lama parte da x = 0 (nu infinito), si usa la seconda riga. */
export const cursorRange = (r: Pick<WaveResult, 'x_m'>): [number, number] => [r.x_m[r.x_m.length > 2 && r.x_m[0] === 0 ? 1 : 0]!, r.x_m[r.x_m.length - 1]!];
export const clampCursor = (r: Pick<WaveResult, 'x_m'>, x: number): number => {
  const [a, b] = cursorRange(r);
  return Number.isFinite(x) ? Math.min(b, Math.max(a, x)) : b;
};

export interface SectionData {
  x: number;
  y: Float64Array;
  simulated: Float64Array;
  exact: Float64Array;
  /** vero per la sezione ad alta risoluzione dell'API (distanza finale), falso per l'interpolazione della griglia */
  fromApi: boolean;
}
/** Intensità relativa del bordo a lama esatto a quota y e distanza x: 10^(-J(nu)/10), nu = -y sqrt(2/(lambda x)). */
export function exactIntensity(y: number, x: number, lambda: number): number {
  return 10 ** (-knifeEdgeDb(-y * Math.sqrt(2 / (lambda * x))) / 10);
}

export const sectionFromApi = (s: WaveSection): SectionData => ({
  x: s.x_m,
  y: Float64Array.from(s.y_m),
  simulated: Float64Array.from(s.intensity),
  exact: Float64Array.from(s.knife_edge_exact),
  fromApi: true,
});

/**
 * Sezione alla distanza `x`: quella dell'API se coincide con la distanza finale della griglia o con `api` (calcolata
 * a quella distanza), altrimenti un'anteprima interpolata tra le due righe vicine (le frange lontane dall'asse
 * variano più in fretta del passo della griglia: l'anteprima è solo indicativa).
 */
export function sectionAt(r: WaveResult, x: number, api?: WaveSection | null): SectionData {
  const lam = r.meta.wavelength_m;
  const xe = r.x_m[r.x_m.length - 1]!;
  if (Math.abs(x - xe) < 1e-6) return sectionFromApi(r.section);
  if (api && Math.abs(api.x_m - x) < 0.5) return sectionFromApi(api);
  const { k, t } = rowAt(r.x_m, x);
  const a = r.intensity[k]!;
  const b = r.intensity[k + 1]!;
  const n = r.y_m.length;
  const simulated = new Float64Array(n);
  const exact = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    simulated[j] = a[j]! + (b[j]! - a[j]!) * t;
    exact[j] = x > 0 ? exactIntensity(r.y_m[j]!, x, lam) : NaN;
  }
  return { x, y: Float64Array.from(r.y_m), simulated, exact, fromApi: false };
}

export function sectionStats(s: SectionData): { maxAbs: number; rms: number } {
  let m = 0;
  let q = 0;
  let c = 0;
  for (let i = 0; i < s.y.length; i++) {
    const d = Math.abs(s.simulated[i]! - s.exact[i]!);
    if (!Number.isFinite(d)) continue;
    m = Math.max(m, d);
    q += d * d;
    c++;
  }
  return { maxAbs: m, rms: c ? Math.sqrt(q / c) : 0 };
}

/* ------------------------------------------- griglia ------------------------------------------- */

export function flattenGrid(rows: number[][], out?: Float32Array): Float32Array {
  const nx = rows.length;
  const ny = rows[0]?.length ?? 0;
  const g = out && out.length === nx * ny ? out : new Float32Array(nx * ny);
  for (let i = 0; i < nx; i++) {
    const r = rows[i]!;
    for (let j = 0; j < ny; j++) g[i * ny + j] = r[j]!;
  }
  return g;
}
/** Quota massima della superficie: almeno 1,2 (la frangia di Fresnel arriva a circa 1,37), arrotondata a 0,1. */
export function zTopOf(g: Float32Array): number {
  let m = 0;
  for (let i = 0; i < g.length; i++) if (g[i]! > m) m = g[i]!;
  return Math.max(1.2, Math.ceil(m * 10) / 10);
}

/* ----------------------------------------- avvisi e testi ----------------------------------------- */

const WARNING_TEXT: Record<string, string> = {
  kernel_aliasing:
    'Il passo di propagazione è troppo lungo per la griglia verticale: il nucleo di Fresnel è campionato troppo poco e le frange possono essere false. Riduci la distanza o usa una lunghezza d’onda maggiore.',
  dy_coarse: 'La griglia verticale è troppo grossolana: le frange vicino al crinale non sono risolte del tutto.',
  paraxial: 'La lunghezza d’onda è grande rispetto alla griglia verticale: l’approssimazione parassiale non vale più e i valori sono poco affidabili.',
  step_raised: 'Il passo di propagazione è stato aumentato dal server per rispettare il limite sul numero di passi.',
};
export function warningText(w: string): string {
  const key = w.split(':')[0]!.trim();
  return WARNING_TEXT[key] ?? 'Avviso del simulatore: ' + w;
}

export const fmt = (v: number, d = 2): string => v.toFixed(d).replace('.', ',');
export function sizeText(m: number): string {
  return m >= 1 ? `${fmt(m, m >= 100 ? 0 : 1)} m` : `${fmt(m * 100, 1)} cm`;
}

/* ----------------------------------------- esportazioni ----------------------------------------- */

export function sectionCsv(s: SectionData, lambda: number): string {
  return toCsv(
    ['y_m', 'nu', 'intensity_simulated', 'intensity_knife_edge_exact'],
    Array.from(s.y, (y, i) => [y, s.x > 0 ? -y * Math.sqrt(2 / (lambda * s.x)) : null, s.simulated[i], Number.isFinite(s.exact[i]!) ? s.exact[i] : null]),
  );
}
export function gridCsv(r: WaveResult): string {
  const rows: number[][] = [];
  r.x_m.forEach((x, i) => r.y_m.forEach((y, j) => rows.push([x, y, r.intensity[i]![j]!])));
  return toCsv(['x_m', 'y_m', 'intensity'], rows);
}
export function sectionJson(s: SectionData, r: WaveResult): string {
  return JSON.stringify(
    {
      distance_m: s.x,
      from_api_section: s.fromApi,
      y_m: Array.from(s.y),
      intensity_simulated: Array.from(s.simulated),
      intensity_knife_edge_exact: Array.from(s.exact, (v) => (Number.isFinite(v) ? v : null)),
      meta: r.meta,
    },
    null,
    2,
  );
}
export const gridJson = (r: WaveResult): string =>
  JSON.stringify({ x_m: r.x_m, y_m: r.y_m, intensity: r.intensity, meta: r.meta, disclaimer: r.disclaimer }, null, 2);
