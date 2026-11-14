// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { chooseDefaultInstant, parseSeries, pickGrazingInstant, seriesUrl, type SunSeries } from './grazingLight';

const H = 3_600_000;
const T0 = Date.UTC(2026, 9, 26, 12);
/** Sito all'equatore, lon 0: "su" = +z, quindi quota = asin(z). */
const dirAt = (elDeg: number): [number, number, number] => {
  const e = (elDeg * Math.PI) / 180;
  return [Math.cos(e), 0, Math.sin(e)];
};
const series = (els: number[]): SunSeries => ({ ms: els.map((_, i) => T0 + i * H), dirs: els.map(dirAt) });

describe('pickGrazingInstant', () => {
  it('picks the first instant with the Sun between 1 and 3 degrees', () => {
    const r = pickGrazingInstant(T0, series([-1.5, -0.2, 0.7, 1.4, 2.6, 4]), 0, 0);
    expect(r.kind).toBe('grazing');
    expect(r.ms).toBe(T0 + 3 * H);
    expect(r.kind === 'grazing' && r.elDeg).toBeCloseTo(1.4, 6);
  });
  it('keeps the given time when the Sun is at the start already in the window', () => {
    expect(pickGrazingInstant(T0, series([2, 2.5]), 0, 0).ms).toBe(T0);
  });
  it('ignores instants before the start', () => {
    expect(pickGrazingInstant(T0 + 2 * H, series([2, 2, -1, -1]), 0, 0).kind).toBe('none');
  });
  it('returns the given time with the Sun elevation at that time when no instant qualifies (terrain in shadow)', () => {
    const r = pickGrazingInstant(T0, series([-1.5, -1, -0.5, 0, 5, 8]), 0, 0);
    expect(r.kind).toBe('none');
    expect(r.ms).toBe(T0);
    expect(r.elDeg).toBeCloseTo(-1.5, 6);
  });
});

describe('series client', () => {
  const body = (els: number[]) => ({
    t_utc: els.map((_, i) => new Date(T0 + i * H).toISOString()),
    sun_direction_body_fixed: els.map(dirAt),
  });
  it('requests one lunar month at 1 h on the Moon', () => {
    const u = seriesUrl(T0);
    expect(u).toContain('/api/raven/sky/series?body=moon&t0=2026-10-26T12%3A00%3A00Z');
    expect(u).toContain('step_s=3600');
    expect(u).toContain('t1=2026-11-25T');
  });
  it('chooses from the API answer', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify(body([-1.5, 0, 1.5])), { status: 200 })) as unknown as typeof fetch;
    const r = await chooseDefaultInstant(T0, 0, 0, f);
    expect(r?.kind).toBe('grazing');
    expect(r?.ms).toBe(T0 + 2 * H);
  });
  it('falls back to null (no invented light) on errors and malformed answers', async () => {
    expect(await chooseDefaultInstant(T0, 0, 0, (async () => new Response('{}', { status: 503 })) as unknown as typeof fetch)).toBeNull();
    expect(await chooseDefaultInstant(T0, 0, 0, (async () => new Response('{"t_utc":["x"],"sun_direction_body_fixed":[[1,0,0]]}', { status: 200 })) as unknown as typeof fetch)).toBeNull();
    expect(await chooseDefaultInstant(T0, 0, 0, (async () => Promise.reject(new Error('x'))) as unknown as typeof fetch)).toBeNull();
    expect(parseSeries({ t_utc: [], sun_direction_body_fixed: [] })).toBeNull();
  });
});
