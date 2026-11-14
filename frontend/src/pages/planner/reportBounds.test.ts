// SPDX-License-Identifier: Apache-2.0
// Unknown steps are not drawn as zero: the cumulative useful hours get a lower bound (confirmed only) and an upper bound (every unknown step useful).
import { describe, expect, it } from 'vitest';
import { reportCharts, usefulBounds } from './reportCharts';
import { siteA, unknownRf } from './reportFixtures';

describe('bounds of the cumulative useful hours', () => {
  it('a fully known site has equal bounds that end at its useful hours', () => {
    const { lower, upper } = usefulBounds(siteA);
    expect(lower).toEqual(upper);
    expect(lower.at(-1)).toBeCloseTo(siteA.metrics.useful_hours, 6);
  });

  it('an all-unknown site stays at 0 confirmed hours and can reach the whole window at most', () => {
    const b = unknownRf();
    const { lower, upper } = usefulBounds(b);
    const unknownSteps = b.steps!.useful.filter((u) => u === null).length;
    const hours = (unknownSteps * b.window.step_min) / 60;
    expect(unknownSteps).toBeGreaterThan(0);
    expect(lower.at(-1)).toBeLessThanOrEqual(upper.at(-1)!);
    expect(upper.at(-1)! - lower.at(-1)!).toBeCloseTo(hours, 6);
    expect(lower.every((v, i) => v <= upper[i]!)).toBe(true);
    expect(lower.every((v, i) => i === 0 || v >= lower[i - 1]!) && upper.every((v, i) => i === 0 || v >= upper[i - 1]!)).toBe(true);
  });

  it('the chart carries one bound per site and only the cumulative chart has them', () => {
    const charts = reportCharts([siteA, unknownRf()]);
    const cum = charts.find((c) => c.id === 'cum')!;
    expect(cum.bounds).toHaveLength(2);
    expect(cum.bounds![0]!.tag).toBe('A');
    expect(charts.filter((c) => c.id !== 'cum').every((c) => c.bounds === undefined)).toBe(true);
  });
});
