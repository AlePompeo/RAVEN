// SPDX-License-Identifier: Apache-2.0
// The comparison at the heart of the report: for every site, how many sampled hours are known-yes, known-no and
// unknown, and ONE deterministic verdict built from those numbers. Pure functions (no UI). An unknown is never a zero:
// it is counted apart, and the verdict says what cannot be concluded because of it.
import { rt, nf } from './reportText';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { earthVisibility } from './journey';

export interface Tri { yes: number; no: number; unknown: number; n: number }
export type TriKey = 'useful' | 'sun' | 'earth' | 'rf';
export type CauseId = 'outside_rf' | 'outside_terrain' | 'missing_dem' | 'outside_coverage' | 'missing_ephemeris' | 'unknown_station' | 'upstream' | 'generic';

export interface SiteFigures {
  tag: 'A' | 'B';
  name: string;
  totalH: number;
  stepMin: number;
  usefulH: number;
  unknownH: number;
  tri: Record<TriKey, Tri>;
  minSoc: number | null;
  minSocScope: string;
  reserve: number | null;
  cause: CauseId | null;
  limit: { factor: string; fraction: number } | null;
}

/** "Malapert Massif (Artemis III candidate region; Mons Malapert)" -> "Malapert Massif": the long form stays in the Sites step. */
export const shortName = (name: string): string => name.replace(/\s*\([^)]*\)\s*$/, '') || name;

export const tri = (values: readonly (boolean | null)[]): Tri => ({
  yes: values.filter((v) => v === true).length, no: values.filter((v) => v === false).length,
  unknown: values.filter((v) => v === null).length, n: values.length,
});
export const triHours = (x: Tri, stepMin: number) => ({ yes: x.yes * stepMin / 60, no: x.no * stepMin / 60, unknown: x.unknown * stepMin / 60, total: x.n * stepMin / 60 });

const CAUSES: Record<string, CauseId> = {
  outside_model: 'outside_rf', missing_dem: 'missing_dem', outside_coverage: 'outside_coverage',
  missing_ephemeris: 'missing_ephemeris', unknown_station: 'unknown_station', upstream_unknown: 'upstream',
};
/** Why the first unknown step is unknown: the radio reason first, then the terrain reason. */
export function unknownCause(e: RavenEvaluation): CauseId | null {
  const i = e.first_unknown_index;
  const s = e.steps;
  if (i === null || i === undefined || !s) return e.metrics.unknown_hours > 0 ? 'generic' : null;
  const rf = s.rf_reason[i];
  if (rf && rf !== 'ok' && rf !== 'upstream_unknown') return CAUSES[rf] ?? 'generic';
  const terrain = s.terrain_reason[i];
  if (terrain && terrain !== 'ok') return terrain === 'outside_model' ? 'outside_terrain' : CAUSES[terrain] ?? 'generic';
  return rf === 'upstream_unknown' ? 'upstream' : 'generic';
}

export function siteFigures(e: RavenEvaluation, index: number): SiteFigures {
  const s = e.steps!;
  const stepMin = e.window.step_min;
  const lim = Object.entries(e.metrics.limiting_fraction).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])[0];
  return {
    tag: index === 0 ? 'A' : 'B', name: shortName(e.site.name), stepMin, totalH: e.window.n_steps * stepMin / 60,
    usefulH: e.metrics.useful_hours, unknownH: e.metrics.unknown_hours,
    tri: { useful: tri(s.useful), sun: tri(s.lit), earth: tri(earthVisibility(e)), rf: tri(s.rf_closes) },
    minSoc: e.metrics.min_soc, minSocScope: e.metrics.min_soc_scope,
    reserve: e.parameters_used?.energy.min_soc === undefined ? null : Number(e.parameters_used.energy.min_soc),
    cause: unknownCause(e), limit: lim ? { factor: lim[0], fraction: lim[1] } : null,
  };
}

