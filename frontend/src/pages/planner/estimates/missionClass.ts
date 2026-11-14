// SPDX-License-Identifier: Apache-2.0
// "Mission class" slider: four named positions that feed RAVEN estimates of cost, development time, vehicle mass, launch class,
// launch CO2 and launch/landing statistics. Every number is read from a public source listed in docs/domain/scenario-archetypes.md
// (secondary sources, NOT checked against the primary NASA documents) or is an explicit tag-I assumption. A quantity with no
// adequate source is NOT produced: it stays unknown and is listed once in the "owner only / no source" checklist.
// These are class scenarios, not an estimate of the user's own mission and not a quote. A value the user declares always wins.
import type { Draft, EstimateItem, EstimateRange } from './types';

export const MISSION_CLASS_IDS = ['rover', 'small_lander', 'medium_lander', 'large_lander'] as const;
export type MissionClassId = typeof MISSION_CLASS_IDS[number];
export const DEFAULT_MISSION_CLASS: MissionClassId = 'small_lander';
export const parseMissionClass = (v: unknown): MissionClassId | null => (MISSION_CLASS_IDS as readonly unknown[]).includes(v) ? v as MissionClassId : null;

type R = { min: number | null; typical: number | null; max: number | null } | null;
interface ClassData {
  cost: R;          // million USD, NASA award values (nominal, 2019-2023), not the provider's own cost
  years: R;         // development time, award to launch
  wetKg: R;         // mass at launch
  massTag: 'D' | 'I';
  launch: string;   // launch class (vehicle names as in the sources)
  co2Vehicle: 'falcon9' | 'falconheavy' | 'newglenn' | null;
  launchStat: { ok: number; n: number; label: string }[];
}
const m = (min: number | null, typical: number | null, max: number | null): R => ({ min, typical, max });

export const CLASS_DATA: Record<MissionClassId, ClassData> = {
  // rover/payload: no adequate public source for cost, time, mass; mass 50-150 kg is an illustrative assumption (tag I)
  rover: { cost: null, years: null, wetKg: m(50, null, 150), massTag: 'I', launch: 'passenger of a lander (see small lander)', co2Vehicle: null, launchStat: [] },
  // CLPS small landers: IM-1 118, IM-2 47, Blue Ghost 1 93.3, Peregrine 108, IM-3 77.5, Blue Ghost 2 112 (median 100.65);
  // development 3.92, 4.33, 4.58, 4.71 years (median 4.455); launch mass 1283, 1517, 1900 kg
  small_lander: { cost: m(47, 100.65, 118), years: m(3.92, 4.455, 4.71), wetKg: m(1283, 1517, 1900), massTag: 'D', launch: 'Falcon 9 Block 5 or Vulcan',
    co2Vehicle: 'falcon9', launchStat: [{ ok: 698, n: 701, label: 'Falcon 9, all flights' }, { ok: 644, n: 645, label: 'Falcon 9 Block 5' }] },
  // Griffin Mission One: 199.5 M USD award (one value), launch mass 1265 kg; Blue Moon Mark 1: 21,350 kg; Griffin in development > 6.5 years
  medium_lander: { cost: m(null, 199.5, null), years: m(6.5, null, null), wetKg: m(1265, null, 21350), massTag: 'D', launch: 'Falcon Heavy or New Glenn',
    co2Vehicle: 'falconheavy', launchStat: [{ ok: 2, n: 3, label: 'New Glenn' }] },
  // Blue Moon Mark 2: dry 16,000 kg, over 45,000 kg at launch; HLS awards ~2.89 to ~3.4 billion USD (one source reports 7, unresolved)
  large_lander: { cost: m(2890, null, 3400), years: null, wetKg: m(45000, null, null), massTag: 'D', launch: 'New Glenn (7 m fairing) or Starship class',
    co2Vehicle: 'newglenn', launchStat: [{ ok: 2, n: 3, label: 'New Glenn' }] },
};

