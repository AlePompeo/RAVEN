// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import {
  earthAngleText,
  fetchSnapshot,
  fsplDeltaText,
  highlightedComplex,
  localDirToBody,
  moonSeenText,
  parseSnapshot,
  placeState,
  SnapshotClient,
  SnapshotError,
  STATE_LABEL,
  wrapLon,
  type Snapshot,
} from './snapshot';
import { latLonToBody } from '../../viewports/scene';

const site = (over: Record<string, unknown> = {}) => ({
  id: 'haworth',
  name: 'Haworth',
  lat_deg: -87.45,
  lon_deg_east: -5.17,
  dem_covered: true,
  earth_az_deg: 12.5,
  earth_el_deg: 0.9,
  earth_range_km: 381000.4,
  fspl_delta_db: -0.07,
  state: 'transition',
  margin_db: 6.86,
  ridge_el_deg: 1.2,
  ...over,
});
const complex = (name: string, el: number, sees: boolean) => ({
  complex: name,
  lat_deg: 40,
  lon_deg_east: 355.7,
  moon_az_deg: 100,
  moon_el_deg: el,
  sees_moon: sees,
  antennas: [
    { id: 'dsn34', name: 'DSS-54', diameter_m: 34, coordinates_verified: true },
    { id: 'dsn18', name: 'stazione 18 m (ipotesi)', diameter_m: 18, coordinates_verified: false },
    { id: 'bogus', name: 'x', diameter_m: 1 },
  ],
});
export const RAW = {
  t_utc: '2027-04-07T00:00:00Z',
  rate_bps: 10000,
  station: 'dsn34',
  reference_range_km: 384400,
  earth_moon_range_km: 381719.5,
  fspl_delta_db: -0.061,
  sites: [
    site(),
    site({ id: 'apollo11', name: 'Apollo 11', lat_deg: 0.67, dem_covered: false, state: 'out_of_coverage', margin_db: null, ridge_el_deg: null }),
  ],
  dsn: {
    min_elevation_deg: 6,
    source: { document: 'DSN 810-005 Module 301 Rev. P, Table 5', url: 'https://example.invalid/x' },
    complexes: [complex('Goldstone', -17.2, false), complex('Madrid', 34, true)],
    best_complex: 'Madrid',
    sees_moon: ['Madrid'],
  },
  limits: ['Copertura DEM: latitudine <= -85 gradi.'],
};
const snap = (): Snapshot => parseSnapshot(structuredClone(RAW));

describe('parseSnapshot', () => {
  it('parses sites, complexes and wraps DSN longitudes to [-180, 180)', () => {
    const s = snap();
    expect(s.sites).toHaveLength(2);
    expect(s.sites[1]).toMatchObject({ state: 'out_of_coverage', marginDb: null, ridgeEl: null, demCovered: false });
    expect(s.complexes[1]!.lon).toBeCloseTo(-4.3, 5);
    expect(s.complexes[1]!.antennas.map((a) => a.id)).toEqual(['dsn34', 'dsn18']); // unknown antenna ignored
    expect(s.complexes[1]!.antennas[1]!.verified).toBe(false);
    expect(s.source.document).toContain('Table 5');
  });

  it('accepts the unknown state of the single model (far terrain outside the model): margin stays unknown', () => {
    const s = parseSnapshot({ ...RAW, sites: [site({ state: 'unknown', margin_db: null, ridge_el_deg: null })] });
    expect(s.sites[0]!.state).toBe('unknown');
    expect(s.sites[0]!.marginDb).toBeNull();
  });

  it.each([
    ['not an object', 42],
    ['no sites', { ...RAW, sites: undefined }],
    ['unknown state', { ...RAW, sites: [site({ state: 'weird' })] }],
    ['non-finite az', { ...RAW, sites: [site({ earth_az_deg: null })] }],
    ['string margin', { ...RAW, sites: [site({ margin_db: '3' })] }],
    ['no range', { ...RAW, earth_moon_range_km: undefined }],
    ['bad complex', { ...RAW, dsn: { ...RAW.dsn, complexes: [{ complex: 'x' }] } }],
  ])('rejects %s', (_n, json) => {
    expect(() => parseSnapshot(json)).toThrow(SnapshotError);
  });
});

