// SPDX-License-Identifier: Apache-2.0
import type { MessageKey } from '../../i18n/i18n.svelte';
import type { JourneyDraft } from './journey';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { tEn as t } from '../../i18n/i18n.svelte';
/** The report is English only, whatever the site language: the document, its JSON and the assistant request. */
const lang = { current: 'en' as const };
import { reportCompletion, reportScenarioKey } from './reportCompletion';
import { acceptedEstimates } from './estimates';
import { COST_ITEMS, planningContext, type BudgetEstimate, type CarbonEstimate } from './reportPlanning';
import type { SimulatedCertificate } from './reportPresentation';
import { newReportSections, REPORT_SECTION_IDS } from './reportSections';
import type { ReliabilityResult } from './reliability';
export { COST_ITEMS } from './reportPlanning';

export const REPORT_PHASES = [
  { id: '0', title: 'report.phase0', scope: 'report.scope0', reviews: ['MDR'],
    fields: ['scientific_objectives', 'technology_objectives', 'other_objectives', 'success_criteria', 'stakeholders'] },
  { id: 'A', title: 'report.phaseA', scope: 'report.scopeA', reviews: ['PRR'],
    fields: ['high_level_requirements', 'technical_feasibility', 'economic_feasibility', 'risk_register', 'schedule'] },
  { id: 'B', title: 'report.phaseB', scope: 'report.scopeB', reviews: ['SRR', 'PDR'],
    fields: ['system_architecture', 'space_and_ground_segments', 'interfaces', 'mass_and_power_budgets', 'verification_plan'] },
  { id: 'C', title: 'report.phaseC', scope: 'report.scopeC', reviews: ['CDR'],
    fields: ['detailed_design', 'hardware_selection', 'drawings_and_software_baselines', 'design_verification', 'ait_plan'] },
  { id: 'D', title: 'report.phaseD', scope: 'report.scopeD', reviews: ['QR', 'AR', 'ORR'],
    fields: ['development_and_production', 'integration', 'qualification_tests', 'acceptance_tests', 'nonconformances'] },
  { id: 'E', title: 'report.phaseE', scope: 'report.scopeE', reviews: ['FRR', 'LRR', 'CRR', 'ELR'],
    fields: ['launch_and_transfer', 'orbit_or_landing', 'commissioning', 'operations_and_ground_services', 'contingencies'] },
  { id: 'F', title: 'report.phaseF', scope: 'report.scopeF', reviews: ['MCR'],
    fields: ['disposal_and_passivation', 'debris_and_site_protection', 'planetary_protection', 'environmental_footprint', 'ground_segment_and_data_closeout'] },
] as const satisfies readonly {
  id: string; title: MessageKey; scope: MessageKey; reviews: readonly string[]; fields: readonly string[];
}[];

export type PhaseReportField = typeof REPORT_PHASES[number]['fields'][number];
export type ReportField = PhaseReportField | typeof COST_ITEMS[number];

