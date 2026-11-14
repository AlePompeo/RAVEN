// SPDX-License-Identifier: Apache-2.0
// Step 2: requirements and verification matrix from the user's objectives/thresholds and the evaluated metrics.
// The verification plan and the AIT plan are deterministic templates over that matrix: no model writes them.
import type { RavenEvaluation } from '../../../shell/ravenApi';
import type { MissionObjectives } from '../objectives';
import type { Cell, Draft, EstimateInput, EstimateItem } from './types';

export type ReqStatus = 'met' | 'not_met' | 'unknown';
export interface Requirement {
  id: string; metric: string; /** result field the value is read from */ source_field: string; unit: string;
  threshold: number | null; threshold_source: string; evaluated: number | null; status: ReqStatus; method: 'analysis' | 'analysis_test';
  scenario: string; note: string | null;
}
const label = (i: number) => (i === 0 ? 'A' : 'B');
const frac = (v: readonly (boolean | null)[] | undefined): number | null =>
  v && v.length && v.every((x) => x !== null) ? v.filter((x) => x === true).length / v.length : null;
const pct = (f: number | null) => f === null ? null : Math.round(f * 1e6) / 1e4;
const round = (n: number, d = 3) => Math.round(n * 10 ** d) / 10 ** d;
/** met/not met against a minimum; a missing value is unknown, never zero. */
export const atLeast = (value: number | null, threshold: number | null): ReqStatus =>
  value === null || threshold === null ? 'unknown' : value >= threshold ? 'met' : 'not_met';

export function requirementsOf(e: RavenEvaluation, i: number, objectives: MissionObjectives): Requirement[] {
  const s = label(i), path = `evaluations[${i}]`;
  const out: Requirement[] = [];
  const steps = e.steps;
  if (objectives.minSunPercent !== null) {
    const v = pct(frac(steps?.lit));
    out.push({ id: `REQ-SUN-${s}`, metric: 'sun', source_field: `${path}.steps.lit`, unit: '%', threshold: objectives.minSunPercent,
      threshold_source: 'objectives.minSunPercent (user)', evaluated: v, status: atLeast(v, objectives.minSunPercent), method: 'analysis', scenario: s, note: null });
  }
  if (objectives.minRfPercent !== null) {
    const v = pct(frac(steps?.rf_closes));
    out.push({ id: `REQ-RF-${s}`, metric: 'rf', source_field: `${path}.steps.rf_closes`, unit: '%', threshold: objectives.minRfPercent,
      threshold_source: 'objectives.minRfPercent (user)', evaluated: v, status: atLeast(v, objectives.minRfPercent), method: 'analysis', scenario: s, note: null });
  }
  out.push({ id: `REQ-USEFUL-${s}`, metric: 'useful', source_field: `${path}.metrics.useful_hours`, unit: 'h', threshold: null,
    threshold_source: 'not declared', evaluated: e.metrics.useful_hours ?? null, status: 'unknown', method: 'analysis', scenario: s, note: 'no threshold declared' });
  const floor = e.parameters_used?.energy.min_soc;
  const floorPct = typeof floor === 'number' ? round(floor * 100) : null;
  const soc = e.metrics.min_soc === null || e.metrics.min_soc === undefined ? null : round(e.metrics.min_soc * 100);
  const prefix = e.metrics.min_soc_scope !== 'all steps';
  const socStatus: ReqStatus = soc !== null && floorPct !== null && soc < floorPct ? 'not_met' : prefix ? 'unknown' : atLeast(soc, floorPct);
  out.push({ id: `REQ-BATT-${s}`, metric: 'battery', source_field: `${path}.metrics.min_soc`, unit: '%', threshold: floorPct,
    threshold_source: `${path}.parameters_used.energy.min_soc (tag I)`, evaluated: soc, status: socStatus, method: 'analysis_test', scenario: s,
    note: prefix ? `scope: ${e.metrics.min_soc_scope}` : null });
  const required = e.parameters_used?.scenario.required_margin_db;
  const margins = steps?.margin_db ?? [];
  const known = margins.filter((m): m is number => m !== null && Number.isFinite(m));
  const minMargin = known.length ? round(Math.min(...known)) : null;
  const gaps = margins.length === 0 || known.length < margins.length;
  const marginStatus: ReqStatus = minMargin !== null && typeof required === 'number' && minMargin < required ? 'not_met'
    : gaps ? 'unknown' : atLeast(minMargin, typeof required === 'number' ? required : null);
  out.push({ id: `REQ-MARGIN-${s}`, metric: 'margin', source_field: `${path}.steps.margin_db`, unit: 'dB', threshold: typeof required === 'number' ? required : null,
    threshold_source: `${path}.parameters_used.scenario.required_margin_db (source V)`, evaluated: minMargin, status: marginStatus, method: 'analysis_test',
    scenario: s, note: gaps ? `${margins.length - known.length} of ${margins.length} samples unknown` : null });
  return out;
}

