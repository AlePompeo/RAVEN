// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from 'vitest';
import { createRavenClient, customAsSiteInfo, type TerrainEstimate } from './ravenApi';
import { clampLat, project, unproject, wrap } from './globeProjection';
import {
  customSites, encodeCustom, makeId, normaliseLon, parseCustom, parseNumber, validateForm, type CustomSiteDef,
} from './customSites';

afterEach(() => customSites.set([]));

describe('coordinate normalisation', () => {
  it('maps 0..360 to (-180, 180] and refuses the rest', () => {
    expect(normaliseLon(350)).toBe(-10);
    expect(normaliseLon(180)).toBe(180);
    expect(normaliseLon(-180)).toBe(-180);
    expect(normaliseLon(360)).toBe(0);
    expect(normaliseLon(0)).toBe(0);
    expect(normaliseLon(361)).toBeNull();
    expect(normaliseLon(-181)).toBeNull();
    expect(normaliseLon(Number.NaN)).toBeNull();
    expect(normaliseLon(Number.POSITIVE_INFINITY)).toBeNull();
  });
  it('reads numbers strictly (comma decimal ok, no exponent, no junk)', () => {
    expect(parseNumber('-88,5')).toBe(-88.5);
    expect(parseNumber(' 12 ')).toBe(12);
    for (const bad of ['', 'abc', '1e5', '0x10', '--1', '1.2.3', 'Infinity', 'NaN', '9'.repeat(30)]) expect(parseNumber(bad)).toBeNull();
  });
});

describe('form validation', () => {
  const ok = { name: 'Pole A', lat: '-89.54', lon: '350', panel: '', antenna: '3' };
  it('accepts and normalises', () => {
    const r = validateForm(ok);
    expect(r).toEqual({ ok: true, value: { name: 'Pole A', lat_deg: -89.54, lon_deg_east: -10, antenna_height_m: 3 } });
  });
  it.each([
    [{ name: '' }, 'name', 'required'],
    [{ name: '<script>' }, 'name', 'format'],
    [{ name: 'x'.repeat(41) }, 'name', 'format'],
    [{ lat: '' }, 'lat', 'required'],
    [{ lat: '91' }, 'lat', 'range'],
    [{ lat: 'north' }, 'lat', 'format'],
    [{ lon: '361' }, 'lon', 'range'],
    [{ lon: '-181' }, 'lon', 'range'],
    [{ panel: '0' }, 'panel', 'range'],
    [{ antenna: '101' }, 'antenna', 'range'],
    [{ antenna: 'tall' }, 'antenna', 'format'],
  ])('refuses %j with a message for the field', (patch, field, issue) => {
    const r = validateForm({ ...ok, ...patch });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors[field as 'name']).toBe(issue);
  });
});

