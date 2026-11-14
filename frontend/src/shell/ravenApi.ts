// SPDX-License-Identifier: Apache-2.0
// Client tipizzato di /api/raven/* (RAVEN Core Model, backend/api/raven_routes.py). Unico punto da cui le pagine
// leggono il modello: costruzione delle richieste con i tetti D9, mappatura degli errori, annullamento delle
// richieste superate e cache delle richieste identiche. I tipi sono scritti a mano e fissati da un test contro
// risposte reali dell'API (fixtures/raven/*.json).
import { customSites, isCustomId, snapshotParam, toApi, type CustomSiteDef } from './customSites';

export const RAVEN_MAX_STEPS_PER_SITE = 1500;
export const RAVEN_MAX_STEPS_TOTAL = 6000;
export const RAVEN_DEFAULT_DAYS = 7;
export const RAVEN_DEFAULT_STEP_MIN = 10;
export const RAVEN_MAX_DAYS = 366;
export const RAVEN_STEP_MIN_BOUNDS = [1, 1440] as const;
export const RAVEN_MAX_SITES = 16;

export type Station = 'dsn34' | 'dsn18';
export type RavenFailure = 'network' | 'invalid' | 'unavailable' | 'server' | 'response' | 'aborted';
/** Perche' un rifiuto non e' un errore generico: terreno da scaricare (409), troppo grande (413), tetto orario (429). */
export type RavenDetail = 'needs_download' | 'too_large' | 'rate_limited';
export type RavenResult<T> =
  | { ok: true; data: T }
  | { ok: false; kind: RavenFailure; detail?: RavenDetail; estimate?: TerrainEstimate; status?: number };

export type CustomSiteIn = CustomSiteDef;

/** Stima a secco dei dati di terreno (POST /api/raven/terrain-estimate e corpo del 409). */
export interface TerrainEstimateSite {
  id: string; name: string; lat_deg: number; lon_deg_east: number;
  status: 'ok' | 'unknown' | 'exceeds_site_cap'; reason: string; terrain_available: boolean;
  near_product: string | null; far_product: string | null; resolution_m: number | null; far_resolution_m: number | null;
  range_km: number | null; tiles: number; mb_total: number; mb_transfer: number;
  tiles_cached: number; tiles_to_download: number; mb_to_download: number;
  products: { id: string; scale_m: number; tiles: number; tiles_cached: number }[];
}
export interface TerrainEstimate {
  sites: TerrainEstimateSite[]; mb_total: number; mb_to_download: number; needs_download: boolean; request_over_cap: boolean;
  caps: { site_mb: number; request_mb: number; cache_mb: number }; cache: { used_mb: number; max_mb: number };
}
export interface TerrainInfo {
  state: 'known' | 'unknown'; reason: string; products: { id: string; resolution_m: number }[];
  resolution_m: number | null; horizon_range_km: number | null; custom: boolean;
}

export interface RavenScenarioIn {
  start_utc: string;
  days: number;
  step_min: number;
  panel_height_m?: number;
  antenna_height_m?: number;
  rate_bps?: number;
  station?: Station;
  required_margin_db?: number;
  rf_overrides?: Record<string, number | boolean | string>;
  energy_overrides?: Record<string, number | string>;
}
export interface EvaluateIn extends RavenScenarioIn {
  site_id: string;
  custom_site?: CustomSiteIn;
  allow_download?: boolean;
  include_steps?: boolean;
  include_windows?: boolean;
}
export interface CompareIn extends RavenScenarioIn {
  site_ids: string[];
  custom_sites?: CustomSiteIn[];
  allow_download?: boolean;
  order?: string[];
}

/** Passi di una finestra: stessa regola del backend (floor(days*1440/step + 1e-9), almeno 1). */
export const ravenSteps = (days: number, stepMin: number): number => Math.max(1, Math.floor((days * 1440) / stepMin + 1e-9));

export type BoundsError = 'start' | 'days' | 'step' | 'sites' | 'size';

