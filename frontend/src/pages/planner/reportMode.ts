// SPDX-License-Identifier: Apache-2.0
// Information architecture of the Dossier for the two report modes. Pure functions, no UI.
//  Learn : the 4 essential questions (+ the 2 thresholds already set in the Mission step, shown read-only);
//          the rest of the report (costs, CO2e, plan text) is estimated by the engine.
//  Expert: the same questions plus the RAVEN estimates; cost, CO2e and the plan text are produced by the engine, not typed.
import { REPORT_PHASES } from './report';
import { reportCompletion } from './reportCompletion';
import type { JourneyDraft } from './journey';
import { type BudgetEstimate, type CarbonEstimate, type ReportPlanning } from './reportPlanning';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { reportModeFor, type ReportMode } from './reportSections';

/** Text fields asked in Learn (and shown first in Expert); the other text fields are optional. */
export const ESSENTIAL_TEXT = ['missionStatement', 'successCriteria', 'owner'] as const;
export const OBJECTIVE_TYPES = ['scientific', 'technology', 'other'] as const;

/** Extension slot for the scenario slider of a later job: no UI and no behaviour yet. */
export const SCENARIO_SLOT = 'dossier-scenario-slot';

export const effectiveReportMode = (p: ReportPlanning | undefined, site: 'learning' | 'avanzato'): ReportMode => p?.reportMode ?? reportModeFor(site);

export interface DossierProgress { total: number; filled: number; estimated: number; unknown: number }
/**
 * Completeness of the report deliverables (phase fields): filled by the user, computed from engine results or
 * carbon arithmetic, or covered by an ACCEPTED RAVEN estimate (counted apart). Proposed estimates count nowhere.
 */
export function dossierProgress(draft: JourneyDraft, evaluations: readonly RavenEvaluation[], budget: BudgetEstimate | null, carbon: CarbonEstimate | null): DossierProgress {
  const { statements } = reportCompletion(draft, evaluations, budget);
  const ids = REPORT_PHASES.flatMap((phase) => [...phase.fields]) as string[];
  let filled = 0; let estimated = 0;
  for (const id of ids) {
    const s = statements[id];
    if (id === 'environmental_footprint' && carbon && carbon.mission.known_phases > 0) filled += 1;
    else if (s?.origin === 'engine_estimate') estimated += 1;
    else if (s && s.origin !== 'draft_proposal') filled += 1;
  }
  return { total: ids.length, filled, estimated, unknown: ids.length - filled - estimated };
}