const num1 = (v: number) => nf(v, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
export const hoursText = num1;
export const pctOf = (part: number, whole: number) => whole > 0 ? part / whole * 100 : 0;
export const pctText = (v: number) => `${num1(v)}%`;
const causeText = (c: CauseId) => rt(`cause.${c}`);

/** "A: 135 of 168 sampled hours confirmed useful (80%); B: 0 confirmed, 146 h unknown because ..." */
export function siteSentence(f: SiteFigures): string {
  const p = { id: f.tag, useful: num1(f.usefulH), total: num1(f.totalH), pct: num1(pctOf(f.usefulH, f.totalH)), unknown: num1(f.unknownH), cause: f.cause ? causeText(f.cause) : '' };
  if (f.unknownH > 0 && f.usefulH === 0) return rt('site.zeroUnknown', p);
  if (f.unknownH > 0) return rt('site.partUnknown', p);
  return rt(f.usefulH === 0 ? 'site.none' : 'site.known', p);
}

export type Outcome = 'clear' | 'tie' | 'none' | 'open';
export interface Verdict { outcome: Outcome; best: SiteFigures | null; headline: string; conclusion: string }

/** Best case of a site: its confirmed useful hours plus every unknown hour, were they all useful. */
const bestCase = (f: SiteFigures) => f.usefulH + f.unknownH;
const EPS = 1e-9;

export function verdict(figs: readonly SiteFigures[]): Verdict {
  const [a, b] = figs;
  const headline0 = figs.map(siteSentence).join('; ');
  if (!a || !b) return { outcome: 'open', best: null, headline: headline0, conclusion: rt('concl.single') };
  const only = (a.usefulH > 0) !== (b.usefulH > 0) ? (a.usefulH > 0 ? a : b) : null;
  const headline = only ? `${headline0}. ${rt('only', { id: only.tag })}` : headline0;
  const lead = a.usefulH >= b.usefulH ? a : b;
  const other = lead === a ? b : a;
  if (lead.usefulH - bestCase(other) > EPS) {
    const unknownFree = other.unknownH === 0;
    return { outcome: 'clear', best: lead, headline, conclusion: unknownFree
      ? rt('concl.clearKnown', { best: lead.tag, other: other.tag, diff: num1(lead.usefulH - other.usefulH) })
      : rt('concl.clearUnknown', { best: lead.tag, other: other.tag, max: num1(bestCase(other)) }) };
  }
  if (a.unknownH === 0 && b.unknownH === 0) {
    return Math.abs(a.usefulH - b.usefulH) < EPS
      ? { outcome: a.usefulH === 0 ? 'none' : 'tie', best: null, headline,
        conclusion: a.usefulH === 0 ? rt('concl.none') : rt('concl.tie', { hours: num1(a.usefulH) }) }
      : { outcome: 'clear', best: lead, headline, conclusion: rt('concl.clearKnown', { best: lead.tag, other: other.tag, diff: num1(lead.usefulH - other.usefulH) }) };
  }
  const conclusion = lead.usefulH - other.usefulH > EPS && other.unknownH > 0
    ? rt('concl.openLead', { lead: lead.tag, other: other.tag, unknown: num1(other.unknownH) })
    : rt('concl.openGeneric', { ua: num1(a.unknownH), ub: num1(b.unknownH) });
  return { outcome: 'open', best: null, headline, conclusion };
}

const FACTORS = ['energy', 'link', 'visibility', 'multiple'];
/** At most three plain bullets: the conclusion, the main limit, what to do about the unknown (or the battery floor). */
export function meaning(figs: readonly SiteFigures[], v: Verdict): string[] {
  const out: string[] = [v.conclusion];
  const limits = figs.filter((f) => f.limit && FACTORS.includes(f.limit.factor))
    .map((f) => rt('means.limitPart', { id: f.tag, factor: rt(`factor.${f.limit!.factor}`), pct: num1(f.limit!.fraction * 100) }));
  if (limits.length) out.push(rt('means.limit', { parts: limits.join(', ') }));
  const unknown = figs.filter((f) => f.unknownH > 0);
  if (unknown.length) {
    out.push(unknown.map((f) => rt(`fix.${f.cause ?? 'generic'}`, { id: f.tag })).join(' '));
  } else {
    const parts = figs.map((f) => `${f.tag} ${f.minSoc === null ? rt('unknown') : pctText(f.minSoc * 100)}`).join(', ');
    const r = figs[0]?.reserve;
    out.push(rt('means.battery', { parts, reserve: r === null || r === undefined ? rt('unknown') : pctText(r * 100) }));
  }
  return out.slice(0, 3);
}