/** Verifica locale dei limiti D9: null se la richiesta e' ammessa, altrimenti il primo limite violato. */
export function checkBounds(r: Pick<RavenScenarioIn, 'start_utc' | 'days' | 'step_min'>, nSites = 1): BoundsError | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(r.start_utc)) return 'start';
  if (!Number.isFinite(r.days) || r.days <= 0 || r.days > RAVEN_MAX_DAYS) return 'days';
  if (!Number.isFinite(r.step_min) || r.step_min < RAVEN_STEP_MIN_BOUNDS[0] || r.step_min > RAVEN_STEP_MIN_BOUNDS[1]) return 'step';
  if (nSites < 1 || nSites > RAVEN_MAX_SITES) return 'sites';
  const n = ravenSteps(r.days, r.step_min);
  return n > RAVEN_MAX_STEPS_PER_SITE || n * nSites > RAVEN_MAX_STEPS_TOTAL ? 'size' : null;
}

/** Richiesta di valutazione con i default del modello (7 giorni a 10 minuti). */
export function evaluateIn(site_id: string, start_utc: string, o: Partial<EvaluateIn> = {}): EvaluateIn {
  return { days: RAVEN_DEFAULT_DAYS, step_min: RAVEN_DEFAULT_STEP_MIN, include_steps: true, ...o, site_id, start_utc };
}

/* --------------------------------- risposte --------------------------------- */

export type Reason = string;
export interface RavenSite {
  id: string; name: string; lat_deg: number; lon_deg_east: number; kind: string; coordinate_basis: string;
  source_url: string; source_accessed: string; source_note: string; verified: boolean; dem_coverage: boolean | null;
  custom?: boolean; panel_height_m?: number | null; antenna_height_m?: number | null;
}
export interface RavenMetrics {
  n_steps: number; known_steps: number; unknown_steps: number;
  useful_hours: number; useful_fraction: number; useful_fraction_of_known: number | null; unknown_hours: number;
  state_hours: Record<string, number>; limiting_fraction: Record<string, number>;
  min_soc: number | null; min_soc_scope: string; time_to_first_blackout_h: number | null; blackout_within_known: boolean;
  unmet_wh: number | null; harvested_wh: number | null; sun_hours: number; longest_unuseful_h: number | null;
}
export interface RavenSteps {
  time_unix: number[];
  sun_az_deg: (number | null)[]; sun_el_deg: (number | null)[];
  earth_az_deg: (number | null)[]; earth_el_deg: (number | null)[]; earth_range_km: (number | null)[];
  sun_horizon_deg: (number | null)[]; earth_horizon_deg: (number | null)[];
  /** Perdita in spazio libero dalla distanza vera: valida anche senza terreno (non e' un margine di collegamento). */
  free_space_loss_db?: (number | null)[];
  terrain_reason: Reason[]; far_terrain_loss_db: (number | null)[];
  /** Termini della perdita per diffrazione (S5): nu del crinale dominante, J(nu), correzione T (ITU-R P.526-9), somma. None = ignoto. */
  diffraction_nu?: (number | null)[]; knife_edge_loss_db?: (number | null)[]; ridge_correction_db?: (number | null)[];
  diffraction_loss_db?: (number | null)[]; multipath_gain_db?: (number | null)[];
  disc_fraction: (number | null)[]; lit: (boolean | null)[];
  margin_db: (number | null)[]; rf_state: string[]; rf_closes: (boolean | null)[]; rf_reason: Reason[];
  chosen_rate_bps?: (number | null)[];
  dsn_visible: (boolean | null)[];
  gen_w: (number | null)[]; soc: (number | null)[];
  state: string[]; link_usable: (boolean | null)[]; useful: (boolean | null)[]; limiting: (string | null)[];
}
export interface RavenWindow {
  start_unix: number; end_unix: number; start_resolved: boolean; end_resolved: boolean;
  open_start: boolean; open_end: boolean; tolerance_s: number; first_sample: number; last_sample: number;
}
export interface RavenEvaluation {
  rf_series?: Record<string, (number | null)[]>;
  model_version: string;
  registry_sha256: string;
  label: string;
  site: RavenSite;
  window: { start_utc: string; step_min: number; n_steps: number };
  implemented_stages: string[];
  metrics: RavenMetrics;
  first_unknown_index: number | null;
  inputs_state: {
    terrain_mask: string; terrain_reason_counts: Record<string, number>; illumination_reason_counts: Record<string, number>;
    rf_reason_counts: Record<string, number>; dsn_reason_counts: Record<string, number>;
  };
  mask: Record<string, unknown> | null;
  terrain?: TerrainInfo;
  heights: { panel_height_m: number; antenna_height_m: number; profile_length_m: number };
  rules: Record<'link_usable' | 'useful' | 'lit' | 'far_terrain', string>;
  declared_limits: string[];
  /** Valori usati davvero dal calcolo (default piu' override): la pagina non tiene una copia propria. */
  parameters_used?: { rf: Record<string, number | string | boolean>; energy: Record<string, number | string>; scenario: Record<string, number> };
  steps?: RavenSteps;
  windows?: Record<'lit' | 'link_usable' | 'useful', RavenWindow[]>;
  windows_rule?: string;
}

