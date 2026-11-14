// SPDX-License-Identifier: Apache-2.0
// Step 4: power budget (only existing engine numbers) and mass estimate (only with the declared, editable tag-I defaults).
import type { RavenEvaluation } from '../../../shell/ravenApi';
import { defaultMassDefaults, massDefaultsIssue, type Cell, type Draft, type EstimateItem, type MassDefaults } from './types';

const label = (i: number) => (i === 0 ? 'A' : 'B');
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const r1 = (n: number) => Math.round(n * 10) / 10;
const r3 = (n: number) => Math.round(n * 1000) / 1000;
const withUnit = (v: unknown, unit: string): Cell => finite(v) ? `${r3(v)} ${unit}` : null;

export function powerDrafts(evaluations: readonly RavenEvaluation[]): Draft[] {
  if (!evaluations.length) return [];
  const items: EstimateItem[] = [];
  evaluations.forEach((e, i) => {
    const s = label(i), path = `evaluations[${i}]`, en = e.parameters_used?.energy ?? {};
    const row = (what: string, value: Cell, source: string, note: Cell = null) =>
      items.push({ id: `PWR-${s}-${String(items.length + 1).padStart(2, '0')}`, cells: { scenario: s, quantity: { key: `est.pwr.${what}` }, value, source, note } });
    row('survival', withUnit(en.survival_load_w, 'W'), `${path}.parameters_used.energy.survival_load_w`);
    row('active', withUnit(en.active_load_w, 'W'), `${path}.parameters_used.energy.active_load_w`);
    const gen = (e.steps?.gen_w ?? []).filter(finite);
    row('peak_generation', gen.length ? `${r3(Math.max(...gen))} W` : null, `${path}.steps.gen_w`, gen.length ? null : { key: 'est.unknown' });
    row('harvested', withUnit(e.metrics.harvested_wh, 'Wh'), `${path}.metrics.harvested_wh`,
      e.metrics.min_soc_scope !== 'all steps' ? { key: 'est.pwr.prefixNote' } : null);
    row('unmet', withUnit(e.metrics.unmet_wh, 'Wh'), `${path}.metrics.unmet_wh`);
    row('battery', withUnit(en.battery_capacity_wh, 'Wh'), `${path}.parameters_used.energy.battery_capacity_wh`);
    const usable = finite(en.battery_capacity_wh) && finite(en.min_soc) ? en.battery_capacity_wh * (1 - en.min_soc) : null;
    row('usable', usable === null ? null : `${r3(usable)} Wh`, `battery_capacity_wh × (1 − min_soc)`);
    const hours = usable !== null && finite(en.survival_load_w) && en.survival_load_w > 0 ? usable / en.survival_load_w : null;
    row('autonomy', hours === null ? null : `${r1(hours)} h`, 'usable / survival_load_w', { key: 'est.pwr.autonomyNote' });
    row('min_soc', finite(e.metrics.min_soc) ? `${r1(e.metrics.min_soc * 100)} %` : null, `${path}.metrics.min_soc`, e.metrics.min_soc_scope);
  });
  return [{
    id: 'est.power', field: 'mass_and_power_budgets', method_id: 'raven.power_rollup.v1',
    source: 'RAVEN engine energy configuration and results (/api/raven/evaluate); arithmetic on existing numbers only', tag: 'D', range: null, items,
    inputs_used: evaluations.map((e, i) => ({ name: `evaluations[${i}].parameters_used.energy`, value: JSON.stringify(e.parameters_used?.energy ?? null) })),
    validity_limits: ['est.limit.pwr.scope', 'est.limit.pwr.prefix'],
  }];
}

export function massDrafts(evaluations: readonly RavenEvaluation[], given: MassDefaults | undefined): Draft[] {
  // Automatic with the declared tag-I defaults; the user can switch it off or edit the densities (the user's choice wins).
  const defaults = given ?? { ...defaultMassDefaults(), applied: true };
  if (!defaults?.applied || massDefaultsIssue(defaults)) return [];
  const out: Draft[] = [];
  evaluations.forEach((e, i) => {
    const area = e.parameters_used?.energy.array_area_m2, cap = e.parameters_used?.energy.battery_capacity_wh;
    if (!finite(area) || !finite(cap) || area <= 0 || cap <= 0) return;
    const d = defaults;
    const total = (a: number, wh: number, radio: number, structure: number) => {
      const array = area * a, battery = cap / wh, modelled = (array + battery) / (1 - radio - structure);
      return { array, battery, radio: modelled * radio, structure: modelled * structure, modelled };
    };
    const lo = total(d.arrayKgPerM2.min, d.batteryWhPerKg.max, d.radioFraction.min, d.structureFraction.min);
    const ty = total(d.arrayKgPerM2.typical, d.batteryWhPerKg.typical, d.radioFraction.typical, d.structureFraction.typical);
    const hi = total(d.arrayKgPerM2.max, d.batteryWhPerKg.min, d.radioFraction.max, d.structureFraction.max);
    const s = label(i);
    const band = (k: keyof typeof lo): Cell => `${r1(lo[k])} – ${r1(hi[k])} kg (typ. ${r1(ty[k])})`;
    const items: EstimateItem[] = (['array', 'battery', 'radio', 'structure', 'modelled'] as const).map((k, n) => ({
      id: `MASS-${s}-${n + 1}`, cells: { scenario: s, quantity: { key: `est.mass.${k}` }, value: band(k), tag: 'I' } }));
    out.push({ id: `est.mass.${s}`, field: 'mass_and_power_budgets', method_id: 'raven.mass_density_defaults.v1',
      source: 'Declared density and fraction defaults (tag I, illustrative, editable) applied to the engine energy configuration',
      tag: 'I', range: { unit: 'kg', min: r1(lo.modelled), typical: r1(ty.modelled), max: r1(hi.modelled) }, items,
      inputs_used: [
        { name: `evaluations[${i}].parameters_used.energy.array_area_m2`, value: area }, { name: `evaluations[${i}].parameters_used.energy.battery_capacity_wh`, value: cap },
        { name: 'default.array_kg_per_m2 (min/typ/max)', value: `${d.arrayKgPerM2.min}/${d.arrayKgPerM2.typical}/${d.arrayKgPerM2.max}`, tag: 'I' },
        { name: 'default.battery_wh_per_kg (min/typ/max)', value: `${d.batteryWhPerKg.min}/${d.batteryWhPerKg.typical}/${d.batteryWhPerKg.max}`, tag: 'I' },
        { name: 'default.radio_fraction (min/typ/max)', value: `${d.radioFraction.min}/${d.radioFraction.typical}/${d.radioFraction.max}`, tag: 'I' },
        { name: 'default.structure_fraction (min/typ/max)', value: `${d.structureFraction.min}/${d.structureFraction.typical}/${d.structureFraction.max}`, tag: 'I' },
      ],
      validity_limits: ['est.limit.mass.scope', 'est.limit.mass.defaults', 'est.limit.mass.notDesign'] });
  });
  return out;
}
