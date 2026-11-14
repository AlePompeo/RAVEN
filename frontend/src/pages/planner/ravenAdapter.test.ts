// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { RavenEvaluation, RavenParameters, RavenSites, RavenSteps } from '../../shell/ravenApi';
import {
  evaluateRequests, horizonFromRaven, metricsOf, missionEvaluateIn, missionFromRaven, plannerCatalog, rfFromRaven, seriesOf, solarFromRaven, timelineFromRaven, usedParameter,
} from './ravenAdapter';
import { missionRequest, validMission } from './mission';
import { synchronizedRfSamples } from './timeline';
import { synchronizedSolarTerrain } from './solarTerrain';

const fx = <T>(n: string): T => JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), `../../shell/fixtures/raven/${n}.json`), 'utf8')) as T;
const ev = fx<RavenEvaluation>('evaluate');
const steps = ev.steps as RavenSteps;

describe('the Planner timeline reads the terrain horizon of the single model', () => {
  it('resolves RF provenance from the full registry without fabricating metadata for runtime settings', () => {
    const reference = fx<RavenParameters>('parameters').parameters[0]!;
    const frequency = { ...reference, key: 'rf.frequency_ghz', scope: 'rf' };
    const aperture = { ...frequency, key: 'grazing.antenna_eta', scope: 'grazing', name: 'antenna_eta', default: .55, min: 0, max: 1 };
    const efficiency = { ...reference, key: 'lunar.cell_efficiency', name: 'cell_efficiency', default: .295 };
    const parameters = [aperture, { ...frequency, key: 'grazing.frequency_ghz', scope: 'grazing' }, efficiency, frequency];
    expect(usedParameter(parameters, 'rf', 'antenna_eta')).toEqual(aperture);
    expect(usedParameter(parameters, 'rf', 'frequency_ghz')).toEqual(parameters.find((p) => p.key === 'rf.frequency_ghz'));
    expect(usedParameter(parameters, 'energy', 'cell_efficiency')).toEqual(parameters.find((p) => p.key === 'lunar.cell_efficiency'));
    expect(usedParameter(parameters, 'rf', 'station')).toBeNull();
  });
  it('Sun and Earth are above the LOLA mask, not above a flat horizon', () => {
    // 2 deg above the flat horizon but 9 deg below the terrain: a flat horizon would say "up"
    const s: RavenSteps = { ...steps, sun_el_deg: [2, 12], sun_horizon_deg: [9, 9], lit: [false, true], earth_el_deg: [2, 2], earth_horizon_deg: [5, -3] };
    const series = seriesOf(s);
    expect(series.sun_up.slice(0, 2)).toEqual([false, true]);
    expect(series.earth_visible.slice(0, 2)).toEqual([false, true]);
  });
  it('an unknown step is never a yes: it stays false and is marked unknown', () => {
    const s: RavenSteps = { ...steps, lit: [null, true, true, true], rf_closes: [null, true, false, true], state: ['unknown', 'operational', 'operational', 'operational'] };
    const series = seriesOf(s);
    expect(series.sun_up[0]).toBe(false);
    expect(series.link_ok[0]).toBe(false);
    expect(series.known).toEqual([false, true, true, true]);
  });
  it('metrics are counts on the model columns (useful hours come from the model, not recomputed)', () => {
    const m = metricsOf(ev);
    expect(m.useful_hours).toBe(ev.metrics.useful_hours);
    expect(m.energy.min_soc).toBe(ev.metrics.min_soc);
    expect(m.link_fraction).toBe(steps.rf_closes.filter(Boolean).length / steps.rf_closes.length);
  });
  it('the timeline carries the model version and the single radio set used', () => {
    const t = timelineFromRaven([ev], null);
    expect(t.model_version).toBe(ev.model_version);
    expect(t.assumptions.link.required_margin_db).toBe(3);
    expect(t.assumptions.link['frequency_ghz']).toBe(8.425);
    expect(t.assumptions.link['station_gain_dbi']).toBe(68.29);
    expect(t.series_time_unix).toEqual(steps.time_unix);
  });
});