const FIELD_INPUTS = {
  scientific_objectives: ['config.planning.objectiveType', 'config.planning.text.missionStatement'],
  technology_objectives: ['config.planning.objectiveType', 'config.planning.text.missionStatement'],
  other_objectives: ['config.planning.objectiveType', 'config.planning.text.missionStatement'],
  success_criteria: ['config.planning.text.successCriteria'],
  stakeholders: ['config.planning.text.owner', 'external.stakeholder_assessment'],
  high_level_requirements: ['config.objectives', 'external.full_mission_requirements'],
  technical_feasibility: ['evaluations', 'external.full_mission_feasibility'],
  economic_feasibility: ['lifecycle.economics.calculation', 'external.economic_feasibility_assessment'],
  risk_register: ['evaluations.inputs_state', 'evaluations.declared_limits', 'external.full_mission_risks'],
  schedule: ['evaluations.window', 'external.development_and_launch_schedule'],
  system_architecture: ['config.planning.text.architecture', 'external.controlled_system_architecture'],
  space_and_ground_segments: ['evaluations.parameters_used', 'external.full_space_and_ground_architecture'],
  interfaces: ['external.interface_control_documents'],
  mass_and_power_budgets: ['evaluations.parameters_used.energy', 'evaluations.metrics', 'external.spacecraft_mass_and_full_power_budget'],
  verification_plan: ['config.objectives', 'external.requirement_verification_matrix'],
  detailed_design: ['external.controlled_detailed_design'],
  hardware_selection: ['evaluations.parameters_used', 'external.flight_hardware_selection_and_qualification'],
  drawings_and_software_baselines: ['evaluations.model_version', 'evaluations.registry_sha256', 'external.flight_design_and_software_baselines'],
  design_verification: ['external.design_verification_records'],
  ait_plan: ['external.assembly_integration_and_test_plan'],
  development_and_production: ['external.manufacturing_records'],
  integration: ['external.integration_records'],
  qualification_tests: ['external.qualification_test_records'],
  acceptance_tests: ['external.acceptance_test_records'],
  nonconformances: ['external.nonconformance_register'],
  launch_and_transfer: ['config.planning.text.launchPlan', 'external.launch_and_transfer_analysis'],
  orbit_or_landing: ['external.trajectory_and_landing_analysis'],
  commissioning: ['external.commissioning_plan_and_records'],
  operations_and_ground_services: ['evaluations.window', 'external.operations_plan_and_ground_agreements'],
  contingencies: ['external.contingency_plan'],
  disposal_and_passivation: ['config.planning.text.disposalPlan', 'external.disposal_and_passivation_analysis'],
  debris_and_site_protection: ['config.planning.text.environmentPlan', 'external.site_protection_assessment'],
  planetary_protection: ['external.planetary_protection_assessment'],
  environmental_footprint: ['lifecycle.sustainability.carbon_indicator', 'external.independently_verified_lifecycle_assessment'],
  ground_segment_and_data_closeout: ['external.ground_and_data_closeout_plan'],
} as const satisfies Record<PhaseReportField, readonly string[]>;

export const REPORT_SOURCES = [
  { id: 'ecss', title: 'ECSS-M-ST-10C Rev.1, sections 4.4.1–4.4.3 (6 March 2009)',
    url: 'https://ecss.nl/standard/ecss-m-st-10c-rev-1-project-planning-and-implementation/' },
  { id: 'itu', title: 'ITU-R — Space Services Department',
    url: 'https://www.itu.int/en/ITU-R/space/Pages/default.aspx' },
  { id: 'gri', title: 'GRI — Sustainability Reporting Standards',
    url: 'https://www.globalreporting.org/standards/' },
  { id: 'paper-carbon', title: 'UK DESNZ 2025 GHG conversion factors — Material use, paper (1345.0779 kg CO2e/tonne, primary production)',
    url: 'https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025' },
  { id: 'reliability-exponential', title: 'NIST/SEMATECH e-Handbook — Exponential lifetime model (constant hazard assumption)',
    url: 'https://www.itl.nist.gov/div898/handbook/apr/section1/apr161.htm' },
  { id: 'thermal-control', title: 'NASA Small Spacecraft Technology — Thermal Control (protection principles, not mission-specific validation)',
    url: 'https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/' },
  { id: 'radiation-parts', title: 'NASA Electronic Parts and Packaging — EEE parts, reliability and test methods',
    url: 'https://nepp.nasa.gov/' },
] as const;

export interface ReportIdentity { model_version: string; registry_sha256: string }

