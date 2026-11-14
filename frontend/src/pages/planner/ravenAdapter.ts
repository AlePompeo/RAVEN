// SPDX-License-Identifier: Apache-2.0
// Planner sul modello unico RAVEN: un'unica valutazione /api/raven/evaluate per sito e scenario alimenta la timeline,
// la sezione radio, il Sole-terreno e la missione. Qui si traducono le colonne del modello nelle forme che la pagina
// gia' usa (TimelineResult, SolarTerrainResult, MissionResult, CompareResult, HorizonResult). Nessun calcolo nuovo:
// frazioni, intervalli e ore sono conteggi sulle colonne del modello; un passo ignoto non diventa mai "si'" o "no".
import type { LunarSite, ParamRow, SiteMetrics } from '../compare/lunar';
import { UNCOVERED_STATE, type AnalysedRow, type CompareResult, type SiteRow } from '../compare/grazingCompare';
import type { Defaults as GrazingDefaults, Status } from '../grazinglink/grazing';
import type { Defaults } from '../compare/lunar';
import {
  RAVEN_MAX_DAYS, RAVEN_MAX_STEPS_PER_SITE, RAVEN_MAX_STEPS_TOTAL, raven, type RavenClient, type EvaluateIn, type RavenEvaluation, type RavenFailure,
  type RavenHorizon, type RavenParameter, type RavenParameters, type RavenResult, type RavenSites, type RavenSteps,
} from '../../shell/ravenApi';
import type { AnalyzeRequest } from '../compare/lunar';
import type { HorizonResult, HorizonSample } from './horizon';
import type { MissionRequest, MissionResult, MissionState, ParamTag } from './mission';
import type { SolarTerrainResult, SolarTerrainState } from './solarTerrain';
import type { TimelineResult, TimelineSeries } from './timeline';

const SAMPLING_TEXT = 'Each sample is evaluated at the start of its step and represents [t, t + step); transitions are known only to the sampling resolution. Generation is evaluated at the step start; battery state of charge is at the end of the step. The model uses the LOLA terrain horizon.';

/** Dichiarazione per le pagine: il modello da cui escono i numeri. */
export interface ModelStamp { model_version: string; registry_sha256: string }
export const stampOf = (e: Pick<RavenEvaluation, 'model_version' | 'registry_sha256'>): ModelStamp => ({
  model_version: e.model_version, registry_sha256: e.registry_sha256,
});

const num = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);
const frac = (xs: readonly (boolean | null)[]): number => {
  const known = xs.filter((x) => x !== null);
  return known.length ? known.filter(Boolean).length / known.length : 0;
};
const hours = (xs: readonly (boolean | null)[], stepMin: number): number => xs.filter((x) => x === true).length * stepMin / 60;

/* ---------------------------------- catalogo ---------------------------------- */

const PANEL_GROUPS = new Set(['energy', 'window']);
function rowOf(p: RavenParameter, group: ParamRow['group']): ParamRow {
  return {
    key: p.name, group, value: p.default as number | string, unit: p.unit,
    ...(typeof p.min === 'number' ? { min: p.min } : {}), ...(typeof p.max === 'number' ? { max: p.max } : {}),
    status: p.tag, source: p.source, note: p.note,
  };
}

export interface PlannerCatalog {
  sites: LunarSite[]; defaults: Defaults; status: Status; grazingDefaults: GrazingDefaults;
  parameterRegistry: readonly RavenParameter[];
}

export function usedParameter(registry: readonly RavenParameter[], group: string, name: string): RavenParameter | null {
  const scopes = group === 'energy' ? ['lunar'] : group === 'rf' ? ['rf', 'grazing'] : ['rf', 'common'];
  for (const scope of scopes) {
    const row = registry.find((p) => p.scope === scope && p.name === name);
    if (row) return row;
  }
  return null;
}

