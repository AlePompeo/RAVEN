// SPDX-License-Identifier: Apache-2.0
import type { RavenClient, RavenWindow } from '../../shell/ravenApi';
import { missionEvaluateIn, missionFromRaven } from './ravenAdapter';

/** Per-step mission evaluation of one site and window, from the single RAVEN model (`POST /api/raven/evaluate`). */
export const MISSION_STATES = ['operational', 'comms_only', 'survival', 'dark', 'unknown'] as const;
export type MissionState = (typeof MISSION_STATES)[number];
export const MISSION_MAX_STEPS = 1500;
const LIMITING = ['energy', 'link', 'visibility', 'multiple'] as const;
type Limiting = (typeof LIMITING)[number];

export interface MissionRequest {
  site_id: string;
  start_utc: string;
  days: number;
  step_min: number;
  observer_height_m: number;
  rate_bps: number;
  station: 'dsn34' | 'dsn18';
  rf_overrides: Record<string, number>;
  energy_overrides: Record<string, number | string>;
}

export interface ParamTag { key: string; value: number | string; unit: string; status: string; source: string }

export interface MissionResult {
  model_version?: string;
  registry_sha256?: string;
  series: {
    time_unix: number[];
    sun_el_deg: number[];
    disc_fraction: (number | null)[];
    gen_w: (number | null)[];
    soc: (number | null)[];
    margin_db: (number | null)[];
    dsn_visible: (boolean | null)[];
    link_usable: (boolean | null)[];
    state: MissionState[];
    useful: (boolean | null)[];
    limiting: (Limiting | null)[];
  };
  metrics: {
    n_steps: number; known_steps: number; unknown_steps: number;
    useful_hours: number; useful_fraction: number; unknown_hours: number;
    state_hours: Record<MissionState, number>;
    limiting_fraction: Record<Limiting, number>;
    min_soc: number | null; min_soc_scope: string;
    time_to_first_blackout_h: number | null;
    sun_hours: number; harvested_wh: number | null; unmet_wh: number | null;
  };
  inputs_state: { shadow: string; rf: string; dsn: string };
  rate_bps: number;
  station: 'dsn34' | 'dsn18';
  tx_power_w: number;
  parameters: { energy: ParamTag[]; rf: ParamTag[]; observer_height: ParamTag; dsn_min_elevation: ParamTag };
  declared_limits: string[];
  /** Useful windows, edges refined by bisection (RAVEN M9); absent when the model did not return them. */
  windows?: RavenWindow[];
}

export interface MissionInput {
  siteId: string;
  start: string | undefined;
  days: number | undefined;
  stepMin: number | undefined;
  station: 'dsn34' | 'dsn18';
  rate: number;
  gain: number | null;
  k: number | null;
  mast: number | null;
  energy: Record<string, number | string> | undefined;
  observerHeight?: number;
}

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
/** Same rule as the backend window: floor(days * 1440 / step + 1e-9), at least 1. */
export const missionSteps = (days: number, stepMin: number) => Math.max(1, Math.floor((days * 1440) / stepMin + 1e-9));

/** The request, or null when an input is missing or outside the endpoint bounds. */
export function missionRequest(i: MissionInput): MissionRequest | null {
  if (!i.siteId || !i.start || !finite(i.days) || !finite(i.stepMin) || !i.energy) return null;
  if (i.days <= 0 || i.days > 366 || i.stepMin < 10 || i.stepMin > 1440) return null;
  if (missionSteps(i.days, i.stepMin) > MISSION_MAX_STEPS) return null;
  const h = i.observerHeight ?? 2;
  if (!finite(h) || h < 0 || h > 100) return null;
  const rf: Record<string, number> = {};
  if (i.gain !== null) rf.tx_gain_dbi = i.gain;
  if (i.k !== null) rf.compensator_k = i.k;
  if (i.mast !== null) rf.antenna_height_m = i.mast;
  if (Object.values(rf).some((v) => !finite(v))) return null;
  return {
    site_id: i.siteId,
    start_utc: i.start, days: i.days, step_min: i.stepMin, observer_height_m: h,
    rate_bps: i.rate, station: i.station, rf_overrides: rf, energy_overrides: { ...i.energy },
  };
}

