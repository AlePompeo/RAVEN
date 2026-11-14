// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { siteA } from './reportFixtures';
import { countdownAt, lunarDays, siteStats } from './visibilityStats';
import type { RavenEvaluation } from '../../shell/ravenApi';

const make = (lit: (boolean | null)[], sunEl: (number | null)[], earthEl: (number | null)[], hor: (number | null)[], useful: (boolean | null)[], stepMin = 60): RavenEvaluation => ({
  ...siteA, window: { ...siteA.window, step_min: stepMin },
  steps: { ...siteA.steps!, time_unix: lit.map((_, i) => 1_800_000_000 + i * stepMin * 60), lit, sun_el_deg: sunEl, earth_el_deg: earthEl, earth_horizon_deg: hor, useful },
});

describe('site figures', () => {
  it('measures Sun elevation only while lit and runs only over known steps', () => {
    const e = make([true, true, false, true, null, true], [10, 30, -5, 20, null, 40], [5, 5, 5, 5, 5, 5], [0, 0, 9, 0, 0, 0], [true, false, false, true, null, true]);
    expect(siteStats(e)).toMatchObject({ sunMaxElDeg: 40, litH: 4, longestLitH: 2, longestDarkH: 1, earthH: 5, longestEarthH: 3, longestNoEarthH: 1, unknownH: 1 });
    expect(siteStats(e)!.sunMeanElDeg).toBeCloseTo(25, 6);
  });
  it('is unknown, not zero, when nothing is known', () => {
    const e = make([null, null], [null, null], [null, null], [null, null], [null, null]);
    expect(siteStats(e)).toMatchObject({ sunMaxElDeg: null, litH: null, longestLitH: null, earthH: null });
  });
});

describe('countdown', () => {
  it('counts the hours to the next change, null when none', () => {
    const e = make([true, true, true, false, false], [1, 1, 1, -1, -1], [5, 5, 5, 5, 5], [0, 0, 0, 0, 0], [true, true, true, false, false]);
    expect(countdownAt(e, 0)).toEqual({ sun: { visible: true, hours: 3 }, earth: { visible: true, hours: null } });
    expect(countdownAt(e, 4)!.sun).toEqual({ visible: false, hours: null });
    expect(countdownAt(e, 99)).toBeNull();
  });
});

describe('lunar days', () => {
  it('cuts the window in synodic months and gives shares and useful hours', () => {
    const n = 24 * 40; // 40 days at 60 min
    const lit = Array.from({ length: n }, (_, i) => i % 2 === 0);
    const e = make(lit, lit.map(() => 5), Array(n).fill(5), Array(n).fill(0), lit);
    const d = lunarDays(e);
    expect(d).toHaveLength(2);
    expect(d[0]!.days).toBeCloseTo(29.5, 1);
    expect(d[0]!.litPct).toBeCloseTo(50, 0);
    expect(d[1]!.days).toBeLessThan(11);
    expect(d[0]!.usefulH + d[1]!.usefulH).toBe(n / 2);
  });
});