/** Siti, parametri e disponibilita' dal modello unico: sostituisce /api/lunar/{sites,defaults} e /api/grazing/{status,defaults}. */
export function plannerCatalog(s: RavenSites, p: RavenParameters): PlannerCatalog {
  const lunarSites: LunarSite[] = s.sites.map((x) => ({
    id: x.id, name: x.name, lat_deg: x.lat_deg, lon_deg_east: x.lon_deg_east, kind: x.kind,
    coordinate_basis: x.coordinate_basis, verified: x.verified, source_url: x.source_url,
  }));
  const orientations = (p.defaults['energy_orientations'] as string[] | undefined) ?? [];
  const energy = p.parameters.filter((r) => r.scope === 'lunar' && PANEL_GROUPS.has(r.group)).map((r) => rowOf(r, r.group as ParamRow['group']));
  const rf = p.parameters.filter((r) => r.scope === 'rf').map((r) => rowOf(r, 'link'));
  const orientation: ParamRow = { key: 'orientation', group: 'energy', value: 'horizontal', unit: '-', allowed: orientations, status: 'I', source: 'illustrative', note: '' };
  const w = p.defaults.window;
  const limits = { days_max: w.max_days, step_min_min: w.step_min_bounds[0] ?? 1, max_total_points: w.max_steps_total, timeline_series_per_site: 1, terrain_solar_max_steps_per_site: w.max_steps_per_site };
  return {
    parameterRegistry: p.parameters,
    sites: lunarSites,
    defaults: { parameters: [...energy, orientation, ...rf], limits, disclaimer: s.disclaimer },
    status: {
      dem: { available: s.dem.available, cached_tiles: s.dem.cached_tiles, mode: 'cache-only', product: s.dem.product, hint: '' },
      ephemeris: s.ephemeris,
      sites: s.sites.map((x) => ({ id: x.id, name: x.name, lat_deg: x.lat_deg, lon_deg_east: x.lon_deg_east, dem_covered: x.dem_covered })),
      limits: { days_max: w.max_days, step_min_min: limits.step_min_min, max_profile_points: 0, max_samples: w.max_steps_total },
      disclaimer: s.disclaimer,
    },
    grazingDefaults: {
      parameters: [{ key: 'window_days', value: 0.04, unit: 'd', min: 0.01, status: 'I', source: 'RAVEN', note: '' }],
      stations: [], rates_bps: p.defaults.rates_bps, k_values: [], declared_limits: [], disclaimer: s.disclaimer,
    },
  };
}

let catalogRef: PlannerCatalog | null = null;
let registryRef: readonly RavenParameter[] = [];
let defaultsRef: RavenParameters['defaults'] | null = null;

export async function loadCatalog(signal?: AbortSignal): Promise<RavenResult<PlannerCatalog & ModelStamp>> {
  const c = signal ? { signal } : {};
  const [s, p] = await Promise.all([raven.sites(c), raven.parameters(c)]);
  if (!s.ok) return s;
  if (!p.ok) return p;
  const cat = plannerCatalog(s.data, p.data);
  catalogRef = cat;
  registryRef = p.data.parameters;
  defaultsRef = p.data.defaults;
  return { ok: true, data: { ...cat, model_version: p.data.model_version, registry_sha256: p.data.registry_sha256 } };
}

/* ---------------------------------- richieste ---------------------------------- */

export interface Radio { station: 'dsn34' | 'dsn18'; rate: number; gain: number | null; mast: number | null; observerHeight?: number; k?: number | null }

/** Energy overrides without the values that equal the model default (the same body as the default request). */
function trimEnergy(e: Record<string, number | string>): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const [k, v] of Object.entries(e)) {
    const row = registryRef.find((x) => x.scope === 'lunar' && x.name === k);
    if (!(row && row.default === v) && !(k === 'orientation' && v === 'horizontal')) out[k] = v;
  }
  return out;
}

/**
 * One evaluation request: window, site, panel and radio. A value equal to the model default is not sent, so the
 * timeline, the radio section and the mission section with default settings share one cached evaluation.
 */
