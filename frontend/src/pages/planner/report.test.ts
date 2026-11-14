// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { t, useCatalog } from '../../i18n/i18n.svelte';
import { siteA } from './reportFixtures';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import type { JourneyDraft, MissionShiftBaseline } from './journey';
import { RADIO_PRESETS } from './setup';
import { missionLifecycleReport } from './report';
import LifecycleReport from './LifecycleReport.svelte';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { budgetInput, budgetReady, COST_ITEMS, isBudgetEstimate, isSiNarrative, newReportPlanning, planningContext, readReportPlanning, type BudgetEstimate, type CarbonEstimate } from './reportPlanning';
import { missionContext, reportScenarioKey } from './reportCompletion';
import { newReportSections, readReportSections } from './reportSections';
import { illustrativeReliability, type ReliabilityResult } from './reliability';
import type { SimulatedCertificate } from './reportPresentation';
import { utcMinute } from './reportFormat';

const draft: JourneyDraft = {
  name: 'Lunar study', decision: 'Compare terrain uncertainty.', objectives: { priority: 'radio', minSunPercent: 0, minRfPercent: null },
  radio: RADIO_PRESETS.baseline,
  panel: { array_area_m2: 1, cell_efficiency: .295, orientation: 'tracking', tilt_deg: 0, tilt_azimuth_deg: 0 },
  input: { mode: 'sites', siteA: 'malapert-massif', siteB: 'haworth', start: '2027-04-16T00:00', startB: '2027-05-16T00:00', days: 3, stepMin: 60 },
};
const identity = { model_version: 'raven-core-1.4', registry_sha256: 'test-registry' };
const paperCarbon: CarbonEstimate = {
  mission: {
    unit: 'kg CO2e', known_phases: 0, missing_phases: ['0', 'A', 'B', 'C', 'D', 'E', 'F'],
    known_subtotal_kg_co2e: null, total_kg_co2e: null,
    phase_emissions_kg_co2e: { '0': null, A: null, B: null, C: null, D: null, E: null, F: null },
    basis: '', boundary: '', source: 'user_estimates', independently_verified: false,
  },
  document: {
    compact_pages: 33, reference_pages: 58, paper_production_kg_co2e_per_sheet: .0067,
    compaction_avoided_kg_co2e: .1675, not_printing_avoided_kg_co2e: .2215,
    paper_factor_source: 'Fixture', paper_factor_id: 'Fixture',
  },
};
const demoCertificate: SimulatedCertificate = {
  status: 'simulation_only_not_broadcast', network: null, broadcast: false, issuer: 'RAVEN',
  hash_algorithm: 'SHA-256', payload_format: 'raven-json-sorted-keys-v1',
  payload_sha256: 'a'.repeat(64), simulated_transaction_id: `DEMO-${'b'.repeat(64)}`, cryptographic_signature: null,
};

beforeEach(() => useCatalog('en', en, en));
afterEach(() => { cleanup(); useCatalog('it', itCatalog, en); });

