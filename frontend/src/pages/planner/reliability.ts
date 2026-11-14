// SPDX-License-Identifier: Apache-2.0
import type { RavenEvaluation } from '../../shell/ravenApi';
import type { ParamRow } from '../compare/lunar';
import { paramError } from '../compare/lunar';

export const COMPONENT_IDS = ['power', 'battery', 'radio', 'computer', 'thermal'] as const;
export const COMPONENT_FIELDS = {
  launch_failure_probability: [0, 1, '1'], landing_failure_probability: [0, 1, '1'],
  launch_loss_fraction: [0, 1, '1'], landing_loss_fraction: [0, 1, '1'],
  failure_rate_per_hour: [0, 1000, 'h⁻¹'], upset_rate_per_hour: [0, 1000, 'h⁻¹'],
  restart_success_probability: [0, 1, '1'], mean_recovery_hours: [0, 1e6, 'h'],
  degradation_rate_per_hour: [0, 1000, 'h⁻¹'], minimum_performance_fraction: [0, 1, '1'],
  thermal_min_c: [-273.15, 1000, '°C'], thermal_max_c: [-273.15, 1000, '°C'],
  rated_min_c: [-273.15, 1000, '°C'], rated_max_c: [-273.15, 1000, '°C'],
  dose_rate_krad_h: [0, 1000, 'krad(Si)/h'], shield_transmission: [0, 1, '1'], tid_limit_krad: [0, 1e9, 'krad(Si)'],
} as const;
export const PROFILE_FIELDS = {
  launch_success_probability: [0, 1, '1'], cruise_success_probability: [0, 1, '1'],
  landing_success_probability: [0, 1, '1'], cruise_hours: [0, 1e6, 'h'], thermal_load_w: [0, 1000, 'W'],
} as const;
export type ComponentField = keyof typeof COMPONENT_FIELDS;
export type ProfileField = keyof typeof PROFILE_FIELDS;
export const componentFields = Object.keys(COMPONENT_FIELDS) as ComponentField[];
export const profileFields = Object.keys(PROFILE_FIELDS) as ProfileField[];
export const PROTECTIONS = ['unspecified', 'none', 'passive', 'active', 'both'] as const;
export type ReliabilityComponent = { id: typeof COMPONENT_IDS[number]; protection: typeof PROTECTIONS[number] } & Record<ComponentField, number | null>;
export type ReliabilityProfile = {
  enabled: boolean; basis: string; apply_thermal_load: boolean; components: ReliabilityComponent[];
} & Record<ProfileField, number | null>;

export function newReliability(): ReliabilityProfile {
  return {
    enabled: false, basis: '', apply_thermal_load: false,
    launch_success_probability: null, cruise_success_probability: null, landing_success_probability: null,
    cruise_hours: null, thermal_load_w: null,
    components: COMPONENT_IDS.map((id) => ({
      id, protection: 'unspecified',
      launch_failure_probability: null, landing_failure_probability: null,
      launch_loss_fraction: null, landing_loss_fraction: null, failure_rate_per_hour: null,
      upset_rate_per_hour: null, restart_success_probability: null, mean_recovery_hours: null,
      degradation_rate_per_hour: null, minimum_performance_fraction: null,
      thermal_min_c: null, thermal_max_c: null, rated_min_c: null, rated_max_c: null,
      dose_rate_krad_h: null, shield_transmission: null, tid_limit_krad: null,
    })),
  };
}
export function illustrativeReliability(basis: string): ReliabilityProfile {
  const p = newReliability();
  return { ...p, enabled: true, basis, launch_success_probability: .98, cruise_success_probability: .99,
    landing_success_probability: .97, cruise_hours: 168, thermal_load_w: 2,
    components: p.components.map((c) => ({ ...c, protection: 'both',
      launch_failure_probability: .001, landing_failure_probability: .002,
      launch_loss_fraction: .01, landing_loss_fraction: .02, failure_rate_per_hour: .00001,
      upset_rate_per_hour: .001, restart_success_probability: .95, mean_recovery_hours: .1,
      degradation_rate_per_hour: .00001, minimum_performance_fraction: .8,
      thermal_min_c: -20, thermal_max_c: 40, rated_min_c: -40, rated_max_c: 85,
      dose_rate_krad_h: .00001, shield_transmission: .5, tid_limit_krad: 10,
    })) };
}
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const within = (v: unknown, min: number, max: number): v is number | null =>
  v === null || (typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max);