const r1 = (n: number) => Math.round(n * 10) / 10;
const rangeOf = (unit: string, d: R): EstimateRange | null => d && (d.min !== null || d.typical !== null || d.max !== null) ? { unit, ...d } : null;
const band = (d: R, unit: string): string => {
  if (!d) return 'unknown';
  if (d.min !== null && d.max !== null) return `${d.min} – ${d.max} ${unit}${d.typical === null ? '' : ` (typ. ${d.typical})`}`;
  if (d.min !== null) return `at least ${d.min} ${unit}`;
  return d.typical !== null ? `${d.typical} ${unit} (one value, no spread)` : 'unknown';
};
const SRC = 'docs/domain/scenario-archetypes.md (secondary sources: Wikipedia pages of CLPS, Nova-C, Peregrine, Blue Ghost, Griffin, Blue Moon, read 9 Nov 2026; not checked against primary NASA documents)';

// ---- launch CO2 from the propellant burned: tank capacities (Wikipedia Falcon 9 Block 5 and Falcon Heavy, read 12 Nov 2026) ----
// CO2 = fuel burned x carbon fraction x 44.01 / 12.011 (RP-1) or fuel burned x 44.01 / 16.04 (methane). LOX, hydrogen: no CO2.
// Burned share 0.85-1.00 (tank capacity is not the loaded mass; a recovered booster keeps some) and carbon fraction 0.85-0.87 are tag I.
const CO2_PER_C = 44.01 / 12.011;
const CO2_PER_CH4 = 44.01 / 16.04;
interface Co2Vehicle { name: string; fuel: string; fuelT: { min: number; max: number }; perKg: { min: number; max: number }; note: string }
export const CO2_VEHICLES: Record<'falcon9' | 'falconheavy' | 'newglenn', Co2Vehicle> = {
  falcon9: { name: 'Falcon 9', fuel: 'RP-1', fuelT: { min: 123.5 + 32.3, max: 123.5 + 32.3 },
    perKg: { min: 0.85 * CO2_PER_C, max: 0.87 * CO2_PER_C }, note: 'RP-1 tank capacity 123.5 t (stage 1) + 32.3 t (stage 2)' },
  falconheavy: { name: 'Falcon Heavy', fuel: 'RP-1', fuelT: { min: 3 * 123.5 + 32.3, max: 3 * 123.5 + 32.3 },
    perKg: { min: 0.85 * CO2_PER_C, max: 0.87 * CO2_PER_C }, note: 'RP-1 tank capacity 3 x 123.5 t (cores) + 32.3 t (stage 2)' },
  newglenn: { name: 'New Glenn', fuel: 'liquid methane (stage 1 only; the hydrogen second stage emits no CO2)', fuelT: { min: 710 * 0.40, max: 710 * 0.43 },
    perKg: { min: CO2_PER_CH4, max: CO2_PER_CH4 }, note: 'methane tank volume 710 m3 x 0.40-0.43 t/m3 (density: assumption, not read from a source)' },
};
export function launchCo2T(id: keyof typeof CO2_VEHICLES): { min: number; typical: number; max: number } {
  const v = CO2_VEHICLES[id];
  const lo = v.fuelT.min * 0.85 * v.perKg.min, hi = v.fuelT.max * 1.0 * v.perKg.max;
  const ty = ((v.fuelT.min + v.fuelT.max) / 2) * 0.95 * ((v.perKg.min + v.perKg.max) / 2);
  return { min: Math.round(lo), typical: Math.round(ty), max: Math.round(hi) };
}

const row = (id: string, quantity: string, value: string, source: string): EstimateItem => ({ id, cells: { quantity, value, source } });

