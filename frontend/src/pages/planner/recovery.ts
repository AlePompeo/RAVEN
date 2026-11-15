// SPDX-License-Identifier: Apache-2.0
import { RAVEN_MAX_DAYS, RAVEN_MAX_STEPS_PER_SITE, ravenSteps, type EvaluateIn,
  type RavenClient, type RavenEvaluation, type RavenFailure, type RavenSiteInfo } from '../../shell/ravenApi';
import { earthVisibility, validEvaluations } from './journey';
import type { EphemerisRange, PlannerInput } from './timeline';

export type RecoveryStatus = 'met' | 'blocked' | 'unknown';
export interface Assessment {
  status: RecoveryStatus;
  firstProblem: { time: number; cause: 'sun' | 'earth' | 'both' | 'unknown' } | null;
}
interface RecoveryOptionBase {
  evaluation: RavenEvaluation;
  request: EvaluateIn;
}
export type RecoveryOption = RecoveryOptionBase & ({ kind: 'time' } | { kind: 'site'; distanceKm: number });
export interface RecoveryResult {
  delayed: RavenEvaluation;
  assessment: Assessment;
  time: RecoveryOption | null;
  site: RecoveryOption | null;
  searchHours: number;
  sitesChecked: number;
  sitesInScope: number;
}
export type RecoveryOutcome = { ok: true; data: RecoveryResult } |
  { ok: false; kind: RavenFailure | 'range'; detail?: string };

/** A known obstruction outranks unknown samples; never treat unknown as visible. */
export function assess(e: RavenEvaluation): Assessment {
  const earth = earthVisibility(e);
  const sun = e.steps!.lit;
  const times = e.steps!.time_unix;
  let firstUnknown: Assessment['firstProblem'] = null;
  let firstBlocked: Assessment['firstProblem'] = null;
  for (let i = 0; i < times.length; i++) {
    const s = sun[i], v = earth[i];
    if (s === false || v === false) {
      firstBlocked ??= { time: times[i]!, cause: s === false && v === false ? 'both' : s === false ? 'sun' : 'earth' };
    } else if (s == null || v == null) {
      firstUnknown ??= { time: times[i]!, cause: 'unknown' };
    }
  }
  return firstBlocked ? { status: 'blocked', firstProblem: firstBlocked } :
    firstUnknown ? { status: 'unknown', firstProblem: firstUnknown } : { status: 'met', firstProblem: null };
}

export function lunarDistanceKm(a: Pick<RavenSiteInfo, 'lat_deg' | 'lon_deg_east'>, b: Pick<RavenSiteInfo, 'lat_deg' | 'lon_deg_east'>): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat_deg - a.lat_deg) * rad;
  const dLon = (b.lon_deg_east - a.lon_deg_east) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat_deg * rad) * Math.cos(b.lat_deg * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 1737.4 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

const utc = (ms: number) => new Date(ms).toISOString().replace('.000Z', 'Z');

export function recoveryInput(input: PlannerInput, option: RecoveryOption, originalSiteId: string): PlannerInput {
  const siteA = option.request.site_id;
  const siteB = input.mode === 'sites' && input.siteB === siteA
    ? originalSiteId !== siteA ? originalSiteId : input.siteA
    : input.siteB;
  return { ...input, siteA, siteB, start: option.request.start_utc.slice(0, 16) };
}

/** Evaluates only the existing RAVEN model and re-evaluates a candidate at mission duration. */
export async function recover(client: Pick<RavenClient, 'evaluate'>, baseline: RavenEvaluation, request: EvaluateIn,
  delayHours: number, sites: readonly RavenSiteInfo[], range: EphemerisRange | null, signal: AbortSignal): Promise<RecoveryOutcome> {
  if (!Number.isInteger(delayHours) || delayHours < 1 || delayHours > 720) return { ok: false, kind: 'invalid' };
  const start = Date.parse(baseline.window.start_utc) + delayHours * 3600000;
  const stepMs = request.step_min * 60000;
  const missionSteps = ravenSteps(request.days, request.step_min);
  const end = range ? Date.parse(range.end_utc) : Infinity;
  if (!Number.isFinite(start) || (range && (start < Date.parse(range.start_utc) || start + request.days * 86400000 > end))) {
    return { ok: false, kind: 'range' };
  }
  const { mission_shift_days: _shift, ...base } = request;
  const delayedRequest = { ...base, start_utc: utc(start), include_steps: true, include_windows: false };
  async function evaluate(q: EvaluateIn): Promise<{ ok: true; data: RavenEvaluation } | { ok: false; kind: RavenFailure; detail?: string }> {
    if (signal.aborted) return { ok: false, kind: 'aborted' };
    const result = await client.evaluate(q, { signal });
    if (signal.aborted) return { ok: false, kind: 'aborted' };
    if (!result.ok) return result;
    if (!validEvaluations([result.data], [q]) || result.data.model_version !== baseline.model_version ||
        result.data.registry_sha256 !== baseline.registry_sha256) return { ok: false, kind: 'response' };
    return result;
  }
  const delayed = await evaluate(delayedRequest);
  if (!delayed.ok) return delayed;

  const maxByRange = Number.isFinite(end) ? Math.floor((end - start - request.days * 86400000) / stepMs) : Infinity;
  const extra = Math.max(0, Math.min(Math.floor(7 * 86400000 / stepMs), RAVEN_MAX_STEPS_PER_SITE - missionSteps,
    Math.floor(RAVEN_MAX_DAYS * 86400000 / stepMs) - missionSteps, maxByRange));
  let time: RecoveryOption | null = null;
  if (extra > 0) {
    const searchRequest = { ...delayedRequest, days: (missionSteps + extra) * request.step_min / 1440 };
    const search = await evaluate(searchRequest);
    if (!search.ok) return search;
    const sun = search.data.steps!.lit;
    const earth = earthVisibility(search.data);
    let consecutive = 0;
    for (let i = 0; i < sun.length; i++) {
      consecutive = sun[i] === true && earth[i] === true ? consecutive + 1 : 0;
      const first = i - missionSteps + 1;
      if (consecutive >= missionSteps && first > 0 && first <= extra) {
        const q = { ...delayedRequest, start_utc: utc(start + first * stepMs) };
        const candidate = await evaluate(q);
        if (!candidate.ok) return candidate;
        if (assess(candidate.data).status !== 'met') return { ok: false, kind: 'response' };
        time = { kind: 'time', request: q, evaluation: candidate.data };
        break;
      }
    }
  }

  const choices = sites.filter((s) => s.id !== baseline.site.id && s.dem_covered)
    .map((s) => ({ site: s, distanceKm: lunarDistanceKm(baseline.site, s) }))
    .sort((a, b) => a.distanceKm - b.distanceKm || a.site.id.localeCompare(b.site.id)).slice(0, 5);
  let site: RecoveryOption | null = null;
  let sitesChecked = 0;
  for (const choice of choices) {
    const { custom_site: _custom, ...withoutCustom } = delayedRequest;
    const q = { ...withoutCustom, site_id: choice.site.id };
    const candidate = await evaluate(q);
    if (!candidate.ok) return candidate;
    sitesChecked++;
    if (assess(candidate.data).status === 'met') {
      site = { kind: 'site', request: q, evaluation: candidate.data, distanceKm: choice.distanceKm };
      break;
    }
  }
  return { ok: true, data: { delayed: delayed.data, assessment: assess(delayed.data), time, site,
    searchHours: extra * request.step_min / 60, sitesChecked, sitesInScope: choices.length } };
}
