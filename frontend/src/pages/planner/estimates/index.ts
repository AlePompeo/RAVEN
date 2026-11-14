// SPDX-License-Identifier: Apache-2.0
import type { RavenEvaluation, RavenValidation } from '../../../shell/ravenApi';
import type { MissionObjectives } from '../objectives';
import { calendarDrafts } from './calendar';
import { massDrafts, powerDrafts } from './power';
import { requirementDrafts } from './requirements';
import { classDrafts, DEFAULT_MISSION_CLASS, type MissionClassId } from './missionClass';
import { activeEstimates, digestOf, type Draft, type EngineEstimate, type EstimateField, type EstimateStatus, type MassDefaults } from './types';

export * from './types';

export interface EstimateContext {
  evaluations: readonly RavenEvaluation[];
  objectives: MissionObjectives;
  validation: RavenValidation | null;
  massDefaults?: MassDefaults;
  /** Mission-class slider position (default: small commercial lander). */
  missionClass?: MissionClassId;
  /** Timestamp of the calculation (not "now"), so the same inputs always produce the same estimates. */
  producedAt: string;
}

/** Pure and deterministic: same context, same list, same order. Every new estimate starts as 'proposed'. */
export function generateEstimates(ctx: EstimateContext): EngineEstimate[] {
  const drafts: Draft[] = [
    ...requirementDrafts(ctx.evaluations, ctx.objectives),
    ...calendarDrafts(ctx.evaluations), ...powerDrafts(ctx.evaluations), ...massDrafts(ctx.evaluations, ctx.massDefaults),
    ...(ctx.evaluations.length ? classDrafts(ctx.missionClass ?? DEFAULT_MISSION_CLASS) : []),
  ];
  return drafts.map((d) => ({ ...d, produced_at: ctx.producedAt, status: 'proposed', digest: digestOf([d.method_id, d.inputs_used, d.items, d.range]) }));
}

/** Keeps the user's decision for an estimate whose digest did not change; a changed or new one is proposed again. */
export function mergeEstimates(previous: readonly EngineEstimate[], fresh: readonly EngineEstimate[]): EngineEstimate[] {
  return fresh.map((f) => {
    const old = previous.find((p) => p.id === f.id);
    return old && old.digest === f.digest ? { ...f, status: old.status, produced_at: old.produced_at } : f;
  });
}
export const sameEstimates = (a: readonly EngineEstimate[], b: readonly EngineEstimate[]) => digestOf(a) === digestOf(b);

export function setEstimateStatus(list: readonly EngineEstimate[], id: string, status: EstimateStatus): EngineEstimate[] {
  return list.map((e) => (e.id === id ? { ...e, status } : e));
}
export const acceptedFor = (list: readonly EngineEstimate[] | undefined, field: EstimateField) =>
  activeEstimates(list).filter((e) => e.field === field);
export const acceptedEstimates = activeEstimates;
