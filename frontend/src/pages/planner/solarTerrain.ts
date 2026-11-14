// SPDX-License-Identifier: Apache-2.0
import type { AnalyzeRequest } from '../compare/lunar';
import type { RavenClient } from '../../shell/ravenApi';
import { evaluateAll, evaluateRequests, solarFromRaven } from './ravenAdapter';

export type SolarTerrainState =
  | 'upper_above_profile'
  | 'upper_below_profile'
  | 'outside_coverage'
  | 'missing_dem'
  | 'invalid_geometry';

export interface SolarTerrainResult {
  window: { start_utc: string; days: number; step_min: number; n_steps: number };
  series_time_unix: number[];
  sites: {
    site_id: string;
    horizon_deg: (number | null)[];
    state: SolarTerrainState[];
    centre_above_profile?: (boolean | null)[];
    lower_above_profile?: (boolean | null)[];
    /** Horizon-mask fields (2026-11-04): null = depends on missing DEM data, never sunlit. */
    upper_limb_visible?: (boolean | null)[];
    centre_visible?: (boolean | null)[];
    lower_limb_visible?: (boolean | null)[];
    disc_fraction?: (number | null)[];
    mask?: {
      n_azimuths: number; observer_height_m: number; complete_azimuth_fraction: number;
      far_terrain_dominant_fraction: number; coverage_limit: string; cache: string;
    } | null;
    energy_sensitivity?: { status: 'unknown_terrain' } | {
      status: 'available'; gen_w: number[]; soc: number[]; harvested_wh: number; min_soc: number;
    };
  }[];
  assumptions: {
    dem_product: string;
    dem_sha256: string;
    dem_label_sha256: string;
    lunar_frame: string;
    ephemeris: { versions: Record<string, string>; kernels: Record<string, string> };
    profile_length_m: number;
    profile_spacing_m: number;
    observer_height_m: number;
    observer_height_status?: string;
    coverage_limits?: Record<string, string | number>;
    sun_semidiameter_deg: number;
    azimuth: string;
    sampling: string;
    limits: string;
    dem_policy: string;
  };
}

export interface LimbCounts { known: number; upper: number; centre: number; lower: number }

/** Counts of the three limb criteria on the same sampled profile; null if absent or inconsistent. */
export function limbCounts(row: SolarTerrainResult['sites'][number]): LimbCounts | null {
  const { state, centre_above_profile: c, lower_above_profile: l } = row;
  if (!Array.isArray(c) || !Array.isArray(l) || c.length !== state.length || l.length !== state.length) return null;
  const out = { known: 0, upper: 0, centre: 0, lower: 0 };
  for (let i = 0; i < state.length; i++) {
    const known = state[i] === 'upper_above_profile' || state[i] === 'upper_below_profile';
    if (known !== (typeof c[i] === 'boolean') || known !== (typeof l[i] === 'boolean')) return null;
    if (!known) continue;
    // lower above implies centre above implies upper above
    if ((l[i] && !c[i]) || (c[i] && state[i] !== 'upper_above_profile')) return null;
    out.known++;
    if (state[i] === 'upper_above_profile') out.upper++;
    if (c[i]) out.centre++;
    if (l[i]) out.lower++;
  }
  return out;
}

/**
 * Mean visible solar-disc fraction over the steps whose fraction is known, and the observer
 * height of the mask. Null when the field is absent, inconsistent or no step is known.
 */
export function discSummary(row: SolarTerrainResult['sites'][number]): { mean: number; known: number; height: number } | null {
  const f = row.disc_fraction;
  if (!Array.isArray(f) || f.length !== row.state.length || !row.mask) return null;
  let sum = 0;
  let known = 0;
  for (let i = 0; i < f.length; i++) {
    const v = f[i];
    if (v === null || v === undefined) continue;
    if (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1) return null;
    sum += v;
    known++;
  }
  const height = row.mask.observer_height_m;
  if (!known || typeof height !== 'number' || !Number.isFinite(height)) return null;
  return { mean: sum / known, known, height };
}

export interface SolarTerrainSegment {
  state: SolarTerrainState;
  length: number;
}

export function solarTerrainSegments(states: readonly SolarTerrainState[]): SolarTerrainSegment[] {
  const segments: SolarTerrainSegment[] = [];
  for (const state of states) {
    const last = segments[segments.length - 1];
    if (last?.state === state) last.length++;
    else segments.push({ state, length: 1 });
  }
  return segments;
}

export type SolarTerrainFetch =
  | { ok: true; data: SolarTerrainResult }
  | { ok: false; kind: 'network' | 'invalid' | 'unavailable' | 'server' };

/** Sole contro la maschera LOLA dal modello unico: gli stessi passi di luce usati da energia e missione. */
export async function fetchSolarTerrain(
  client: RavenClient,
  request: AnalyzeRequest,
  signal: AbortSignal,
): Promise<SolarTerrainFetch> {
  const r = await evaluateAll(client, evaluateRequests(request), signal);
  if (!r.ok) return { ok: false, kind: r.kind === 'invalid' ? 'invalid' : r.kind === 'unavailable' ? 'unavailable' : r.kind === 'network' || r.kind === 'aborted' ? 'network' : 'server' };
  return { ok: true, data: solarFromRaven(r.data) };
}

export function synchronizedSolarTerrain(
  result: SolarTerrainResult | null,
  siteId: string,
  times: readonly number[] | undefined,
): SolarTerrainResult['sites'][number] | null {
  if (!result || !times?.length || !Array.isArray(result.series_time_unix) || !Array.isArray(result.sites) ||
      result.series_time_unix.length !== times.length ||
      result.series_time_unix.some((time, i) => time !== times[i])) return null;
  const row = result.sites.find((site) => site && site.site_id === siteId);
  if (!row || !Array.isArray(row.state) || !Array.isArray(row.horizon_deg) ||
      row.state.length !== times.length || row.horizon_deg.length !== times.length) return null;
  if (row.state.some((state, i) => {
    const height = row.horizon_deg[i];
    if (state === 'upper_above_profile' || state === 'upper_below_profile')
      return typeof height !== 'number' || !Number.isFinite(height);
    return !['outside_coverage', 'missing_dem', 'invalid_geometry'].includes(state) || height !== null;
  })) return null;
  const energy = row.energy_sensitivity;
  if (energy !== undefined) {
    if (!energy || (energy.status !== 'available' && energy.status !== 'unknown_terrain')) return null;
    const unknown = row.state.some((state) => state !== 'upper_above_profile' && state !== 'upper_below_profile');
    if (energy.status === 'unknown_terrain' && !unknown) return null;
    if (energy.status === 'available' && (unknown ||
        !Array.isArray(energy.gen_w) || energy.gen_w.length !== times.length ||
        !energy.gen_w.every((v) => typeof v === 'number' && Number.isFinite(v) && v >= 0) ||
        !Array.isArray(energy.soc) || energy.soc.length !== times.length ||
        !energy.soc.every((v) => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1) ||
        !Number.isFinite(energy.harvested_wh) || energy.harvested_wh < 0 ||
        !Number.isFinite(energy.min_soc) || energy.min_soc < 0 || energy.min_soc > 1)) return null;
  }
  return row;
}