describe('texts and mapping', () => {
  it('writes the Earth angle with an Italian decimal comma', () => {
    expect(earthAngleText(0.9)).toBe('Terra a 0,9° sull’orizzonte');
    expect(earthAngleText(1.04)).toBe('Terra a 1,0° sull’orizzonte');
    expect(earthAngleText(-1.26)).toBe('Terra a 1,3° sotto l’orizzonte');
  });

  it('writes the free-space-loss delta with its true sign', () => {
    expect(fsplDeltaText(-0.49)).toBe('−0,49 dB');
    expect(fsplDeltaText(0.461)).toBe('+0,46 dB');
    expect(fsplDeltaText(0)).toBe('0,00 dB');
  });

  it('maps each link state to a text label (colour is never the only cue)', () => {
    expect(STATE_LABEL).toEqual({
      open: 'aperto',
      transition: 'transizione',
      blocked: 'bloccato',
      out_of_coverage: 'fuori copertura DEM',
      unavailable: 'dati DEM non disponibili',
      needs_download: 'terreno da scaricare',
      unknown: 'sconosciuto',
    });
    const s = snap();
    expect(placeState('haworth', -87.45, s)).toMatchObject({ state: 'transition', label: 'transizione' });
    expect(placeState('apollo11', 0.67, s)).toMatchObject({ state: 'out_of_coverage', label: 'fuori copertura DEM' });
    // luogo fuori dal registro dell'analisi e fuori copertura: mai uno stato inventato
    expect(placeState(undefined, -45, s)).toMatchObject({ state: 'out_of_coverage', site: null });
    expect(placeState('haworth', -87.45, null)).toMatchObject({ state: 'pending', label: 'in calcolo' });
    // senza istantanea nulla e' noto: un sito a nord di -85 gradi non e' "fuori copertura" finche' il servizio non risponde
    expect(placeState('apollo11', 0.67, null)).toMatchObject({ state: 'pending', label: 'in calcolo' });
  });

  it('highlights the complex that sees the Moon, none when nobody does', () => {
    const s = snap();
    expect(highlightedComplex(s)).toBe('Madrid');
    expect(highlightedComplex({ ...s, bestComplex: null })).toBeNull();
    expect(highlightedComplex({ ...s, bestComplex: 'Atlantide' })).toBeNull();
    expect(moonSeenText(s.complexes[1]!, 6)).toContain('Luna a 34° sull’orizzonte');
    expect(moonSeenText(s.complexes[0]!, 6)).toContain('sotto l’orizzonte');
  });

  it('wraps longitudes', () => {
    expect(wrapLon(243.1)).toBeCloseTo(-116.9, 5);
    expect(wrapLon(180)).toBe(-180);
    expect(wrapLon(-5)).toBe(-5);
  });
});

describe('localDirToBody', () => {
  it('zenith is the surface normal; horizon directions are tangent', () => {
    const up = localDirToBody(-87, 30, 0, 90);
    const n = latLonToBody(-87, 30);
    up.forEach((c, i) => expect(c).toBeCloseTo(n[i]!, 9));
    const h = localDirToBody(-87, 30, 123, 0);
    expect(h[0] * n[0] + h[1] * n[1] + h[2] * n[2]).toBeCloseTo(0, 9);
    expect(Math.hypot(...h)).toBeCloseTo(1, 9);
  });
  it('at the south pole azimuth 0 (north) points away from the pole along the meridian', () => {
    const d = localDirToBody(-89.999, 0, 0, 0);
    expect(d[1]).toBeGreaterThan(0); // towards the north pole axis direction (up the +y)
  });
});

