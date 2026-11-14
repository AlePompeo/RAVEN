// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildParams,
  buildUrl,
  clampCursor,
  createRequester,
  cursorRange,
  DEFAULT_FORM,
  exactIntensity,
  fetchWave,
  flattenGrid,
  gridCsv,
  lambdaOf,
  RES_HI,
  RES_LO,
  rowAt,
  sectionAt,
  sectionCsv,
  sectionJson,
  sectionStats,
  validateForm,
  warningText,
  zTopOf,
  type WaveOutcome,
  type WaveResult,
} from './wave';

function fake(): WaveResult {
  const x_m = [0, 100, 200, 300];
  const y_m = [-10, 0, 10];
  const intensity = x_m.map((x) => y_m.map((y) => 0.5 + x / 1000 + y / 100));
  return {
    x_m,
    y_m,
    intensity,
    section: { x_m: 300, y_m: [-10, 0, 10], nu: [1, 0, -1], intensity: [0.4, 0.25, 1.2], knife_edge_exact: [0.1, 0.25, 1.1], max_abs_diff_vs_knife: 0.1, rms_diff_vs_knife: 0.05 },
    meta: { wavelength_m: 0.0357, warnings: [], grid_shape: [4, 3] } as unknown as WaveResult['meta'],
    disclaimer: 'd',
  };
}
const okBody = (r: WaveResult) => new Response(JSON.stringify(r), { status: 200 });

afterEach(() => vi.useRealTimers());

describe('richiesta', () => {
  it('banda X: frequenza, lama, passo adattato alla distanza', () => {
    const p = buildParams(DEFAULT_FORM, RES_HI);
    expect(p).toMatchObject({ frequency_ghz: '8.4', radius_m: '0', distance_m: '2000', step_m: '20', y_min_m: '-40', y_max_m: '40', nx: '100', ny: '160' });
    expect(p.wavelength_m).toBeUndefined();
  });
  it('lunghezza d’onda al posto della frequenza e risoluzione ridotta', () => {
    const p = buildParams({ ...DEFAULT_FORM, spec: 'wavelength', wavelengthM: 0.0357 }, RES_LO);
    expect(p.wavelength_m).toBe('0.0357');
    expect(p.frequency_ghz).toBeUndefined();
    expect(p).toMatchObject({ nx: '60', ny: '80', step_m: '33.3' });
    expect(buildUrl(DEFAULT_FORM, RES_HI)).toMatch(/^\/api\/raven\/wave\?frequency_ghz=8\.4&radius_m=0/);
  });
  it('lambda della banda X', () => {
    expect(lambdaOf(8.4)).toBeCloseTo(0.0357, 4);
  });
  it('validazione con messaggi in italiano', () => {
    expect(validateForm(DEFAULT_FORM)).toEqual({});
    const e = validateForm({ ...DEFAULT_FORM, frequencyGhz: 100, radiusM: 500, distanceM: 50, halfWindowM: null });
    expect(Object.keys(e).sort()).toEqual(['distanceM', 'frequencyGhz', 'halfWindowM', 'radiusM']);
    expect(e.radiusM).toMatch(/raggio/);
    expect(validateForm({ ...DEFAULT_FORM, radiusM: 400, distanceM: 120 }).distanceM).toMatch(/troppo corta/);
  });
});

describe('rete', () => {
  it('422, 503, 429, errore di rete e corpo non valido', async () => {
    const status = async (s: number, detail?: string): Promise<WaveOutcome> =>
      fetchWave(async () => new Response(JSON.stringify({ detail }), { status: s }), '/u');
    expect(await status(422)).toMatchObject({ ok: false, kind: 'invalid' });
    expect(await status(503, 'servizio')).toMatchObject({ ok: false, kind: 'unavailable' });
    expect(await status(503, 'troppe analisi in corso')).toMatchObject({ ok: false, kind: 'busy' });
    expect(await status(429)).toMatchObject({ ok: false, kind: 'busy' });
    expect(await status(500)).toMatchObject({ ok: false, kind: 'server' });
    expect(await fetchWave(async () => Promise.reject(new TypeError('x')), '/u')).toMatchObject({ ok: false, kind: 'network' });
    expect(await fetchWave(async () => new Response('{"x_m":[]}'), '/u')).toMatchObject({ ok: false, kind: 'server' });
    const good = await fetchWave(async () => okBody(fake()), '/u');
    expect(good.ok).toBe(true);
  });
});

describe('richiedente: debounce e annullamento', () => {
  it('una sola richiesta per una raffica di modifiche', async () => {
    vi.useFakeTimers();
    const f = vi.fn(async () => okBody(fake()));
    const results: WaveOutcome[] = [];
    const r = createRequester(f as unknown as typeof fetch, { onStart: () => {}, onResult: (o) => results.push(o) }, 300);
    r.schedule('/a');
    await vi.advanceTimersByTimeAsync(100);
    r.schedule('/b');
    await vi.advanceTimersByTimeAsync(100);
    r.schedule('/c');
    await vi.advanceTimersByTimeAsync(299);
    expect(f).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2);
    expect(f).toHaveBeenCalledTimes(1);
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe('/c');
    expect(results).toHaveLength(1);
  });

  it('una richiesta superata viene annullata e la sua risposta scartata', async () => {
    const signals: AbortSignal[] = [];
    const resolvers: ((r: Response) => void)[] = [];
    const f = vi.fn((_u: string, init?: RequestInit) => {
      signals.push(init!.signal!);
      return new Promise<Response>((res) => resolvers.push(res));
    });
    const results: WaveOutcome[] = [];
    const starts = vi.fn();
    const r = createRequester(f as unknown as typeof fetch, { onStart: starts, onResult: (o) => results.push(o) });
    r.now('/1');
    r.now('/2');
    expect(signals[0]!.aborted).toBe(true);
    expect(signals[1]!.aborted).toBe(false);
    expect(starts).toHaveBeenCalledTimes(2);
    resolvers[0]!(okBody(fake())); // tardiva: ignorata
    resolvers[1]!(okBody(fake()));
    await new Promise((res) => setTimeout(res, 0));
    expect(results).toHaveLength(1);
    r.now('/3');
    r.cancel();
    expect(signals[2]!.aborted).toBe(true);
  });
});