describe('ECSS-aligned mission report', () => {
  it('orders the final report as an executive decision followed by ECSS phases 0 and A-F', () => {
    render(LifecycleReport, {
      draft, identity, evaluations: [siteA, siteA], expert: true, created: '2027-01-01T00:00:00Z',
    });
    const root = screen.getByTestId('mission-lifecycle-report');
    const sections = Array.from(root.children)
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node.hasAttribute('data-part'))
      .map((node) => node.getAttribute('data-part'));
    expect(sections).toEqual(['executive', '0', 'A', 'B', 'C', 'D', 'E', 'F']);
    expect(root.querySelector('[data-testid="report-site-verdict"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="report-moon"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="report-traceability"]')).toBeNull();
    expect(root.querySelector('[data-testid="report-end-of-life"]')).toBeNull();
    expect(root.querySelector('[data-testid="report-toc"]')).toBeNull();
    expect(root.querySelector('[data-appendix="parameters"]')).toBeNull();
    expect(root.querySelector('.rp-formula-block')).toBeNull();
    expect(root.querySelector('[data-testid="reliability-results"]')).toBeNull();
    expect(root.textContent).not.toContain('SHA-256 report payload');
    expect(root.textContent).not.toContain('DEMO-');
    expect(root.textContent).not.toContain('Layout estimate:');
    expect(root.textContent).not.toContain('Prepare and independently review:');
    expect(root.textContent).not.toContain('battery passivation');
    expect(root.querySelector('[data-testid="report-digital-savings"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="report-final-seal"]')).not.toBeNull();
    expect(root.lastElementChild?.getAttribute('data-testid')).toBe('report-final-seal');
    expect(root.textContent).toContain('Digital signature');
    expect(root.textContent).toContain('Not issued: no trusted signing key is configured.');
    expect(root.querySelector('[data-testid="report-phase-E"]')?.textContent).toContain('DSN geometric visibility');
    expect(root.querySelector('[data-testid="report-phase-E"]')?.textContent).toContain('station scheduling');
  });

  it('shows the paper estimate, payload fingerprint and clearly unissued signature/blockchain fields at the report end', () => {
    render(LifecycleReport, {
      draft, identity, evaluations: [siteA], carbon: paperCarbon, certificate: demoCertificate,
      expert: true, created: '2027-01-01T00:00:00Z',
    });
    const root = screen.getByTestId('mission-lifecycle-report');
    const savings = screen.getByTestId('report-digital-savings');
    const seal = screen.getByTestId('report-final-seal');
    expect(savings.textContent).toContain('33-page report');
    expect(savings.textContent).toContain('221.5 g CO₂e');
    expect(savings.querySelector('.leaf')).not.toBeNull();
    expect(seal.textContent).toContain('a'.repeat(64));
    expect(seal.textContent).toContain(`DEMO-${'b'.repeat(64)}`);
    expect(seal.textContent).toContain('not a transaction');
    expect(seal.querySelector('.raven-seal-mark img')).not.toBeNull();
    expect(root.lastElementChild).toBe(seal);
  });

  it('includes methodology, reliability and parameter details only when selected in the dossier', () => {
    const planning = newReportPlanning();
    planning.sections = newReportSections();
    const d = { ...draft, planning };
    const profile = illustrativeReliability('Illustrative assumptions.');
    const reliability: ReliabilityResult = {
      model: 'raven-reliability-1', source: 'declared_assumptions', qualification: 'not_validated',
      assumptions: profile, scenarios: [], method: 'test fixture', limits: [],
    };
    render(LifecycleReport, { draft: d, identity, evaluations: [siteA], expert: true, created: '2027-01-01T00:00:00Z' });
    const root = screen.getByTestId('mission-lifecycle-report');
    expect(root.querySelector('.rp-formula-block')).toBeNull();
    expect(root.querySelector('[data-appendix="parameters"]')).toBeNull();
    expect(root.querySelector('[data-testid="reliability-results"]')).toBeNull();

    cleanup();
    planning.sections.methodology = true;
    planning.sections.configuration = true;
    planning.sections.provenance = true;
    planning.sections.reliability = true;
    planning.reliability = profile;
    render(LifecycleReport, {
      draft: d, identity, evaluations: [siteA], reliability, expert: true, created: '2027-01-01T00:00:00Z',
    });
    const enabled = screen.getByTestId('mission-lifecycle-report');
    expect(enabled.querySelector('.rp-formula-block')).not.toBeNull();
    expect(enabled.querySelector('[data-appendix="parameters"]')).not.toBeNull();
    expect(enabled.querySelector('[data-testid="reliability-results"]')).not.toBeNull();
  });

  it('pairs shifted report scenarios with the matching baseline UTC window', () => {
    const evaluations = [structuredClone(siteA), structuredClone(siteA)] as RavenEvaluation[];
    const starts = ['2027-01-01T00:00:00Z', '2027-02-01T00:00:00Z'];
    const baseline: MissionShiftBaseline[] = starts.map((start, i) => ({
      site_id: siteA.site.id, site_name: siteA.site.name, start_utc: start,
      useful_hours: i + 1, unknown_hours: 0, harvested_wh: null, min_soc: null,
    }));
    evaluations.forEach((evaluation, i) => {
      evaluation.base_start_utc = starts[i]!;
      evaluation.mission_shift_days = 28;
      evaluation.window.start_utc = new Date(Date.parse(starts[i]!) + 28 * 86400000).toISOString().replace('.000Z', 'Z');
      evaluation.metrics.useful_hours = 10 + i;
    });

    const report = missionLifecycleReport(draft, '', identity, evaluations, null, null, null, null, baseline);
    expect(report.mission_time_shift.scenarios.map((scenario) => scenario.baseline_metrics?.useful_hours)).toEqual([1, 2]);
  });

  it('restores full sections for old drafts and rejects malformed persisted selections', () => {
    const planning = newReportPlanning();
    const { sections: _sections, ...old } = planning;
    expect(readReportPlanning(old)?.sections).toEqual(newReportSections());
    planning.sections = newReportSections(true);
    expect(readReportPlanning(planning)?.sections).toEqual(newReportSections(true));
    expect(readReportSections({ ...planning.sections, charts: 'false' })).toBeNull();
    expect(readReportPlanning({ ...planning, sections: { summary: true } })).toBeNull();
    expect(readReportSections({ ...planning.sections, summary: false })?.summary).toBe(false);
  });

  it('restores older dossiers and requires attributed, bounded mission emission estimates', () => {
    const planning = newReportPlanning();
    const { carbon: _carbon, ...old } = planning;
    expect(readReportPlanning(old)?.carbon?.phases.F).toBeNull();
    planning.carbon!.phases.E = 0;
    expect(budgetReady(planning)).toBe(false);
    planning.carbon!.basis = 'User phase estimate';
    planning.carbon!.boundary = 'Whole mission';
    expect(budgetReady(planning)).toBe(true);
    expect(readReportPlanning(planning)?.carbon?.phases.E).toBe(0);
    planning.carbon!.phases.E = -1;
    expect(readReportPlanning(planning)).toBeNull();
  });
  it('accepts Core budget totals above an individual cost line limit', () => {
    const budget = {
      known_cost_items: 9, missing_cost_items: [], known_subtotal: 9e15,
      contingency_amount: 9e15, total_lifecycle_cost: 18e15, funding_gap: 17e15,
      within_declared_funding: false, economic_feasibility: null,
      currency: 'EUR', price_base_year: 2027, basis: 'User estimate', source: 'user_estimates',
    };
    expect(isBudgetEstimate(budget)).toBe(true);
    expect(isBudgetEstimate({ ...budget, total_lifecycle_cost: Infinity })).toBe(false);
  });

  it('preserves planning inputs without turning them into feasibility, qualification or approved reviews', () => {
    const report = missionLifecycleReport(draft, t('report.liabilityText'), identity);
    expect(report.phases.map((phase) => phase.id)).toEqual(['0', 'A', 'B', 'C', 'D', 'E', 'F']);
    expect(report.planning_objectives).toMatchObject({
      mission_name: 'Lunar study', priority: 'radio', minimum_sunlight_percent: 0,
      minimum_rf_availability_percent: null, mission_statement: null, decision: draft.decision,
    });
    expect(report.phases.flatMap((phase) => phase.reviews).every((review) => review.status === 'not_performed' && review.approval === null)).toBe(true);
    expect(report.framework.compliance_status).toBe('not_assessed');
    expect(report.modeled_scope).toMatchObject({ flight_design_qualified: false, launch_or_orbit_simulated: false });
    report.modeled_scope.operations_window.days = 99;
    expect(draft.input.days).toBe(3);
  });

  it('exports missing mission costs and sustainability evidence as null, never zero or approval', () => {
    const report = JSON.parse(JSON.stringify(missionLifecycleReport(draft, t('report.liabilityText'), identity)));
    expect(report.economics).toMatchObject({
      currency: null, price_base_year: null, total_lifecycle_cost: null, funding_available: null, economic_feasibility: null,
    });
    expect(report.economics.cost_items.every((item: { amount: number | null }) => item.amount === null)).toBe(true);
    expect(report.phases[6].deliverables.find((item: { id: string }) => item.id === 'environmental_footprint')).toMatchObject({ status: 'draft_proposal', verified: false });
    expect(report.assistance).toMatchObject({ mission_specific_si_generated: false, human_review: 'required_not_recorded', approval: null });
    expect(report.sustainability).toMatchObject({ perspective: 'ESG', esg_score: null, conformity_claim: false });
    expect(report.sustainability.pillars.map((pillar: { pillar: string }) => pillar.pillar)).toEqual(['E', 'S', 'G']);
    expect(report.liability_disclaimer.notice).toContain('To the extent permitted by applicable law');
    expect(report.liability_disclaimer.user_acceptance_recorded).toBe(false);
    expect(report.raven_seal).toMatchObject({ ...identity, cryptographic_signature: null, mission_approval: false });
  });

  it('fills phases from actual Core outputs and user objectives, without treating proposals as evidence', () => {
    const planning = newReportPlanning();
    planning.objectiveType = 'scientific';
    planning.text.missionStatement = 'Measure lunar dust.';
    planning.text.successCriteria = 'Archive one dataset.';
    planning.text.environmentPlan = 'Document contamination risks.';
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    evaluation.metrics.min_soc = 0;
    const report = missionLifecycleReport({ ...draft, planning }, '', identity, [evaluation]);
    expect(report.planning_objectives.mission_statement).toBe('Measure lunar dust.');
    expect(report.phases[0]!.deliverables.find((item) => item.id === 'scientific_objectives')).toMatchObject({ status: 'user_input', value: 'Measure lunar dust.', verified: false });
    expect(report.phases[1]!.draft_summary).toContain(evaluation.site.name);
    expect(report.phases[1]!.draft_summary).toContain('0 %');
    expect(report.sustainability.environmental_plan).toBe('Document contamination risks.');
    expect(report.sustainability.environmental_footprint).toBeNull();
    expect(report.phases.find((phase) => phase.id === 'D')!.deliverables.find((item) => item.id === 'qualification_tests')?.evidence).toBeNull();
  });

  it('audits missing dependencies without labelling absent evaluations or empty costs as computed evidence', () => {
    const emptyBudget: BudgetEstimate = {
      known_cost_items: 0, missing_cost_items: [...COST_ITEMS], known_subtotal: null, contingency_amount: null,
      total_lifecycle_cost: null, funding_gap: null, within_declared_funding: null, economic_feasibility: null,
      currency: null, price_base_year: null, basis: '', source: 'user_estimates',
    };
    const report = missionLifecycleReport(draft, '', identity, [], emptyBudget);
    const fields = report.phases.flatMap((phase) => phase.deliverables);
    expect(fields.every((item) => item.input_dependencies.length > 0 && !item.verified)).toBe(true);
    expect(fields.some((item) => item.status === 'engine_result' || item.status === 'core_arithmetic')).toBe(false);
    expect(fields.find((item) => item.id === 'technical_feasibility')).toMatchObject({
      completion_state: 'requires_external_evidence', evidence: null,
    });
    expect(fields.find((item) => item.id === 'verification_plan')).toMatchObject({ completion_state: 'proposal_only', evidence: null });
    expect(report.economics.status).toBe('not_assessed');
    expect(report.completion_audit.proposed_or_missing).toContain('economic_feasibility');
    expect(report.completion_audit.proposed_or_missing).toContain('qualification_tests');
  });

  it('grounds requirements, power, hardware and baselines in their actual inputs, preserving unknown energy and zero charge', () => {
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    evaluation.parameters_used!.rf.tx_gain_dbi = 37;
    evaluation.metrics.harvested_wh = null;
    evaluation.metrics.min_soc = 0;
    evaluation.metrics.min_soc_scope = 'known prefix';
    const report = missionLifecycleReport(draft, '', identity, [evaluation]);
    const fields = report.phases.flatMap((phase) => phase.deliverables);
    expect(fields.find((item) => item.id === 'high_level_requirements')?.value).toContain('minimum sunlight 0 %');
    expect(fields.find((item) => item.id === 'hardware_selection')?.value).toContain('37 dBi');
    expect(fields.find((item) => item.id === 'space_and_ground_segments')?.value).toContain('37 dBi');
    const power = fields.find((item) => item.id === 'mass_and_power_budgets');
    expect(power).toMatchObject({ status: 'engine_result', completion_state: 'partial_study', verified: false });
    expect(power?.value).toContain(`generated energy ${t('report.notAssessed')}`);
    expect(power?.value).toContain('minimum charge 0 %');
    expect(power?.value).toContain('known prefix');
    expect(power?.value).toContain('Spacecraft mass and a full power budget are not calculated');
    expect(fields.find((item) => item.id === 'drawings_and_software_baselines')?.value).toContain(evaluation.registry_sha256);
    expect(fields.find((item) => item.id === 'schedule')?.value).toContain(utcMinute(evaluation.window.start_utc));
    expect(JSON.parse(missionContext(newReportPlanning(), draft, [evaluation], null)).scenarios[0].parameters_used.rf.tx_gain_dbi).toBe(37);
  });

  it('keeps a populated reliability profile and both scenarios within the existing SI context bound', () => {
    const planning = newReportPlanning();
    planning.reliability = illustrativeReliability('Synthetic assumptions, not qualified hardware.');
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    const context = missionContext(planning, { ...draft, planning }, [evaluation, evaluation], null);
    expect(context.length).toBeLessThanOrEqual(16000);
    expect(JSON.parse(context).user_inputs.reliability.components).toHaveLength(5);
  });

  it('carries declared ESG data and Core budget figures into the report without granting approval', () => {
    const planning = newReportPlanning();
    planning.currency = 'EUR'; planning.priceBaseYear = 2026; planning.costBasis = 'Declared estimates';
    planning.contingencyPercent = 20; planning.funding = 1000;
    for (const id of COST_ITEMS) planning.costs[id] = 100;
    planning.text.owner = 'Study operator';
    planning.text.environmentPlan = 'Assess site contamination.';
    planning.carbon!.phases.A = 0; planning.carbon!.basis = 'Declared phase estimate'; planning.carbon!.boundary = 'Manufacturing only';
    const budget: BudgetEstimate = {
      known_cost_items: 9, missing_cost_items: [], known_subtotal: 900, contingency_amount: 180,
      total_lifecycle_cost: 1080, funding_gap: 80, within_declared_funding: false, economic_feasibility: null,
      currency: 'EUR', price_base_year: 2026, basis: planning.costBasis, source: 'user_estimates',
    };
    const carbon: CarbonEstimate = {
      mission: { unit: 'kg CO2e', known_phases: 1, missing_phases: ['0', 'B', 'C', 'D', 'E', 'F'],
        known_subtotal_kg_co2e: 0, total_kg_co2e: null, phase_emissions_kg_co2e: { ...planning.carbon!.phases },
        basis: planning.carbon!.basis, boundary: planning.carbon!.boundary, source: 'user_estimates', independently_verified: false },
      document: { compact_pages: null, reference_pages: null, paper_production_kg_co2e_per_sheet: .00671140068984,
        compaction_avoided_kg_co2e: null, not_printing_avoided_kg_co2e: null,
        paper_factor_source: 'https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025',
        paper_factor_id: '19_506_5164_15_1' },
    };
    const d = { ...draft, planning };
    const report = missionLifecycleReport(d, '', identity, [], budget, carbon);
    expect(report.economics).toMatchObject({ contingency_percent: 20, economic_feasibility: null, taxes_and_inflation: null });
    expect(report.sustainability.emissions_lifecycle_boundary).toBe('Manufacturing only');
    expect(report.sustainability.organizational_and_lifecycle_boundaries).toBeNull();
    expect(report.sustainability.pillars[0]).toMatchObject({
      declared_plan: 'Assess site contamination.', measured_value: null,
      estimated_indicator: { known_subtotal_kg_co2e: 0, total_kg_co2e: null, independently_verified: false },
    });
    expect(report.sustainability.pillars[1]?.estimated_indicator).toBeNull();
    render(LifecycleReport, { draft: d, identity, budget, carbon, evaluations: [siteA, siteA], expert: true, created: '2027-01-01T00:00:00Z' });
    expect(screen.getByTestId('report-budget-summary').textContent).toContain('900 EUR');
    expect(screen.getByTestId('report-budget-summary').textContent).toContain('80 EUR');
    expect(screen.getByTestId('mission-carbon').textContent).toContain('0');
  });

  it('accepts only a well-formed local SI draft and excludes it after scenario, dossier or language changes', () => {
    const planning = newReportPlanning();
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    const evaluations = [evaluation];
    const result = {
      sections: { '0': 'Draft 0', A: 'Draft A', B: 'Draft B', C: 'Draft C', D: 'Draft D', E: 'Draft E', F: 'Draft F' },
      model: 'local-model', provider: 'ollama', local: true as const, generated_at: '2026-11-09T10:00:00Z',
      context_sha256: 'a'.repeat(64), status: 'unreviewed_si_proposal' as const, lang: 'en' as const,
    };
    expect(isSiNarrative(result)).toBe(true);
    const cloud = { ...result, local: false, provider: 'groq', data_scope: 'anonymous_technical_profile' };
    expect(isSiNarrative(cloud)).toBe(true);
    expect(isSiNarrative({ ...cloud, data_scope: undefined })).toBe(false);
    expect(isSiNarrative({ ...cloud, provider: 'unknown' })).toBe(false);
    expect(isSiNarrative({ ...result, data_scope: 'unknown' })).toBe(false);
    expect(isSiNarrative({ ...result, sections: { '0': 'Incomplete' } })).toBe(false);
    planning.si = { inputKey: planningContext(planning, reportScenarioKey(evaluations), draft.name, draft.decision, 'en', draft.objectives), result };
    const d = { ...draft, planning };
    expect(missionLifecycleReport(d, '', identity, evaluations).assistance.mission_specific_si_generated).toBe(true);
    planning.sections = newReportSections(true);
    expect(missionLifecycleReport(d, '', identity, evaluations).assistance.mission_specific_si_generated).toBe(true);
    expect(missionLifecycleReport({ ...d, objectives: { ...d.objectives, minSunPercent: 50 } }, '', identity, evaluations)
      .assistance.mission_specific_si_generated).toBe(false);
    evaluation.metrics.unknown_hours++;
    expect(missionLifecycleReport(d, '', identity, evaluations).assistance.mission_specific_si_generated).toBe(false);
    expect(readReportPlanning(planning)?.si?.result.model).toBe('local-model');
    expect(readReportPlanning({ ...planning, costs: { ...planning.costs, disposal: -1 } })).toBeNull();
    expect(budgetInput(newReportPlanning()).costs.disposal).toBeNull();
  });
});
