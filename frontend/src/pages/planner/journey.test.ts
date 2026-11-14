// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation, RavenSites } from '../../shell/ravenApi';
import type { ParamRow } from '../compare/lunar';
import { customSites } from '../../shell/customSites';
import { useCatalog } from '../../i18n/i18n.svelte';
import enPages from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import { JOURNEY_STEPS, earthVisibility, firstChange, fraction, journeyIssue, journeyRequests, missionBaseKey, missionShiftBaseline, newDraft, readDraft, readRun, requestKey, shiftedStartUtc, validEvaluations } from './journey';
import ParameterControl from './ParameterControl.svelte';
import { illustrativeReliability } from './reliability';

const ev = evaluationFixture as RavenEvaluation;
const sites: RavenSites = {
  model_version: ev.model_version, disclaimer: '', ephemeris: { available: true },
  dem: { available: true, cached_tiles: 1, product: { id: 'lola', coverage: '', coverage_north_limit_deg: -85, credit: '', url: '' } },
  sites: [{ ...ev.site, dem_covered: true }, { ...ev.site, id: 'haworth', dem_covered: true }],
};
const rows: ParamRow[] = [
  { key: 'array_area_m2', group: 'energy', value: 1, min: .01, max: 100 },
  { key: 'cell_efficiency', group: 'energy', value: .295, min: .05, max: .5 },
  { key: 'orientation', group: 'energy', value: 'horizontal', allowed: ['horizontal', 'tilted', 'tracking'] },
  { key: 'tilt_deg', group: 'energy', value: 0, min: 0, max: 90 },
  { key: 'tilt_azimuth_deg', group: 'energy', value: 0, min: 0, max: 360 },
].map((row) => ({ ...row, group: 'energy', unit: '-', status: 'I', source: 'illustrative', note: '' }));
const ids = sites.sites.map((s) => s.id);
const makeDraft = () => {
  const d = newDraft(rows, ids)!;
  d.input.start = '2027-01-01T00:00';
  d.input.days = 1; d.input.stepMin = 360;
  return d;
};

afterEach(() => { customSites.set([]); cleanup(); useCatalog('it', itCatalog, enPages); });