describe('ids and URL round trip', () => {
  it('makes unique c- ids that never equal a catalogue id', () => {
    const taken = new Set<string>();
    const a = makeId('Shackleton', taken);
    expect(a).toBe('c-shackleton');
    taken.add(a);
    expect(makeId('Shackleton', taken)).toBe('c-shackleton-2');
    expect(makeId('!!!', new Set())).toBe('c-site');
    expect(/^c-[a-z0-9-]{1,31}$/.test(makeId('A very long name '.repeat(5), new Set()))).toBe(true);
  });
  it('round-trips the compact form, with heights, precision 5 decimals', () => {
    const list: CustomSiteDef[] = [
      { id: 'c-a', name: "Rim (north)", lat_deg: -89.54321, lon_deg_east: 129.78, panel_height_m: 2.5, antenna_height_m: 4 },
      { id: 'c-b', name: 'Eq', lat_deg: 0, lon_deg_east: -0.00001 },
    ];
    const enc = encodeCustom(list);
    expect(enc).toBe("c-a~-89.54321~129.78~Rim (north)~2.5~4!c-b~0~-0.00001~Eq");
    expect(parseCustom(enc)).toEqual(list);
    expect(enc.length).toBeLessThan(900);
  });
  it('drops anything invalid without error', () => {
    expect(parseCustom(null)).toEqual([]);
    expect(parseCustom('x'.repeat(901))).toEqual([]);
    expect(parseCustom('c-a~1~2')).toEqual([]);
    expect(parseCustom('c-a~1~2~A~3')).toEqual([]);
    expect(parseCustom('c-a~1~2~A!junk!c-b~3~4~B').map((s) => s.id)).toEqual(['c-a', 'c-b']);
  });
  it('the shared list revalidates what it receives', () => {
    customSites.set([{ id: 'shackleton', name: 'x', lat_deg: 0, lon_deg_east: 0 }, { id: 'c-ok', name: 'Ok', lat_deg: 1, lon_deg_east: 2 }]);
    expect(customSites.get().map((s) => s.id)).toEqual(['c-ok']);
  });
  it('shows a custom site like a catalogue row, never verified', () => {
    const r = customAsSiteInfo({ id: 'c-a', name: 'A', lat_deg: 1, lon_deg_east: 2 });
    expect(r).toMatchObject({ id: 'c-a', verified: false, custom: true, dem_covered: true });
  });
});

describe('globe projection', () => {
  const v = { lat0: -60, lon0: 30 };
  it('unproject inverts project on the visible hemisphere', () => {
    for (const [la, lo] of [[-60, 30], [-80, 10], [-30, 60], [0, 30], [-89, 200]] as const) {
      const p = project(la, lo, v);
      if (!p) continue;
      const q = unproject(p.x, p.y, v)!;
      expect(q.lat).toBeCloseTo(la, 6);
      expect(wrap(q.lon - lo)).toBeCloseTo(0, 6);
    }
    expect(project(60, 210, v)).toBeNull(); // far side
    expect(unproject(1.1, 0, v)).toBeNull();
    expect(unproject(0, 0, v)).toEqual({ lat: -60, lon: 30 });
    expect(clampLat(95)).toBe(90);
  });
});