describe('radio, solar-terrain, mission and horizon views come from the same evaluation', () => {
  const covered = new Set([ev.site.id]);
  it('radio rows are synchronised with the timeline and unknown stays unknown', () => {
    const rf = rfFromRaven([ev], { station: 'dsn34', rate: 1e5 }, covered);
    const row = rf.sites[0];
    expect(row?.covered).toBe(true);
    if (row?.covered) {
      expect(synchronizedRfSamples(row, steps.time_unix)).not.toBeNull();
      expect(row.window_samples!.link_ok).toEqual(steps.rf_closes.map((x) => x === true));
      expect(row.window_samples!.margin_db).toEqual(steps.margin_db);
    }
    expect(rfFromRaven([ev], { station: 'dsn34', rate: 1e5 }, new Set()).sites[0]?.covered).toBe(false);
  });
  it('solar rows pass the strict synchronisation check and use the model disc fraction', () => {
    const s = solarFromRaven([ev]);
    const row = synchronizedSolarTerrain(s, ev.site.id, steps.time_unix);
    expect(row).not.toBeNull();
    expect(row?.disc_fraction).toEqual(steps.disc_fraction);
  });
  it('the mission result passes the structural check and keeps the model counts', () => {
    const req = missionRequest({ siteId: ev.site.id, start: ev.window.start_utc, days: 1, stepMin: 360, station: 'dsn34', rate: 1e5, gain: null, k: null, mast: null, energy: {} })!;
    const m = missionFromRaven(ev, req, []);
    expect(validMission(m, req)).toBe(true);
    expect(m.metrics.useful_hours).toBe(ev.metrics.useful_hours);
    expect(m.windows).toEqual(ev.windows?.useful);
    expect(m.model_version).toBe(ev.model_version);
  });
  it('horizon samples are measured directions only', () => {
    const h = fx<Parameters<typeof horizonFromRaven>[0]>('horizon');
    const out = horizonFromRaven(h);
    expect(out.samples).toHaveLength(h.elevation_deg.length);
    expect(out.samples[1]?.azimuth_deg).toBe(h.azimuth_step_deg);
    expect(out.samples.every((x) => x.state === 'ok' || x.elevation_deg === null)).toBe(true);
  });
});

describe('requests and catalogue', () => {
  const req = { site_ids: ['a'], start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, overrides: { array_area_m2: 2 } };
  it('maps the Planner request one evaluation per site with windows', () => {
    const r = evaluateRequests({ ...req, site_ids: ['a', 'b'] });
    expect(r.map((x) => x.site_id)).toEqual(['a', 'b']);
    expect(r[0]).toMatchObject({ include_steps: true, include_windows: true, energy_overrides: { array_area_m2: 2 }, days: 1, step_min: 60 });
  });
  it('radio values become rf_overrides and top-level parameters; the compensator k is sent only when it is not the default', () => {
    const [r] = evaluateRequests(req, { station: 'dsn18', rate: 3e5, gain: 20, mast: 5 });
    expect(r).toMatchObject({ station: 'dsn18', rate_bps: 3e5, rf_overrides: { tx_gain_dbi: 20 }, antenna_height_m: 5 });
    const input = { siteId: 'a', start: '2027-01-01T00:00:00Z', days: 1, stepMin: 60, station: 'dsn34' as const, rate: 1e5, gain: 15, mast: 2, energy: { battery_capacity_wh: 100 } };
    expect(JSON.stringify(missionEvaluateIn(missionRequest({ ...input, k: 2.33 })!))).not.toContain('compensator');
    expect(missionEvaluateIn(missionRequest({ ...input, k: 1.2 })!).rf_overrides).toMatchObject({ compensator_k: 1.2 });
    const [withK] = evaluateRequests(req, { station: 'dsn34', rate: 1e5, gain: null, mast: null, k: 0 });
    expect(withK!.rf_overrides).toEqual({ compensator_k: 0 }); // 0 is a real value, not "unset"
  });
  it('builds the catalogue from /api/raven/sites and /parameters (no legacy status/defaults)', () => {
    const params = fx<RavenParameters>('parameters');
    params.defaults['energy_orientations'] = ['horizontal', 'tilted', 'tracking'];
    const sites: RavenSites = {
      model_version: 'raven-core-1', disclaimer: 'x', ephemeris: { available: true },
      dem: { available: true, cached_tiles: 3, product: { id: 'p', coverage: 'c', coverage_north_limit_deg: -85, credit: '', url: '' } },
      sites: [{ ...ev.site, dem_covered: true }],
    };
    const c = plannerCatalog(sites, params);
    expect(c.sites[0]?.id).toBe(ev.site.id);
    expect(c.status.sites[0]?.dem_covered).toBe(true);
    expect(c.defaults.limits).toMatchObject({ days_max: 366, max_total_points: 6000, terrain_solar_max_steps_per_site: 1500 });
    expect(c.defaults.parameters.find((p) => p.key === 'orientation')?.allowed).toEqual(['horizontal', 'tilted', 'tracking']);
  });
});
