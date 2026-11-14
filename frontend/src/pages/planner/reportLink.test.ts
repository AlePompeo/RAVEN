// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { siteA } from './reportFixtures';
import { elevationMargin, formatCoordinate, linkHours, linkTerms, medianHorizon, polarPosition } from './reportLink';
import type { RavenEvaluation } from '../../shell/ravenApi';

const make = (el: (number | null)[], hor: (number | null)[], closes: (boolean | null)[], margin: (number | null)[]): RavenEvaluation => ({
  ...siteA, window: { ...siteA.window, step_min: 60 },
  steps: { ...siteA.steps!, earth_el_deg: el, earth_horizon_deg: hor, rf_closes: closes, margin_db: margin },
});

describe('link hours', () => {
  it('separates line of sight, closed link and link beyond the line of sight, and counts unknown apart', () => {
    const e = make([5, 5, -1, null, 5], [2, 6, -3, 0, 2], [true, false, true, true, null], [10, -2, 4, 5, null]);
    // steps: LOS+closes | no LOS (5<6) and no link | LOS? -1>-3 yes, closes | unknown geometry | LOS, unknown link
    expect(linkHours(e)).toEqual({ geometric: 3, available: 3, beyondLos: 0, unknown: 2, total: 5 });
    const beyond = make([-5, 5], [0, 2], [true, true], [3, 9]);
    expect(linkHours(beyond)).toMatchObject({ geometric: 1, available: 2, beyondLos: 1, unknown: 0 });
  });
  it('is null without steps', () => expect(linkHours({ ...siteA, steps: undefined })).toBeNull());
});

describe('elevation chart data', () => {
  it('keeps only points with both values and thins evenly', () => {
    const e = make([1, null, 3, 4], [0, 0, 0, 0], [true, true, true, true], [5, 6, null, 8]);
    expect(elevationMargin(e)).toEqual([{ el: 1, margin: 5 }, { el: 4, margin: 8 }]);
    const many = make(Array.from({ length: 1000 }, (_, i) => i), Array(1000).fill(0), Array(1000).fill(true), Array(1000).fill(1));
    expect(elevationMargin(many, 100)).toHaveLength(100);
  });
  it('median horizon and mean terms ignore unknown', () => {
    const e = make([1, 2, 3], [1, null, 3], [true, true, true], [4, null, 8]);
    expect(medianHorizon(e)).toBe(3);
    expect(linkTerms(e)).toMatchObject({ marginDb: 6, knownSteps: 2 });
    expect(medianHorizon(make([1], [null], [true], [1]))).toBeNull();
  });
});

describe('coordinates and polar map', () => {
  it('writes S/N and E/W', () => {
    expect(formatCoordinate(-85.5, 12)).toBe('85.50° S, 12.00° E');
    expect(formatCoordinate(0.7, 350)).toBe('0.70° N, 10.00° W');
  });
  it('places the south pole at the centre and rejects sites outside the map', () => {
    expect(polarPosition(-90, 0, -60)).toEqual({ x: 0, y: -0 });
    const p = polarPosition(-75, 90, -60)!;
    expect(p.x).toBeCloseTo(0.5, 6);
    expect(p.y).toBeCloseTo(0, 6);
    expect(polarPosition(-50, 0, -60)).toBeNull();
  });
});