function buildEvaluate(
  siteId: string, w: { start_utc: string; days: number; step_min: number },
  energy: Record<string, number | string>, radio: Partial<Radio> | undefined,
): EvaluateIn {
  const d = defaultsRef;
  const r: Partial<Radio> = { ...radio };
  if (r.k === 2.33) r.k = null; // grazing.compensator_k default (registry): the default request stays the cached one
  if (d) {
    if (r.station === d.scenario['station']) delete r.station;
    if (r.rate === d.scenario['rate_bps']) delete r.rate;
    if (r.gain === d.rf['tx_gain_dbi']) r.gain = null;
    if (r.mast === d.scenario['antenna_height_m']) r.mast = null;
    if (r.observerHeight === d.scenario['panel_height_m']) delete r.observerHeight;
  }
  return {
    site_id: siteId,
    start_utc: w.start_utc, days: w.days, step_min: w.step_min, include_steps: true, include_windows: true,
    ...(r.station ? { station: r.station } : {}), ...(r.rate ? { rate_bps: r.rate } : {}),
    ...(r.gain != null || r.k != null ? { rf_overrides: { ...(r.gain != null ? { tx_gain_dbi: r.gain } : {}), ...(r.k != null ? { compensator_k: r.k } : {}) } } : {}),
    ...(r.mast != null ? { antenna_height_m: r.mast } : {}),
    ...(r.observerHeight != null ? { panel_height_m: r.observerHeight } : {}),
    energy_overrides: trimEnergy(energy),
  };
}

/** Una valutazione per sito: richiesta del Planner (finestra, sito, pannello) piu' la radio scelta. */
export function evaluateRequests(req: AnalyzeRequest, radio?: Partial<Radio>): EvaluateIn[] {
  return req.site_ids.map((id) => buildEvaluate(id, req, req.overrides, radio));
}

export type Fetched<T> = { ok: true; data: T } | { ok: false; kind: RavenFailure };

export async function evaluateAll(client: RavenClient, reqs: EvaluateIn[], signal: AbortSignal): Promise<Fetched<RavenEvaluation[]>> {
  const out = await Promise.all(reqs.map((r) => client.evaluate(r, { signal })));
  const bad = out.find((r) => !r.ok);
  if (bad && !bad.ok) return { ok: false, kind: bad.kind };
  return { ok: true, data: out.map((r) => (r as { data: RavenEvaluation }).data) };
}

/* ----------------------------------- timeline ---------------------------------- */

export function seriesOf(s: RavenSteps): TimelineSeries & { known: boolean[] } {
  const earthVisible = s.earth_el_deg.map((e, i) => {
    const h = s.earth_horizon_deg[i];
    return num(e) && num(h) ? e > h : false;
  });
  return {
    sun_az_deg: s.sun_az_deg, sun_el_deg: s.sun_el_deg, earth_az_deg: s.earth_az_deg, earth_el_deg: s.earth_el_deg,
    sun_up: s.lit.map((x) => x === true),
    earth_visible: earthVisible,
    dsn_visible: s.dsn_visible.map((x) => x === true),
    link_ok: s.rf_closes.map((x) => x === true),
    margin_db: s.margin_db,
    useful: s.useful.map((x) => x === true),
    gen_w: s.gen_w, soc: s.soc,
    known: s.state.map((x) => x !== 'unknown'),
  };
}

function longestRun(flags: readonly boolean[], stepMin: number): number {
  let best = 0;
  let cur = 0;
  for (const f of flags) { cur = f ? 0 : cur + 1; best = Math.max(best, cur); }
  return best * stepMin / 60;
}