export function readReliability(v: unknown): ReliabilityProfile | null {
  if (!record(v) || typeof v.enabled !== 'boolean' || typeof v.apply_thermal_load !== 'boolean' ||
      typeof v.basis !== 'string' || v.basis.length > 1000 || !Array.isArray(v.components) ||
      !v.components.length || v.components.length > 5) return null;
  const p = newReliability();
  for (const key of profileFields) {
    const value = v[key]; const [min, max] = PROFILE_FIELDS[key];
    if (!within(value, min, max)) return null;
    p[key] = value;
  }
  const components: ReliabilityComponent[] = [];
  for (const item of v.components) {
    if (!record(item)) return null;
    const template = p.components.find((c) => c.id === item.id);
    if (!template || components.some((c) => c.id === template.id)) return null;
    const protection = PROTECTIONS.find((value) => value === item.protection);
    if (!protection) return null;
    const component = { ...template, protection };
    for (const key of componentFields) {
      const value = item[key]; const [min, max] = COMPONENT_FIELDS[key];
      if (!within(value, min, max)) return null;
      component[key] = value;
    }
    if ((component.thermal_min_c !== null && component.thermal_max_c !== null && component.thermal_min_c > component.thermal_max_c) ||
        (component.rated_min_c !== null && component.rated_max_c !== null && component.rated_min_c > component.rated_max_c) ||
        (component.mean_recovery_hours !== null && component.mean_recovery_hours > 0 && component.mean_recovery_hours < 1e-6)) return null;
    components.push(component);
  }
  return { ...p, enabled: v.enabled, basis: v.basis, apply_thermal_load: v.apply_thermal_load, components };
}
export function reliabilityReady(p: ReliabilityProfile): boolean {
  return !!readReliability(p) && !!p.basis.trim() && (!p.apply_thermal_load || p.thermal_load_w !== null);
}
export function thermalOverrides(p: ReliabilityProfile | undefined, rows: readonly ParamRow[]): Record<string, number> | null {
  if (!p?.enabled || !p.apply_thermal_load) return {};
  if (p.thermal_load_w === null || !Number.isFinite(p.thermal_load_w) || p.thermal_load_w < 0) return null;
  const overrides: Record<string, number> = {};
  for (const key of ['survival_load_w', 'active_load_w']) {
    const row = rows.find((r) => r.group === 'energy' && r.key === key);
    if (!row || typeof row.value !== 'number') return null;
    const load = row.value + p.thermal_load_w;
    if (paramError(row, load)) return null;
    overrides[key] = load;
  }
  return overrides;
}
export function reliabilityRequest(profile: ReliabilityProfile, evaluations: readonly RavenEvaluation[]) {
  return { profile, windows: evaluations.map((e, i) => ({
    id: i === 0 ? 'A' : 'B', start_unix: Date.parse(e.window.start_utc) / 1000,
    step_hours: e.window.step_min / 60, useful: e.steps?.useful ?? [],
  })) };
}
export interface ReliabilityComponentResult {
  id: typeof COMPONENT_IDS[number]; missing: ComponentField[];
  failure_probability: number | null; malfunction_probability: number | null; restart_probability: number | null;
  expected_restart_count_full_exposure: number | null; mean_recovery_hours: number | null;
  retained_at_landing: number | null; retained_at_end: number | null;
  performance_known: boolean; performance_cutoff_hours: number | null;
  thermal_margin_c: number | null; dose_krad: number | null; radiation_margin_krad: number | null;
  environment_status: 'unknown' | 'within_declared_envelope' | 'outside_declared_envelope';
}
export interface ReliabilityScenario {
  id: string; duration_hours: number; complete_probability_inputs: boolean;
  stages: { phase: 'launch' | 'cruise' | 'landing'; survival_probability: number | null }[];
  components: ReliabilityComponentResult[];
  hardware_survival_probability: number | null; conditional_operational_probability: number | null;
  expected_available_hours: number | null; expected_unavailable_hours: number | null;
  expected_useful_hours: number | null; expected_useful_lower_hours: number | null; expected_useful_upper_hours: number | null;
  timeline: { hours: number; time_unix: number; hardware_survival: number | null; conditional_operational: number | null; retained_min: number | null }[];
}
export interface ReliabilityResult {
  model: 'raven-reliability-1'; source: 'declared_assumptions'; qualification: 'not_validated';
  assumptions: ReliabilityProfile; scenarios: ReliabilityScenario[]; method: string; limits: string[];
}
export function isReliabilityResult(v: unknown): v is ReliabilityResult {
  const finite = (n: unknown) => n === null || (typeof n === 'number' && Number.isFinite(n));
  const probability = (n: unknown) => within(n, 0, 1 + 1e-12);
  return record(v) && v.model === 'raven-reliability-1' && v.source === 'declared_assumptions' &&
    v.qualification === 'not_validated' && !!readReliability(v.assumptions) && typeof v.method === 'string' &&
    Array.isArray(v.limits) && v.limits.every((x) => typeof x === 'string') &&
    Array.isArray(v.scenarios) && v.scenarios.length > 0 && v.scenarios.length <= 2 && v.scenarios.every((s) => {
      if (!record(s) || typeof s.duration_hours !== 'number' || s.duration_hours <= 0 || !Number.isFinite(s.duration_hours)) return false;
      const duration = s.duration_hours;
      return (s.id === 'A' || s.id === 'B') &&
      typeof s.complete_probability_inputs === 'boolean' &&
      ['hardware_survival_probability', 'conditional_operational_probability'].every((k) => probability(s[k])) &&
      ['expected_available_hours', 'expected_unavailable_hours', 'expected_useful_hours', 'expected_useful_lower_hours', 'expected_useful_upper_hours'].every((k) => within(s[k], 0, duration + 1e-9)) &&
      Array.isArray(s.stages) && s.stages.length === 3 && s.stages.every((stage) => record(stage) && ['launch', 'cruise', 'landing'].includes(String(stage.phase)) && probability(stage.survival_probability)) &&
      Array.isArray(s.components) && s.components.length > 0 && s.components.length <= 5 && s.components.every((c) => record(c) &&
        COMPONENT_IDS.some((id) => id === c.id) && Array.isArray(c.missing) && c.missing.every((key) => componentFields.some((field) => field === key)) &&
        ['failure_probability', 'malfunction_probability', 'restart_probability', 'retained_at_landing', 'retained_at_end'].every((key) => probability(c[key])) &&
        typeof c.performance_known === 'boolean' && within(c.performance_cutoff_hours, 0, duration) &&
        ['expected_restart_count_full_exposure', 'mean_recovery_hours', 'thermal_margin_c', 'dose_krad', 'radiation_margin_krad'].every((key) => finite(c[key])) &&
        ['unknown', 'within_declared_envelope', 'outside_declared_envelope'].includes(String(c.environment_status))) &&
      Array.isArray(s.timeline) && s.timeline.length === 129 && s.timeline.every((point) => record(point) &&
        typeof point.time_unix === 'number' && Number.isFinite(point.time_unix) && within(point.hours, 0, duration) &&
        ['hardware_survival', 'conditional_operational', 'retained_min'].every((key) => probability(point[key])));
    });
}

/** When both scenarios carry exactly the same numbers (shared declared assumptions), one series labelled "A = B" is enough. Never merges different results. */
export function mergeIdenticalScenarios(scenarios: readonly ReliabilityScenario[]): { identical: boolean; shown: ReliabilityScenario[] } {
  const [first, second] = scenarios;
  const body = (s: ReliabilityScenario) => JSON.stringify({ ...s, id: null }, (key, value) => key === 'time_unix' ? undefined : value);
  if (scenarios.length === 2 && first && second && body(first) === body(second)) return { identical: true, shown: [{ ...first, id: `${first.id} = ${second.id}` }] };
  return { identical: false, shown: [...scenarios] };
}
