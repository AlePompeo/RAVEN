// SPDX-License-Identifier: Apache-2.0
import { toStartUtc, type AnalyzeRequest, type ApiFailure, type LunarSite, type ParamRow, type SiteMetrics } from '../compare/lunar';
import type { AnalysedRow } from '../compare/grazingCompare';
import { RAVEN_MAX_STEPS_PER_SITE, RAVEN_MAX_STEPS_TOTAL, type RavenClient, type RavenSites } from '../../shell/ravenApi';
import { evaluateAll, evaluateRequests, timelineFromRaven, type ModelStamp } from './ravenAdapter';
import { customSites, isCustomId, type CustomSiteDef } from '../../shell/customSites';

export interface TimelineSeries {
  sun_az_deg: (number | null)[];
  sun_el_deg: (number | null)[];
  earth_az_deg: (number | null)[];
  earth_el_deg: (number | null)[];
  sun_up: boolean[];
  earth_visible: boolean[];
  dsn_visible: boolean[];
  link_ok: boolean[];
  margin_db: (number | null)[];
  useful: boolean[];
  gen_w: (number | null)[];
  soc: (number | null)[];
}

export interface TimelineResult {
  model_version?: string;
  registry_sha256?: string;
  disclaimer: string;
  sampling: string;
  window: { start_utc: string; days: number; step_min: number; n_steps: number };
  series_time_unix: number[];
  sites: { site: LunarSite; metrics: SiteMetrics; series: TimelineSeries }[];
  assumptions: {
    link: { data_rate_bps: number; required_margin_db: number } & Record<string, number | string>;
    energy: Record<string, number | string>;
    parameters: ParamRow[];
    sun_up_rule: string;
    earth_visible_rule: string;
    useful_rule: string;
    lunar_frame?: string;
    ephemeris?: { versions: Record<string, string>; kernels: Record<string, string> };
  };
}

export type TimelineComparison = TimelineResult & { timesBySite: number[][]; startsBySite: string[] };

export interface PlannerInput {
  mode: 'sites' | 'dates';
  siteA: string;
  siteB: string;
  start: string;
  startB: string;
  days: number | null;
  stepMin: number | null;
}

export interface PlannerRequests {
  first: AnalyzeRequest;
  second: AnalyzeRequest | null;
}

export type PlannerValidationError = 'planner.errorStart' | 'planner.errorSites' | 'planner.errorStartB' |
  'planner.errorDates' | 'planner.errorDays' | 'planner.errorStep' | 'planner.errorSize' | 'planner.customInvalid' | 'planner.errorEphemerisRange';
export type TimelineError = 'planner.errorNetwork' | 'planner.errorInvalid' | 'planner.errorUnavailable' |
  'planner.errorServer' | 'planner.errorResponse';

export interface SavedPlanner {
  input: PlannerInput;
  lesson: number;
  siteView: 'A' | 'B';
  decision: string;
  quiz: '' | 'yes' | 'no';
  quizSolar?: '' | 'yes' | 'no';
  quizMissing?: '' | 'yes' | 'no';
  mast: number;
  panel?: unknown;
  objectives?: unknown;
  setup?: unknown;
}

export function readSavedPlanner(raw: string | null, validSites: readonly string[], definitions = customSites.get()): SavedPlanner | null {
  const input = readSavedInput(raw, validSites, definitions);
  if (!input || !raw) return null;
  const v: unknown = JSON.parse(raw);
  if (!v || typeof v !== 'object') return null;
  const state = v as Record<string, unknown>;
  return {
    input,
    lesson: typeof state.lesson === 'number' && Number.isInteger(state.lesson) && state.lesson >= 0 && state.lesson < 6 ? state.lesson : 0,
    siteView: state.siteView === 'B' ? 'B' : 'A',
    decision: typeof state.decision === 'string' && state.decision.length <= 2000 ? state.decision : '',
    quiz: state.quiz === 'yes' || state.quiz === 'no' ? state.quiz : '',
    ...(state.quizSolar === undefined ? {} : { quizSolar: state.quizSolar === 'yes' || state.quizSolar === 'no' ? state.quizSolar : '' }),
    ...(state.quizMissing === undefined ? {} : { quizMissing: state.quizMissing === 'yes' || state.quizMissing === 'no' ? state.quizMissing : '' }),
    mast: typeof state.mast === 'number' && Number.isFinite(state.mast) && state.mast >= 0.1 && state.mast <= 100 ? state.mast : 2,
    ...(state.panel === undefined ? {} : { panel: state.panel }),
    ...(state.objectives === undefined ? {} : { objectives: state.objectives }),
    ...(state.setup === undefined ? {} : { setup: state.setup }),
  };
}