export function metricsOf(ev: RavenEvaluation): SiteMetrics {
  const s = ev.steps!;
  const step = ev.window.step_min;
  const m = ev.metrics;
  const margins = s.margin_db.filter(num);
  const useful = s.useful.map((x) => x === true);
  const windows = ev.windows?.useful.length ?? useful.filter((u, i) => u && !useful[i - 1]).length;
  return {
    useful_hours: m.useful_hours, useful_fraction: m.useful_fraction, longest_gap_h: longestRun(useful, step), n_windows: windows,
    mean_margin_db: margins.length ? margins.reduce((a, b) => a + b, 0) / margins.length : null,
    min_margin_db: margins.length ? Math.min(...margins) : null,
    sun_fraction: frac(s.lit), earth_fraction: frac(s.earth_el_deg.map((e, i) => num(e) && num(s.earth_horizon_deg[i]) ? e > s.earth_horizon_deg[i]! : null)),
    ground_station_fraction: frac(s.dsn_visible), link_fraction: frac(s.rf_closes),
    power_available_fraction: frac(s.gen_w.map((g) => (num(g) ? g > 0 : null))),
    energy: {
      min_soc: m.min_soc ?? 0, survived: m.time_to_first_blackout_h === null, harvested_wh: m.harvested_wh, unmet_wh: m.unmet_wh,
      longest_dark_h: longestRun(s.lit.map((x) => x === true), step),
    },
  };
}

const tagOf = (reg: readonly RavenParameter[], name: string, value: number | string, scopes = ['rf', 'lunar']): ParamTag => {
  const r = reg.find((x) => x.name === name && scopes.includes(x.scope));
  return { key: name, value, unit: r?.unit ?? '', status: r?.tag ?? 'I', source: r?.source ?? 'illustrative' };
};

export function timelineFromRaven(evs: readonly RavenEvaluation[], catalog: PlannerCatalog | null = catalogRef, days?: number): TimelineResult & ModelStamp {
  const first = evs[0]!;
  const used = first.parameters_used!;
  const rate = (used.rf['rate_bps'] as number | undefined) ?? 1e5;
  const link: TimelineResult['assumptions']['link'] = {
    data_rate_bps: rate, required_margin_db: used.scenario['required_margin_db']!,
    ...Object.fromEntries(Object.entries(used.rf).filter(([, v]) => typeof v === 'number' || typeof v === 'string')) as Record<string, number | string>,
  };
  const parameters = catalog?.defaults.parameters ?? [];
  return {
    model_version: first.model_version, registry_sha256: first.registry_sha256,
    disclaimer: first.declared_limits[0] ?? '',
    sampling: SAMPLING_TEXT,
    window: { start_utc: first.window.start_utc, days: days ?? first.window.n_steps * first.window.step_min / 1440, step_min: first.window.step_min, n_steps: first.window.n_steps },
    series_time_unix: first.steps!.time_unix,
    sites: evs.map((ev) => ({
      site: catalog?.sites.find((s) => s.id === ev.site.id) ?? { id: ev.site.id, name: ev.site.name, lat_deg: ev.site.lat_deg, lon_deg_east: ev.site.lon_deg_east, kind: ev.site.kind, coordinate_basis: ev.site.coordinate_basis, verified: ev.site.verified, source_url: ev.site.source_url },
      metrics: metricsOf(ev), series: seriesOf(ev.steps!),
    })),
    assumptions: {
      link, energy: used.energy, parameters,
      sun_up_rule: first.rules.lit, earth_visible_rule: 'Earth elevation above the terrain horizon towards the Earth (LOLA mask)',
      useful_rule: first.rules.useful,
      lunar_frame: 'Mean Earth / Polar Axis', ephemeris: { versions: { model: first.model_version }, kernels: {} },
    },
  };
}

/* ----------------------------------- radio (CompareResult) ---------------------------------- */

