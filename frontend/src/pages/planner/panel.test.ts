// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import type { ParamRow } from '../compare/lunar';
import { panelDefaults, panelOverrides, readPanel } from './panel';

const row = (key: string, value: number | string, min?: number, max?: number, allowed?: string[]): ParamRow =>
  ({ key, group: 'energy', value, unit: '', min, max, allowed, status: 'I', source: '', note: '' });
const rows = [
  row('array_area_m2', 1, 0.01, 100),
  row('cell_efficiency', 0.295, 0.05, 0.5),
  row('orientation', 'horizontal', undefined, undefined, ['horizontal', 'tilted', 'tracking']),
  row('tilt_deg', 0, 0, 90),
  row('tilt_azimuth_deg', 0, 0, 360),
];

describe('solar panel parameters', () => {
  it('uses backend defaults and applies valid changes as request overrides', () => {
    const panel = panelDefaults(rows);
    expect(panel).not.toBeNull();
    expect(panelOverrides({ ...panel!, array_area_m2: 2, orientation: 'tilted', tilt_deg: 30 }, rows))
      .toEqual({ array_area_m2: 2, orientation: 'tilted', tilt_deg: 30 });
    expect(panelOverrides({ ...panel!, tilt_deg: null }, rows)).toEqual({});
  });

  it('rejects invalid values and unavailable bounds rather than guessing', () => {
    const panel = panelDefaults(rows)!;
    expect(panelOverrides({ ...panel, cell_efficiency: 0.9 }, rows)).toBeNull();
    expect(panelOverrides({ ...panel, orientation: 'tilted', tilt_deg: null }, rows)).toBeNull();
    expect(readPanel({ ...panel, orientation: 'unsupported' }, rows)).toBeNull();
    expect(panelDefaults(rows.filter((r) => r.key !== 'array_area_m2'))).toBeNull();
  });
});
