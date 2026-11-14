// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { bitRate, minusSign, sameSeries, sharedParameters, splitShared, utcMinute } from './reportFormat';

describe('report formatting', () => {
  it('uses a typographic minus for numbers but never rewrites ISO dates or words', () => {
    expect(minusSign('-5,3')).toBe('−5,3');
    expect(minusSign('da -5,3 a -1,5 °')).toBe('da −5,3 a −1,5 °');
    expect(minusSign('2027-04-16 00:00 UTC')).toBe('2027-04-16 00:00 UTC');
    expect(minusSign('Mons-Malapert')).toBe('Mons-Malapert');
  });
  it('prints one UTC format without seconds or milliseconds', () => {
    expect(utcMinute('2026-11-09T16:07:48.123Z')).toBe('2026-11-09 16:07 UTC');
    expect(utcMinute('2027-04-16T00:00')).toBe('2027-04-16 00:00 UTC');
    expect(utcMinute(Date.UTC(2027, 3, 16, 1, 30, 59))).toBe('2027-04-16 01:30 UTC');
    expect(utcMinute('not a date')).toBe('not a date');
    expect(utcMinute(Number.NaN)).toBe('NaN');
  });
  it('shows round bit rates in the largest exact unit and keeps odd ones exact', () => {
    expect(bitRate(3000000)).toBe('3 Mbit/s');
    expect(bitRate(100000)).toBe('100 kbit/s');
    expect(bitRate(1500)).toBe('1.5 kbit/s');
    expect(bitRate(1234567)).toBe('1234.567 kbit/s');
    expect(bitRate(512)).toBe('512 bit/s');
  });
  it('detects identical series without equating unknown with zero', () => {
    expect(sameSeries([1, null, 3], [1, null, 3])).toBe(true);
    expect(sameSeries([0, 1], [null, 1])).toBe(false);
    expect(sameSeries([1], [1, 2])).toBe(false);
  });
  it('splits scenario parameters into shared and differing rows', () => {
    const { differing, shared } = splitShared({ a: 1, b: 2, c: 'x' }, { a: 1, b: 3, d: 4 });
    expect(shared).toEqual(['a']);
    expect(differing.sort()).toEqual(['b', 'c', 'd']);
  });
  it('lists identical scenario parameters once and only the differing rows per scenario', () => {
    const a = { energy: { area: 1, load: 5 }, rf: { gain: 20 } };
    const b = { energy: { area: 1, load: 6 }, rf: { gain: 20 } };
    const { shared, differing } = sharedParameters([a, b]);
    expect(shared).toEqual({ energy: { area: 1 }, rf: { gain: 20 } });
    expect(differing).toEqual([{ energy: { load: 5 } }, { energy: { load: 6 } }]);
    expect(sharedParameters([a, a]).differing).toEqual([{}, {}]);
  });
});