export function classDrafts(id: MissionClassId): Draft[] {
  const d = CLASS_DATA[id];
  const inputs = [{ name: 'mission_class', value: id, tag: 'I' }];
  const out: Draft[] = [];
  // cost
  out.push({ id: 'est.cost', field: 'economic_feasibility', method_id: 'raven.class_cost_band.v1', source: SRC, tag: 'D',
    range: rangeOf('M USD', d.cost), inputs_used: inputs,
    items: [row('COST-1', 'Total mission cost band (million USD, NASA award values 2019-2023, not inflation-adjusted)', band(d.cost, 'M USD'),
      d.cost ? 'CLPS / HLS award values' : 'no adequate public source: unknown')],
    validity_limits: ['est.limit.class.award', 'est.limit.class.notQuote'] });
  // development time
  out.push({ id: 'est.devtime', field: 'schedule', method_id: 'raven.class_dev_time.v1', source: SRC, tag: 'D', range: rangeOf('years', d.years), inputs_used: inputs,
    items: [row('DEV-1', 'Development time, award to launch (years)', band(d.years, 'years'), d.years ? 'differences of award and launch dates' : 'no adequate public source: unknown')],
    validity_limits: ['est.limit.class.fewCases', 'est.limit.class.notQuote'] });
  // vehicle mass and launch class
  out.push({ id: 'est.vehicle', field: 'mass_and_power_budgets', method_id: 'raven.class_vehicle.v1', source: SRC, tag: d.massTag, range: rangeOf('kg', d.wetKg), inputs_used: inputs,
    items: [row('VEH-1', 'Mass at launch (kg)', band(d.wetKg, 'kg'), d.massTag === 'I' ? 'illustrative assumption (tag I): no public source' : 'launch masses of the reference landers'),
      row('VEH-2', 'Launch class', d.launch, 'reference missions of the class')],
    validity_limits: ['est.limit.class.notDesign', 'est.limit.class.notQuote'] });
  // launch CO2
  if (d.co2Vehicle) {
    const v = CO2_VEHICLES[d.co2Vehicle], c = launchCo2T(d.co2Vehicle);
    out.push({ id: 'est.launch_co2', field: 'environmental_footprint', method_id: 'raven.launch_co2_combustion.v1',
      source: 'Wikipedia Falcon 9 Block 5 and Falcon Heavy (tank capacities, read 12 Nov 2026); New Glenn page (tank volume); stoichiometry C + O2 -> CO2 (44.01/12.011) and CH4 + 2 O2 -> CO2 + 2 H2O (44.01/16.04)',
      tag: 'I', range: { unit: 't CO2', ...c }, inputs_used: [...inputs, { name: 'vehicle', value: v.name }, { name: 'propellant', value: v.note },
        { name: 'burned share (min/max)', value: '0.85 / 1.00', tag: 'I' }, { name: 'RP-1 carbon mass fraction (min/max)', value: '0.85 / 0.87', tag: 'I' }],
      items: [row('CO2-1', `Launch CO2 from burning the ${v.fuel} of ${v.name} (t CO2)`, `${c.min} – ${c.max} t (typ. ${c.typical})`, 'propellant mass x combustion emission factor'),
        row('CO2-2', 'Shown as CO2e', 'a lower bound: CO2 of combustion only', 'black carbon, NOx, water vapour and propellant production are not included')],
      validity_limits: ['est.limit.class.co2combustion', 'est.limit.class.notQuote'] });
  }
  // launch and landing statistics
  const landing = { min: r1(3 / 8 * 100), max: r1(5 / 8 * 100) };
  const launchRows = d.launchStat.map((s, k) => row(`STAT-${k + 1}`, `Launch success, ${s.label} (${s.n} flights)`, `${r1(s.ok / s.n * 100)} % (${s.ok} of ${s.n})`, 'Wikipedia vehicle pages, 7 Nov 2026'));
  const fracs = d.launchStat.map((s) => s.ok / s.n * 100);
  out.push({ id: 'est.stats', field: 'orbit_or_landing', method_id: 'raven.class_launch_landing_stats.v1', source: 'newspaceeconomy.ca "Moon landing attempts 2023 to 2025" (14 Jul 2025); Wikipedia vehicle pages (7 Nov 2026)',
    tag: 'D', range: { unit: '% landing success', min: landing.min, typical: null, max: landing.max }, inputs_used: inputs,
    items: [...launchRows, row('STAT-L', 'Landing success of the 8 lunar landing attempts of 2023-2025 (full success only to including partial)', `${landing.min} – ${landing.max} %`, '3 full, 2 partial, 3 failures; small sample, not class specific'),
      row('STAT-T', 'Success of the transfer to the Moon, reliability per component class', 'unknown', 'no adequate public source: listed in the owner-only / no-source checklist'),
      ...(fracs.length ? [] : [row('STAT-0', 'Launch success of the vehicle', 'unknown', 'carried by a lander: use the small lander class')])],
    validity_limits: ['est.limit.class.fewCases', 'est.limit.class.stats'] });
  return out;
}

/** Quantities with no adequate public source: they are never estimated and appear once in the report checklist. */
export const NO_SOURCE_CHECKLIST = [
  'Cost of a rover or payload; development time of the rover and large classes',
  'Cost per line item (structure, propulsion, avionics, operations)',
  'Manufacturing CO2e (no material emission factor was read from a source)',
  'Reliability per component class; probability of a successful transfer to the Moon',
  'Quotes, tests, approvals, funding and signatures: only the mission owner can declare them',
] as const;