describe('client: custom definitions and the download confirmation', () => {
  const est: TerrainEstimate = {
    sites: [{ id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3, status: 'ok', reason: 'ok', terrain_available: true, near_product: 'p', far_product: 'p', resolution_m: 240, far_resolution_m: 240, range_km: 75, tiles: 29, mb_total: 1.9, mb_transfer: 2.4, tiles_cached: 0, tiles_to_download: 29, mb_to_download: 2.4, products: [] }],
    mb_total: 1.9, mb_to_download: 2.4, needs_download: true, request_over_cap: false,
    caps: { site_mb: 10, request_mb: 40, cache_mb: 200 }, cache: { used_mb: 0, max_mb: 200 },
  };
  const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

  it('attaches the definition of a c- site and refuses an undefined one before any request', async () => {
    const bodies: unknown[] = [];
    const fetcher = (async (_u: string, init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return json(200, { ok: 1 }); }) as unknown as typeof fetch;
    const c = createRavenClient({ fetch: fetcher });
    const base = { start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60 };
    expect(await c.evaluate({ ...base, site_id: 'c-a' })).toEqual({ ok: false, kind: 'invalid' });
    expect(bodies).toHaveLength(0);
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3 }]);
    await c.evaluate({ ...base, site_id: 'c-a' });
    await c.compare({ ...base, site_ids: ['shackleton', 'c-a'] });
    expect(bodies[0]).toMatchObject({ custom_site: { id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3 } });
    expect(bodies[1]).toMatchObject({ custom_sites: [{ id: 'c-a' }] });
    await c.evaluate({ ...base, site_id: 'shackleton' });
    expect(bodies[2]).not.toHaveProperty('custom_site');
  });

  it('asks before downloading: 409 -> confirm -> same request with allow_download', async () => {
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3 }]);
    const calls: unknown[] = [];
    const fetcher = (async (_u: string, init?: RequestInit) => {
      const b = JSON.parse(String(init?.body));
      calls.push(b);
      return b.allow_download ? json(200, { done: true }) : json(409, { detail: 'needs download', estimate: est });
    }) as unknown as typeof fetch;
    const asked: TerrainEstimate[] = [];
    const yes = createRavenClient({ fetch: fetcher, confirmDownload: async (e) => { asked.push(e); return true; } });
    const base = { start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'c-a' };
    expect(await yes.evaluate(base)).toEqual({ ok: true, data: { done: true } });
    expect(asked).toHaveLength(1);
    expect(asked[0]!.mb_to_download).toBe(2.4);
    expect(calls).toHaveLength(2);
    expect(calls[0]).not.toHaveProperty('allow_download');
    expect(calls[1]).toMatchObject({ allow_download: true });
  });

  it('a catalogue site outside the 20 m product goes through the same consent: 409 -> confirm -> retry with allow_download', async () => {
    const calls: unknown[] = [];
    const fetcher = (async (_u: string, init?: RequestInit) => {
      const b = JSON.parse(String(init?.body));
      calls.push(b);
      return b.allow_download ? json(200, { done: true }) : json(409, { detail: 'needs download', estimate: est });
    }) as unknown as typeof fetch;
    const yes = createRavenClient({ fetch: fetcher, confirmDownload: async () => true });
    const r = await yes.evaluate({ start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'apollo11' });
    expect(r).toEqual({ ok: true, data: { done: true } });
    expect(calls).toHaveLength(2);
    expect(calls[0]).not.toHaveProperty('custom_site');
    expect(calls[1]).toMatchObject({ site_id: 'apollo11', allow_download: true });
  });

  it('on a refusal returns the reason and the estimate, and downloads nothing', async () => {
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3 }]);
    let n = 0;
    const fetcher = (async () => { n++; return json(409, { detail: 'needs download', estimate: est }); }) as unknown as typeof fetch;
    const no = createRavenClient({ fetch: fetcher, confirmDownload: async () => false });
    const r = await no.evaluate({ start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'c-a' });
    expect(r).toMatchObject({ ok: false, kind: 'unavailable', detail: 'needs_download' });
    expect(n).toBe(1);
    const big = createRavenClient({ fetch: (async () => json(413, { detail: 'x', estimate: est })) as unknown as typeof fetch });
    expect(await big.evaluate({ start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'c-a' })).toMatchObject({ kind: 'invalid', detail: 'too_large' });
    const rate = createRavenClient({ fetch: (async () => json(429, { detail: 'x' })) as unknown as typeof fetch });
    expect(await rate.evaluate({ start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'c-a' })).toMatchObject({ kind: 'unavailable', detail: 'rate_limited' });
    const busy = createRavenClient({ fetch: (async () => json(503, { detail: 'x' })) as unknown as typeof fetch });
    expect(await busy.evaluate({ start_utc: '2027-01-01T00:00:00Z', days: 1, step_min: 60, site_id: 'c-a' })).toMatchObject({ kind: 'unavailable' });
  });

  it('scene and horizon carry the coordinates of a custom site as query parameters', async () => {
    customSites.set([{ id: 'c-a', name: 'A', lat_deg: -80, lon_deg_east: 3 }]);
    const urls: string[] = [];
    const fetcher = (async (u: string) => { urls.push(u); return json(200, { ok: 1 }); }) as unknown as typeof fetch;
    const c = createRavenClient({ fetch: fetcher });
    await c.horizon({ site: 'c-a', height_m: 2 });
    await c.scene({ site: 'c-a', t: '2027-01-01T00:00:00Z' });
    await c.snapshot({ t: '2027-01-01T00:00:00Z' });
    expect(urls[0]).toContain('lat_deg=-80');
    expect(urls[0]).toContain('name=A');
    expect(urls[1]).toContain('lon_deg_east=3');
    expect(decodeURIComponent(urls[2]!)).toContain('custom=c-a|A|-80|3');
  });
});
