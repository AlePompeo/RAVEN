// SPDX-License-Identifier: Apache-2.0
// Sun and Earth against the horizon: one panel per site, filled marks above the terrain horizon, open marks below, unknown steps left out and counted.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/svelte';
import ReportSky from './ReportSky.svelte';
import { cutAxis } from './reportCharts';
import { siteA, unknownRf } from './reportFixtures';

afterEach(() => cleanup());

describe('ReportSky', () => {
  it('draws one panel per site with Sun circles and Earth squares and no invalid number', () => {
    const { container } = render(ReportSky, { evaluations: [siteA, unknownRf()] });
    const panels = container.querySelectorAll('svg[data-sky]');
    expect(panels).toHaveLength(2);
    expect(container.querySelectorAll('svg[data-sky="A"] circle').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('svg[data-sky="A"] rect').length).toBeGreaterThan(1); // the frame and the Earth squares
    expect(container.innerHTML).not.toMatch(/NaN|Infinity|undefined/);
    expect(container.innerHTML).not.toContain('<pattern');
    expect(container.querySelector('.rp-read')?.textContent).toContain('below');
  });

  it('a mark is filled only when the body is above the horizon at its azimuth', () => {
    const e = structuredClone(siteA);
    const n = e.steps!.sun_el_deg.length;
    e.steps!.sun_el_deg = Array.from({ length: n }, (_, i) => (i % 2 === 0 ? 5 : -5));
    e.steps!.sun_horizon_deg = Array.from({ length: n }, () => 0);
    e.steps!.sun_az_deg = Array.from({ length: n }, (_, i) => 100 + i);
    const { container } = render(ReportSky, { evaluations: [e] });
    const circles = Array.from(container.querySelectorAll('svg[data-sky="A"] circle'));
    const filled = circles.filter((c) => c.getAttribute('fill') !== '#ffffff').length;
    const open = circles.filter((c) => c.getAttribute('fill') === '#ffffff').length;
    expect(filled).toBeGreaterThan(0);
    expect(open).toBeGreaterThan(0);
    expect(Math.abs(filled - open)).toBeLessThanOrEqual(1);
  });

  it('counts unknown steps and says so instead of drawing them', () => {
    const e = structuredClone(siteA);
    const n = e.steps!.earth_el_deg.length;
    e.steps!.earth_el_deg = Array.from({ length: n }, () => null);
    const { container } = render(ReportSky, { evaluations: [e] });
    expect(container.textContent).toContain(`${n} Earth steps`);
    expect(container.textContent).toContain('unknown and left out');
  });
});

describe('cutAxis', () => {
  it('keeps a movement across north together instead of spreading it over 0 to 360', () => {
    const { start, span } = cutAxis([340, 350, 355, 5, 10, 60]); // crosses north
    expect(start).toBe(340);
    expect(span).toBeCloseTo(80, 6);
  });
  it('is the plain range when the data do not cross north, and the whole circle when there is none', () => {
    expect(cutAxis([100, 120, 150])).toEqual({ start: 100, span: 50 });
    expect(cutAxis([])).toEqual({ start: 0, span: 360 });
    expect(cutAxis([10])).toEqual({ start: 10, span: 0 });
  });
});