describe('planner journey', () => {
  it('invalidates physical calculations only when additional thermal demand changes, not when fault assumptions change', () => {
    const energyRows: ParamRow[] = [...rows, ...['survival_load_w', 'active_load_w'].map((key, i): ParamRow => ({
      key, value: i ? 50 : 10, group: 'energy', min: 0, max: 1000, unit: 'W', status: 'I', source: 'test', note: '',
    }))];
    const d = makeDraft();
    d.planning!.reliability = illustrativeReliability('Synthetic');
    const before = requestKey(journeyRequests(d, energyRows)!);
    d.planning!.reliability.components[0]!.upset_rate_per_hour = 0.1;
    expect(requestKey(journeyRequests(d, energyRows)!)).toBe(before);
    d.planning!.reliability.apply_thermal_load = true;
    const after = journeyRequests(d, energyRows)!;
    expect(requestKey(after)).not.toBe(before);
    for (const q of after) expect(q.energy_overrides).toMatchObject({ survival_load_w: 12, active_load_w: 52 });
  });
  it('has a dedicated reliability step right after energy, whose issue is not an energy issue', () => {
    expect(JOURNEY_STEPS.slice(3, 6)).toEqual(['energy', 'reliability', 'radio']);
    const d = makeDraft();
    d.planning!.reliability = illustrativeReliability('Synthetic');
    expect(journeyIssue(d, 3, ids, rows)).toBeNull();
    expect(journeyIssue(d, 5, ids, rows)).toBeNull();
  });
  it('uses the same panel and radio inputs in both scenarios, including k and custom coordinates', () => {
    const d = makeDraft();
    d.radio.k = 1.7; d.radio.mast = 5; d.radio.gain = 22;
    d.panel.array_area_m2 = 2;
    customSites.set([{ id: 'c-ridge', name: 'Ridge', lat_deg: -88, lon_deg_east: 42 }]);
    d.input.siteB = 'c-ridge';
    const reqs = journeyRequests(d, rows)!;
    expect(reqs).toHaveLength(2);
    for (const q of reqs) {
      expect(q).toMatchObject({ antenna_height_m: 5, rf_overrides: { compensator_k: 1.7, tx_gain_dbi: 22 }, energy_overrides: { array_area_m2: 2 } });
    }
    expect(reqs[1]!.custom_site).toMatchObject({ id: 'c-ridge', lat_deg: -88, lon_deg_east: 42 });
    const previous = requestKey(reqs);
    customSites.set([{ id: 'c-ridge', name: 'Ridge', lat_deg: -87, lon_deg_east: 42 }]);
    expect(requestKey(journeyRequests(d, rows)!)).not.toBe(previous);
  });

  it('sends a selected mission offset and validates results against the shifted engine window', () => {
    const d = makeDraft();
    const requests = journeyRequests(d, rows, undefined, undefined, 28)!;
    const baselineRequests = journeyRequests(d, rows)!;
    expect(missionBaseKey(requests)).toBe(missionBaseKey(baselineRequests));
    expect(requests[0]).toMatchObject({ start_utc: '2027-01-01T00:00:00Z', mission_shift_days: 28 });
    const start = shiftedStartUtc(requests[0]!.start_utc, 28)!;
    const shifted = structuredClone(ev);
    shifted.base_start_utc = requests[0]!.start_utc;
    shifted.mission_shift_days = 28;
    shifted.window.start_utc = start;
    shifted.steps!.time_unix = shifted.steps!.time_unix.map((_, i) => Date.parse(start) / 1000 + i * shifted.window.step_min * 60);
    const shiftedSecond = structuredClone(shifted);
    shiftedSecond.site.id = requests[1]!.site_id;
    expect(validEvaluations([shifted, shiftedSecond], requests)).toBe(true);
    shifted.mission_shift_days = 7;
    expect(validEvaluations([shifted, shiftedSecond], requests)).toBe(false);
    expect(missionShiftBaseline([ev])[0]).toMatchObject({ site_id: ev.site.id, start_utc: ev.window.start_utc });

    const shiftedResults = requests.map((request) => {
      const result = structuredClone(ev);
      const start = shiftedStartUtc(request.start_utc, 28)!;
      result.site.id = request.site_id;
      result.base_start_utc = request.start_utc;
      result.mission_shift_days = 28;
      result.window.start_utc = start;
      result.steps!.time_unix = result.steps!.time_unix.map((_, i) => Date.parse(start) / 1000 + i * result.window.step_min * 60);
      return result;
    });
    const baselineResults = baselineRequests.map((request) => ({ ...structuredClone(ev), site: { ...ev.site, id: request.site_id } }));
    const run = { key: requestKey(requests), createdAt: '2026-11-06T00:00:00Z', config: d, requests, evaluations: shiftedResults,
      missionShiftDays: 28 as const, baseline: missionShiftBaseline(baselineResults), baselineKey: missionBaseKey(baselineRequests) };
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256)?.baseline).toEqual(run.baseline);
  });

  it('uses one site and two UTC windows for date comparison; rejects invalid and oversized inputs', () => {
    const d = makeDraft();
    d.input.mode = 'dates';
    const reqs = journeyRequests(d, rows)!;
    expect(reqs.map((q) => q.site_id)).toEqual([d.input.siteA, d.input.siteA]);
    expect(reqs[1]!.start_utc).toBe('2027-05-07T00:00:00Z');
    d.input.startB = d.input.start;
    expect(journeyIssue(d, 2, ids, rows)).toBe('planner.errorDates');
    expect(journeyRequests(d, rows)).toBeNull();
    d.input.mode = 'sites'; d.input.days = 366; d.input.stepMin = 10;
    expect(journeyIssue(d, 2, ids, rows)).toBe('planner.errorSize');
    d.panel.cell_efficiency = null;
    expect(journeyIssue(d, 3, ids, rows)).toBe('planner.panelInvalid');
  });

  it('restores a matching run but rejects mismatched sampling, missing series and registry changes', () => {
    const d = makeDraft();
    const requests = journeyRequests(d, rows)!;
    const evaluations = requests.map((q) => ({ ...structuredClone(ev), site: { ...ev.site, id: q.site_id } }));
    expect(validEvaluations(evaluations, requests)).toBe(true);
    const run = { key: requestKey(requests), createdAt: '2026-11-06T00:00:00Z', config: d, requests, evaluations };
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256)).not.toBeNull();
    expect(readRun(JSON.stringify(run), rows, ids, 'different-registry')).toBeNull();
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256, 'new-model')).toBeNull();
    evaluations[0]!.steps!.soc.pop();
    expect(validEvaluations(evaluations, requests)).toBe(false);
    expect(readDraft(JSON.stringify({ ...d, radio: { ...d.radio, gain: 'invalid' } }), rows, ids)).toBeNull();
    expect(readDraft('{broken', rows, ids)).toBeNull();
  });

  it('preserves unknowns in fractions, horizon visibility and next-event detection', () => {
    expect(fraction([true, null, false])).toBeNull();
    expect(fraction([true, false])).toBe(.5);
    expect(firstChange([true, null, false], 0)).toBeNull();
    expect(firstChange([true, true, false], 0)).toBe(2);
    const e = structuredClone(ev);
    e.steps!.earth_horizon_deg[0] = null;
    expect(earthVisibility(e)[0]).toBeNull();
  });

  it('restores custom coordinates from the calculation rather than the current global sites', () => {
    const d = makeDraft();
    const definition = { id: 'c-ridge', name: 'Ridge', lat_deg: -88, lon_deg_east: 42 };
    customSites.set([definition]);
    d.input.siteB = definition.id;
    const requests = journeyRequests(d, rows)!;
    const evaluations = requests.map((q) => ({ ...structuredClone(ev),
      site: { ...ev.site, id: q.site_id, ...(q.custom_site ? q.custom_site : {}) } }));
    const run = { key: requestKey(requests), createdAt: '2026-11-08T00:00:00Z', config: d, requests, evaluations };
    customSites.set([{ ...definition, lat_deg: -87 }]);
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256)?.requests[1]?.custom_site?.lat_deg).toBe(-88);
    customSites.set([]);
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256)).not.toBeNull();
    evaluations[1]!.site.lat_deg = -87;
    expect(readRun(JSON.stringify(run), rows, ids, ev.registry_sha256)).toBeNull();
  });

  it('accepts genuinely unknown energy instead of inventing a zero total', () => {
    const requests = journeyRequests(makeDraft(), rows)!;
    const evaluations = requests.map((q) => ({ ...structuredClone(ev), site: { ...ev.site, id: q.site_id } }));
    for (const e of evaluations) {
      e.metrics.harvested_wh = null; e.metrics.unmet_wh = null; e.metrics.min_soc = null;
      e.metrics.unknown_steps = 4; e.metrics.known_steps = 0; e.metrics.unknown_hours = 24;
      e.steps!.soc.fill(null); e.steps!.state.fill('unknown');
    }
    expect(validEvaluations(evaluations, requests)).toBe(true);
    evaluations[0]!.steps!.state[0] = 'fabricated-state';
    expect(validEvaluations(evaluations, requests)).toBe(false);
  });

  it('rejects malformed chosen-rate series before restoring or charting a run', () => {
    const requests = journeyRequests(makeDraft(), rows)!;
    const evaluations = requests.map((q) => ({ ...structuredClone(ev), site: { ...ev.site, id: q.site_id } }));
    evaluations[0]!.steps!.chosen_rate_bps = [100000];
    expect(validEvaluations(evaluations, requests)).toBe(false);
    evaluations[0]!.steps!.chosen_rate_bps = evaluations[0]!.steps!.time_unix.map(() => null);
    expect(validEvaluations(evaluations, requests)).toBe(true);
    evaluations[0]!.steps!.chosen_rate_bps[0] = -1;
    expect(validEvaluations(evaluations, requests)).toBe(false);
  });

  it('does not silently clamp an out-of-range numeric input', async () => {
    useCatalog('en', {}, enPages);
    render(ParameterControl, { id: 'power', label: 'Power', value: 5, min: 0, max: 10, unit: 'W' });
    const field = screen.getByRole('spinbutton', { name: 'Power' });
    await fireEvent.input(field, { target: { value: '12' } });
    expect((field as HTMLInputElement).value).toBe('12');
    expect(screen.getByRole('alert').textContent).toContain('between 0 and 10');
    await fireEvent.input(field, { target: { value: '' } });
    expect(field.getAttribute('aria-invalid')).toBe('true');
  });
});