export function rfFromRaven(evs: readonly RavenEvaluation[], radio: { station: 'dsn34' | 'dsn18'; rate: number; k?: number }, covered: ReadonlySet<string>): CompareResult & ModelStamp {
  const first = evs[0]!;
  const used = first.parameters_used!;
  const step = first.window.step_min;
  const rows: SiteRow[] = evs.map((ev): SiteRow => {
    const site = { id: ev.site.id, name: ev.site.name, lat_deg: ev.site.lat_deg, lon_deg_east: ev.site.lon_deg_east };
    if (!covered.has(ev.site.id)) return { site, state: UNCOVERED_STATE, covered: false, rank: null };
    const s = ev.steps!;
    const geo = s.earth_el_deg.map((e, i) => (num(e) && num(s.earth_horizon_deg[i]) ? e > s.earth_horizon_deg[i]! : false));
    const ok = s.rf_closes.map((x) => x === true);
    const margins = s.margin_db.filter(num).sort((a, b) => a - b);
    const el = s.earth_el_deg.filter(num);
    const row: AnalysedRow = {
      site, state: 'ok', covered: true, rank: null,
      geometric_hours: hours(geo, step), real_hours: hours(ok, step), transition_hours: hours(s.rf_state.map((x) => x === 'transition'), step),
      total_hours: ev.window.n_steps * step / 60,
      margin_min_db: margins[0] ?? null, margin_median_db: margins.length ? margins[Math.floor((margins.length - 1) / 2)]! : null,
      rate_bps: { min: radio.rate, median: radio.rate, max: radio.rate, mean_declared: radio.rate, declared_fraction: 1 },
      compensator: { k: 0, outage_pct: 0, delivered_bits: 0, scheduled_bits: 0, relative_data: null, declared_steps: 0 },
      earth_el_min_deg: el.length ? Math.min(...el) : null, earth_el_max_deg: el.length ? Math.max(...el) : null,
      terrain: { source: 'lola', product_id: null, synthetic: false, radius_resolved: true, radius_resolved_fraction: 1, correction_status: 'model', correction_label: '', multipath_status: 'not modelled', blocked_fraction: 1 - frac(s.terrain_reason.map((r) => r === 'ok')) },
      series: { time_unix: s.time_unix, margin_db: s.margin_db, earth_el_deg: s.earth_el_deg, chosen_rate_bps: ok.map((x) => (x ? radio.rate : 0)), geometric_visible: geo.map((g) => (g ? 1 : 0)), step_min: step },
      window_samples: { time_unix: s.time_unix, geometric_visible: geo, link_ok: ok, margin_db: s.margin_db, chosen_rate_bps: ok.map((x) => (x ? radio.rate : 0)) },
    };
    return row;
  });
  return {
    model_version: first.model_version, registry_sha256: first.registry_sha256,
    label: first.label, window: { start_utc: first.window.start_utc, days: first.window.n_steps * step / 1440, step_min: step, n_steps: first.window.n_steps },
    sites: rows, ranking: [], ranking_rule: 'see /compare: no score, components shown', ranking_columns: [],
    uncovered_state: UNCOVERED_STATE, rate_bps: radio.rate, station: radio.station, k: radio.k ?? 0,
    parameters: Object.entries(used.rf).filter(([, v]) => typeof v === 'number').map(([k, v]) => { const g = tagOf(registryRef, k, v as number, ['rf']); return { key: k, value: v as number, unit: g.unit, status: g.status as 'V' | 'D' | 'I', source: g.source }; }),
    disclaimer: first.declared_limits[0] ?? '',
  };
}

/* ----------------------------------- Sole e terreno ---------------------------------- */

const solarState = (lit: boolean | null, reason: string): SolarTerrainState =>
  lit === true ? 'upper_above_profile' : lit === false ? 'upper_below_profile'
    : reason === 'outside_coverage' ? 'outside_coverage' : reason === 'missing_dem' ? 'missing_dem' : 'invalid_geometry';

