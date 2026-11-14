// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { createRavenClient, type RavenEvaluation } from '../../shell/ravenApi';
import { dominantLimit, fetchMission, missionRequest, missionSegments, missionSteps, validMission, type MissionInput, type MissionResult } from './mission';
import { discSummary, type SolarTerrainResult } from './solarTerrain';

const input: MissionInput = {
  siteId: 'malapert-massif', start: '2027-01-01T00:00:00Z', days: 0.125, stepMin: 60,
  station: 'dsn34', rate: 1e5, gain: 15, k: 2.33, mast: 2, energy: { battery_capacity_wh: 100 },
};
const req = missionRequest(input)!;

function result(over: Partial<MissionResult['series']> = {}): MissionResult {
  const n = 3;
  return {
    series: {
      time_unix: [0, 3600, 7200], sun_el_deg: [1, 1, 1], disc_fraction: [1, 0.5, null],
      gen_w: [100, 50, null], soc: [1, 0.9, null], margin_db: [3, -1, null],
      dsn_visible: [true, true, true], link_usable: [true, false, null],
      state: ['operational', 'operational', 'unknown'], useful: [true, false, null],
      limiting: [null, 'link', null], ...over,
    },
    metrics: {
      n_steps: n, known_steps: 2, unknown_steps: 1, useful_hours: 1, useful_fraction: 1 / 3, unknown_hours: 1,
      state_hours: { operational: 2, comms_only: 0, survival: 0, dark: 0, unknown: 1 },
      limiting_fraction: { energy: 0, link: 1 / 3, visibility: 0, multiple: 0 },
      min_soc: 0.9, min_soc_scope: 'known steps only', time_to_first_blackout_h: null,
      sun_hours: 2, harvested_wh: 150, unmet_wh: 0,
    },
    inputs_state: { shadow: 'missing_dem', rf: 'ok', dsn: 'geometric_34m' },
    rate_bps: 1e5, station: 'dsn34', tx_power_w: 10,
    parameters: {
      energy: [], rf: [],
      observer_height: { key: 'observer_height_m', value: 2, unit: 'm', status: 'I', source: '' },
      dsn_min_elevation: { key: 'ground_station_min_elevation_deg', value: 6, unit: 'deg', status: 'V', source: '' },
    },
    declared_limits: ['x'],
  };
}

describe('coupled mission mapping', () => {
  it('builds a bounded request from the planner inputs', () => {
    expect(req).toMatchObject({ site_id: 'malapert-massif', step_min: 60, observer_height_m: 2, station: 'dsn34',
      rf_overrides: { tx_gain_dbi: 15, compensator_k: 2.33, antenna_height_m: 2 } });
    expect(missionSteps(0.125, 60)).toBe(3);
    expect(missionRequest({ ...input, days: 91 })).toBeNull();
    expect(missionRequest({ ...input, stepMin: 5 })).toBeNull();
    expect(missionRequest({ ...input, days: 90, stepMin: 60 })).toBeNull(); // 2160 > 1500 steps
    expect(missionRequest({ ...input, energy: undefined })).toBeNull();
    expect(missionRequest({ ...input, start: undefined })).toBeNull();
  });

  it('accepts consistent results and keeps unknown steps unknown', () => {
    const r = result();
    expect(validMission(r, req)).toBe(true);
    expect(missionSegments(r.series.state)).toEqual([{ state: 'operational', length: 2 }, { state: 'unknown', length: 1 }]);
    expect(dominantLimit(r)).toBe('link');
    // an unknown step that claims usefulness or a battery value is rejected
    expect(validMission(result({ useful: [true, false, true] }), req)).toBe(false);
    expect(validMission(result({ soc: [1, 0.9, 0.5] }), req)).toBe(false);
    // useful requires the operational state and a usable link
    expect(validMission(result({ state: ['survival', 'operational', 'unknown'] }), req)).toBe(false);
    expect(validMission(result({ soc: [1.2, 0.9, null] }), req)).toBe(false);
    expect(validMission(result({ gen_w: [100, 50] }), req)).toBe(false);
  });

  it('maps HTTP failures and invalid bodies', async () => {
    const ok = (body: unknown, status = 200) => createRavenClient({ fetch: (async () => new Response(JSON.stringify(body), { status })) as typeof fetch });
    const signal = new AbortController().signal;
    const here = dirname(fileURLToPath(import.meta.url));
    const ev = JSON.parse(readFileSync(resolve(here, '../../shell/fixtures/raven/evaluate.json'), 'utf8')) as RavenEvaluation;
    const real = missionRequest({ ...input, days: 1, stepMin: 360 })!; // the fixture: 4 steps of 6 h
    const got = await fetchMission(ok(ev), real, signal);
    expect(got).toMatchObject({ ok: true });
    if (got.ok) {
      expect(got.data.model_version).toBe(ev.model_version);
      expect(got.data.metrics.useful_hours).toBe(ev.metrics.useful_hours);
      expect(got.data.series.useful).toEqual(ev.steps!.useful);
    }
    expect(await fetchMission(ok({ detail: 'x' }, 422), req, signal)).toEqual({ ok: false, kind: 'invalid' });
    expect(await fetchMission(ok({ detail: 'x' }, 503), req, signal)).toEqual({ ok: false, kind: 'unavailable' });
    expect(await fetchMission(ok({ series: {} }), req, signal)).toEqual({ ok: false, kind: 'server' });
    const fail = createRavenClient({ fetch: (async () => { throw new Error('down'); }) as typeof fetch });
    expect(await fetchMission(fail, req, signal)).toEqual({ ok: false, kind: 'network' });
  });
});

type Row = SolarTerrainResult['sites'][number];
const solarRow = (disc: (number | null)[]): Row => ({
  site_id: 's', horizon_deg: disc.map(() => 1), state: disc.map((v) => (v === null ? 'missing_dem' : v > 0 ? 'upper_above_profile' : 'upper_below_profile')),
  disc_fraction: disc,
  mask: { n_azimuths: 1440, observer_height_m: 2, complete_azimuth_fraction: 1, far_terrain_dominant_fraction: 0.5, coverage_limit: '', cache: 'memory' },
});

describe('horizon-mask shadows in the planner', () => {
  it('summarises the visible disc over known samples only', () => {
    expect(discSummary(solarRow([1, 0.5, null]))).toEqual({ mean: 0.75, known: 2, height: 2 });
    expect(discSummary(solarRow([null, null]))).toBeNull();
    expect(discSummary({ ...solarRow([1]), mask: null })).toBeNull();
    expect(discSummary(solarRow([1.5]))).toBeNull();
  });
});
