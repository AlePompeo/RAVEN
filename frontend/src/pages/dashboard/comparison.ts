// SPDX-License-Identifier: Apache-2.0
import type { RavenEvaluation } from '../../shell/ravenApi';

export function knownHours(values: readonly (boolean | null)[], stepMin: number): number | null {
  if (!values.length || values.some((value) => value === null)) return null;
  return values.filter((value) => value === true).length * stepMin / 60;
}

export function comparisonHours(e: RavenEvaluation): { sun: number | null; contact: number | null; useful: number | null } {
  return {
    sun: e.steps ? knownHours(e.steps.lit, e.window.step_min) : null,
    contact: e.steps ? knownHours(e.steps.link_usable, e.window.step_min) : null,
    useful: e.steps ? knownHours(e.steps.useful, e.window.step_min) : null,
  };
}
