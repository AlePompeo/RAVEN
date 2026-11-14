// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { newReliability, illustrativeReliability, readReliability, reliabilityReady, thermalOverrides } from './reliability';
import { newReportPlanning, readReportPlanning } from './reportPlanning';
import { newReportSections, readReportSections } from './reportSections';
import type { ParamRow } from '../compare/lunar';
import ReliabilityInputs from './ReliabilityInputs.svelte';

afterEach(cleanup);

it('preserves unknowns and explicit zeros, migrates old plans, and rejects damaged bounds', () => {
  const { reliability: _reliability, ...old } = newReportPlanning();
  expect(readReportPlanning(old)?.reliability).toEqual(newReliability());
  const p = illustrativeReliability('Synthetic study');
  p.components[0]!.failure_rate_per_hour = 0;
  expect(readReliability(p)?.components[0]?.failure_rate_per_hour).toBe(0);
  p.components[0]!.failure_rate_per_hour = null;
  expect(readReliability(p)?.components[0]?.failure_rate_per_hour).toBeNull();
  p.components[0]!.thermal_min_c = 100;
  expect(readReliability(p)).toBeNull();
  p.components[0]!.thermal_min_c = -20;
  p.components[0]!.mean_recovery_hours = 1e-10;
  expect(readReliability(p)).toBeNull();
  p.components[0]!.mean_recovery_hours = 0;
  p.basis = '';
  expect(reliabilityReady(p)).toBe(false);
  p.basis = 'Declared synthetic assumptions';
  expect(reliabilityReady(p)).toBe(true);
});

it('migrates full and brief section selections without losing prior choices', () => {
  for (const brief of [false, true]) {
    const { reliability: _reliability, ...legacy } = newReportSections(brief);
    expect(readReportSections(legacy)).toEqual(newReportSections(brief));
    expect(readReportSections({ ...legacy, unexpected: true })).toBeNull();
  }
});

it('only adds explicitly enabled incremental thermal demand and rejects out-of-range totals', () => {
  const rows: ParamRow[] = ['survival_load_w', 'active_load_w'].map((key, i) => ({
    key, value: i ? 50 : 10, group: 'energy', min: 0, max: 1000, unit: 'W', status: 'I', source: 'test', note: '',
  }));
  const p = illustrativeReliability('Synthetic');
  expect(thermalOverrides(p, rows)).toEqual({});
  p.apply_thermal_load = true;
  expect(thermalOverrides(p, rows)).toEqual({ survival_load_w: 12, active_load_w: 52 });
  p.thermal_load_w = null;
  expect(thermalOverrides(p, rows)).toBeNull();
  p.thermal_load_w = 960;
  expect(thermalOverrides(p, rows)).toBeNull();
  p.enabled = false;
  expect(thermalOverrides(p, rows)).toEqual({});
});

it('requires explicit demonstration loading before populating numerical assumptions', async () => {
  render(ReliabilityInputs, { profile: newReliability() });
  expect(screen.queryByLabelText(/Tasso di guasto/)).toBeNull();
  await fireEvent.click(screen.getByRole('button', { name: /Carica ipotesi illustrative/ }));
  const basis = screen.getByLabelText('Fonte / metodo / base delle ipotesi') as HTMLTextAreaElement;
  expect(basis.value).toContain('Solo dimostrazione illustrativa');
  expect((screen.getByLabelText('Aggiungi il carico termico continuo dichiarato al calcolo energetico') as HTMLInputElement).checked).toBe(false);
});
