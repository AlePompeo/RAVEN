// SPDX-License-Identifier: Apache-2.0
// Link figures of the report derived from the engine steps of each scenario, no new model call.
// Unknown stays unknown: a step with a missing input is counted apart and never as "closed" or "blocked".
import type { RavenEvaluation } from '../../shell/ravenApi';

export interface LinkHours {
  /** Hours with the Earth above the local horizon (the line of sight is open). */
  geometric: number;
  /** Hours in which the link closes (margin at or above the required margin). */
  available: number;
  /** Hours in which the link closes although the Earth is below the horizon (diffraction). */
  beyondLos: number;
  /** Hours in which one of the two answers is unknown. */
  unknown: number;
  total: number;
}

/** Counts the three link hours of one scenario. Steps are one step apart: hours = steps x step / 60. */
export function linkHours(e: RavenEvaluation): LinkHours | null {
  const s = e.steps;
  if (!s) return null;
  const h = e.window.step_min / 60;
  let geometric = 0, available = 0, beyond = 0, unknown = 0;
  for (let i = 0; i < s.earth_el_deg.length; i++) {
    const el = s.earth_el_deg[i], hor = s.earth_horizon_deg[i], closes = s.rf_closes[i];
    const geo = el == null || hor == null ? null : el > hor;
    if (geo === null || closes === null || closes === undefined) { unknown += 1; if (geo === true) geometric += 1; if (closes === true) available += 1; continue; }
    if (geo) geometric += 1;
    if (closes) { available += 1; if (!geo) beyond += 1; }
  }
  return { geometric: geometric * h, available: available * h, beyondLos: beyond * h, unknown: unknown * h, total: s.earth_el_deg.length * h };
}

export interface ElevationPoint { el: number; margin: number }
/** Margin against the elevation of the Earth: the points where both are known, thinned evenly to at most `max`. */
export function elevationMargin(e: RavenEvaluation, max = 500): ElevationPoint[] {
  const s = e.steps;
  if (!s) return [];
  const pts: ElevationPoint[] = [];
  for (let i = 0; i < s.earth_el_deg.length; i++) {
    const el = s.earth_el_deg[i], m = s.margin_db[i];
    if (typeof el === 'number' && typeof m === 'number' && Number.isFinite(el) && Number.isFinite(m)) pts.push({ el, margin: m });
  }
  if (pts.length <= max) return pts;
  const stride = pts.length / max;
  return Array.from({ length: max }, (_, k) => pts[Math.floor(k * stride)]!);
}

/** Median of the horizon elevation at the Earth azimuth (ridge horizon), over the known steps; null if none is known. */
export function medianHorizon(e: RavenEvaluation): number | null {
  const v = (e.steps?.earth_horizon_deg ?? []).filter((x): x is number => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b);
  return v.length ? v[Math.floor(v.length / 2)]! : null;
}

export interface LinkTerms { freeSpaceDb: number | null; diffractionDb: number | null; multipathDb: number | null; marginDb: number | null; knownSteps: number }
const mean = (a: readonly (number | null | undefined)[]): number | null => {
  const k = a.filter((x): x is number => typeof x === 'number' && Number.isFinite(x));
  return k.length ? k.reduce((p, c) => p + c, 0) / k.length : null;
};
/** Mean of each loss term over the steps where it is known (the diffraction term only where the link is evaluated). */
export function linkTerms(e: RavenEvaluation): LinkTerms | null {
  const s = e.steps;
  if (!s) return null;
  return { freeSpaceDb: mean(s.free_space_loss_db ?? []), diffractionDb: mean(s.diffraction_loss_db ?? []), multipathDb: mean(s.multipath_gain_db ?? []),
    marginDb: mean(s.margin_db), knownSteps: s.margin_db.filter((x) => typeof x === 'number').length };
}

/** Latitude and longitude as written in the report: 85.5° S, 12.0° E. */
export function formatCoordinate(latDeg: number, lonEastDeg: number): string {
  const lon = ((lonEastDeg + 540) % 360) - 180;
  return `${Math.abs(latDeg).toFixed(2)}° ${latDeg < 0 ? 'S' : 'N'}, ${Math.abs(lon).toFixed(2)}° ${lon < 0 ? 'W' : 'E'}`;
}

/** Position of a point on the south-polar azimuthal map (radius 1 at the limit latitude, longitude clockwise from the top). */
export function polarPosition(latDeg: number, lonEastDeg: number, limitLatDeg: number): { x: number; y: number } | null {
  if (latDeg > limitLatDeg) return null;
  const rho = (90 + latDeg) / (90 + limitLatDeg);
  const th = (lonEastDeg * Math.PI) / 180;
  return { x: rho * Math.sin(th), y: -rho * Math.cos(th) };
}
