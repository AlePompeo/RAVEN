// SPDX-License-Identifier: Apache-2.0
import type { MessageKey } from '../../i18n/i18n.svelte';
import { customSites, isCustomId, toApi, validateForm, type CustomSiteDef } from '../../shell/customSites';
import { ravenSteps, type EvaluateIn, type RavenEvaluation } from '../../shell/ravenApi';
import type { ParamRow } from '../compare/lunar';
import { panelDefaults, panelOverrides, readPanel, type PanelValues } from './panel';
import { defaultObjectives, readObjectives, type MissionObjectives } from './objectives';
import { RADIO_PRESETS, type RadioPreset } from './setup';
import { evaluateRequests } from './ravenAdapter';
import { plannerRequest, type EphemerisRange, type PlannerInput } from './timeline';
import { newReportPlanning, readReportPlanning, type ReportPlanning } from './reportPlanning';
import { thermalOverrides } from './reliability';

export const JOURNEY_STEPS = ['mission', 'sites', 'period', 'energy', 'reliability', 'radio', 'compare', 'dossier', 'report'] as const;
export type JourneyStep = typeof JOURNEY_STEPS[number];
export const MISSION_SHIFT_DAYS = [0, 3, 7, 28] as const;
export type MissionShiftDays = typeof MISSION_SHIFT_DAYS[number];
export const DRAFT_KEY = 'hb.planner-journey.v1';
export const RUN_KEY = 'hb.planner-journey.run.v1';

export interface MissionShiftBaseline {
  site_id: string;
  site_name: string;
  start_utc: string;
  useful_hours: number;
  unknown_hours: number;
  harvested_wh: number | null;
  min_soc: number | null;
}

export interface JourneyDraft {
  name: string;
  input: PlannerInput;
  panel: PanelValues;
  radio: { [K in keyof RadioPreset]: RadioPreset[K] extends number ? number | null : RadioPreset[K] };
  objectives: MissionObjectives;
  decision: string;
  planning?: ReportPlanning;
}

export interface JourneyRun {
  key: string;
  createdAt: string;
  config: JourneyDraft;
  requests: EvaluateIn[];
  evaluations: RavenEvaluation[];
  missionShiftDays?: MissionShiftDays;
  baseline?: MissionShiftBaseline[];
  baselineKey?: string;
}

export function newDraft(rows: readonly ParamRow[], siteIds: readonly string[], site?: string | null, time?: string | null): JourneyDraft | null {
  const panel = panelDefaults(rows);
  if (!panel) return null;
  const siteA = site && siteIds.includes(site) ? site : siteIds[0] ?? '';
  return {
    name: '', input: { mode: 'sites', siteA, siteB: siteIds.find((id) => id !== siteA) ?? '',
      start: time?.slice(0, 16) ?? '2027-04-07T00:00', startB: '2027-05-07T00:00', days: 7, stepMin: 60 },
    panel, radio: { ...RADIO_PRESETS.baseline }, objectives: defaultObjectives(), decision: '', planning: newReportPlanning(),
  };
}

export function radioValid(r: JourneyDraft['radio']): boolean {
  const within = (v: number | null, min: number, max: number) => v !== null && Number.isFinite(v) && v >= min && v <= max;
  return (r.station === 'dsn34' || r.station === 'dsn18') && within(r.gain, -10, 45) && within(r.mast, 0.1, 100) &&
    within(r.k, 0, 6) && r.rate !== null && [10000, 30000, 100000, 300000, 1000000, 3000000].includes(r.rate);
}

export function journeyIssue(d: JourneyDraft, step: number, ids: readonly string[], rows: readonly ParamRow[], definitions = customSites.get(), range?: EphemerisRange | null): MessageKey | null {
  if (step === 0) return d.name.length > 80 || !readObjectives(d.objectives) ? 'planner.objectivesInvalid' : null;
  if (step === 1) return !ids.includes(d.input.siteA) ||
    (d.input.mode === 'sites' && (!ids.includes(d.input.siteB) || d.input.siteA === d.input.siteB)) ? 'planner.errorSites' : null;
  if (step === 2) {
    const r = plannerRequest(d.input, 6000, 1, {}, definitions, range);
    return typeof r === 'string' ? r : null;
  }
  if (step === 3) return panelOverrides(d.panel, rows) === null ? 'planner.panelInvalid' : null;
  if (step === 4) return thermalOverrides(d.planning?.reliability, rows) === null ? 'rel.invalidPower' : null;
  if (step === 5) return radioValid(d.radio) ? null : 'planner.radioInvalid';
  return null;
}