export interface RankingRow { site_id: string; rank: number; components: Record<string, number | null>; [k: string]: unknown }
export interface NotComparable { site_id: string; reasons: string[]; [k: string]: unknown }
export interface RavenRanking {
  order: string[];
  directions: Record<string, string>;
  tie_break: string;
  score: null;
  ranking: RankingRow[];
  not_comparable: NotComparable[];
  components_legend: Record<string, unknown>;
}
export interface RavenComparison {
  model_version: string; registry_sha256: string; ranking: RavenRanking; sites: RavenEvaluation[];
}

export interface SnapshotSite {
  id: string; name: string; lat_deg: number; lon_deg_east: number; dem_covered: boolean;
  earth_az_deg: number; earth_el_deg: number; earth_el_geocentric_deg: number; parallax_deg: number; earth_range_km: number;
  fspl_delta_db: number; state: string; margin_db: number | null; ridge_el_deg: number | null;
  custom?: boolean; terrain_resolution_m?: number | null;
}
export interface RavenSnapshot {
  label: string; t_utc: string; rate_bps: number; station: Station; reference_range_km: number;
  sites: SnapshotSite[]; dsn: Record<string, unknown>; state_rule: string; limits: string[];
}
/** La scena e la sua struttura interna sono letti da lander/model.ts, che le valida campo per campo. */
export type RavenScene = Record<string, unknown> & { label: string; t_utc: string; site: { id: string } };
export interface RavenHorizon {
  site: RavenSite; height_m: number; limit: string; state: string; meta: Record<string, unknown>;
  azimuth_step_deg: number; elevation_deg: (number | null)[]; distance_m: (number | null)[]; complete: boolean[];
}
export interface RavenParameter {
  key: string; scope: string; name: string; group: string; stage: string; default: number | string | boolean | null;
  unit: string; min?: number; max?: number; tag: 'V' | 'D' | 'I'; source: string; note: string;
}
export interface RavenParameters {
  model_version: string; registry_sha256: string; tags: Record<string, string>; parameters: RavenParameter[];
  defaults: {
    window: { days: number; step_min: number; n_steps: number; max_steps_per_site: number; max_steps_total: number; max_days: number; step_min_bounds: number[]; note: string };
    scenario: Record<string, number | string>;
    rf: Record<string, number | string | boolean>;
    rates_bps: number[];
    sites: string[];
    [k: string]: unknown;
  };
  duplicated_concepts: unknown;
}
export interface RavenValidation {
  model_version: string; statuses: string[]; note: string; stages: Record<string, unknown>[]; parameter_groups: Record<string, unknown>[];
}
export interface RavenSiteInfo extends RavenSite { dem_covered: boolean }
/** Un sito personalizzato come riga dell'elenco dei siti (stessa forma di quelli del catalogo; mai "verificato"). */
export function customAsSiteInfo(d: CustomSiteDef): RavenSiteInfo {
  return {
    id: d.id, name: d.name, lat_deg: d.lat_deg, lon_deg_east: d.lon_deg_east, kind: 'user', coordinate_basis: 'point',
    source_url: '', source_accessed: '', source_note: 'coordinates given by the user, not verified', verified: false,
    dem_coverage: true, dem_covered: true, custom: true,
  };
}
export interface RavenSites {
  model_version: string;
  sites: RavenSiteInfo[];
  dem: { available: boolean; cached_tiles: number; product: { id: string; coverage: string; coverage_north_limit_deg: number; credit: string; url: string } };
  ephemeris: { available: boolean; supported_range?: { start_utc: string; end_utc: string } | null };
  custom_sites?: { max: number; id_prefix: string; caps_mb: { site: number; request: number } };
  disclaimer: string;
}
/** Cost band and CO2e of a mission class from the core (GET /api/raven/report/estimate). A null bound is unknown, never zero. */
export interface EconBand { min: number | null; typical: number | null; max: number | null }
export interface RavenEconomics {
  model: string; mission_class: string; launch_class: string;
  cost: EconBand & { unit: string; tag: string; source: string };
  development_years: EconBand & { unit: string; tag: string };
  launch_mass: EconBand & { unit: string; tag: string };
  co2e: {
    unit: string;
    launch: (EconBand & { tag: string; vehicle: string; propellant: string; source: string }) | null;
    production: EconBand & { tag: string; source: string };
    total: EconBand | null;
  };
  limits: string[]; unknown: string[];
  context: { mission_class: string; cost: EconBand; co2e_launch: EconBand | null }[];
}
/** RAVEN engine estimates (tag I): an interval with its source; a null bound is unknown, never zero. */
export interface EstBand { min: number | null; typical: number | null; max: number | null; source?: string | null; note?: string }
export interface RavenFresnelEstimate { model: string; tag: string; eps_real: EstBand; eps_imag: EstBand; roughness_rms_m: EstBand; limits: string }
export interface RavenLandingEstimate {
  model: string; tag: string; attempts: number; successes: number; ambiguous: number;
  landing_success: EstBand; landing_failure: EstBand; interval: string; source: string; limits: string;
  missions: { mission: string; year: number; outcome: string }[]; component_failure_rates: null;
}
/** A remote-sensing style raster of the south-polar disc (GET /api/raven/overlay): 8-bit, row-major, 0 = no data. */
export interface RavenOverlay {
  layer: 'elevation' | 'slope' | 'coverage' | 'sun' | 'earth' | 'both' | 'sun_gap' | 'earth_gap'; size: number; limit_lat_deg: number; nodata: number; encoding: 'uint8-linear';
  unit: string; min: number; max: number; tag: string; kind: 'sequential' | 'categorical';
  classes?: { value: number; label: string }[]; data_b64: string; source: string; note: string; cell_m?: number;
  /** Absent = the south-polar disc (square); 'equirectangular' = the whole Moon (width x height, like the colour map). */
  scope?: 'polar' | 'global'; projection?: 'equirectangular'; width?: number; height?: number;
}
export interface RavenModel { model_version: string; registry_sha256?: string; validation?: RavenValidation; [k: string]: unknown }