export function solarFromRaven(evs: readonly RavenEvaluation[]): SolarTerrainResult {
  const first = evs[0]!;
  const m = (first.mask ?? {}) as Record<string, unknown>;
  const p0 = ((m['products'] as Record<string, unknown>[] | undefined) ?? [])[0] ?? {};
  return {
    window: { start_utc: first.window.start_utc, days: first.window.n_steps * first.window.step_min / 1440, step_min: first.window.step_min, n_steps: first.window.n_steps },
    series_time_unix: first.steps!.time_unix,
    sites: evs.map((ev) => {
      const s = ev.steps!;
      const state = s.lit.map((l, i) => solarState(l, s.terrain_reason[i]!));
      const allKnown = state.every((x) => x === 'upper_above_profile' || x === 'upper_below_profile');
      const mask = ev.mask as Record<string, number | string> | null;
      return {
        site_id: ev.site.id,
        horizon_deg: s.sun_horizon_deg.map((h, i) => (state[i] === 'upper_above_profile' || state[i] === 'upper_below_profile' ? h : null)),
        state,
        disc_fraction: s.disc_fraction,
        mask: mask ? {
          n_azimuths: mask['n_azimuths'] as number, observer_height_m: ev.heights.panel_height_m,
          complete_azimuth_fraction: mask['complete_azimuth_fraction'] as number, far_terrain_dominant_fraction: mask['far_terrain_dominant_fraction'] as number,
          coverage_limit: mask['coverage_limit'] as string, cache: mask['cache'] as string,
        } : null,
        energy_sensitivity: allKnown && ev.metrics.harvested_wh !== null && ev.metrics.min_soc !== null &&
            s.gen_w.every(num) && s.soc.every(num)
          ? { status: 'available' as const, gen_w: s.gen_w.map((x) => x ?? 0), soc: s.soc.map((x) => x ?? 0), harvested_wh: ev.metrics.harvested_wh, min_soc: ev.metrics.min_soc ?? 0 }
          : { status: 'unknown_terrain' as const },
      };
    }),
    assumptions: {
      dem_product: String(p0['id'] ?? ''), dem_sha256: String(p0['sha256'] ?? ''), dem_label_sha256: String(p0['label_sha256'] ?? ''),
      lunar_frame: 'Mean Earth / Polar Axis', ephemeris: { versions: { model: first.model_version }, kernels: {} },
      profile_length_m: first.heights.profile_length_m, profile_spacing_m: Number(m['near_step_m'] ?? 0), observer_height_m: first.heights.panel_height_m,
      sun_semidiameter_deg: 0, azimuth: `${String(m['n_azimuths'] ?? '')} azimuths`, sampling: `${first.window.n_steps} steps`,
      limits: String(m['coverage_limit'] ?? ''), dem_policy: 'cache only',
    },
  };
}

/* ----------------------------------- missione ---------------------------------- */

export function missionFromRaven(ev: RavenEvaluation, req: MissionRequest, registry: readonly RavenParameter[] = registryRef): MissionResult & ModelStamp {
  const s = ev.steps!;
  const m = ev.metrics;
  const used = ev.parameters_used!;
  const tag = (name: string, value: number | string) => tagOf(registry, name, value);
  const sh = ev.inputs_state;
  return {
    model_version: ev.model_version, registry_sha256: ev.registry_sha256,
    series: {
      time_unix: s.time_unix, sun_el_deg: s.sun_el_deg as number[], disc_fraction: s.disc_fraction, gen_w: s.gen_w, soc: s.soc, margin_db: s.margin_db,
      dsn_visible: s.dsn_visible, link_usable: s.link_usable, state: s.state as MissionState[], useful: s.useful,
      limiting: s.limiting as MissionResult['series']['limiting'],
    },
    metrics: {
      n_steps: m.n_steps, known_steps: m.known_steps, unknown_steps: m.unknown_steps, useful_hours: m.useful_hours, useful_fraction: m.useful_fraction,
      unknown_hours: m.unknown_hours, state_hours: m.state_hours as Record<MissionState, number>,
      limiting_fraction: m.limiting_fraction as MissionResult['metrics']['limiting_fraction'], min_soc: m.min_soc, min_soc_scope: m.min_soc_scope,
      time_to_first_blackout_h: m.time_to_first_blackout_h, sun_hours: m.sun_hours, harvested_wh: m.harvested_wh, unmet_wh: m.unmet_wh,
    },
    inputs_state: {
      shadow: `${sh.terrain_mask}; ${Object.entries(sh.illumination_reason_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}`,
      rf: Object.entries(sh.rf_reason_counts).map(([k, v]) => `${k}: ${v}`).join(', '),
      dsn: Object.entries(sh.dsn_reason_counts).map(([k, v]) => `${k}: ${v}`).join(', '),
    },
    rate_bps: (used.rf['rate_bps'] as number) ?? req.rate_bps, station: req.station,
    tx_power_w: 10 ** ((used.rf['tx_power_dbw'] as number) / 10),
    parameters: {
      energy: Object.entries(used.energy).map(([k, v]) => tag(k, v)),
      rf: Object.entries(used.rf).filter(([, v]) => typeof v === 'number').map(([k, v]) => tag(k, v as number)),
      observer_height: tag('panel_height_m', ev.heights.panel_height_m),
      dsn_min_elevation: tag('ground_station_min_elevation_deg', used.scenario['dsn_min_elevation_deg']!),
    },
    declared_limits: ev.declared_limits,
    ...(ev.windows ? { windows: ev.windows.useful } : {}),
  };
}