describe('SnapshotClient', () => {
  function setup() {
    let t = 0;
    const timers: { at: number; fn: () => void; id: number }[] = [];
    let nextId = 1;
    const sched = {
      now: () => t,
      setTimeout: (fn: () => void, ms: number) => {
        const id = nextId++;
        timers.push({ at: t + ms, fn, id });
        return id;
      },
      clearTimeout: (h: unknown) => {
        const i = timers.findIndex((x) => x.id === h);
        if (i >= 0) timers.splice(i, 1);
      },
    };
    const advance = (ms: number) => {
      t += ms;
      for (;;) {
        const due = timers.filter((x) => x.at <= t).sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        timers.splice(timers.indexOf(due), 1);
        due.fn();
      }
    };
    const calls: { ms: number; signal: AbortSignal; resolve: (s: Snapshot) => void; reject: (e: unknown) => void }[] = [];
    const fetcher = vi.fn(
      (ms: number, _r: number, _s: string, signal: AbortSignal) =>
        new Promise<Snapshot>((resolve, reject) => {
          calls.push({ ms, signal, resolve, reject });
        }),
    );
    const got: number[] = [];
    const errors: string[] = [];
    const client = new SnapshotClient({
      fetcher,
      scheduler: sched,
      onSnapshot: (_s, ms) => got.push(ms),
      onError: (e) => errors.push(e.kind),
    });
    return { client, advance, calls, fetcher, got, errors };
  }
  const flush = () => new Promise((r) => setTimeout(r, 0));

  it('limits accelerated play to about one call per second and keeps the last value', async () => {
    const h = setup();
    for (let i = 0; i < 40; i++) {
      h.client.request(1_800_000_000_000 + i * 3_600_000, 1e4, 'dsn34'); // 40 ticks at 250 ms = 10 s
      h.advance(250);
    }
    h.advance(1000);
    expect(h.fetcher).toHaveBeenCalledTimes(1);
    expect(h.calls[0]!.signal.aborted).toBe(false);
    h.calls[0]!.resolve(snap());
    await flush();
    h.advance(0);
    expect(h.fetcher).toHaveBeenCalledTimes(2);
    const last = h.fetcher.mock.calls.at(-1)![0];
    expect(last).toBe(1_800_000_000_000 + 39 * 3_600_000);
  });

  it('coalesces newer instants without orphaning an in-progress server calculation', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.advance(0);
    expect(h.calls).toHaveLength(1);
    h.client.request(1_800_000_100_000, 1e4, 'dsn34');
    expect(h.calls[0]!.signal.aborted).toBe(false);
    h.calls[0]!.resolve(snap());
    await flush();
    expect(h.got).toEqual([]);
    h.advance(1000);
    expect(h.calls).toHaveLength(2);
    expect(h.calls[0]!.signal.aborted).toBe(false);
    h.calls[0]!.resolve(snap()); // late answer for the old instant
    await flush();
    expect(h.got).toEqual([]);
    h.calls[1]!.resolve(snap());
    await flush();
    expect(h.got).toEqual([1_800_000_100_000]);
  });

  it('serves a cached instant immediately without cancelling an obsolete running calculation', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.advance(0);
    h.calls[0]!.resolve(snap());
    await flush();
    h.client.request(1_800_000_060_000, 1e4, 'dsn34');
    h.advance(1000);
    expect(h.calls).toHaveLength(2);
    h.client.request(1_800_000_000_000, 1e4, 'dsn34'); // back to the cached instant
    expect(h.calls[1]!.signal.aborted).toBe(false);
    expect(h.got.at(-1)).toBe(1_800_000_000_000);
    expect(h.fetcher).toHaveBeenCalledTimes(2);
    h.calls[1]!.resolve(snap());
    await flush();
    expect(h.got).toHaveLength(2); // stale answer ignored
  });

  it('drops the queued replacement when returning to the instant still being calculated', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.advance(0);
    h.client.request(1_800_000_060_000, 1e4, 'dsn34');
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.calls[0]!.resolve(snap());
    await flush();
    h.advance(2000);
    expect(h.got).toEqual([1_800_000_000_000]);
    expect(h.fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not overwrite the latest requested instant with a stale error', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.advance(0);
    h.client.request(1_800_000_060_000, 1e4, 'dsn34');
    h.calls[0]!.reject(new SnapshotError('unavailable', 'x'));
    await flush();
    expect(h.errors).toEqual([]);
    h.advance(1000);
    h.calls[1]!.resolve(snap());
    await flush();
    expect(h.got).toEqual([1_800_000_060_000]);
  });

  it('keys the cache by rate and station and reports errors without calling onSnapshot', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34');
    h.advance(0);
    h.calls[0]!.resolve(snap());
    await flush();
    h.client.request(1_800_000_000_000, 1e5, 'dsn34');
    h.advance(1000);
    expect(h.fetcher).toHaveBeenCalledTimes(2);
    h.calls[1]!.reject(new SnapshotError('unavailable', 'x'));
    await flush();
    expect(h.errors).toEqual(['unavailable']);
    expect(h.got).toHaveLength(1);
  });

  it('uses the gain in requests and cache keys', async () => {
    const h = setup();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34', 10);
    h.advance(0);
    h.calls[0]!.resolve(snap());
    await flush();
    h.client.request(1_800_000_000_000, 1e4, 'dsn34', 20);
    h.advance(1000);
    expect(h.fetcher).toHaveBeenLastCalledWith(1_800_000_000_000, 1e4, 'dsn34', expect.any(AbortSignal), 20);
    expect(h.fetcher).toHaveBeenCalledTimes(2);
  });
});

describe('fetchSnapshot', () => {
  const resp = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
  it('builds the query and parses', async () => {
    const f = vi.fn(() => resp(200, RAW)) as unknown as typeof fetch;
    const s = await fetchSnapshot(Date.UTC(2027, 3, 7), 1e4, 'dsn18', undefined, f);
    expect(s.sites).toHaveLength(2);
    expect((f as unknown as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toBe('/api/raven/snapshot?t=2027-04-07T00%3A00%3A00Z&rate_bps=10000&station=dsn18');
    await fetchSnapshot(Date.UTC(2027, 3, 7), 1e4, 'dsn18', undefined, f, 20);
    expect((f as unknown as ReturnType<typeof vi.fn>).mock.calls[1]![0]).toContain('&gain_dbi=20');
  });
  it('maps 422, 503 and network failures to generic kinds', async () => {
    await expect(fetchSnapshot(0, 1e4, 'dsn34', undefined, (() => resp(422, { detail: 'x' })) as unknown as typeof fetch)).rejects.toMatchObject({ kind: 'range' });
    await expect(fetchSnapshot(0, 1e4, 'dsn34', undefined, (() => resp(503, { detail: 'x' })) as unknown as typeof fetch)).rejects.toMatchObject({ kind: 'unavailable' });
    await expect(fetchSnapshot(0, 1e4, 'dsn34', undefined, (() => Promise.reject(new TypeError('boom'))) as unknown as typeof fetch)).rejects.toMatchObject({ kind: 'network' });
  });
});
