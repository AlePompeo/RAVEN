// SPDX-License-Identifier: Apache-2.0
import { customSites } from '../../shell/customSites';
import { afterEach, describe, expect, it } from 'vitest';
import type { ParamRow } from '../compare/lunar';
import { readLibrary, restoreMission, writeLibrary } from './library';

const parameters = [
  { key: 'array_area_m2', group: 'energy', value: 1, min: 0.01, max: 100 },
  { key: 'cell_efficiency', group: 'energy', value: 0.295, min: 0.05, max: 0.5 },
  { key: 'orientation', group: 'energy', value: 'horizontal', allowed: ['horizontal', 'tilted'] },
] as ParamRow[];
const mission = {
  planner: {
    mode: 'sites', siteA: 'c-a', siteB: 'shackleton', start: '2027-04-07T00:00',
    startB: '2027-05-07T00:00', days: 7, stepMin: 60, mast: 2,
    panel: { array_area_m2: 1, cell_efficiency: 0.295, orientation: 'horizontal', tilt_deg: 0, tilt_azimuth_deg: 0 },
    objectives: { priority: 'balanced', minSunPercent: null, minRfPercent: null },
    setup: { name: 'Test', kind: 'site-study', path: 'guided' },
  },
  radio: { station: 'dsn34', gain: 15, rate: 100000, k: 2.33, mast: 2 },
  selectedTime: null,
};

describe('saved missions', () => {
  afterEach(() => customSites.set([]));
  it('rejects a damaged library or unavailable storage without overwriting it', () => {
    expect(readLibrary({ getItem: () => '{' })).toEqual({ ok: false });
    expect(readLibrary({ getItem: () => { throw new Error('blocked'); } })).toEqual({ ok: false });
    expect(writeLibrary({ setItem: () => { throw new Error('quota'); } }, [])).toBe(false);
  });

  it('does not overwrite a readable library with an oversized dossier', () => {
    let stored = JSON.stringify({ version: 1, entries: [] });
    const storage = {
      getItem: () => stored,
      setItem: (_key: string, value: string) => { stored = value; },
    };
    expect(writeLibrary(storage, [{
      id: '1', name: 'Large dossier', savedAt: '2027-04-07T00:00:00Z',
      config: { evidence: 'x'.repeat(200_000) },
    }])).toBe(false);
    expect(readLibrary(storage)).toEqual({ ok: true, entries: [] });
  });

  it('validates sites, coordinates, radio and current panel limits on reopen', () => {
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -88, lon_deg_east: 12 }]);
    const ids = ['c-a', 'shackleton'];
    expect(restoreMission(mission, ids, parameters)?.planner.input.siteA).toBe('c-a');
    expect(restoreMission(mission, ['shackleton'], parameters)).toBeNull();
    expect(restoreMission({ ...mission, radio: { ...mission.radio, mast: 3 } }, ids, parameters)).toBeNull();
    expect(restoreMission(mission, ids, [])).toBeNull();
  });

  it('validates saved custom definitions before changing the shared session', () => {
    customSites.set([]);
    const definitions = [{ id: 'c-a', name: 'A', lat_deg: -88, lon_deg_east: 12 }];
    const ids = ['c-a', 'shackleton'];
    expect(restoreMission(mission, ids, parameters)).toBeNull();
    expect(restoreMission(mission, ids, parameters, definitions)?.planner.input.siteA).toBe('c-a');
    expect(customSites.get()).toEqual([]);
  });
});