/** Richiesta di missione del Planner tradotta per il modello unico (la compensazione k non fa parte della catena). */
export function missionEvaluateIn(req: MissionRequest): EvaluateIn {
  const { antenna_height_m, tx_gain_dbi, compensator_k } = req.rf_overrides;
  return buildEvaluate(req.site_id, req, req.energy_overrides, {
    station: req.station, rate: req.rate_bps, gain: tx_gain_dbi ?? null, k: compensator_k ?? null, mast: antenna_height_m ?? null, observerHeight: req.observer_height_m,
  });
}

/* ----------------------------------- orizzonte ---------------------------------- */

export function horizonFromRaven(h: RavenHorizon): HorizonResult & ModelStamp & { model_version: string } {
  const meta = (h.meta ?? {}) as Record<string, unknown>;
  const products = (meta['products'] as Record<string, unknown>[] | undefined) ?? [];
  const p0 = products[0] ?? {};
  const step = h.azimuth_step_deg || 0.25;
  const bad: HorizonSample['state'] = h.state === 'outside_coverage' ? 'outside_coverage' : 'missing_dem';
  // outside the LOLA coverage the model returns no profile: every azimuth is unknown, never a clear horizon
  const samples: HorizonSample[] = Array.isArray(h.elevation_deg)
    ? h.elevation_deg.map((e, i): HorizonSample => {
        const complete = h.complete[i] === true && e !== null;
        return { azimuth_deg: i * step, elevation_deg: complete ? e : null, distance_m: complete ? h.distance_m[i] ?? null : null, state: complete ? 'ok' : 'missing_dem' };
      })
    : Array.from({ length: Math.round(360 / step) }, (_, i): HorizonSample => ({ azimuth_deg: i * step, elevation_deg: null, distance_m: null, state: bad }));
  return {
    model_version: '', registry_sha256: '',
    site: { id: h.site.id, name: h.site.name }, samples,
    dem_product: String(p0['id'] ?? meta['near_product'] ?? ''), dem_sha256: String(p0['sha256'] ?? ''), dem_label_sha256: String(p0['label_sha256'] ?? ''),
    lunar_frame: 'Mean Earth / Polar Axis', profile_length_m: 10000, profile_spacing_m: Number(meta['near_step_m'] ?? 0),
    azimuth_step_deg: step, observer_height_m: h.height_m, limits: h.limit, dem_policy: 'cache only',
  };
}

/** Limiti D9 per la finestra del Planner (stessi numeri del modello). */
export const PLANNER_LIMITS = { daysMax: RAVEN_MAX_DAYS, perSite: RAVEN_MAX_STEPS_PER_SITE, total: RAVEN_MAX_STEPS_TOTAL } as const;