export function journeyRequests(d: JourneyDraft, rows: readonly ParamRow[], definitions = customSites.get(), range?: EphemerisRange | null,
  missionShiftDays: MissionShiftDays = 0): EvaluateIn[] | null {
  const energy = panelOverrides(d.panel, rows);
  const thermal = thermalOverrides(d.planning?.reliability, rows);
  const r = d.radio;
  if (energy === null || thermal === null || !radioValid(r) || r.gain === null || r.rate === null || r.mast === null || r.k === null) return null;
  const req = plannerRequest(d.input, 6000, 1, { ...energy, ...thermal }, definitions, range);
  if (typeof req === 'string') return null;
  const radio = { station: r.station, rate: r.rate, gain: r.gain, mast: r.mast };
  const requests = [...evaluateRequests(req.first, radio), ...(req.second ? evaluateRequests(req.second, radio) : [])];
  return requests.map((q) => {
    const custom = definitions.find((s) => s.id === q.site_id);
    return { ...q, rf_overrides: { ...q.rf_overrides, compensator_k: r.k! },
      ...(missionShiftDays ? { mission_shift_days: missionShiftDays } : {}),
      ...(custom ? { custom_site: toApi(custom) } : {}) };
  });
}

export function isMissionShiftDays(value: unknown): value is MissionShiftDays {
  return MISSION_SHIFT_DAYS.some((days) => days === value);
}