export function readSavedInput(raw: string | null, validSites: readonly string[], definitions = customSites.get()): PlannerInput | null {
  if (!raw || raw.length > 5000) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object') return null;
    const v = value as Record<string, unknown>;
    if (typeof v.siteA !== 'string' || typeof v.siteB !== 'string' || !validSites.includes(v.siteA) ||
        !validSites.includes(v.siteB) || typeof v.start !== 'string' ||
        typeof v.days !== 'number' || typeof v.stepMin !== 'number') return null;
    const input: PlannerInput = {
      mode: v.mode === 'dates' ? 'dates' : 'sites',
      siteA: v.siteA, siteB: v.siteB, start: v.start,
      startB: typeof v.startB === 'string' ? v.startB : v.start,
      days: v.days, stepMin: v.stepMin,
    };
    return typeof plannerRequest(input, Number.MAX_SAFE_INTEGER, 10, {}, definitions) === 'string' ? null : input;
  } catch {
    return null;
  }
}

export type EphemerisRange = NonNullable<RavenSites['ephemeris']['supported_range']>;

export function plannerDateBounds(range: EphemerisRange | null | undefined, days: number | null) {
  if (!range) return null;
  const duration = days !== null && Number.isFinite(days) && days >= 0 ? days * 86400000 : 0;
  return {
    min: new Date(Math.ceil(Date.parse(range.start_utc) / 60000) * 60000).toISOString().slice(0, 16),
    max: new Date(Math.floor((Date.parse(range.end_utc) - duration) / 60000) * 60000).toISOString().slice(0, 16),
  };
}

/** Steps offered by the period step, in minutes. */
export const STEP_OPTIONS = [10, 30, 60, 180, 360, 1440] as const;

/**
 * The smallest offered step, not below the current one, that keeps the period inside the per-scenario cap
 * (1500 samples) and the total cap (6000, two scenarios in sites mode). null when no offered step fits.
 * Long periods are admitted only with a step chosen this way and shown to the user, never silently.
 */
export function compatibleStep(days: number, stepMin: number, scenarios: 1 | 2): number | null {
  if (!Number.isFinite(days) || days <= 0 || days > 366) return null;
  for (const s of STEP_OPTIONS) {
    if (s < stepMin) continue;
    const n = Math.max(1, Math.floor(days * 1440 / s + 1e-9));
    if (n <= RAVEN_MAX_STEPS_PER_SITE && n * scenarios <= RAVEN_MAX_STEPS_TOTAL) return s;
  }
  return null;
}

