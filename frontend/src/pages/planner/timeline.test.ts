// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { createRavenClient } from '../../shell/ravenApi';
import { compatibleStep, fetchTimeline, plannerDateBounds, plannerRequest, readSavedInput, readSavedPlanner, segments, synchronizedRfSamples, type PlannerInput } from './timeline';
import { customSites } from '../../shell/customSites';

const input: PlannerInput = {
  mode: 'sites',
  siteA: 'shackleton',
  siteB: 'de-gerlache',
  start: '2027-04-07T00:00',
  startB: '2027-05-07T00:00',
  days: 7,
  stepMin: 60,
};

describe('long periods get a compatible step', () => {
  it('raises the step only as far as the 1500 / 6000 sample caps require', () => {
    expect(compatibleStep(7, 60, 2)).toBe(60);
    expect(compatibleStep(7, 10, 2)).toBe(10); // 1008 samples
    expect(compatibleStep(29.53, 10, 2)).toBe(30); // 4252 at 10 min is over the cap
    expect(compatibleStep(365, 10, 2)).toBe(360); // 1460 samples, 2920 for two scenarios
    expect(compatibleStep(366, 10, 1)).toBe(360);
    expect(compatibleStep(365, 1440, 2)).toBe(1440);
    expect(compatibleStep(0, 60, 2)).toBeNull();
    expect(compatibleStep(400, 60, 2)).toBeNull(); // over the maximum duration
  });
});