describe('sezione', () => {
  it('rowAt interpola e satura ai bordi', () => {
    const xs = [0, 100, 300];
    expect(rowAt(xs, -5)).toEqual({ k: 0, t: 0 });
    expect(rowAt(xs, 50)).toEqual({ k: 0, t: 0.5 });
    expect(rowAt(xs, 200)).toEqual({ k: 1, t: 0.5 });
    expect(rowAt(xs, 999)).toEqual({ k: 1, t: 1 });
  });
  it('intervallo del cursore: salta x = 0 della lama', () => {
    const r = fake();
    expect(cursorRange(r)).toEqual([100, 300]);
    expect(clampCursor(r, 0)).toBe(100);
    expect(clampCursor(r, 1e9)).toBe(300);
    expect(clampCursor(r, Number.NaN)).toBe(300);
    expect(cursorRange({ x_m: [20, 40, 60] })).toEqual([20, 60]);
  });
  it('alla distanza finale usa la sezione dell’API; altrove interpola', () => {
    const r = fake();
    const end = sectionAt(r, 300);
    expect(end.fromApi).toBe(true);
    expect(Array.from(end.simulated)).toEqual([0.4, 0.25, 1.2]);
    const mid = sectionAt(r, 150);
    expect(mid.fromApi).toBe(false);
    expect(mid.simulated[1]).toBeCloseTo(0.5 + 0.15, 6);
    expect(mid.exact[1]).toBeCloseTo(exactIntensity(0, 150, 0.0357), 9);
    const api = { ...r.section, x_m: 150, intensity: [9, 9, 9] };
    expect(sectionAt(r, 150.2, api).simulated[0]).toBe(9);
    expect(sectionAt(r, 160, api).fromApi).toBe(false);
  });
  it('lama esatta: 0,25 sulla linea di vista, 1 lontano sopra, quasi 0 nell’ombra profonda', () => {
    expect(exactIntensity(0, 1000, 0.0357)).toBeCloseTo(0.25, 3);
    expect(exactIntensity(200, 1000, 0.0357)).toBeGreaterThan(0.9);
    expect(exactIntensity(-200, 1000, 0.0357)).toBeLessThan(0.01);
  });
  it('statistiche sulla differenza', () => {
    const s = sectionStats(sectionAt(fake(), 300));
    expect(s.maxAbs).toBeCloseTo(0.3, 9);
    expect(s.rms).toBeGreaterThan(0);
  });
});

describe('griglia e testi', () => {
  it('flattenGrid riusa il buffer della stessa misura', () => {
    const r = fake();
    const a = flattenGrid(r.intensity);
    expect(a).toHaveLength(12);
    expect(a[4]).toBeCloseTo(r.intensity[1]![1]!, 6);
    const b = flattenGrid(r.intensity, a);
    expect(b).toBe(a);
    expect(flattenGrid(r.intensity, new Float32Array(3))).not.toBe(a);
  });
  it('quota massima: almeno 1,2 e arrotondata', () => {
    expect(zTopOf(new Float32Array([0.2, 1.0]))).toBe(1.2);
    expect(zTopOf(new Float32Array([0.2, 1.37]))).toBe(1.4);
  });
  it('avvisi del server in italiano chiaro', () => {
    expect(warningText('kernel_aliasing: dz > N dy^2 / lambda, ...')).toMatch(/troppo lungo/);
    expect(warningText('dy_coarse: x')).toMatch(/grossolana/);
    expect(warningText('paraxial: x')).toMatch(/parassiale/);
    expect(warningText('step_raised: x')).toMatch(/aumentato/);
    expect(warningText('nuovo: x')).toMatch(/^Avviso del simulatore/);
  });
});

describe('esportazioni', () => {
  it('CSV della sezione: intestazione, nu e una riga per punto', () => {
    const r = fake();
    const lines = sectionCsv(sectionAt(r, 300), 0.0357).trim().split('\n');
    expect(lines[0]).toBe('y_m,nu,intensity_simulated,intensity_knife_edge_exact');
    expect(lines).toHaveLength(4);
    expect(Number(lines[1]!.split(',')[1])).toBeCloseTo(10 * Math.sqrt(2 / (0.0357 * 300)), 6);
  });
  it('CSV della griglia e JSON della sezione', () => {
    const r = fake();
    const lines = gridCsv(r).trim().split('\n');
    expect(lines).toHaveLength(1 + 12);
    expect(lines[0]).toBe('x_m,y_m,intensity');
    const j = JSON.parse(sectionJson(sectionAt(r, 150), r)) as { distance_m: number; from_api_section: boolean; y_m: number[] };
    expect(j).toMatchObject({ distance_m: 150, from_api_section: false });
    expect(j.y_m).toHaveLength(3);
  });
});
