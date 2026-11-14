// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { validHorizonSamples, type HorizonSample } from './horizon';

describe('sampled horizon display', () => {
  it('excludes missing profiles rather than inventing points', () => {
    const samples: HorizonSample[] = [
      { azimuth_deg: 0, elevation_deg: 2, distance_m: 100, state: 'ok' },
      { azimuth_deg: 5, elevation_deg: null, distance_m: null, state: 'missing_dem' },
      { azimuth_deg: 10, elevation_deg: 5, distance_m: 200, state: 'ok' },
      { azimuth_deg: 15, elevation_deg: 4, distance_m: 200, state: 'ok' },
    ];
    expect(validHorizonSamples(samples)).toEqual([samples[0], samples[2], samples[3]]);
  });
});
