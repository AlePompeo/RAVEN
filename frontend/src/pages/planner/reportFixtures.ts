// SPDX-License-Identifier: Apache-2.0
// Test fixtures of the report: A is the recorded engine response, B is the same site with the radio link outside the model
// (everything downstream unknown), the case the verdict has to word with care.
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation } from '../../shell/ravenApi';

export const siteA = evaluationFixture as unknown as RavenEvaluation;

export function unknownRf(base: RavenEvaluation = siteA): RavenEvaluation {
  const e = structuredClone(base) as RavenEvaluation;
  const s = e.steps!;
  const n = s.time_unix.length;
  const nulls = <T,>(): (T | null)[] => Array(n).fill(null);
  e.site = { ...e.site, id: 'haworth', name: 'Haworth' };
  s.margin_db = nulls<number>(); s.rf_closes = nulls<boolean>(); s.link_usable = nulls<boolean>(); s.useful = nulls<boolean>();
  s.soc = nulls<number>(); s.limiting = nulls<string>(); s.chosen_rate_bps = nulls<number>();
  s.rf_reason = Array(n).fill('outside_model'); s.state = Array(n).fill('unknown');
  e.metrics = { ...e.metrics, useful_hours: 0, useful_fraction: 0, useful_fraction_of_known: null, known_steps: 0, unknown_steps: n,
    unknown_hours: n * e.window.step_min / 60, min_soc: null, limiting_fraction: { energy: 0, link: 0, visibility: 0, multiple: 0 } };
  e.first_unknown_index = 0;
  return e;
}
