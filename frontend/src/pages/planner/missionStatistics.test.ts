// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import CompositionChart from './CompositionChart.svelte';
import MissionStatistics from './MissionStatistics.svelte';
import PlanningStatistics from './PlanningStatistics.svelte';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { newReportPlanning, type BudgetEstimate, type CarbonEstimate } from './reportPlanning';

afterEach(cleanup);

it('draws a complete partition with an explicit unknown sector while preserving zero categories', () => {
  const { container } = render(CompositionChart, {
    label: 'Sampled hours', description: 'Fixture', total: 4, unit: 'h',
    slices: [{ label: 'Useful', value: 2 }, { label: 'Not useful', value: 0 }, { label: 'Unknown', value: 2 }],
  });
  expect(container.querySelectorAll('circle')).toHaveLength(2);
  expect(container.querySelector('circle')!.getAttribute('stroke-dasharray')).toBe('50 50');
  expect(container.querySelector('circle')!.getAttribute('stroke-dashoffset')).toBe('0');
  expect(container.textContent).toContain('Not useful: 0 h');
  expect(container.textContent).toContain('Unknown: 2 h');
});

it.each([
  [null, 4], [1, 4], [0, 0],
])('does not normalise missing, inconsistent or empty parts into a full pie (%s, total %s)', (value, total) => {
  const { container } = render(CompositionChart, {
    label: 'Incomplete', description: 'Fixture', total, unit: 'h',
    slices: [{ label: 'Known', value: 0 }, { label: 'Other', value }],
  });
  expect(container.querySelector('svg')).toBeNull();
  expect(container.textContent).toContain('proporzioni non disegnate');
});

it('partitions actual useful/known/unknown engine hours without conflating unknowns with failures', () => {
  const a = structuredClone(evaluationFixture) as RavenEvaluation;
  const b = structuredClone(a);
  b.metrics.known_steps = 2; b.metrics.unknown_steps = 2;
  b.metrics.useful_hours = 6; b.metrics.unknown_hours = 12;
  b.metrics.harvested_wh = null;
  const { container } = render(MissionStatistics, { evaluations: [a, b] });
  const donuts = container.querySelectorAll('.composition-chart');
  expect(donuts).toHaveLength(2);
  expect(donuts[1]!.textContent).toContain('Utili confermate: 6 h');
  expect(donuts[1]!.textContent).toContain('Note, non utili: 6 h');
  expect(donuts[1]!.textContent).toContain('Ignote: 12 h');
  expect(donuts[1]!.querySelectorAll('circle')).toHaveLength(3);
  const energy = screen.getByRole('figure', { name: 'Totali energetici A/B' });
  expect(energy.textContent).toContain('Non calcolabile / ignoto');
  expect(energy.textContent).toContain('0 Wh');
});

it('charts declared partial costs and emissions as values, never as a complete percentage breakdown', () => {
  const planning = newReportPlanning();
  planning.costs.mission_studies = 0;
  const budget: BudgetEstimate = {
    known_cost_items: 1, missing_cost_items: [], known_subtotal: 0, contingency_amount: null, total_lifecycle_cost: null,
    funding_gap: null, within_declared_funding: null, economic_feasibility: null,
    currency: 'EUR', price_base_year: 2026, basis: 'Fixture', source: 'user_estimates',
  };
  const carbon: CarbonEstimate = {
    mission: { unit: 'kg CO2e', known_phases: 1, missing_phases: [], known_subtotal_kg_co2e: 0,
      total_kg_co2e: null, phase_emissions_kg_co2e: { '0': 0, A: null, B: null, C: null, D: null, E: null, F: null },
      basis: 'Fixture', boundary: 'Fixture', source: 'user_estimates', independently_verified: false },
    document: { compact_pages: null, reference_pages: null, paper_production_kg_co2e_per_sheet: .001,
      compaction_avoided_kg_co2e: null, not_printing_avoided_kg_co2e: null, paper_factor_source: 'Fixture', paper_factor_id: 'Fixture' },
  };
  const { container } = render(PlanningStatistics, { planning, budget, carbon });
  expect(screen.getByTestId('cost-statistics').textContent).toContain('0 EUR');
  expect(screen.getByTestId('carbon-statistics').textContent).toContain('0 kg CO₂e');
  expect(container.querySelectorAll('.bar-fill')).toHaveLength(2);
  expect(container.querySelectorAll('.composition-chart')).toHaveLength(0);
});

it('does not create empty cost or emission charts when no estimates exist', () => {
  const { container } = render(PlanningStatistics, { planning: newReportPlanning() });
  expect(container.querySelector('.chart')).toBeNull();
});
