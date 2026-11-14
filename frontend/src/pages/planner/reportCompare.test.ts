// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { meaning, siteFigures, tri, verdict } from './reportCompare';
import { niceAxis, reportCharts, runs, segments } from './reportCharts';
import { siteA, unknownRf } from './reportFixtures';

describe('site comparison', () => {
  it('counts known yes, known no and unknown apart', () => {
    expect(tri([true, false, null, true])).toEqual({ yes: 2, no: 1, unknown: 1, n: 4 });
  });

  it('words a clear verdict when the other site is unknown but cannot catch up', () => {
    const b = unknownRf(); b.metrics.unknown_hours = 3; // best case 3 h < 24 h confirmed
    const v = verdict([siteFigures(siteA, 0), siteFigures(b, 1)]);
    expect(v.outcome).toBe('clear');
    expect(v.headline).toContain('A: 24 of 24 sampled hours confirmed useful (100%)');
    expect(v.headline).toContain('B: 0 confirmed, 3 h unknown because the radio link is outside the model');
    expect(v.headline).toContain('A is the only site with confirmed useful time');
  });

  it('refuses to conclude when the unknown hours could change the order', () => {
    const v = verdict([siteFigures(siteA, 0), siteFigures(unknownRf(), 1)]);
    expect(v.outcome).toBe('open');
    expect(v.conclusion).toBe('A leads on confirmed time, but the 24 h unknown for B could change the order. No conclusion.');
  });

  it('reports a tie and a double zero without inventing a winner', () => {
    expect(verdict([siteFigures(siteA, 0), siteFigures(siteA, 1)]).outcome).toBe('tie');
    const zero = structuredClone(siteA); zero.metrics.useful_hours = 0;
    expect(verdict([siteFigures(zero, 0), siteFigures(zero, 1)]).outcome).toBe('none');
  });

  it('gives at most three bullets, with an instruction when something is unknown', () => {
    const figs = [siteFigures(siteA, 0), siteFigures(unknownRf(), 1)];
    const bullets = meaning(figs, verdict(figs));
    expect(bullets.length).toBeLessThanOrEqual(3);
    expect(bullets.at(-1)).toContain('Do not rank B on this run');
  });
});

describe('chart helpers', () => {
  it('breaks lines at unknown samples and never bridges them', () => {
    expect(segments([1, 2, null, 3, null, null, 4, 5])).toEqual([[0, 1], [3], [6, 7]]);
  });
  it('keeps unknown runs apart from known-no runs', () => {
    expect(runs([true, true, false, null, null, true])).toEqual([
      { value: true, length: 2 }, { value: false, length: 1 }, { value: null, length: 2 }, { value: true, length: 1 }]);
  });
  it('uses one axis for both sites and ignores unknown values', () => {
    const axis = niceAxis([-3.2, 7.9, null], [0]);
    expect(axis.low).toBeLessThanOrEqual(-3.2);
    expect(axis.high).toBeGreaterThanOrEqual(7.9);
    expect(niceAxis([null, null], [])).toEqual({ low: 0, high: 1, ticks: [0, 1] });
  });
});

describe('cumulative useful hours chart', () => {
  it('never decreases, ends at the confirmed useful hours, starts at elapsed 0 and has no values (not 0) for an all-unknown site', () => {
    const [a, b] = [siteA, unknownRf()];
    const chart = reportCharts([a, b]).find((c) => c.id === 'cum')!;
    const va = chart.lines[0]!.values as number[]; // site A is fully known
    expect(va.every((v, i) => i === 0 || v >= va[i - 1]!)).toBe(true);
    expect(va.at(-1)).toBeCloseTo(a.metrics.useful_hours, 6);
    expect(chart.lines[0]!.times[0]).toBe(0);
    expect(chart.lines[1]!.values.every((v) => v === null)).toBe(true); // not 0
    expect(chart.strips[1]!.values.every((v) => v === null)).toBe(true); // unknown is drawn as unknown, not as no
    expect(chart.unit).toBe('h');
  });
});
