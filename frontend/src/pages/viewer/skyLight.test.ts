// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { LightClient, SkyError, fetchSubsolar, parseSubsolar, type Light, type Scheduler } from './skyLight';
import { latLonToBody, objToView, rotationRows, subsolarToLightObj } from '../../viewports/scene';

const light = (ms: number, body: Light['body'] = 'moon'): Light => ({ ms, body, lat_deg: 1, lon_deg_east: 2, dir: [0, 0, 1], sun_distance_au: 1 });

function fakeClock() {
  let t = 0;
  const q: { at: number; fn: () => void; id: number }[] = [];
  let n = 0;
  const s: Scheduler = {
    now: () => t,
    setTimeout: (fn, ms) => {
      q.push({ at: t + ms, fn, id: ++n });
      return n;
    },
    clearTimeout: (h) => {
      const i = q.findIndex((x) => x.id === h);
      if (i >= 0) q.splice(i, 1);
    },
  };
  const advance = (ms: number) => {
    t += ms;
    q.sort((a, b) => a.at - b.at);
    while (q.length && q[0]!.at <= t) q.shift()!.fn();
  };
  return { s, advance };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

describe('LightClient', () => {
  it('throttle: solo primo e ultimo valore in una raffica', async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async (_b: string, ms: number) => light(ms));
    const got: number[] = [];
    const c = new LightClient({ fetcher, scheduler: clock.s, minIntervalMs: 250, onLight: (l) => got.push(l.ms), onError: () => {} });
    c.request('moon', 1);
    clock.advance(0);
    await flush();
    for (const m of [2, 3, 4, 5]) c.request('moon', m);
    clock.advance(100);
    expect(fetcher).toHaveBeenCalledTimes(1);
    clock.advance(200);
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(got).toEqual([1, 5]);
  });
  it('annulla la richiesta superata e scarta la sua risposta', async () => {
    const clock = fakeClock();
    const signals: AbortSignal[] = [];
    const resolvers: ((l: Light) => void)[] = [];
    const fetcher = (_b: string, _ms: number, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise<Light>((res) => resolvers.push(res));
    };
    const got: number[] = [];
    const c = new LightClient({ fetcher, scheduler: clock.s, minIntervalMs: 100, onLight: (l) => got.push(l.ms), onError: () => {} });
    c.request('moon', 1);
    clock.advance(0);
    c.request('moon', 2);
    clock.advance(100);
    expect(signals[0]!.aborted).toBe(true);
    resolvers[0]!(light(1)); // risposta vecchia: ignorata
    resolvers[1]!(light(2));
    await flush();
    expect(got).toEqual([2]);
    expect(c.last?.ms).toBe(2);
  });
  it('errore: nessuna luce nuova, la cache resta', async () => {
    const clock = fakeClock();
    let fail = false;
    const fetcher = async (_b: string, ms: number) => {
      if (fail) throw new SkyError('range', 'fuori');
      return light(ms);
    };
    const errs: string[] = [];
    const got: number[] = [];
    const c = new LightClient({ fetcher, scheduler: clock.s, minIntervalMs: 10, onLight: (l) => got.push(l.ms), onError: (e) => errs.push(e.kind) });
    c.request('moon', 1);
    clock.advance(0);
    await flush();
    fail = true;
    c.request('moon', 2);
    clock.advance(10);
    await flush();
    expect(errs).toEqual(['range']);
    expect(got).toEqual([1]);
    expect(c.last?.ms).toBe(1);
  });
  it('stesso istante e corpo dell ultima luce valida: nessuna rete', async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async (_b: string, ms: number) => light(ms));
    const c = new LightClient({ fetcher, scheduler: clock.s, minIntervalMs: 10, onLight: () => {}, onError: () => {} });
    c.request('moon', 7);
    clock.advance(0);
    await flush();
    c.request('moon', 7);
    clock.advance(10);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('un cambio di corpo non usa la cache', async () => {
    const clock = fakeClock();
    const fetcher = vi.fn(async (b: Light['body'], ms: number) => light(ms, b));
    const c = new LightClient({ fetcher, scheduler: clock.s, minIntervalMs: 10, onLight: () => {}, onError: () => {} });
    c.request('moon', 7);
    clock.advance(0);
    await flush();
    c.request('earth', 7);
    clock.advance(10);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

describe('fetchSubsolar / parseSubsolar', () => {
  const ok = { subsolar: { lat_deg: -1.5, lon_deg_east: 40 }, sun_distance_au: 1.01, sun_direction_body_fixed: [0, 0, 2] };
  it('mappa gli stati HTTP', async () => {
    const mk = (status: number, body: unknown = {}) => (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
    await expect(fetchSubsolar('moon', 0, undefined, mk(422))).rejects.toMatchObject({ kind: 'range' });
    await expect(fetchSubsolar('moon', 0, undefined, mk(503))).rejects.toMatchObject({ kind: 'unavailable' });
    await expect(fetchSubsolar('moon', 0, undefined, (async () => Promise.reject(new TypeError('x'))) as unknown as typeof fetch)).rejects.toMatchObject({ kind: 'network' });
    await expect(fetchSubsolar('moon', 0, undefined, mk(200, { subsolar: {} }))).rejects.toMatchObject({ kind: 'invalid' });
    const l = await fetchSubsolar('mars', Date.UTC(2026, 0, 1), undefined, mk(200, ok));
    expect(l.dir).toEqual([0, 0, 1]);
  });
  it('rifiuta vettori degeneri', () => {
    expect(() => parseSubsolar({ ...ok, sun_direction_body_fixed: [0, 0, 0] }, 'moon', 0)).toThrow();
    expect(() => parseSubsolar({ ...ok, sun_direction_body_fixed: [1, Number.NaN, 0] }, 'moon', 0)).toThrow();
  });
});

describe('mappa della luce', () => {
  it('il punto subsolare coincide con la direzione dell API (assi del viewer)', () => {
    const v = subsolarToLightObj(0, 90);
    expect(v[0]).toBeCloseTo(1);
    expect(subsolarToLightObj(0, 0)[2]).toBeCloseTo(1);
    expect(subsolarToLightObj(90, 0)[1]).toBeCloseTo(1);
    expect(subsolarToLightObj(10, 20)).toEqual(latLonToBody(10, 20));
  });
  it('nella vista la luce ruota come il corpo: guardando il punto subsolare e illuminato in pieno', () => {
    // yaw che porta lon 0 verso la camera (+z della vista): la luce a lon 0 deve avere vista z = 1
    const rows = rotationRows(0, 0);
    expect(objToView(rows, [0, 0, 1])[2]).toBeCloseTo(1);
    // dopo yaw 90 il punto lon 0 non guarda piu' la camera
    const r2 = rotationRows(90, 0);
    expect(Math.abs(objToView(r2, [0, 0, 1])[2])).toBeLessThan(1e-9);
    // modulo conservato
    const w = objToView(rotationRows(33, -20), [0.3, 0.5, 0.8124038404635961]);
    expect(Math.hypot(...w)).toBeCloseTo(1);
  });
});
