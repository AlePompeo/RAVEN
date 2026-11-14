<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Totals on TWO lines: what the user declared, and the total including the RAVEN estimates as a range. The estimate is a class
     scenario (mission-class slider), never a quote; a quantity without a source is not shown (it is in the checklist of part 4). -->
<script lang="ts">
  import { nf, rt } from './reportText';
  import { costTotals, co2Totals, type Band, type TotalLines } from './estimates/totals';
  import { DEFAULT_MISSION_CLASS } from './estimates/missionClass';
  import { activeEstimates, type EngineEstimate } from './estimates';
  import type { BudgetEstimate, CarbonEstimate } from './reportPlanning';
  let { budget = null, carbon = null, estimates, missionClass, expert = true }: {
    expert?: boolean;
    budget?: BudgetEstimate | null; carbon?: CarbonEstimate | null; estimates: readonly EngineEstimate[] | undefined; missionClass?: string;
  } = $props();
  const cost = $derived(costTotals(budget, estimates));
  const co2 = $derived(co2Totals(carbon, estimates));
  const cls = $derived(missionClass ?? DEFAULT_MISSION_CLASS);
  const active = $derived(activeEstimates(estimates));
  // number and unit apart, so that a range reads "47 – 118 M USD" (the unit once)
  const scale = (which: 'cost' | 'co2', unit: string, ref: number) =>
    which === 'cost' ? (unit === 'USD' && ref >= 1e6 ? { div: 1e6, unit: 'M USD' } : { div: 1, unit })
      : (ref >= 1000 ? { div: 1000, unit: 't CO2e' } : { div: 1, unit: 'kg CO2e' });
  const digits = (v: number) => nf(v, { maximumFractionDigits: v < 10 ? 1 : 0 });
  function one(v: number, which: 'cost' | 'co2', unit: string) { const s = scale(which, unit, v); return `${digits(v / s.div)} ${s.unit}`; }
  function band(b: Band, which: 'cost' | 'co2', unit: string): string {
    const ref = b.max ?? b.min ?? b.typical ?? 0;
    const s = scale(which, unit, ref);
    const n = (v: number) => digits(v / s.div);
    if (b.min !== null && b.max !== null) return `${n(b.min)} – ${n(b.max)} ${s.unit}${b.typical === null ? '' : ` (${rt('tot.typical')} ${n(b.typical)})`}`;
    if (b.min !== null) return `≥ ${n(b.min)} ${s.unit}`;
    return b.typical !== null ? `${n(b.typical)} ${s.unit}` : rt('unknown');
  }
  const fmt = one;
  const rows = $derived([
    { id: 'cost', label: rt('tot.cost'), t: cost as TotalLines, show: cost.declared !== null || cost.including !== null },
    { id: 'co2', label: rt('tot.co2'), t: co2 as TotalLines, show: co2.declared !== null || co2.including !== null },
  ] as const);
</script>

{#if active.length && rows.some((r) => r.show)}
  <div class="rp-totals" data-testid="report-totals">
    <h4 class="rp-means">{rt('tot.title')}</h4>
    <table class="rp-risktable">
      <thead><tr><th scope="col"></th><th scope="col">{rt('tot.declared')}</th><th scope="col">{rt(expert ? 'tot.including' : 'tot.includingShort')}</th></tr></thead>
      <tbody>
        {#each rows.filter((r) => r.show) as r}
          <tr data-total={r.id}><th scope="row">{r.label}</th>
            <td>{r.t.declared === null ? rt('tot.none') : fmt(r.t.declared, r.id, r.t.unit)}</td>
            <td>{r.t.including === null ? (r.t.note ? rt(`tot.note.${r.t.note}`) : rt('unknown')) : band(r.t.including, r.id, r.t.unit)}</td></tr>
        {/each}
      </tbody>
    </table>
    {#if expert}<p class="rp-how">{rt('tot.est', { cls: rt(`tot.class.${cls}`) })}</p>{/if}
  </div>
{/if}
