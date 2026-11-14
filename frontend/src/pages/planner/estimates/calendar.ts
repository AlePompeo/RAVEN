// SPDX-License-Identifier: Apache-2.0
// Step 3: operational calendar of the EVALUATED surface window (start, duration, step and milestones read from the
// per-sample series). Development and launch dates are never inferred: they stay user-declared.
import type { RavenEvaluation } from '../../../shell/ravenApi';
import type { Cell, Draft, EstimateItem } from './types';

const label = (i: number) => (i === 0 ? 'A' : 'B');
const iso = (ms: number): string | null => Number.isFinite(ms) ? new Date(ms).toISOString().slice(0, 16) + 'Z' : null;

export type EventId = 'first_useful' | 'last_useful' | 'first_sunlit' | 'first_unknown' | 'first_blackout';
/** Time of a milestone: an ISO minute; {none} when the whole window is known and the event never occurs; null when unknown. */
export function milestone(e: RavenEvaluation, event: EventId): string | 'none' | null {
  const steps = e.steps;
  if (!steps) return null;
  const at = (k: number) => { const s = steps.time_unix[k]; return s === undefined ? null : iso(s * 1000); };
  const first = (test: (k: number) => boolean) => { for (let k = 0; k < steps.time_unix.length; k++) if (test(k)) return k; return -1; };
  const last = (test: (k: number) => boolean) => { for (let k = steps.time_unix.length - 1; k >= 0; k--) if (test(k)) return k; return -1; };
  const complete = e.metrics.unknown_steps === 0;
  const found = (k: number): string | 'none' | null => k >= 0 ? at(k) : complete ? 'none' : null;
  switch (event) {
    case 'first_useful': return found(first((k) => steps.useful[k] === true));
    case 'last_useful': { const k = last((j) => steps.useful[j] === true); return k >= 0 && !complete ? null : found(k); }
    case 'first_sunlit': return found(first((k) => steps.lit[k] === true));
    case 'first_unknown': { const k = first((j) => steps.state[j] === 'unknown'); return k >= 0 ? at(k) : 'none'; }
    case 'first_blackout': return found(first((k) => steps.state[k] === 'dark'));
  }
}

const EVENTS: EventId[] = ['first_useful', 'last_useful', 'first_sunlit', 'first_unknown', 'first_blackout'];
const FIELD: Record<EventId, string> = { first_useful: 'steps.useful', last_useful: 'steps.useful', first_sunlit: 'steps.lit',
  first_unknown: 'steps.state', first_blackout: 'steps.state' };

export function calendarDrafts(evaluations: readonly RavenEvaluation[]): Draft[] {
  if (!evaluations.length) return [];
  const items: EstimateItem[] = [];
  evaluations.forEach((e, i) => {
    const s = label(i), path = `evaluations[${i}]`;
    const start = Date.parse(e.window.start_utc);
    const row = (event: string, time: Cell, field: string) =>
      items.push({ id: `CAL-${s}-${String(items.length + 1).padStart(2, '0')}`, cells: { scenario: s, event: { key: `est.cal.${event}` }, time, source: field } });
    row('window_start', iso(start), `${path}.window.start_utc`);
    row('window_end', iso(start + e.window.n_steps * e.window.step_min * 60000), `${path}.window.n_steps × ${path}.window.step_min`);
    row('duration', `${Math.round(e.window.n_steps * e.window.step_min / 6) / 10} h; ${e.window.n_steps} × ${e.window.step_min} min`, `${path}.window`);
    for (const event of EVENTS) {
      const m = milestone(e, event);
      row(event, m === 'none' ? { key: 'est.cal.none' } : m, `${path}.${FIELD[event]}`);
    }
  });
  items.push({ id: 'CAL-USER', cells: { scenario: '-', event: { key: 'est.cal.user' }, time: null, source: 'user-declared; none inferred' } });
  return [{
    id: 'est.calendar', field: 'schedule', method_id: 'raven.window_calendar.v1',
    source: 'RAVEN engine evaluated window and per-sample series (/api/raven/evaluate)', tag: 'D', range: null, items,
    inputs_used: evaluations.map((e, i) => ({ name: `evaluations[${i}].window`, value: `${e.window.start_utc}; ${e.window.n_steps} × ${e.window.step_min} min` })),
    validity_limits: ['est.limit.cal.surface', 'est.limit.cal.unknown'],
  }];
}
