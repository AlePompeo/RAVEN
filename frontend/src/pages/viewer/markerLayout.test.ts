// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { BODIES } from '../../viewports/bodies/registry';
import { centerOn, defaultFrame, projectLatLon } from '../../viewports/scene';
import { MIN_MARKER_DISTANCE, thinMarkers } from './markerLayout';

describe('thinMarkers', () => {
  const m = (id: string, x: number, y: number) => ({ id, x, y });

  it('tiene tutti i marcatori lontani', () => {
    const a = [m('a', 0, 0), m('b', 100, 0), m('c', 0, 100)];
    expect(thinMarkers(a, null)).toEqual(a);
  });

  it('di un gruppo vicino resta il primo, nell ordine originale', () => {
    const a = [m('a', 0, 0), m('b', 10, 5), m('c', 200, 0)];
    expect(thinMarkers(a, null).map((x) => x.id)).toEqual(['a', 'c']);
  });

  it('il selezionato ha la precedenza e l ordine resta quello originale', () => {
    const a = [m('a', 0, 0), m('b', 10, 5), m('c', 200, 0)];
    expect(thinMarkers(a, 'b').map((x) => x.id)).toEqual(['b', 'c']);
  });

  it('la soglia e inclusiva e vuoto resta vuoto', () => {
    expect(thinMarkers([m('a', 0, 0), m('b', MIN_MARKER_DISTANCE, 0)], null)).toHaveLength(2);
    expect(thinMarkers([], null)).toEqual([]);
  });

  it('sui siti polari reali nessuna coppia tenuta si sovrappone, con la vista centrata su ciascuno', () => {
    const polar = BODIES.moon.places.filter((p) => p.siteId);
    const f = defaultFrame(1000, 700);
    for (const c of polar) {
      const v = centerOn(c.lat, c.lon);
      const vis = polar
        .map((p) => ({ id: p.id, ...projectLatLon(p.lat, p.lon, v, f) }))
        .filter((p) => p.visible);
      const kept = thinMarkers(vis, c.id);
      expect(kept.some((k) => k.id === c.id)).toBe(true);
      for (const a of kept) for (const b of kept) if (a !== b) expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(MIN_MARKER_DISTANCE);
    }
  });
});