const known = (v: unknown): number | string => typeof v === 'number' && Number.isFinite(v) ? v : '?';
const fmt = (v: number | null, unit: string): Cell => v === null ? null : `${v} ${unit}`;
const SOURCE = 'User objectives and thresholds; RAVEN evaluated metrics; margin threshold from the model (source V); deterministic comparison';
const LIMITS = ['est.limit.req.scope', 'est.limit.req.unknown'];

export function requirementDrafts(evaluations: readonly RavenEvaluation[], objectives: MissionObjectives): Draft[] {
  if (!evaluations.length) return [];
  const reqs = evaluations.flatMap((e, i) => requirementsOf(e, i, objectives));
  const inputs: EstimateInput[] = [
    { name: 'objectives.minSunPercent', value: objectives.minSunPercent }, { name: 'objectives.minRfPercent', value: objectives.minRfPercent },
    ...evaluations.map((e, i) => ({ name: `evaluations[${i}].model`, value: `${e.model_version} / ${e.registry_sha256}` })),
  ];
  const matrix: EstimateItem[] = reqs.map((r) => ({ id: r.id, cells: {
    requirement: { key: `est.req.${r.metric}`, params: { scenario: r.scenario } }, metric: r.source_field,
    threshold: fmt(r.threshold, r.unit), threshold_source: r.threshold_source, evaluated: fmt(r.evaluated, r.unit),
    status: { key: `est.reqstatus.${r.status}` }, verification: { key: `est.method.${r.method}` }, note: r.note,
  } }));
  const plan: EstimateItem[] = reqs.flatMap((r, k) => [
    { id: `VP-${String(k + 1).padStart(2, '0')}a`, cells: { requirement: r.id, step: { key: 'est.vp.analysis', params: { scenario: r.scenario } },
      evidence: { key: 'est.vp.analysisEvidence' }, status: { key: 'est.vp.notPerformed' } } },
    { id: `VP-${String(k + 1).padStart(2, '0')}b`, cells: { requirement: r.id,
      step: { key: r.method === 'analysis_test' ? 'est.vp.test' : 'est.vp.independent' },
      evidence: { key: 'est.vp.independentEvidence' }, status: { key: 'est.vp.notPerformed' } } },
  ]);
  const ait: EstimateItem[] = [];
  const add = (cells: Record<string, Cell>) => ait.push({ id: `AIT-${String(ait.length + 1).padStart(2, '0')}`, cells });
  evaluations.forEach((e, i) => {
    const p = e.parameters_used;
    add({ step: { key: 'est.ait.baseline', params: { scenario: label(i), area: known(p?.energy.array_area_m2), capacity: known(p?.energy.battery_capacity_wh),
      gain: known(p?.rf.tx_gain_dbi), rate: known(p?.rf.rate_bps) } }, requirement: null });
  });
  add({ step: { key: 'est.ait.power' }, requirement: reqs.filter((r) => r.metric === 'sun' || r.metric === 'battery').map((r) => r.id).join(', ') || null });
  add({ step: { key: 'est.ait.rf' }, requirement: reqs.filter((r) => r.metric === 'rf' || r.metric === 'margin').map((r) => r.id).join(', ') || null });
  add({ step: { key: 'est.ait.functional' }, requirement: reqs.map((r) => r.id).join(', ') });
  add({ step: { key: 'est.ait.environment' }, requirement: null });
  return [
    { id: 'est.requirements', field: 'high_level_requirements', method_id: 'raven.requirement_matrix.v1', source: SOURCE, tag: 'D', range: null,
      items: matrix, inputs_used: inputs, validity_limits: LIMITS },
    { id: 'est.verification_plan', field: 'verification_plan', method_id: 'raven.verification_template.v1', source: SOURCE, tag: 'D', range: null,
      items: plan, inputs_used: inputs, validity_limits: [...LIMITS, 'est.limit.plan.template'] },
    { id: 'est.ait_plan', field: 'ait_plan', method_id: 'raven.ait_template.v1', source: SOURCE, tag: 'D', range: null,
      items: ait, inputs_used: inputs, validity_limits: [...LIMITS, 'est.limit.plan.template'] },
  ];
}