const triple = (a: unknown[], ok: (v: unknown) => boolean) => a.every((v) => v === null || ok(v));

/** Structural check: every series has one value per step and unknown stays unknown. */
export function validMission(r: MissionResult | null | undefined, req: MissionRequest): r is MissionResult {
  if (!r || typeof r !== 'object' || !r.series || !r.metrics || !r.parameters) return false;
  const s = r.series;
  const n = missionSteps(req.days, req.step_min);
  const arrays = [s.time_unix, s.disc_fraction, s.gen_w, s.soc, s.margin_db, s.dsn_visible, s.link_usable, s.state, s.useful, s.limiting];
  if (arrays.some((a) => !Array.isArray(a) || a.length !== n)) return false;
  if (!s.state.every((v) => (MISSION_STATES as readonly string[]).includes(v))) return false;
  if (!triple(s.soc, (v) => finite(v) && v >= 0 && v <= 1) || !triple(s.disc_fraction, (v) => finite(v) && v >= 0 && v <= 1) ||
      !triple(s.gen_w, (v) => finite(v) && v >= 0) || !triple(s.margin_db, finite) ||
      !triple(s.useful, (v) => typeof v === 'boolean') || !triple(s.limiting, (v) => (LIMITING as readonly unknown[]).includes(v))) return false;
  // an unknown state never carries a useful flag or a battery value
  for (let k = 0; k < n; k++) {
    if (s.state[k] === 'unknown' && (s.useful[k] !== null || s.soc[k] !== null)) return false;
    if (s.state[k] !== 'unknown' && (typeof s.useful[k] !== 'boolean' || s.soc[k] === null)) return false;
    if (s.useful[k] === true && (s.state[k] !== 'operational' || s.link_usable[k] !== true)) return false;
  }
  const m = r.metrics;
  return finite(m.useful_hours) && finite(m.unknown_hours) && (m.min_soc === null || finite(m.min_soc)) &&
    (m.time_to_first_blackout_h === null || finite(m.time_to_first_blackout_h));
}

export interface StateSegment { state: MissionState; length: number }

export function missionSegments(states: readonly MissionState[]): StateSegment[] {
  const out: StateSegment[] = [];
  for (const state of states) {
    const last = out[out.length - 1];
    if (last?.state === state) last.length++;
    else out.push({ state, length: 1 });
  }
  return out;
}

/** The dominant limiting factor over the window, or null when nothing known limits it. */
export function dominantLimit(r: MissionResult): Limiting | null {
  let best: Limiting | null = null;
  let value = 0;
  for (const k of LIMITING) {
    const v = r.metrics.limiting_fraction[k] ?? 0;
    if (v > value) { best = k; value = v; }
  }
  return best;
}

export type MissionFetch = { ok: true; data: MissionResult } | { ok: false; kind: 'network' | 'invalid' | 'unavailable' | 'server' };

/** Missione dal modello unico (/api/raven/evaluate): stesso calcolo di timeline, Confronto e viste. */
export async function fetchMission(client: RavenClient, req: MissionRequest, signal: AbortSignal): Promise<MissionFetch> {
  const r = await client.evaluate(missionEvaluateIn(req), { signal });
  if (!r.ok) return { ok: false, kind: r.kind === 'invalid' ? 'invalid' : r.kind === 'unavailable' ? 'unavailable' : r.kind === 'network' || r.kind === 'aborted' ? 'network' : 'server' };
  if (!r.data.steps || !r.data.parameters_used) return { ok: false, kind: 'server' };
  const data = missionFromRaven(r.data, req);
  return validMission(data, req) ? { ok: true, data } : { ok: false, kind: 'server' };
}
