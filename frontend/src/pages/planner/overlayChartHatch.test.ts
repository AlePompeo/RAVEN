// SPDX-License-Identifier: Apache-2.0
// Unknown must stay visible in the PDF: the PDF engine ignores SVG <pattern>, so the hatching is drawn as plain lines (an unknown strip used to
// come out blank, like a known "no").
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/svelte';
import OverlayChart from './OverlayChart.svelte';
import { reportCharts } from './reportCharts';
import { siteA, unknownRf } from './reportFixtures';

afterEach(() => cleanup());

describe('hatching of unknown steps in the report charts', () => {
  const charts = reportCharts([siteA, unknownRf()]);

  it('uses no SVG pattern anywhere and draws diagonal lines for the unknown strip and the unknown span', () => {
    const rf = charts.find((c) => c.id === 'rf')!;
    expect(rf.strips[1]!.values.every((v) => v === null)).toBe(true); // site B has no radio value at all
    const { container } = render(OverlayChart, { chart: rf });
    expect(container.querySelectorAll('pattern')).toHaveLength(0);
    expect(container.innerHTML).not.toContain('url(#');
    const lines = container.querySelectorAll('svg line[stroke="#4b5563"]'); // the grey hatching of the unknown strip
    expect(lines.length).toBeGreaterThan(10);
    const band = container.querySelectorAll('svg line[stroke-opacity="0.6"]'); // the hatched band over the plot
    expect(band.length).toBeGreaterThan(10);
  });

  it('the cumulative chart draws the band between confirmed and possible hours instead of hatching', () => {
    const cum = charts.find((c) => c.id === 'cum')!;
    const { container } = render(OverlayChart, { chart: cum });
    expect(container.querySelectorAll('polygon')).toHaveLength(2); // one band per site
    expect(container.querySelectorAll('svg line[stroke-opacity="0.6"]')).toHaveLength(0);
  });

  it('a fully known chart has no hatching and no key about unknown spans', () => {
    const known = reportCharts([siteA, siteA]).find((c) => c.id === 'sun')!;
    const { container } = render(OverlayChart, { chart: known });
    expect(container.querySelectorAll('svg line[stroke-opacity="0.6"]')).toHaveLength(0);
    expect(container.textContent).not.toContain('Hatched spans');
  });
});