export function shiftedStartUtc(startUtc: string, days: MissionShiftDays): string | null {
  const timestamp = Date.parse(startUtc);
  if (!Number.isFinite(timestamp)) return null;
  return new Date(timestamp + days * 86400000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function missionShiftBaseline(evaluations: readonly RavenEvaluation[]): MissionShiftBaseline[] {
  return evaluations.map((e) => ({
    site_id: e.site.id,
    site_name: e.site.name,
    start_utc: e.base_start_utc ?? e.window.start_utc,
    useful_hours: e.metrics.useful_hours,
    unknown_hours: e.metrics.unknown_hours,
    harvested_wh: e.metrics.harvested_wh,
    min_soc: e.metrics.min_soc,
  }));
}

export function requestKey(requests: readonly EvaluateIn[]): string {
  return JSON.stringify(requests);
}

export function missionBaseKey(requests: readonly EvaluateIn[]): string {
  return JSON.stringify(requests.map((request) => {
    const base = { ...request };
    delete base.mission_shift_days;
    return base;
  }));
}

/** Unknown samples are not failures and never disappear into the denominator. */
export function fraction(values: readonly (boolean | null)[]): number | null {
  return values.length && values.every((v) => v !== null) ? values.filter((v) => v === true).length / values.length : null;
}

export function earthVisibility(e: RavenEvaluation): (boolean | null)[] {
  return e.steps?.earth_el_deg.map((el, i) => {
    const horizon = e.steps?.earth_horizon_deg[i];
    return el == null || horizon == null ? null : el > horizon;
  }) ?? [];
}

export function firstChange(values: readonly (boolean | null)[], index: number): number | null {
  if (values[index] == null) return null;
  for (let i = index + 1; i < values.length; i++) {
    if (values[i] === null) return null;
    if (values[i] !== values[index]) return i;
  }
  return null;
}

export function readDraft(raw: string | null, rows: readonly ParamRow[], ids: readonly string[], definitions = customSites.get()): JourneyDraft | null {
  if (!raw || raw.length > 64000) return null;
  try {
    const d: JourneyDraft = JSON.parse(raw);
    if (!d || typeof d !== 'object' || typeof d.name !== 'string' || d.name.length > 80 ||
        typeof d.decision !== 'string' || d.decision.length > 2000 || !d.input || !d.radio ||
        !readObjectives(d.objectives) || !readPanel(d.panel, rows) || !radioValid(d.radio)) return null;
    if (!['sites', 'dates'].includes(d.input.mode) || !ids.includes(d.input.siteA) ||
        (d.input.mode === 'sites' && !ids.includes(d.input.siteB)) ||
        typeof d.input.start !== 'string' || typeof d.input.startB !== 'string' ||
        typeof d.input.days !== 'number' || typeof d.input.stepMin !== 'number') return null;
    const planning = d.planning === undefined ? newReportPlanning() : readReportPlanning(d.planning);
    return !planning || journeyIssue(d, 2, ids, rows, definitions) ? null : { ...d, planning };
  } catch {
    return null;
  }
}

/** Check sampled payloads before charting or restoring an untrusted browser archive. */
export function validEvaluations(values: unknown, requests: readonly EvaluateIn[]): values is RavenEvaluation[] {
  if (!Array.isArray(values) || values.length !== requests.length) return false;
  const numeric = ['sun_az_deg', 'sun_el_deg', 'earth_az_deg', 'earth_el_deg', 'sun_horizon_deg',
    'earth_horizon_deg', 'margin_db', 'gen_w', 'soc'] as const;
  const flags = ['lit', 'rf_closes', 'dsn_visible', 'link_usable', 'useful'] as const;
  return values.every((e: RavenEvaluation, i) => {
    if (!e) return false;
    const req = requests[i]!;
    const n = ravenSteps(req.days, req.step_min);
    const shiftDays = req.mission_shift_days ?? 0;
    const expectedStart = shiftedStartUtc(req.start_utc, shiftDays);
    if (!expectedStart || (shiftDays > 0 && (e.mission_shift_days !== shiftDays || e.base_start_utc !== req.start_utc))) return false;
    if (!e || !e.site || e.site.id !== req.site_id || !e.window || e.window.n_steps !== n ||
        e.window.start_utc !== expectedStart || e.window.step_min !== req.step_min ||
        (e.mission_shift_days !== undefined && e.mission_shift_days !== shiftDays) ||
        (e.base_start_utc !== undefined && e.base_start_utc !== req.start_utc) ||
        typeof e.site.name !== 'string' || !Number.isFinite(e.site.lat_deg) || !Number.isFinite(e.site.lon_deg_east) ||
        typeof e.model_version !== 'string' || typeof e.registry_sha256 !== 'string' || !e.metrics ||
        !e.inputs_state || typeof e.inputs_state.terrain_mask !== 'string' ||
        (req.custom_site && (e.site.lat_deg !== req.custom_site.lat_deg || e.site.lon_deg_east !== req.custom_site.lon_deg_east)) ||
        !['useful_hours', 'unknown_hours', 'unknown_steps'].every((key) =>
          typeof e.metrics[key as keyof typeof e.metrics] === 'number' && Number.isFinite(e.metrics[key as keyof typeof e.metrics])) ||
        (e.metrics.harvested_wh !== null && (typeof e.metrics.harvested_wh !== 'number' || !Number.isFinite(e.metrics.harvested_wh))) ||
        (e.metrics.min_soc !== null && (typeof e.metrics.min_soc !== 'number' || !Number.isFinite(e.metrics.min_soc))) ||
        !Array.isArray(e.declared_limits) || !e.declared_limits.every((v) => typeof v === 'string') || !e.steps) return false;
    if (req.include_windows && !e.windows) return false;
    if (e.rf_series && (typeof e.rf_series !== 'object' || Array.isArray(e.rf_series) ||
        !Object.values(e.rf_series).every((column) => Array.isArray(column) && column.length === n &&
          column.every((v) => v === null || (typeof v === 'number' && Number.isFinite(v)))))) return false;
    if (e.windows && !(['lit', 'link_usable', 'useful'] as const).every((key) =>
      Array.isArray(e.windows![key]) && e.windows![key].every((w) => w &&
        Number.isFinite(w.start_unix) && Number.isFinite(w.end_unix) && w.end_unix >= w.start_unix &&
        typeof w.open_start === 'boolean' && typeof w.open_end === 'boolean'))) return false;
    if (e.parameters_used && !(['rf', 'energy', 'scenario'] as const).every((key) =>
      e.parameters_used![key] && typeof e.parameters_used![key] === 'object' &&
      Object.values(e.parameters_used![key]).every((v) => typeof v === 'string' || typeof v === 'boolean' || (typeof v === 'number' && Number.isFinite(v))))) return false;
    const s = e.steps;
    if (s.chosen_rate_bps !== undefined && (!Array.isArray(s.chosen_rate_bps) || s.chosen_rate_bps.length !== n ||
        !s.chosen_rate_bps.every((v) => v === null || (typeof v === 'number' && Number.isFinite(v) && v >= 0)))) return false;
    return Array.isArray(s.time_unix) && s.time_unix.length === n &&
      s.time_unix.every((t, j) => t === Date.parse(expectedStart) / 1000 + j * req.step_min * 60) &&
      numeric.every((k) => Array.isArray(s[k]) && s[k].length === n && s[k].every((v) => v === null || (typeof v === 'number' && Number.isFinite(v)))) &&
      flags.every((k) => Array.isArray(s[k]) && s[k].length === n && s[k].every((v) => v === null || typeof v === 'boolean')) &&
      s.soc.every((v) => v === null || (v >= 0 && v <= 1)) &&
      Array.isArray(s.state) && s.state.length === n && s.state.every((v) => ['operational', 'comms_only', 'survival', 'dark', 'unknown'].includes(v)) &&
      Array.isArray(s.limiting) && s.limiting.length === n && s.limiting.every((v) => v === null || ['energy', 'link', 'visibility', 'multiple'].includes(v));
  });
}

function runCustomSites(requests: unknown): CustomSiteDef[] | null {
  if (!Array.isArray(requests)) return null;
  const definitions: CustomSiteDef[] = [];
  for (const q of requests) {
    if (!q || typeof q !== 'object') return null;
    if (!q.custom_site) {
      if (isCustomId(q.site_id)) return null;
      continue;
    }
    const s = q.custom_site;
    if (!s || !isCustomId(s.id) || q.site_id !== s.id ||
        typeof s.lat_deg !== 'number' || typeof s.lon_deg_east !== 'number') return null;
    const result = validateForm({ name: s.name, lat: s.lat_deg, lon: s.lon_deg_east,
      panel: s.panel_height_m, antenna: s.antenna_height_m });
    if (!result.ok) return null;
    const definition = { id: s.id, ...result.value };
    const previous = definitions.find((d) => d.id === s.id);
    if (previous && JSON.stringify(previous) !== JSON.stringify(definition)) return null;
    if (!previous) definitions.push(definition);
  }
  return definitions;
}

export function readRun(raw: string | null, rows: readonly ParamRow[], ids: readonly string[], registry: string, modelVersion?: string): JourneyRun | null {
  if (!raw || raw.length > 4000000) return null;
  try {
    const run: JourneyRun = JSON.parse(raw);
    if (!run || typeof run !== 'object') return null;
    const definitions = runCustomSites(run.requests);
    if (!definitions) return null;
    const missionShiftDays = run.requests.length ? run.requests[0]!.mission_shift_days ?? 0 : 0;
    if (!isMissionShiftDays(missionShiftDays) ||
        !run.requests.every((q) => (q.mission_shift_days ?? 0) === missionShiftDays) ||
        (run.missionShiftDays !== undefined &&
          (!isMissionShiftDays(run.missionShiftDays) || run.missionShiftDays !== missionShiftDays)) ||
        (missionShiftDays > 0 && run.missionShiftDays !== missionShiftDays)) return null;
    const config = readDraft(JSON.stringify(run.config), rows, [...ids, ...definitions.map((s) => s.id)], definitions);
    if (!config || typeof run.createdAt !== 'string' || !Number.isFinite(Date.parse(run.createdAt))) return null;
    const requests = journeyRequests(config, rows, definitions, undefined, missionShiftDays);
    if (!requests || run.key !== requestKey(requests) || requestKey(run.requests) !== run.key || !validEvaluations(run.evaluations, requests) ||
        run.evaluations.some((e) => e.registry_sha256 !== registry || (modelVersion && e.model_version !== modelVersion)) ||
        new Set(run.evaluations.map((e) => e.model_version)).size !== 1) return null;
    const baselineKey = run.baselineKey ?? (missionShiftDays === 0 ? missionBaseKey(requests) : undefined);
    if (run.baseline !== undefined && baselineKey !== missionBaseKey(requests)) return null;
    if (run.baseline !== undefined && (!Array.isArray(run.baseline) || !run.baseline.every((b) =>
      b && typeof b.site_id === 'string' && typeof b.site_name === 'string' && typeof b.start_utc === 'string' &&
      Number.isFinite(Date.parse(b.start_utc)) && Number.isFinite(b.useful_hours) && Number.isFinite(b.unknown_hours) &&
      (b.harvested_wh === null || Number.isFinite(b.harvested_wh)) && (b.min_soc === null || Number.isFinite(b.min_soc))))) return null;
    return { ...run, config, requests };
  } catch {
    return null;
  }
}
