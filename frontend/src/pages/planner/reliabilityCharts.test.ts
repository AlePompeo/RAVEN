// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/svelte';
import ComparisonBars from './ComparisonBars.svelte';
import ReliabilityCharts from './ReliabilityCharts.svelte';
import ReliabilityResults from './ReliabilityResults.svelte';
import { illustrativeReliability, mergeIdenticalScenarios, type ReliabilityResult, type ReliabilityScenario } from './reliability';

afterEach(cleanup);

function fixture(): ReliabilityResult {
  const assumptions = illustrativeReliability('Synthetic rendering fixture');
  assumptions.components = assumptions.components.filter((c) => c.id === 'computer');
  const scenario = (id: string, duration: number): ReliabilityScenario => ({
    id, duration_hours: duration, complete_probability_inputs: false,
    stages: ['launch', 'cruise', 'landing'].map((phase) => ({
      phase: phase as 'launch' | 'cruise' | 'landing', survival_probability: .95,
    })),
    components: [{
      id: 'computer', missing: ['failure_rate_per_hour'], failure_probability: null, malfunction_probability: .02,
      restart_probability: .01, expected_restart_count_full_exposure: .01, mean_recovery_hours: 0,
      retained_at_landing: .95, retained_at_end: .9, performance_known: true, performance_cutoff_hours: null,
      thermal_margin_c: -15, dose_krad: id === 'A' ? 100 : 200, radiation_margin_krad: -90,
      environment_status: 'outside_declared_envelope',
    }],
    hardware_survival_probability: .9, conditional_operational_probability: null,
    expected_available_hours: null, expected_unavailable_hours: null, expected_useful_hours: null,
    expected_useful_lower_hours: null, expected_useful_upper_hours: null,
    timeline: [0, duration / 2, duration].map((hours, i) => ({
      hours, time_unix: (id === 'A' ? 1800000000 : 1900000000) + hours * 3600,
      hardware_survival: id === 'A' && i === 1 ? null : .9, conditional_operational: null, retained_min: .9,
    })),
  });
  return { model: 'raven-reliability-1', source: 'declared_assumptions', qualification: 'not_validated',
    assumptions, scenarios: [scenario('A', 4), scenario('B', 8)], method: 'fixture', limits: [] };
}

it('distinguishes missing and zero bars, and shares a signed numerical scale', () => {
  const { container } = render(ComparisonBars, {
    label: 'Margin', unit: '°C', description: 'Zero is the limit.', series: ['Shared'],
    rows: [
      { label: 'Below limit', values: [-10] }, { label: 'Inside limit', values: [10] },
      { label: 'At limit', values: [0] }, { label: 'Missing', values: [null] },
    ],
  });
  const fills = container.querySelectorAll<HTMLElement>('.bar-fill');
  expect(fills).toHaveLength(3);
  expect(fills[0]!.style.left).toBe('0%');
  expect(fills[0]!.style.width).toBe('50%');
  expect(fills[1]!.style.left).toBe('50%');
  expect(fills[2]!.style.width).toBe('0%');
  expect(fills[0]!.classList.contains('negative')).toBe(true);
  expect(screen.getByText('Non calcolabile / ignoto')).toBeTruthy();
});

it('overlays scenarios on actual elapsed hours, not sample index or absolute UTC, without bridging unknowns', () => {
  const { container } = render(ReliabilityCharts, { result: fixture() });
  const plot = container.querySelector('.reliability-timeline')!;
  const a = plot.querySelector('[data-scenario="A"]')!;
  const b = plot.querySelector('[data-scenario="B"]')!;
  expect(a.querySelectorAll('polyline')).toHaveLength(0);
  expect(a.querySelectorAll('circle')).toHaveLength(2);
  expect(a.querySelectorAll('circle')[1]!.getAttribute('cx')).toBe('300');
  expect(b.querySelector('polyline')!.getAttribute('points')).toMatch(/600,/);
  expect(container.querySelectorAll('.chart')).toHaveLength(10);
});

it('uses authoritative thermal/dose results and their own tolerance without inventing missing probabilities', () => {
  render(ReliabilityCharts, { result: fixture() });
  const thermal = screen.getByRole('figure', { name: 'Margine termico del componente protetto' });
  expect(thermal.textContent).toContain('-15 °C');
  const radiation = screen.getByRole('figure', { name: 'Dose schermata rispetto alla tolleranza TID dichiarata' });
  expect(radiation.textContent).toContain('100 krad(Si)');
  expect(radiation.textContent).toContain('200 krad(Si)');
  expect(radiation.textContent).toContain('10 krad(Si)');
  const faults = screen.getByRole('figure', { name: 'Probabilità di guasto per componente' });
  expect(within(faults).getAllByText('Non calcolabile / ignoto')).toHaveLength(2);
  expect(faults.querySelectorAll('.bar-fill')).toHaveLength(0);
});

it('omits every comparison chart when report graphs are unchecked', () => {
  const { container } = render(ReliabilityResults, { result: fixture(), charts: false });
  expect(container.querySelectorAll('.chart')).toHaveLength(0);
  expect(screen.getByTestId('reliability-A')).toBeTruthy();
});

it('draws one A = B series and one table only when every figure coincides, otherwise keeps both', () => {
  const result = fixture();
  const b = { ...structuredClone(result.scenarios[0]!), id: 'B', timeline: result.scenarios[0]!.timeline.map((p) => ({ ...p, time_unix: p.time_unix + 1e8 })) };
  const same = { ...result, scenarios: [result.scenarios[0]!, b] };
  expect(mergeIdenticalScenarios(same.scenarios).shown.map((s) => s.id)).toEqual(['A = B']);
  const { container } = render(ReliabilityCharts, { result: same });
  expect(container.querySelectorAll('.reliability-timeline')[0]!.querySelectorAll('[data-scenario]')).toHaveLength(1);
  expect(mergeIdenticalScenarios(result.scenarios).identical).toBe(false);
  expect(mergeIdenticalScenarios(result.scenarios).shown).toHaveLength(2);
});