/* --------------------------------- client --------------------------------- */

export interface RavenClientOptions {
  fetch?: typeof fetch;
  cacheSize?: number;
  /** Chiamata quando il server risponde 409 "needs download": true = scarica (la richiesta e' ripetuta con allow_download). */
  confirmDownload?: (estimate: TerrainEstimate) => Promise<boolean>;
}
type Retry = () => { url: string; init: RequestInit };

// predefinita: la finestra di conferma (chunk lazy, montata solo al primo 409)
let sharedConfirm: ((e: TerrainEstimate) => Promise<boolean>) | null = (e) => import('./terrainPrompt').then((m) => m.confirmTerrainDownload(e));
/** Registra la finestra di conferma del download (la monta il componente dei siti personalizzati). */
export function setTerrainConfirm(fn: ((e: TerrainEstimate) => Promise<boolean>) | null): void {
  sharedConfirm = fn;
}
export interface Call { signal?: AbortSignal }

interface Flight { promise: Promise<RavenResult<unknown>>; controller: AbortController; waiters: number }

const failureOf = (status: number): RavenFailure => (status === 422 ? 'invalid' : status === 503 ? 'unavailable' : 'server');

/** Query string con chiavi ordinate: la stessa richiesta ha sempre la stessa chiave di cache. */
export function queryString(q: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams();
  for (const k of Object.keys(q).sort()) if (q[k] !== undefined) p.set(k, String(q[k]));
  return p.toString();
}

const stable = (v: unknown): string => JSON.stringify(v, (_k, x: unknown) =>
  x && typeof x === 'object' && !Array.isArray(x)
    ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => (a < b ? -1 : 1))) : x);

