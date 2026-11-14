// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { pixelFromPolar, polarFromPixel } from './moonMap';

describe('south-polar map', () => {
  it('puts the pole at the centre and the limit latitude on the rim', () => {
    expect(pixelFromPolar(-90, 0, 400, 400, -60)).toEqual({ x: 200, y: 200 });
    const rim = pixelFromPolar(-60, 90, 400, 400, -60)!;
    expect(rim.x).toBeCloseTo(400, 6);
    expect(rim.y).toBeCloseTo(200, 6);
    expect(pixelFromPolar(-50, 0, 400, 400, -60)).toBeNull();
  });
  it('is the inverse of the projection, longitude clockwise from the top', () => {
    for (const [lat, lon] of [[-85.98, -1.67], [-75, 120], [-65, -170]] as const) {
      const p = pixelFromPolar(lat, lon, 840, 840, -60)!;
      const g = polarFromPixel(p.x, p.y, 840, 840, -60)!;
      expect(g.lat).toBeCloseTo(lat, 6);
      expect(g.lon).toBeCloseTo(lon, 6);
    }
    expect(polarFromPixel(0, 0, 400, 400, -60)).toBeNull();
  });
});
