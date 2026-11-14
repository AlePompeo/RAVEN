// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { createRavenClient } from '../../shell/ravenApi';
import { fetchSolarTerrain, limbCounts, solarTerrainSegments, synchronizedSolarTerrain, type SolarTerrainResult } from './solarTerrain';

const result: SolarTerrainResult = {
  window: { start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, n_steps: 2 },
  series_time_unix: [100, 200],
  sites: [{ site_id: 'a', horizon_deg: [4, null], state: ['upper_below_profile', 'missing_dem'] }],
  assumptions: {
    dem_product: 'lola', dem_sha256: '', dem_label_sha256: '', lunar_frame: 'MOON_ME',
    ephemeris: { versions: {}, kernels: {} }, profile_length_m: 10000, profile_spacing_m: 20,
    observer_height_m: 0, sun_semidiameter_deg: 0.27, azimuth: '', sampling: '', limits: '', dem_policy: '',
  },
};

describe('terrain solar samples', () => {
  it('keeps unknown states separate when grouping the timeline', () => {
    expect(solarTerrainSegments(['upper_above_profile', 'upper_above_profile', 'missing_dem', 'upper_below_profile'])).toEqual([
      { state: 'upper_above_profile', length: 2 },
      { state: 'missing_dem', length: 1 },
      { state: 'upper_below_profile', length: 1 },
    ]);
  });

  it('only accepts matching site, instants and series lengths', () => {
    expect(synchronizedSolarTerrain(result, 'a', [100, 200])).toEqual(result.sites[0]);
    expect(synchronizedSolarTerrain(result, 'b', [100, 200])).toBeNull();
    expect(synchronizedSolarTerrain(result, 'a', [100, 201])).toBeNull();
    expect(synchronizedSolarTerrain(result, 'a', [100])).toBeNull();
    expect(synchronizedSolarTerrain({ ...result, sites: [{ ...result.sites[0]!, state: [] }] }, 'a', [100, 200])).toBeNull();
    expect(synchronizedSolarTerrain({ ...result, sites: [{ ...result.sites[0]!, horizon_deg: [4, 0] }] }, 'a', [100, 200])).toBeNull();
  });

  it('surfaces endpoint failures without substituting a result', async () => {
    const request = { site_ids: ['a'], start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, overrides: {} };
    const signal = new AbortController().signal;
    const f = vi.fn<typeof fetch>().mockResolvedValue(new Response('', { status: 422 }));
    expect(await fetchSolarTerrain(createRavenClient({ fetch: f }), request, signal)).toEqual({ ok: false, kind: 'invalid' });
  });

  it('only accepts a sensitivity result when it is synchronized and terrain is known', () => {
    const unknown = { ...result, sites: [{ ...result.sites[0]!, energy_sensitivity: { status: 'unknown_terrain' as const } }] };
    expect(synchronizedSolarTerrain(unknown, 'a', [100, 200])).not.toBeNull();
    const complete: SolarTerrainResult = {
      ...result,
      sites: [{
        site_id: 'a', horizon_deg: [4, 5], state: ['upper_below_profile', 'upper_above_profile'],
        energy_sensitivity: { status: 'available', gen_w: [0, 40], soc: [0.8, 0.9], harvested_wh: 40, min_soc: 0.8 },
      }],
    };
    expect(synchronizedSolarTerrain(complete, 'a', [100, 200])).not.toBeNull();
    const energy = complete.sites[0]!.energy_sensitivity!;
    if (energy.status !== 'available') throw new Error('test setup');
    expect(synchronizedSolarTerrain({
      ...complete, sites: [{ ...complete.sites[0]!, energy_sensitivity: { ...energy, soc: [0.8] } }],
    }, 'a', [100, 200])).toBeNull();
    expect(synchronizedSolarTerrain({
      ...result, sites: [{ ...result.sites[0]!, energy_sensitivity: energy }],
    }, 'a', [100, 200])).toBeNull();
  });

  it('counts the three limb criteria and rejects inconsistent rows', () => {
    const row = {
      site_id: 'a', horizon_deg: [1, 2, 3, null], state: ['upper_above_profile', 'upper_above_profile', 'upper_below_profile', 'missing_dem'],
      centre_above_profile: [true, false, false, null], lower_above_profile: [true, false, false, null],
    } as SolarTerrainResult['sites'][number];
    expect(limbCounts(row)).toEqual({ known: 3, upper: 2, centre: 1, lower: 1 });
    expect(limbCounts(result.sites[0]!)).toBeNull();
    expect(limbCounts({ ...row, lower_above_profile: [false, true, false, null] })).toBeNull();
    expect(limbCounts({ ...row, centre_above_profile: [true, false, true, null] })).toBeNull();
    expect(limbCounts({ ...row, centre_above_profile: [true, false, false, false] })).toBeNull();
  });
});