export function createRavenClient(opts: RavenClientOptions = {}) {
  const doFetch = opts.fetch ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const cacheSize = opts.cacheSize ?? 32;
  const cache = new Map<string, unknown>();
  const flights = new Map<string, Flight>();
  const channels = new Map<string, AbortController>();

  function remember(key: string, data: unknown): void {
    cache.set(key, data);
    if (cache.size > cacheSize) cache.delete(cache.keys().next().value as string);
  }

  const confirmFn = (e: TerrainEstimate): Promise<boolean> => (opts.confirmDownload ?? sharedConfirm)?.(e) ?? Promise.resolve(false);

  async function refusal(response: Response, retry: Retry | undefined, controller: AbortController): Promise<{ response: Response } | RavenResult<unknown>> {
    const status = response.status;
    const detail: RavenDetail = status === 409 ? 'needs_download' : status === 413 ? 'too_large' : 'rate_limited';
    let estimate: TerrainEstimate | undefined;
    try {
      const body = (await response.json()) as { estimate?: TerrainEstimate };
      if (body && typeof body === 'object' && body.estimate && Array.isArray(body.estimate.sites)) estimate = body.estimate;
    } catch { /* corpo non JSON */ }
    const fail: RavenResult<unknown> = { ok: false, kind: status === 413 ? 'invalid' : 'unavailable', detail, ...(estimate ? { estimate } : {}) };
    if (status !== 409 || !estimate || !retry) return fail;
    let yes = false;
    try { yes = await confirmFn(estimate); } catch { yes = false; }
    if (!yes) return fail;
    const r = retry();
    try {
      return { response: await doFetch(r.url, { ...r.init, signal: controller.signal }) };
    } catch {
      return { ok: false, kind: controller.signal.aborted ? 'aborted' : 'network' };
    }
  }

  async function send<T>(key: string, url: string, init: RequestInit, signal: AbortSignal | undefined, retry?: Retry): Promise<RavenResult<T>> {
    if (signal?.aborted) return { ok: false, kind: 'aborted' };
    if (cache.has(key)) return { ok: true, data: cache.get(key) as T };
    let flight = flights.get(key);
    if (!flight) {
      const controller = new AbortController();
      const promise = (async (): Promise<RavenResult<unknown>> => {
        let response: Response;
        try {
          response = await doFetch(url, { ...init, signal: controller.signal });
        } catch {
          return { ok: false, kind: controller.signal.aborted ? 'aborted' : 'network' };
        }
        if (!response.ok) {
          if (response.status !== 409 && response.status !== 413 && response.status !== 429) return { ok: false, kind: failureOf(response.status), status: response.status };
          const out = await refusal(response, retry, controller);
          if (!('response' in out)) return out;
          response = out.response;
          if (!response.ok) return { ok: false, kind: failureOf(response.status), status: response.status };
        }
        try {
          const data: unknown = await response.json();
          if (!data || typeof data !== 'object') return { ok: false, kind: 'response' };
          remember(key, data);
          return { ok: true, data };
        } catch {
          return { ok: false, kind: 'response' };
        }
      })().finally(() => flights.delete(key));
      flight = { promise, controller, waiters: 0 };
      flights.set(key, flight);
    }
    const f = flight;
    f.waiters++;
    let onAbort: (() => void) | undefined;
    const aborted = new Promise<RavenResult<T>>((resolve) => {
      onAbort = () => resolve({ ok: false, kind: 'aborted' });
      signal?.addEventListener('abort', onAbort, { once: true });
    });
    try {
      return await Promise.race([f.promise as Promise<RavenResult<T>>, aborted]);
    } finally {
      if (onAbort) signal?.removeEventListener('abort', onAbort);
      f.waiters--;
      // il calcolo parte solo se qualcuno lo aspetta: se tutti hanno annullato, si ferma anche la richiesta
      if (f.waiters === 0 && signal?.aborted) f.controller.abort();
    }
  }

  const jsonInit = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const post = <T>(path: string, body: unknown, c?: Call, allowRetry = false) =>
    send<T>(`POST ${path} ${stable(body)}`, path, jsonInit(body), c?.signal,
      allowRetry ? () => ({ url: path, init: jsonInit({ ...(body as object), allow_download: true }) }) : undefined);
  const get = <T>(path: string, q: Record<string, string | number | boolean | undefined> | null, c?: Call, allowRetry = false) => {
    const url = q ? `${path}?${queryString(q)}` : path;
    return send<T>(`GET ${url}`, url, {}, c?.signal,
      allowRetry && q ? () => ({ url: `${path}?${queryString({ ...q, allow_download: true })}`, init: {} }) : undefined);
  };
  const failInvalid = (): Promise<RavenResult<never>> => Promise.resolve({ ok: false, kind: 'invalid' });
  /** Definizioni dei siti personalizzati richiesti; null se un id `c-` non e' definito (la richiesta e' invalida). */
  const defsFor = (ids: readonly string[]): CustomSiteIn[] | null => {
    const out: CustomSiteIn[] = [];
    for (const id of ids) {
      if (!isCustomId(id)) continue;
      const d = customSites.find(id);
      if (!d) return null;
      out.push(toApi(d));
    }
    return out;
  };
  const customQuery = (site: string): Record<string, string | number> | null => {
    if (!isCustomId(site)) return {};
    const d = customSites.find(site);
    return d ? { lat_deg: d.lat_deg, lon_deg_east: d.lon_deg_east, name: d.name } : null;
  };

  return {
    /** I siti `c-...` sono presi dallo scenario condiviso (`customSites`): le pagine passano solo l'id. */
    evaluate: (r: EvaluateIn, c?: Call) => {
      const defs = defsFor([r.site_id]);
      if (defs === null) return failInvalid();
      const { custom_site: _drop, ...rest } = r;
      return post<RavenEvaluation>('/api/raven/evaluate', defs.length ? { ...rest, custom_site: defs[0] } : rest, c, true);
    },
    compare: (r: CompareIn, c?: Call) => {
      const defs = defsFor(r.site_ids);
      if (defs === null) return failInvalid();
      const { custom_sites: _drop, ...rest } = r;
      return post<RavenComparison>('/api/raven/compare', defs.length ? { ...rest, custom_sites: defs } : rest, c, defs.length > 0);
    },
    snapshot: (q: { t: string; rate_bps?: number; station?: Station }, c?: Call) => {
      const list = customSites.get();
      const custom = snapshotParam(list);
      return get<RavenSnapshot>('/api/raven/snapshot', { ...q, ...(custom ? { custom } : {}) }, c);
    },
    scene: (q: { site: string; t: string; rate_bps?: number; station?: Station; antenna_height_m?: number }, c?: Call) => {
      const cq = customQuery(q.site);
      return cq === null ? failInvalid() : get<RavenScene>('/api/raven/scene', { ...q, ...cq }, c, true);
    },
    horizon: (q: { site: string; height_m?: number }, c?: Call) => {
      const cq = customQuery(q.site);
      return cq === null ? failInvalid() : get<RavenHorizon>('/api/raven/horizon', { ...q, ...cq }, c, true);
    },
    /** Stima a secco (nessun download): tessere e MB per sito, cio' che e' gia' in cache, i tetti. */
    terrainEstimate: (sites: CustomSiteIn[], c?: Call) => post<TerrainEstimate>('/api/raven/terrain-estimate', { sites: sites.map(toApi) }, c),
    sites: (c?: Call) => get<RavenSites>('/api/raven/sites', null, c),
    parameters: (c?: Call) => get<RavenParameters>('/api/raven/parameters', null, c),
    model: (c?: Call) => get<RavenModel>('/api/raven/model', null, c),
    overlay: (layer: RavenOverlay['layer'], c?: Call, scope: 'polar' | 'global' = 'polar') => get<RavenOverlay>('/api/raven/overlay', scope === 'global' ? { layer, scope } : { layer, size: 384 }, c),
    /** Costo e CO2e di una classe di missione, calcolati dal nucleo RAVEN. */
    reportEstimate: (missionClass: string, c?: Call) => get<RavenEconomics>('/api/raven/report/estimate', { mission_class: missionClass }, c),
    fresnelEstimate: (c?: Call) => get<RavenFresnelEstimate>('/api/raven/report/fresnel-estimate', null, c),
    landingEstimate: (c?: Call) => get<RavenLandingEstimate>('/api/raven/report/landing-estimate', null, c),
    validation: (c?: Call) => get<RavenValidation>('/api/raven/validation', null, c),
    /** Annulla la richiesta precedente dello stesso canale e restituisce il segnale della nuova. */
    latest(channel: string): AbortSignal {
      channels.get(channel)?.abort();
      const next = new AbortController();
      channels.set(channel, next);
      return next.signal;
    },
    clear(): void { cache.clear(); },
    get cached(): number { return cache.size; },
  };
}

export type RavenClient = ReturnType<typeof createRavenClient>;

/** Per i moduli che non passano dal client (la scena del Lander): stessa finestra di conferma del download. */
export function askTerrainConfirm(estimate: TerrainEstimate): Promise<boolean> {
  return sharedConfirm ? sharedConfirm(estimate) : Promise.resolve(false);
}

/** Client condiviso dalle pagine (stessa cache: Planner, Confronto e viste leggono le stesse risposte). */
export const raven: RavenClient = createRavenClient();
