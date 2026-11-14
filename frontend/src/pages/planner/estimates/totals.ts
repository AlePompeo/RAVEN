// SPDX-License-Identifier: Apache-2.0
// The two lines of every total: what the user DECLARED, and the total INCLUDING the RAVEN estimates (a range).
// The user's own value always wins: an estimate of a quantity the user declared is not added. Nothing is invented:
// without a declared value or an estimate the line is null (unknown), never zero.
import type { BudgetEstimate, CarbonEstimate } from '../reportPlanning';
import { activeEstimates, type EngineEstimate } from './types';

export interface Band { min: number | null; typical: number | null; max: number | null }
export interface TotalLines {
  unit: string;
  declared: number | null;
  /** Range of the total including RAVEN estimates; null when there is neither a declared value nor an estimate. */
  including: Band | null;
  /** Why an estimate was not added to the declared value (for example a different currency). */
  note: string | null;
}
const byId = (list: readonly EngineEstimate[], id: string) => list.find((e) => e.id === id);

/** Cost, in the user's currency when declared. The class band is in million USD and is a TOTAL: it replaces the missing items. */
export function costTotals(budget: BudgetEstimate | null, estimates: readonly EngineEstimate[] | undefined): TotalLines {
  const est = byId(activeEstimates(estimates), 'est.cost');
  const declared = budget && budget.known_cost_items > 0 ? budget.known_subtotal : null;
  const complete = !!budget && budget.known_cost_items === 9;
  const currency = budget?.currency ?? null;
  const band: Band | null = est?.range ? { min: est.range.min, typical: est.range.typical, max: est.range.max } : null;
  if (complete) return { unit: currency ?? '', declared: budget!.total_lifecycle_cost, including: { min: budget!.total_lifecycle_cost, typical: budget!.total_lifecycle_cost, max: budget!.total_lifecycle_cost }, note: null };
  if (!band) return { unit: currency ?? '', declared, including: null, note: null };
  const musd = (v: number | null) => (v === null ? null : v * 1e6);
  if (declared === null) return { unit: 'USD', declared: null, including: { min: musd(band.min), typical: musd(band.typical), max: musd(band.max) }, note: null };
  if (currency !== 'USD') return { unit: currency ?? '', declared, including: null, note: 'currency' };
  const lift = (v: number | null) => (v === null ? null : Math.max(v * 1e6, declared));
  return { unit: 'USD', declared, including: { min: lift(band.min), typical: lift(band.typical), max: lift(band.max) }, note: null };
}

/** Mission CO2e in kg. The launch estimate (phase E) is added only when the user declared no value for phase E. */
export function co2Totals(carbon: CarbonEstimate | null, estimates: readonly EngineEstimate[] | undefined): TotalLines {
  const est = byId(activeEstimates(estimates), 'est.launch_co2');
  const declared = carbon && carbon.mission.known_phases > 0 ? carbon.mission.known_subtotal_kg_co2e : null;
  const eDeclared = !!carbon && carbon.mission.phase_emissions_kg_co2e.E !== null;
  const add = est?.range && !eDeclared ? est.range : null;
  if (!add) return { unit: 'kg CO2e', declared, including: declared === null ? null : { min: declared, typical: declared, max: declared }, note: null };
  const k = (v: number | null) => (v === null ? null : v * 1000 + (declared ?? 0));
  return { unit: 'kg CO2e', declared, including: { min: k(add.min), typical: k(add.typical), max: k(add.max) }, note: null };
}