describe('mission planner', () => {
  it('creates a shared-window request for both sites', () => {
    expect(plannerRequest(input, 20000, 10)).toEqual({
      first: {
        site_ids: ['shackleton', 'de-gerlache'],
        start_utc: '2027-04-07T00:00:00Z',
        days: 7,
        step_min: 60,
        overrides: {},
      },
      second: null,
    });
  });

  it('uses the same site, duration and resolution for two separate dates', () => {
    const req = plannerRequest({ ...input, mode: 'dates' }, 20000, 10, { array_area_m2: 2 });
    if (typeof req === 'string') throw new Error(req);
    expect(req.first.site_ids).toEqual(['shackleton']);
    expect(req.second).toMatchObject({
      site_ids: ['shackleton'], start_utc: '2027-05-07T00:00:00Z', days: 7, step_min: 60, overrides: { array_area_m2: 2 },
    });
    expect(plannerRequest({ ...input, mode: 'dates', startB: input.start }, 20000, 10)).toBe('planner.errorDates');
  });

  it('rejects duplicate sites, invalid dates and oversize or fractional steps', () => {
    expect(plannerRequest({ ...input, siteB: input.siteA }, 20000, 10)).toBe('planner.errorSites');
    expect(plannerRequest({ ...input, start: '2027-02-30T00:00' }, 20000, 10)).toBe('planner.errorStart');
    expect(plannerRequest({ ...input, stepMin: 10.1 }, 20000, 10)).toBe('planner.errorStep');
    expect(plannerRequest({ ...input, days: 30, stepMin: 10 }, 20000, 10)).toBe('planner.errorSize');
  });

  it('enforces kernel dates for both scenarios and the complete requested duration', () => {
    const range = { start_utc: '1972-01-01T00:00:00Z', end_utc: '2030-01-08T00:00:00Z' };
    const request = (patch: Partial<PlannerInput>) => plannerRequest({ ...input, ...patch }, 20000, 10, {}, [], range);
    expect(request({ start: '1971-12-31T23:59' })).toBe('planner.errorEphemerisRange');
    expect(request({ start: '1972-01-01T00:00' })).toHaveProperty('first');
    expect(request({ start: '2001-01-01T00:00' })).toHaveProperty('first');
    expect(request({ start: '2030-01-01T00:00' })).toHaveProperty('first');
    expect(request({ start: '2030-01-01T00:01' })).toBe('planner.errorEphemerisRange');
    expect(request({ mode: 'dates', startB: '1971-12-31T23:59' })).toBe('planner.errorEphemerisRange');
    expect(request({ mode: 'dates', startB: '2030-01-02T00:00' })).toBe('planner.errorEphemerisRange');
    expect(plannerDateBounds(range, 7)).toEqual({ min: '1972-01-01T00:00', max: '2030-01-01T00:00' });
    expect(plannerDateBounds({
      start_utc: '1972-01-01T00:00:00.100Z', end_utc: '2030-01-08T00:00:59.800Z',
    }, 7)).toEqual({ min: '1972-01-01T00:01', max: '2030-01-01T00:00' });
  });

  it('sends a custom site only if it is defined in the shared scenario', () => {
    const custom = { ...input, siteA: 'c-a' };
    customSites.set([]);
    expect(plannerRequest(custom, 20000, 10, {})).toBe('planner.customInvalid');
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -88, lon_deg_east: 15 }]);
    const req = plannerRequest(custom, 20000, 10, {});
    if (typeof req === 'string') throw new Error(req);
    // the request carries only the id: the client attaches the definition from the shared scenario
    expect(req.first.site_ids).toEqual(['c-a', input.siteB]);
    expect(req.first).not.toHaveProperty('custom_sites');
    customSites.set([]);
  });

  it('preserves actual sample transitions when constructing timeline segments', () => {
    expect(segments([true, true, false, true, true, true])).toEqual([
      { start: 0, length: 2, value: true },
      { start: 2, length: 1, value: false },
      { start: 3, length: 3, value: true },
    ]);
    expect(segments([])).toEqual([]);
  });

  it('only uses RF samples with the exact same instants and lengths', () => {
    const window_samples = {
      time_unix: [100, 160], geometric_visible: [true, false], link_ok: [true, false],
      margin_db: [0.1, -0.1], chosen_rate_bps: [100, 0],
    };
    expect(synchronizedRfSamples({ window_samples }, [100, 160])).toEqual(window_samples);
    expect(synchronizedRfSamples({ window_samples }, [100, 161])).toBeNull();
    expect(synchronizedRfSamples({ window_samples: { ...window_samples, link_ok: [true] } }, [100, 160])).toBeNull();
    expect(synchronizedRfSamples({ window_samples: { ...window_samples, margin_db: [NaN, 0] } }, [100, 160])).toBeNull();
    expect(synchronizedRfSamples(undefined, [100, 160])).toBeNull();
  });

  it('restores only a valid saved mission with known sites', () => {
    expect(readSavedInput(JSON.stringify(input), [input.siteA, input.siteB])).toEqual(input);
    expect(readSavedInput(JSON.stringify(input), [input.siteA])).toBeNull();
    expect(readSavedInput('{', [input.siteA, input.siteB])).toBeNull();
    expect(readSavedInput(JSON.stringify({ ...input, days: -1 }), [input.siteA, input.siteB])).toBeNull();
    expect(readSavedPlanner(JSON.stringify({ ...input, lesson: 5, siteView: 'B', decision: 'Luce', quiz: 'no' }), [input.siteA, input.siteB]))
      .toEqual({ input, lesson: 5, siteView: 'B', decision: 'Luce', quiz: 'no', mast: 2 });
    expect(readSavedPlanner(JSON.stringify({ ...input, lesson: 99, siteView: 'x', quiz: 'x' }), [input.siteA, input.siteB]))
      .toMatchObject({ lesson: 0, siteView: 'A', quiz: '' });
    expect(readSavedPlanner(JSON.stringify({ ...input, objectives: { priority: 'radio', minSunPercent: null, minRfPercent: 50 } }), [input.siteA, input.siteB]))
      .toMatchObject({ objectives: { priority: 'radio', minSunPercent: null, minRfPercent: 50 } });
  });

  it('surfaces server and network errors', async () => {
    const req = plannerRequest(input, 20000, 10);
    if (typeof req === 'string') throw new Error(req);
    const signal = new AbortController().signal;
    const invalid = vi.fn<typeof fetch>().mockResolvedValue(new Response('', { status: 422 }));
    expect(await fetchTimeline(createRavenClient({ fetch: invalid }), req.first, signal)).toMatchObject({ ok: false, kind: 'invalid', message: 'planner.errorInvalid' });
    const network = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'));
    expect(await fetchTimeline(createRavenClient({ fetch: network }), req.first, signal)).toMatchObject({ ok: false, kind: 'network', message: 'planner.errorNetwork' });
  });
});
