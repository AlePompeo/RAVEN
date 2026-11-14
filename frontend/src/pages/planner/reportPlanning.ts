// SPDX-License-Identifier: Apache-2.0
import { BASE } from '../../registry';
import { newReportSections, parseReportMode, readReportSections, type ReportMode, type ReportSections } from './reportSections';
import type { MissionObjectives } from './objectives';
import { newReliability, readReliability, type ReliabilityProfile } from './reliability';
import { readEstimates, readMassDefaults, type EngineEstimate, type MassDefaults } from './estimates/types';
import { parseMissionClass, type MissionClassId } from './estimates/missionClass';

export const COST_ITEMS = [
  'mission_studies', 'system_definition', 'detailed_design_cost', 'development_and_ait',
  'launch_and_transfer', 'ground_segment', 'operations', 'disposal', 'insurance_and_regulatory',
] as const;
export const PLAN_TEXT_FIELDS = [
  'missionStatement', 'successCriteria', 'owner', 'architecture',
  'launchPlan', 'disposalPlan', 'environmentPlan', 'socialPlan', 'governancePlan', 'evidence',
] as const;
export type PhaseId = '0' | 'A' | 'B' | 'C' | 'D' | 'E' | 'F';
export const CARBON_PHASES = ['0', 'A', 'B', 'C', 'D', 'E', 'F'] as const;
export interface CarbonPlanning {
  phases: Record<PhaseId, number | null>; basis: string; boundary: string;
}
export interface DocumentPages { compact: number | null; reference: number | null }
export interface CarbonEstimate {
  mission: {
    unit: 'kg CO2e'; known_phases: number; missing_phases: string[];
    known_subtotal_kg_co2e: number | null; total_kg_co2e: number | null;
    phase_emissions_kg_co2e: Record<PhaseId, number | null>; basis: string; boundary: string;
    source: 'user_estimates'; independently_verified: false;
  };
  document: {
    compact_pages: number | null; reference_pages: number | null;
    paper_production_kg_co2e_per_sheet: number;
    compaction_avoided_kg_co2e: number | null; not_printing_avoided_kg_co2e: number | null;
    paper_factor_source: string; paper_factor_id: string;
  };
}
export function newCarbonPlanning(): CarbonPlanning {
  return { phases: { '0': null, A: null, B: null, C: null, D: null, E: null, F: null }, basis: '', boundary: '' };
}
export interface SiNarrative {
  sections: Record<PhaseId, string>; model: string; provider: string; local: boolean; generated_at: string;
  data_scope?: 'full_local_context' | 'anonymous_technical_profile';
  context_sha256: string; status: 'unreviewed_si_proposal'; lang: 'it' | 'en';
}
export interface ReportPlanning {
  objectiveType: 'scientific' | 'technology' | 'other' | '';
  text: Record<typeof PLAN_TEXT_FIELDS[number], string>;
  currency: 'EUR' | 'USD' | 'GBP' | '';
  priceBaseYear: number | null;
  costBasis: string;
  costs: Record<typeof COST_ITEMS[number], number | null>;
  contingencyPercent: number | null;
  funding: number | null;
  carbon?: CarbonPlanning;
  sections?: ReportSections;
  /** Chosen report mode (Learn or Expert). Set when the Dossier is first opened (default from the site mode) or by the user. */
  reportMode?: ReportMode;
  si?: { inputKey: string; result: SiNarrative };
  reliability?: ReliabilityProfile;
  /** RAVEN estimates (separate from every user value; counted only once accepted) and the declared mass defaults (tag I). */
  estimates?: EngineEstimate[];
  /** The user switched the RAVEN estimates off: none is shown in the report (default: on). */
  estimatesOff?: boolean;
  massDefaults?: MassDefaults;
  /** Mission-class slider position; undefined = small commercial lander. */
  missionClass?: MissionClassId;
}
export interface BudgetEstimate {
  known_cost_items: number; missing_cost_items: string[];
  known_subtotal: number | null; contingency_amount: number | null; total_lifecycle_cost: number | null;
  funding_gap: number | null; within_declared_funding: boolean | null; economic_feasibility: null;
  currency: ReportPlanning['currency'] | null; price_base_year: number | null; basis: string; source: 'user_estimates';
}
export function newReportPlanning(): ReportPlanning {
  return {
    objectiveType: '', text: { missionStatement: '', successCriteria: '', owner: '',
      architecture: '', launchPlan: '', disposalPlan: '', environmentPlan: '', socialPlan: '', governancePlan: '', evidence: '' },
    currency: '', priceBaseYear: null, costBasis: '',
    costs: { mission_studies: null, system_definition: null, detailed_design_cost: null, development_and_ait: null,
      launch_and_transfer: null, ground_segment: null, operations: null, disposal: null, insurance_and_regulatory: null },
    contingencyPercent: null, funding: null,
    carbon: newCarbonPlanning(),
    sections: newReportSections(),
    reliability: newReliability(),
  };
}
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const amount = (v: unknown, max = 1e15): v is number | null =>
  v === null || (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= max);
