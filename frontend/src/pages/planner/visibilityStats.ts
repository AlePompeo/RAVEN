// SPDX-License-Identifier: Apache-2.0
// Key figures of Sun and Earth, countdowns to sunset / Earthset and per-lunar-day figures, derived from the engine steps.
// Unknown stays unknown: an unknown step ends a continuous run, is never counted as dark or hidden, and is reported apart.
import type { RavenEvaluation } from '../../shell/ravenApi';
import { earthVisibility, nextChange } from './journey';

export const SYNODIC_DAYS = 29.530588;

export interface SiteStats {
  sunMaxElDeg: number | null;
  sunMeanElDeg: number | null;
  litH: number | null;
  longestLitH: number | null;
  longestDarkH: number | null;
  earthH: number | null;
  longestEarthH: number | null;
  longestNoEarthH: number | null;
  dsnVisibleH: number | null;
  dsnUnknownH: number;
  unknownH: number;
}

/** Longest run of `true` (or of `false`) over the known values; an unknown value ends a run. */
function longestRun(values: readonly (boolean | null)[], want: boolean): number {
  let best = 0, cur = 0;
  for (const v of values) { cur = v === want ? cur + 1 : 0; if (cur > best) best = cur; }
  return best;
}
const count = (v: readonly (boolean | null)[], want: boolean) => v.filter((x) => x === want).length;
const countUnknown = (v: readonly (boolean | null)[]) => v.filter((x) => x === null).length;

export function siteStats(e: RavenEvaluation): SiteStats | null {
  const s = e.steps;
  if (!s) return null;
  const h = e.window.step_min / 60;
  const earth = earthVisibility(e);
  const lit = s.lit;
  const dsn = s.dsn_visible;
  const knownLit = lit.some((x) => x !== null), knownEarth = earth.some((x) => x !== null);
  const knownDsn = dsn.some((x) => x !== null);
  const litEl = s.sun_el_deg.filter((el, i) => lit[i] === true && typeof el === 'number' && Number.isFinite(el)) as number[];
  return {
    sunMaxElDeg: litEl.length ? Math.max(...litEl) : null,
    sunMeanElDeg: litEl.length ? litEl.reduce((a, b) => a + b, 0) / litEl.length : null,
    litH: knownLit ? count(lit, true) * h : null,
    longestLitH: knownLit ? longestRun(lit, true) * h : null,
    longestDarkH: knownLit ? longestRun(lit, false) * h : null,
    earthH: knownEarth ? count(earth, true) * h : null,
    longestEarthH: knownEarth ? longestRun(earth, true) * h : null,
    longestNoEarthH: knownEarth ? longestRun(earth, false) * h : null,
    dsnVisibleH: knownDsn ? count(dsn, true) * h : null,
    dsnUnknownH: countUnknown(dsn) * h,
    unknownH: Math.max(countUnknown(lit), countUnknown(earth)) * h,
  };
}

export interface Countdown { visible: boolean | null; hours: number | null; status: 'change' | 'unknown' | 'end' }
/** A missing sample prevents a claim that no change occurs in the window. */
export function countdownAt(e: RavenEvaluation, index: number): { sun: Countdown; earth: Countdown } | null {
  const s = e.steps;
  if (!s || index < 0 || index >= s.lit.length) return null;
  const h = e.window.step_min / 60;
  const one = (v: readonly (boolean | null)[]): Countdown => {
    const next = nextChange(v, index);
    return { visible: v[index] ?? null, status: next.kind,
      hours: next.kind === 'change' ? (next.index - index) * h : null };
  };
  return { sun: one(s.lit), earth: one(earthVisibility(e)) };
}

export interface LunarDay {
  index: number;
  startMs: number;
  days: number;
  litPct: number | null;
  earthPct: number | null;
  usefulH: number;
}
/** The window cut in synodic months from its start: sunlight share, Earth share and useful hours of each (the last may be shorter). */
export function lunarDays(e: RavenEvaluation): LunarDay[] {
  const s = e.steps;
  if (!s || s.time_unix.length === 0) return [];
  const stepD = e.window.step_min / 1440, h = e.window.step_min / 60;
  const per = Math.max(1, Math.round(SYNODIC_DAYS / stepD));
  const earth = earthVisibility(e);
  const out: LunarDay[] = [];
  for (let a = 0, k = 0; a < s.time_unix.length; a += per, k++) {
    const b = Math.min(s.time_unix.length, a + per);
    const share = (v: readonly (boolean | null)[]) => {
      const known = v.slice(a, b).filter((x) => x !== null);
      return known.length === 0 ? null : (known.filter((x) => x === true).length / known.length) * 100;
    };
    out.push({ index: k + 1, startMs: s.time_unix[a]! * 1000, days: (b - a) * stepD, litPct: share(s.lit), earthPct: share(earth),
      usefulH: s.useful.slice(a, b).filter((x) => x === true).length * h });
  }
  return out;
}
