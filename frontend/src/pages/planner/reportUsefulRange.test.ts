// SPDX-License-Identifier: Apache-2.0
// "0 h useful" must not hide that most of the window is unknown: the report states the confirmed hours AND the most it could be.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/svelte';
import ReportSummary from './ReportSummary.svelte';
import { siteA, unknownRf } from './reportFixtures';

afterEach(() => cleanup());

describe('useful time range in the verdict page', () => {
  it('says "confirmed X h, at most Y h" for a site with unknown steps and nothing for a fully known one', () => {
    const { container } = render(ReportSummary, {
      evaluations: [siteA, unknownRf()], missionName: 'Study', start: '2027-04-16T00:00:00Z', days: 3, created: '2027-04-10T08:00:00Z',
    });
    const ranges = Array.from(container.querySelectorAll('[data-testid="useful-range"]')).map((n) => n.textContent ?? '');
    expect(ranges.length).toBeGreaterThan(0);
    for (const r of ranges) {
      const m = /Confirmed ([\d.,]+) h, at most ([\d.,]+) h if every unknown step were useful\./.exec(r);
      expect(m, r).not.toBeNull();
      expect(Number(m![2]!.replace(',', '.'))).toBeGreaterThanOrEqual(Number(m![1]!.replace(',', '.')));
    }
    // the fully known site (A) has no range line: the table has one per site with unknown steps only
    expect(ranges.length).toBeLessThan(2);
  });
});
