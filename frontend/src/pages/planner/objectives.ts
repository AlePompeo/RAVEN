// SPDX-License-Identifier: Apache-2.0
export type Objective = 'sun' | 'earth' | 'radio' | 'balanced';
export interface MissionObjectives {
  priority: Objective;
  minSunPercent: number | null;
  minRfPercent: number | null;
}

export const defaultObjectives = (): MissionObjectives => ({ priority: 'balanced', minSunPercent: null, minRfPercent: null });

function validThreshold(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100);
}

export function readObjectives(value: unknown): MissionObjectives | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  if (v.priority !== 'sun' && v.priority !== 'earth' && v.priority !== 'radio' && v.priority !== 'balanced') return null;
  if (!validThreshold(v.minSunPercent) || !validThreshold(v.minRfPercent)) return null;
  return { priority: v.priority, minSunPercent: v.minSunPercent, minRfPercent: v.minRfPercent };
}

export type Criterion = 'not_set' | 'unknown' | 'met' | 'not_met';

export function evaluateObjectives(objectives: MissionObjectives, sunFraction: number, rfSamples: boolean[] | null): { sun: Criterion; rf: Criterion } {
  const check = (threshold: number | null, fraction: number | null): Criterion => threshold === null ? 'not_set'
    : fraction === null || !Number.isFinite(fraction) || fraction < 0 || fraction > 1 ? 'unknown'
      : fraction >= threshold / 100 ? 'met' : 'not_met';
  const rf = rfSamples?.length ? rfSamples.filter(Boolean).length / rfSamples.length : null;
  return { sun: check(objectives.minSunPercent, sunFraction), rf: check(objectives.minRfPercent, rf) };
}