export function isSiNarrative(v: unknown): v is SiNarrative {
  if (!record(v) || !record(v.sections)) return false;
  const sections = v.sections;
  return ['0', 'A', 'B', 'C', 'D', 'E', 'F'].every((id) =>
    typeof sections[id] === 'string' && sections[id].length > 0 && sections[id].length <= 1600) &&
    typeof v.model === 'string' && v.model.length <= 128 && typeof v.provider === 'string' && v.provider.length <= 64 &&
    ((v.local === true && (v.data_scope === undefined || v.data_scope === 'full_local_context')) ||
      (v.local === false && v.provider === 'groq' && v.data_scope === 'anonymous_technical_profile')) &&
    typeof v.generated_at === 'string' && Number.isFinite(Date.parse(v.generated_at)) &&
    typeof v.context_sha256 === 'string' && /^[a-f0-9]{64}$/.test(v.context_sha256) &&
    v.status === 'unreviewed_si_proposal' && (v.lang === 'en' || v.lang === 'it');
}
export function readReportPlanning(v: unknown): ReportPlanning | null {
  if (!record(v) || !record(v.text) || !record(v.costs) ||
      !['', 'scientific', 'technology', 'other'].includes(String(v.objectiveType)) ||
      !['', 'EUR', 'USD', 'GBP'].includes(String(v.currency)) ||
      !amount(v.priceBaseYear, 2200) || (v.priceBaseYear !== null && (!Number.isInteger(v.priceBaseYear) || v.priceBaseYear < 1972)) ||
      typeof v.costBasis !== 'string' || v.costBasis.length > 1000 ||
      !amount(v.contingencyPercent, 100) || !amount(v.funding)) return null;
  const result = newReportPlanning();
  if (v.reliability !== undefined) {
    const reliability = readReliability(v.reliability);
    if (!reliability) return null;
    result.reliability = reliability;
  }
  if (v.estimates !== undefined) result.estimates = readEstimates(v.estimates);
  if (v.estimatesOff === true) result.estimatesOff = true;
  if (v.massDefaults !== undefined) {
    const defaults = readMassDefaults(v.massDefaults);
    if (!defaults) return null;
    result.massDefaults = defaults;
  }
  if (v.missionClass !== undefined) {
    const c = parseMissionClass(v.missionClass);
    if (!c) return null;
    result.missionClass = c;
  }
  if (v.reportMode !== undefined) {
    const mode = parseReportMode(v.reportMode);
    if (!mode) return null;
    result.reportMode = mode;
  }
  if (v.sections !== undefined) {
    const sections = readReportSections(v.sections);
    if (!sections) return null;
    result.sections = sections;
  }
  if (v.carbon !== undefined) {
    if (!record(v.carbon) || !record(v.carbon.phases) ||
        typeof v.carbon.basis !== 'string' || v.carbon.basis.length > 1000 ||
        typeof v.carbon.boundary !== 'string' || v.carbon.boundary.length > 1000) return null;
    const carbon = newCarbonPlanning();
    for (const id of CARBON_PHASES) {
      if (!amount(v.carbon.phases[id])) return null;
      carbon.phases[id] = v.carbon.phases[id];
    }
    carbon.basis = v.carbon.basis;
    carbon.boundary = v.carbon.boundary;
    result.carbon = carbon;
  }
  for (const id of PLAN_TEXT_FIELDS) {
    const text = v.text[id];
    if (typeof text !== 'string' || text.length > 1000) return null;
    result.text[id] = text;
  }
  for (const id of COST_ITEMS) {
    const value = v.costs[id];
    if (!amount(value)) return null;
    result.costs[id] = value;
  }
  if (v.si !== undefined) {
    if (!record(v.si) || typeof v.si.inputKey !== 'string' || v.si.inputKey.length > 32000 || !isSiNarrative(v.si.result)) return null;
    result.si = { inputKey: v.si.inputKey, result: v.si.result };
  }
  return { ...result, objectiveType: v.objectiveType as ReportPlanning['objectiveType'],
    currency: v.currency as ReportPlanning['currency'], priceBaseYear: v.priceBaseYear,
    costBasis: v.costBasis, contingencyPercent: v.contingencyPercent, funding: v.funding };
}
export function budgetInput(p: ReportPlanning) {
  return { costs: p.costs, contingency_percent: p.contingencyPercent, funding: p.funding,
    currency: p.currency || null, price_base_year: p.priceBaseYear, basis: p.costBasis };
}
export function budgetReady(p: ReportPlanning): boolean {
  const c = p.carbon;
  const carbonReady = !c || !CARBON_PHASES.some((id) => c.phases[id] !== null) || !!(c.basis.trim() && c.boundary.trim());
  return carbonReady && ((!COST_ITEMS.some((id) => p.costs[id] !== null) && p.funding === null) || !!(p.currency && p.priceBaseYear && p.costBasis.trim()));
}
export function carbonInput(p: ReportPlanning, pages: DocumentPages) {
  return { ...(p.carbon ?? newCarbonPlanning()), compact_pages: pages.compact, reference_pages: pages.reference };
}
export function planningContext(p: ReportPlanning, scenarioKey: string, name: string, decision: string, lang: string, objectives: MissionObjectives) {
  const { si: _si, sections: _sections, reportMode: _mode, estimates: _estimates, estimatesOff: _off, massDefaults: _massDefaults, missionClass: _class, ...inputs } = p;
  return JSON.stringify({ inputs, scenarioKey, name, decision, lang, objectives });
}
export async function reportPost(path: 'budget' | 'narrative' | 'carbon' | 'reliability', body: unknown, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`${BASE}api/raven/report/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  });
  if (!response.ok) throw new Error(response.status === 429 && path === 'narrative' ? 'si.rateLimited' :
    response.status === 503 && path === 'narrative' ? 'dossier.siUnavailable' :
    response.status === 422 ? 'dossier.invalid' : 'dossier.requestFailed');
  return response.json();
}
export function isCarbonEstimate(v: unknown): v is CarbonEstimate {
  if (!record(v) || !record(v.mission) || !record(v.document)) return false;
  const m = v.mission; const d = v.document;
  const phases = m.phase_emissions_kg_co2e;
  return m.unit === 'kg CO2e' && m.source === 'user_estimates' && m.independently_verified === false &&
    typeof m.known_phases === 'number' && Number.isInteger(m.known_phases) && m.known_phases >= 0 && m.known_phases <= 7 &&
    Array.isArray(m.missing_phases) && m.missing_phases.every((p) => typeof p === 'string' && CARBON_PHASES.some((id) => id === p)) &&
    amount(m.known_subtotal_kg_co2e, 7e15) && amount(m.total_kg_co2e, 7e15) &&
    record(phases) && CARBON_PHASES.every((id) => amount(phases[id])) &&
    typeof m.basis === 'string' && typeof m.boundary === 'string' &&
    [d.compact_pages, d.reference_pages].every((n) => n === null || (typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 100000)) &&
    typeof d.paper_production_kg_co2e_per_sheet === 'number' && Number.isFinite(d.paper_production_kg_co2e_per_sheet) && d.paper_production_kg_co2e_per_sheet > 0 &&
    (d.compaction_avoided_kg_co2e === null || (typeof d.compaction_avoided_kg_co2e === 'number' && Number.isFinite(d.compaction_avoided_kg_co2e))) &&
    amount(d.not_printing_avoided_kg_co2e) && typeof d.paper_factor_source === 'string' && typeof d.paper_factor_id === 'string';
}
export function isBudgetEstimate(v: unknown): v is BudgetEstimate {
  return record(v) && ['known_subtotal', 'contingency_amount', 'total_lifecycle_cost'].every((id) => amount(v[id], COST_ITEMS.length * 1e15 * 2)) &&
    (v.funding_gap === null || (typeof v.funding_gap === 'number' && Number.isFinite(v.funding_gap))) &&
    (v.within_declared_funding === null || typeof v.within_declared_funding === 'boolean') &&
    v.economic_feasibility === null && v.source === 'user_estimates' &&
    typeof v.known_cost_items === 'number' && v.known_cost_items >= 0 && v.known_cost_items <= 9 &&
    Array.isArray(v.missing_cost_items) && v.missing_cost_items.every((s) => typeof s === 'string') &&
    (v.currency === null || ['EUR', 'USD', 'GBP'].includes(String(v.currency))) &&
    amount(v.price_base_year, 2200) && typeof v.basis === 'string';
}