export function plannerRequest(input: PlannerInput, maxPoints: number, seriesPerSite: number, overrides: Record<string, number | string> = {}, definitions: readonly CustomSiteDef[] = customSites.get(), range?: EphemerisRange | null): PlannerRequests | PlannerValidationError {
  const start = toStartUtc(input.start);
  if (!start) return 'planner.errorStart';
  if (!input.siteA || (input.mode === 'sites' && (!input.siteB || input.siteA === input.siteB))) return 'planner.errorSites';
  const startB = input.mode === 'dates' ? toStartUtc(input.startB) : start;
  if (!startB) return 'planner.errorStartB';
  if (input.mode === 'dates' && start === startB) return 'planner.errorDates';
  if (input.days === null || !Number.isFinite(input.days) || input.days < 0.01 || input.days > 366)
    return 'planner.errorDays';
  const duration = input.days * 86400000;
  if (range && [start, startB].some((s) => Date.parse(s) < Date.parse(range.start_utc) ||
      Date.parse(s) + duration > Date.parse(range.end_utc)))
    return 'planner.errorEphemerisRange';
  if (input.stepMin === null || !Number.isInteger(input.stepMin) || input.stepMin < 10 || input.stepMin > 1440)
    return 'planner.errorStep';
  const steps = Math.max(1, Math.floor(input.days * 1440 / input.stepMin + 1e-9));
  if (steps > RAVEN_MAX_STEPS_PER_SITE) return 'planner.errorSize';
  if (steps * (input.mode === 'sites' ? 2 : 1) * seriesPerSite > maxPoints)
    return 'planner.errorSize';
  const siteIds = input.mode === 'sites' ? [input.siteA, input.siteB] : [input.siteA];
  if (siteIds.some((id) => isCustomId(id) && !definitions.some((s) => s.id === id))) return 'planner.customInvalid';
  const first: AnalyzeRequest = { site_ids: siteIds, start_utc: start, days: input.days, step_min: input.stepMin, overrides };
  const second: AnalyzeRequest | null = input.mode === 'dates' ? { ...first, site_ids: [input.siteA], start_utc: startB } : null;
  return { first, second };
}

export interface Segment {
  start: number;
  length: number;
  value: boolean;
}

export function synchronizedRfSamples(row: Pick<AnalysedRow, 'window_samples'> | undefined, times: number[] | undefined): AnalysedRow['window_samples'] | null {
  const samples = row?.window_samples;
  if (!samples || !times || !times.length) return null;
  const arrays = [samples.time_unix, samples.geometric_visible, samples.link_ok, samples.margin_db, samples.chosen_rate_bps];
  if (arrays.some((values) => !Array.isArray(values) || values.length !== times.length)) return null;
  if (samples.time_unix.some((time, i) => time !== times[i])) return null;
  if (!samples.geometric_visible.every((v) => typeof v === 'boolean') ||
      !samples.link_ok.every((v) => typeof v === 'boolean') ||
      !samples.margin_db.every((v) => v === null || (typeof v === 'number' && Number.isFinite(v))) ||
      !samples.chosen_rate_bps.every((v) => typeof v === 'number' && Number.isFinite(v))) return null;
  return samples;
}

/** Intervalli contigui di campioni: nessuna interpolazione delle transizioni. */
export function segments(values: boolean[]): Segment[] {
  const out: Segment[] = [];
  values.forEach((value, i) => {
    const last = out[out.length - 1];
    if (last && last.value === value) last.length++;
    else out.push({ start: i, length: 1, value });
  });
  return out;
}

const failureMessage: Record<'network' | 'invalid' | 'unavailable' | 'server' | 'response' | 'aborted', TimelineError> = {
  network: 'planner.errorNetwork', invalid: 'planner.errorInvalid', unavailable: 'planner.errorUnavailable',
  server: 'planner.errorServer', response: 'planner.errorResponse', aborted: 'planner.errorNetwork',
};

/** Timeline dal modello unico (/api/raven/evaluate): stessa terra, stessa maschera LOLA, stesso set radio delle altre pagine. */
export async function fetchTimeline(client: RavenClient, req: AnalyzeRequest, signal: AbortSignal): Promise<
  { ok: true; data: TimelineResult & ModelStamp } | { ok: false; kind: ApiFailure; message: TimelineError }
> {
  const r = await evaluateAll(client, evaluateRequests(req), signal);
  if (!r.ok) {
    const kind: ApiFailure = r.kind === 'invalid' ? 'invalid' : r.kind === 'unavailable' ? 'unavailable' : r.kind === 'server' || r.kind === 'response' ? 'server' : 'network';
    return { ok: false, kind, message: failureMessage[r.kind] };
  }
  return { ok: true, data: timelineFromRaven(r.data, undefined, req.days) };
}