export function missionLifecycleReport(draft: JourneyDraft, liabilityNotice: string, identity: ReportIdentity,
  evaluations: readonly RavenEvaluation[] = [], budget: BudgetEstimate | null = null,
  carbon: CarbonEstimate | null = null, certificate: SimulatedCertificate | null = null,
  reliability: ReliabilityResult | null = null) {
  const completion = reportCompletion(draft, evaluations, budget);
  const p = completion.plan;
  const sections = p.sections ?? newReportSections();
  const contextKey = planningContext(p, reportScenarioKey(evaluations),
    draft.name, draft.decision, lang.current, draft.objectives);
  const si = p.si?.inputKey === contextKey ? p.si.result : null;
  const phases = REPORT_PHASES.map((phase) => ({
    id: phase.id,
    assessment_status: phase.id === '0' || phase.id === 'A' ? 'partial_planning_inputs' : 'not_assessed',
    reviews: phase.reviews.map((id) => ({ id, status: 'not_performed', approval: null })),
    draft_summary: completion.paragraphs[phase.id],
    si_proposal: si?.sections[phase.id] ?? null,
    deliverables: phase.fields.map((id) => {
      const statement = id === 'environmental_footprint' && carbon && carbon.mission.known_phases > 0 ? {
        origin: 'core_arithmetic' as const, value: t('carbon.missionSummary', {
          count: carbon.mission.known_phases,
          subtotal: carbon.mission.known_subtotal_kg_co2e ?? t('report.notAssessed'),
          total: carbon.mission.total_kg_co2e ?? t('report.notAssessed'),
        }), evidence: `${carbon.mission.basis}; ${carbon.mission.boundary}`,
      } : completion.statements[id];
      return {
        id, status: statement?.origin ?? 'draft_proposal',
        completion_state: statement?.origin === 'draft_proposal' ? 'proposal_only' :
          statement ? (statement.origin === 'user_input' ? 'declared_input' : 'partial_study') :
            FIELD_INPUTS[id].some((input) => input.startsWith('external.')) ? 'requires_external_evidence' : 'requires_input',
        input_dependencies: FIELD_INPUTS[id],
        value: statement?.value ?? t('dossier.proposedTask', { field: t(`report.field.${id}`) }),
        evidence: statement?.evidence ?? null, verified: false,
      };
    }),
  }));
  const deliverables = phases.flatMap((phase) => phase.deliverables);
  return {
    completion_audit: {
      scope: 'Phase deliverables, not a count of approved mission requirements.',
      total_fields: deliverables.length,
      populated_from_inputs_or_core: deliverables.filter((item) => item.completion_state === 'declared_input' || item.completion_state === 'partial_study').length,
      proposed_or_missing: deliverables.filter((item) => item.completion_state !== 'declared_input' && item.completion_state !== 'partial_study').map((item) => item.id),
      verified_deliverables: 0,
      note: 'Every field identifies its input dependencies. Populated text, SI proposals and Core arithmetic do not establish completed engineering deliverables.',
    },
    presentation: {
      sections: { ...sections },
      omitted_sections: REPORT_SECTION_IDS.filter((id) => !sections[id]),
      json_contains_complete_data: true,
      note: 'Selection controls preview and PDF sections, not redaction of repeated facts. JSON retains the complete calculation and dossier.',
    },
    framework: {
      standard: 'ECSS-M-ST-10C Rev.1',
      clauses: '4.4.1–4.4.3',
      approach: 'Sequential phase-gate outline; ECSS verification uses the V model and permits phase overlap.',
      compliance_status: 'not_assessed',
      tailoring: null,
      document_status: 'preliminary_planning_report',
    },
    phases,
    planning_objectives: {
      mission_name: draft.name || null,
      priority: draft.objectives.priority,
      minimum_sunlight_percent: draft.objectives.minSunPercent,
      minimum_rf_availability_percent: draft.objectives.minRfPercent,
      decision: draft.decision || null,
      mission_statement: p.text.missionStatement || null,
      objective_type: p.objectiveType || null,
      scientific_or_technology_success_criteria: p.text.successCriteria || null,
    },
    engine_estimates: {
      label: 'RAVEN estimate — not a quote, design or forecast',
      note: 'Derived by the engine from its own results; shown apart from every user value; counted in the completion audit only when accepted.',
      mass_defaults: p.massDefaults ?? null,
      accepted: evaluations.length ? acceptedEstimates(p.estimates) : [],
      not_accepted: (p.estimates ?? []).filter((e) => e.status !== 'accepted').map((e) => ({ id: e.id, field: e.field, status: e.status, digest: e.digest })),
    },
    modeled_scope: {
      purpose: 'Lunar-site energy and communication comparison under declared assumptions; not full mission feasibility.',
      configuration_reference: 'config',
      technical_results_reference: 'evaluations',
      operations_window: { ...draft.input },
      flight_design_qualified: false,
      launch_or_orbit_simulated: false,
      ground_station_scheduling_confirmed: false,
    },
    reliability: {
      enabled: p.reliability?.enabled ?? false,
      assumptions: p.reliability ?? null,
      calculation: p.reliability?.enabled ? reliability : null,
      qualification: 'not_validated',
      boundary: 'Independent critical series components, declared phase risks and environmental envelopes; not a full mission FMECA or flight qualification.',
    },
    economics: {
      status: budget && budget.known_cost_items > 0 ? 'user_estimates_arithmetic' : 'not_assessed',
      currency: p.currency || null,
      price_base_year: p.priceBaseYear,
      estimation_method: budget ? 'user_estimates_plus_contingency' : null,
      cost_items: COST_ITEMS.map((id) => ({ id, amount: p.costs[id], uncertainty: null, basis: p.costBasis || null, source: 'user_estimate' })),
      contingency: budget?.contingency_amount ?? null,
      contingency_percent: p.contingencyPercent,
      taxes_and_inflation: null,
      total_lifecycle_cost: budget?.total_lifecycle_cost ?? null,
      funding_available: p.funding,
      calculation: budget,
      schedule_and_cash_flow: null,
      economic_feasibility: null,
      note: 'Mission costs are not RAVEN subscription prices. Missing amounts are not zero.',
    },
    sustainability: {
      perspective: 'ESG',
      status: 'not_assessed',
      applicable_phases: REPORT_PHASES.map((phase) => phase.id),
      reporting_framework: null,
      reporting_period: null,
      organizational_and_lifecycle_boundaries: null,
      emissions_lifecycle_boundary: p.carbon?.boundary || null,
      materiality_and_stakeholder_assessment: null,
      pillars: ['E', 'S', 'G'].map((pillar) => ({
        pillar, status: 'not_assessed', indicators: null, baseline: null, target: null,
        measured_value: null, unit: null, method: null, source: null, accountable_owner: null, verification: null,
        declared_plan: (pillar === 'E' ? p.text.environmentPlan : pillar === 'S' ? p.text.socialPlan : p.text.governancePlan) || null,
        estimated_indicator: pillar === 'E' && carbon && carbon.mission.known_phases > 0 ? carbon.mission : null,
      })),
      environmental_plan: p.text.environmentPlan || null,
      environmental_footprint: carbon?.mission.known_phases ? carbon.mission : null,
      carbon_indicator: carbon?.mission ?? null,
      document_paper_estimate: carbon?.document ?? null,
      social_plan: p.text.socialPlan || null,
      social_impact_assessment: null,
      governance_plan: p.text.governancePlan || null,
      governance_and_accountability: null,
      independent_assurance: null,
      esg_score: null,
      conformity_claim: false,
    },
    assistance: {
      report_generation: 'Deterministic report template and RAVEN engine outputs.',
      software_development: 'GitHub Copilot-assisted development.',
      mission_specific_si_generated: si !== null,
      mission_specific_si_model: si?.model ?? null,
      mission_specific_si_prompt_or_record: si,
      human_review: 'required_not_recorded',
      reviewer: null,
      approval: null,
    },
    sources: REPORT_SOURCES,
    liability_disclaimer: {
      notice: liabilityNotice,
      applicability: 'Only to the extent permitted by applicable law; not an exclusion of non-excludable liability.',
      user_acceptance_recorded: false,
    },
    raven_seal: {
      issuer: 'RAVEN',
      ...identity,
      type: 'visual_report_origin_mark',
      cryptographic_signature: null,
      authorized_mission_signatory: null,
      mission_approval: false,
      blockchain_simulation: certificate,
    },
  };
}
