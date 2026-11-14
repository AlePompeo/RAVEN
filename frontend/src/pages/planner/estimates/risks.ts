// SPDX-License-Identifier: Apache-2.0
// The few risks a reader needs, taken from the engine's own results (no probabilities, no invented causes).
// At most MAX_RISKS rows, merged across scenarios A and B (one row per kind, the scenarios named inside it), ordered by
// severity and then by the largest share of the evaluated window they affect. Each row has a plain "what", the
// consequence and the next action, in English (the report is English only; see reportText.ts, keys `risk.*`).
// Severity rule (deterministic): high when the largest affected share of the window is at least HIGH_SHARE, or a
// blackout is known; medium otherwise. Unknown time is a risk of its own and is never counted as zero.
import type { RavenEvaluation } from '../../../shell/ravenApi';
import { nf, rt } from '../reportText';

export type Severity = 'high' | 'medium';
export type RiskKind = 'blocked' | 'unknown' | 'survival' | 'blackout' | 'custom';
export const HIGH_SHARE = 0.25;
export const MAX_RISKS = 5;

export interface Risk { kind: RiskKind; severity: Severity; share: number; what: string; consequence: string; action: string }

const label = (i: number) => (i === 0 ? 'A' : 'B');
const h = (n: number) => nf(n, { maximumFractionDigits: 1 });
const windowHours = (e: RavenEvaluation) => e.window.n_steps * e.window.step_min / 60;
const stepHours = (e: RavenEvaluation, steps: number) => steps * e.window.step_min / 60;

interface Part { scenario: string; hours: number; total: number; text: string }
const join = (parts: Part[]) => parts.map((p) => p.text).join('; ');
const share = (parts: Part[]) => Math.max(0, ...parts.map((p) => (p.total > 0 ? p.hours / p.total : 0)));

export function topRisks(evaluations: readonly RavenEvaluation[]): Risk[] {
  const out: Risk[] = [];
  const push = (kind: RiskKind, parts: Part[], force: Severity | null = null, params: Record<string, string> = {}) => {
    if (!parts.length) return;
    const s = share(parts);
    const where = join(parts);
    out.push({
      kind, share: s, severity: force ?? (s >= HIGH_SHARE ? 'high' : 'medium'),
      what: rt(`risk.${kind}.what`, { where, ...params }), consequence: rt(`risk.${kind}.cons`), action: rt(`risk.${kind}.act`),
    });
  };
  const per = (pick: (e: RavenEvaluation) => number, text: (hours: number, total: number, s: string) => string): Part[] =>
    evaluations.map((e, i) => ({ e, i, hours: pick(e) })).filter((x) => x.hours > 0)
      .map((x) => ({ scenario: label(x.i), hours: x.hours, total: windowHours(x.e), text: text(x.hours, windowHours(x.e), label(x.i)) }));

  // far terrain closes the link: the steps whose radio reason is blocked_far_terrain
  push('blocked', per((e) => stepHours(e, Math.max(e.inputs_state.rf_reason_counts?.blocked_far_terrain ?? 0, e.inputs_state.terrain_reason_counts?.blocked_far_terrain ?? 0)),
    (hours, total, s) => `${s} for ${h(hours)} of ${h(total)} h`));
  // hours the model cannot compute: unknown, not zero
  push('unknown', per((e) => e.metrics.unknown_hours, (hours, _total, s) => `${s} for ${h(hours)} h`));
  // survival mode or no power at all
  const surv = evaluations.flatMap((e, i) => {
    const hs = e.metrics.state_hours?.survival ?? 0, dark = e.metrics.state_hours?.dark ?? 0, total = windowHours(e);
    const parts: Part[] = [];
    if (hs > 0) parts.push({ scenario: label(i), hours: hs, total, text: `${label(i)} ${h(hs)} h in survival mode` });
    if (dark > 0) parts.push({ scenario: label(i), hours: dark, total, text: `${label(i)} ${h(dark)} h without power (dark)` });
    return parts;
  });
  push('survival', surv);
  // a known blackout
  push('blackout', evaluations.flatMap((e, i) => e.metrics.time_to_first_blackout_h === null ? [] :
    [{ scenario: label(i), hours: 0, total: windowHours(e), text: `${label(i)} after ${h(e.metrics.time_to_first_blackout_h)} h` }]), 'high');
  // a user-defined terrain
  push('custom', evaluations.flatMap((e, i) => (e.terrain?.custom || e.site.custom) ?
    [{ scenario: label(i), hours: 0, total: windowHours(e),
      text: `${label(i)} at ${e.terrain?.resolution_m == null ? 'unknown' : h(e.terrain.resolution_m)} m resolution` }] : []), 'medium');

  const order = { high: 0, medium: 1 } as const;
  return out.map((r, k) => ({ r, k })).sort((a, b) => order[a.r.severity] - order[b.r.severity] || b.r.share - a.r.share || a.k - b.k)
    .map(({ r }) => r).slice(0, MAX_RISKS);
}
