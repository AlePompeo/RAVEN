// SPDX-License-Identifier: Apache-2.0
import { expect, it } from 'vitest';
import { paramError, toStartUtc, type ParamRow } from './lunar';

it('preserves explicit UTC seconds and rejects impossible instants', () => {
  expect(toStartUtc('2027-04-07T00:00')).toBe('2027-04-07T00:00:00Z');
  expect(toStartUtc('2027-04-07T12:34:56')).toBe('2027-04-07T12:34:56Z');
  for (const invalid of ['', '2027-02-30T00:00', '2027-04-07T25:00', '2027-04-07T12:34:60']) {
    expect(toStartUtc(invalid)).toBeNull();
  }
});

it('validates Planner numerical and enumerated parameter controls', () => {
  const row: ParamRow = { key: 'tx_power_w', group: 'link', value: 20, unit: 'W',
    min: 0.01, max: 200, status: 'I', source: 'illustrative', note: '' };
  expect(paramError(row, 20)).toBeNull();
  expect(paramError(row, 0)).toMatch(/Minimo/);
  expect(paramError(row, 201)).toMatch(/Massimo/);
  expect(paramError(row, null)).toMatch(/numero/);
  expect(paramError({ ...row, allowed: ['horizontal', 'tracking'] }, 'tracking')).toBeNull();
  expect(paramError({ ...row, allowed: ['horizontal', 'tracking'] }, 'vertical')).not.toBeNull();
});
