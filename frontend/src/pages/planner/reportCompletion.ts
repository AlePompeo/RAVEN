// SPDX-License-Identifier: Apache-2.0
import { formatNumberEn as formatNumber, tEn as t } from '../../i18n/i18n.svelte';
import type { RavenEvaluation } from '../../shell/ravenApi';
import type { JourneyDraft } from './journey';
import { bitRate, utcMinute } from './reportFormat';
import { newReportPlanning, type BudgetEstimate, type ReportPlanning } from './reportPlanning';
import { acceptedFor, ESTIMATE_FIELDS } from './estimates';
import { topRisks } from './estimates/risks';
import { rt } from './reportText';

export const reportScenarioKey = (evaluations: readonly RavenEvaluation[]) => JSON.stringify(evaluations.map((e) =>
  [e.site, e.window, e.parameters_used, e.metrics, e.inputs_state, e.declared_limits, e.registry_sha256, e.model_version]));

export function reportCompletion(draft: JourneyDraft, evaluations: readonly RavenEvaluation[], budget: BudgetEstimate | null) {
  const p = draft.planning ?? newReportPlanning();
  const number = (v: number | null | undefined, unit: string, digits = 2) => v == null ? t('report.notAssessed') :
    `${formatNumber(v, { maximumFractionDigits: digits })} ${unit}`;
  const parameter = (e: RavenEvaluation, group: 'energy' | 'rf', key: string, unit: string) => {
    const value = e.parameters_used?.[group][key];
    if (unit === 'bit/s' && typeof value === 'number' && Number.isFinite(value)) return bitRate(value, (n) => formatNumber(n, { maximumFractionDigits: 3 }));
    return number(typeof value === 'number' && Number.isFinite(value) ? value : null, unit, unit === 'GHz' ? 4 : 2);
  };
  const station = (e: RavenEvaluation) => typeof e.parameters_used?.rf.station === 'string' ? e.parameters_used.rf.station : t('report.notProvided');
  const scenarioSummary = evaluations.map((e, i) => t('dossier.scenarioSummary', {
    scenario: i === 0 ? 'A' : 'B', site: e.site.name, start: utcMinute(e.window.start_utc),
    useful: number(e.metrics.useful_hours, 'h'), unknown: number(e.metrics.unknown_hours, 'h'),
    energy: number(e.metrics.harvested_wh, 'Wh'), soc: number(e.metrics.min_soc == null ? null : e.metrics.min_soc * 100, '%'),
  })).join('\n');
  const configuration = evaluations.length ? evaluations.map((e) => `${e.site.name}: ` + t('dossier.configurationSummary', {
    area: parameter(e, 'energy', 'array_area_m2', 'm²'), gain: parameter(e, 'rf', 'tx_gain_dbi', 'dBi'),
    rate: parameter(e, 'rf', 'rate_bps', 'bit/s'), station: station(e),
  })).join('\n') : t('dossier.configurationSummary', {
    area: number(draft.panel.array_area_m2, 'm²'), gain: number(draft.radio.gain, 'dBi'),
    rate: draft.radio.rate === null ? t('report.notAssessed') : bitRate(draft.radio.rate, (n) => formatNumber(n, { maximumFractionDigits: 3 })), station: draft.radio.station,
  });
  const technical = scenarioSummary;
  const top = topRisks(evaluations);
  const risks = top.length ? rt('risk.see') : rt('risk.none');
  const contingencies = top.length ? rt('risk.see') : rt('risk.none');
  const costSummary = budget ? t('dossier.costSummary', {
    count: budget.known_cost_items, subtotal: number(budget.known_subtotal, budget.currency ?? ''),
    total: number(budget.total_lifecycle_cost, budget.currency ?? ''),
    gap: number(budget.funding_gap, budget.currency ?? ''),
  }) : t('dossier.costPending');
  const statements: Partial<Record<string, { value: string; origin: 'user_input' | 'engine_result' | 'engine_estimate' | 'core_arithmetic' | 'draft_proposal'; evidence: string | null }>> = {};
  const user = (field: string, value: string) => { if (value.trim()) statements[field] = { value, origin: 'user_input', evidence: p.text.evidence || null }; };
  const engine = (field: string, value: string) => { if (evaluations.length) statements[field] = {
    value, origin: 'engine_result', evidence: [...new Set(evaluations.map((e) => `${e.model_version} / ${e.registry_sha256}`))].join('; '),
  }; };
  const requirements = t('reportAuto.requirements', {
    sun: draft.objectives.minSunPercent === null ? t('planner.criterionNotSet') : number(draft.objectives.minSunPercent, '%'),
    rf: draft.objectives.minRfPercent === null ? t('planner.criterionNotSet') : number(draft.objectives.minRfPercent, '%'),
  });
  user(p.objectiveType === 'scientific' ? 'scientific_objectives' : p.objectiveType === 'technology' ? 'technology_objectives' : 'other_objectives', p.text.missionStatement);
  user('success_criteria', p.text.successCriteria);
  user('stakeholders', p.text.owner);
  user('system_architecture', p.text.architecture);
  user('launch_and_transfer', p.text.launchPlan);
  user('disposal_and_passivation', p.text.disposalPlan);
  user('debris_and_site_protection', p.text.environmentPlan);
  if (draft.objectives.minSunPercent !== null || draft.objectives.minRfPercent !== null) user('high_level_requirements', requirements);
  engine('technical_feasibility', technical);
  engine('risk_register', risks);
  engine('contingencies', contingencies);
  engine('space_and_ground_segments', configuration);
  engine('schedule', evaluations.map((e) => t('reportAuto.schedule', {
    site: e.site.name, start: utcMinute(e.window.start_utc), count: e.window.n_steps, step: e.window.step_min,
  })).join('\n'));
  engine('mass_and_power_budgets', evaluations.map((e) => t('reportAuto.power', {
    site: e.site.name, capacity: parameter(e, 'energy', 'battery_capacity_wh', 'Wh'),
    survival: parameter(e, 'energy', 'survival_load_w', 'W'), active: parameter(e, 'energy', 'active_load_w', 'W'),
    generated: number(e.metrics.harvested_wh, 'Wh'), unmet: number(e.metrics.unmet_wh, 'Wh'),
    soc: number(e.metrics.min_soc === null ? null : e.metrics.min_soc * 100, '%'),
    scope: e.metrics.min_soc_scope,
  })).join('\n'));
  engine('hardware_selection', evaluations.map((e) => t('reportAuto.hardware', {
    site: e.site.name, area: parameter(e, 'energy', 'array_area_m2', 'm²'),
    gain: parameter(e, 'rf', 'tx_gain_dbi', 'dBi'), rate: parameter(e, 'rf', 'rate_bps', 'bit/s'),
    frequency: parameter(e, 'rf', 'frequency_ghz', 'GHz'),
    station: station(e),
  })).join('\n'));
  engine('drawings_and_software_baselines', t('reportAuto.baseline', {
    models: [...new Set(evaluations.map((e) => `${e.model_version} / SHA-256 ${e.registry_sha256}`))].join('; '),
  }));
  statements.verification_plan = {
    value: t('reportAuto.verification', { requirements }), origin: 'draft_proposal', evidence: null,
  };
  engine('operations_and_ground_services', evaluations.map((e) => `${e.site.name}: ${utcMinute(e.window.start_utc)}; ${e.window.n_steps} × ${e.window.step_min} min`).join('\n') + '\n' + t('dossier.groundNotBooked'));
  if (budget && budget.known_cost_items > 0) statements.economic_feasibility = {
    value: costSummary + '\n' + t('dossier.notFeasibility'), origin: 'core_arithmetic',
    evidence: '/api/raven/report/budget; ' + p.costBasis,
  };
  // Accepted RAVEN estimates fill a field only when the user has not provided it; their rows are printed in the estimate box.
  for (const field of ESTIMATE_FIELDS) {
    const accepted = evaluations.length ? acceptedFor(p.estimates, field) : [];
    const taken = statements[field]?.origin;
    if (!accepted.length || taken === 'user_input' || taken === 'core_arithmetic') continue;
    statements[field] = {
      value: t('est.statement', { count: accepted.reduce((n, e) => n + e.items.length, 0) }), origin: 'engine_estimate',
      evidence: accepted.map((e) => `${e.method_id} #${e.digest}`).join('; '),
    };
  }
  const paragraphs = {
    '0': p.text.missionStatement || t('dossier.proposedMission'),
    A: technical + '\n' + costSummary,
    B: [p.text.architecture, configuration].filter(Boolean).join('\n'),
    C: t('dossier.designProposal'),
    D: t('dossier.testProposal'),
    E: [p.text.launchPlan, statements.operations_and_ground_services?.value].filter(Boolean).join('\n'),
    F: [p.text.disposalPlan, p.text.environmentPlan, p.text.socialPlan, p.text.governancePlan].filter(Boolean).join('\n') || t('dossier.disposalProposal'),
  };
  return { statements, paragraphs, plan: p };
}

export function missionContext(p: ReportPlanning, draft: JourneyDraft, evaluations: readonly RavenEvaluation[], budget: BudgetEstimate | null) {
  const { si: _si, sections: _sections, reportMode: _mode, estimates: _estimates, massDefaults: _massDefaults, missionClass: _class, ...inputs } = p;
  return JSON.stringify({
    user_inputs: inputs,
    mission_name: draft.name,
    decision: draft.decision,
    requirements: draft.objectives,
    scenarios: evaluations.map((e) => ({
      site: e.site, window: e.window, parameters_used: e.parameters_used, metrics: e.metrics, inputs_state: e.inputs_state,
      limits: e.declared_limits, model_version: e.model_version, registry_sha256: e.registry_sha256,
    })),
    budget,
    limits: 'Client-supplied planning data. Energy metrics may cover only a known prefix; unknown is not zero. No qualification, authorization or ESG assurance.',
  });
}
