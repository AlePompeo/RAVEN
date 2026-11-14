<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Lunar-day view: the window cut in synodic months from its start; for each lunar day the sunlight share, the Earth share and the
     useful hours of A and B, as a table with an inline bar in every cell (compact on the page and in the PDF; no CSS grid).
     Shown only when the window is at least 20 days long (a shorter window is a fraction of one lunar day). -->
<script lang="ts">
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { lunarDays, type LunarDay } from './visibilityStats';
  let { evaluations, tr, fmt }: {
    evaluations: readonly RavenEvaluation[]; tr: (key: string, params?: Record<string, string | number>) => string; fmt: (v: number, digits?: number) => string;
  } = $props();
  const tags = $derived(evaluations.map((_, i) => (i === 0 ? 'A' : 'B')));
  const days = $derived(evaluations.map(lunarDays));
  const total = $derived(Math.max(0, ...days.map((d) => d.reduce((a, x) => a + x.days, 0))));
  const n = $derived(Math.max(0, ...days.map((d) => d.length)));
  const show = $derived(evaluations.length > 0 && total >= 20);
  const maxUseful = $derived(Math.max(1, ...days.flatMap((d) => d.map((x) => x.usefulH))));
  const lenOf = (k: number) => days.map((x) => x[k]).find((x): x is LunarDay => !!x);
  const cols = [
    { key: 'lun.useful', pick: (d: LunarDay) => d.usefulH, unit: 'h', scale: () => maxUseful },
    { key: 'lun.sun', pick: (d: LunarDay) => d.litPct, unit: '%', scale: () => 100 },
    { key: 'lun.earth', pick: (d: LunarDay) => d.earthPct, unit: '%', scale: () => 100 },
  ];
</script>

{#if show}
  <div class="lun" data-testid="lunar-days">
    <h4 class="rp-means">{tr('lun.title')}</h4>
    <table class="rp-risktable rp-luntable">
      <thead>
        <tr><th scope="col" rowspan="2"></th>{#each cols as c}<th scope="colgroup" colspan={tags.length}>{tr(c.key)}</th>{/each}</tr>
        <tr>{#each cols as c}{#each tags as g}<th scope="col">{g}</th>{/each}{/each}</tr>
      </thead>
      <tbody>
        {#each Array.from({ length: n }, (_, k) => k) as k}
          {@const d0 = lenOf(k)}
          <tr>
            <th scope="row">{tr('lun.row', { n: k + 1, days: d0 ? fmt(d0.days, d0.days < 10 ? 1 : 0) : '' })}</th>
            {#each cols as c}{#each days as dd, gi}
              {@const v = dd[k] ? c.pick(dd[k]!) : null}
              <td class={gi === 0 ? 'ga' : 'gb'}>
                {#if v === null}{tr('vis.unknown')}{:else}
                  <span class="bar" style:width={`${Math.max(1, Math.min(100, (v / c.scale()) * 100)) * 0.6}%`}></span>
                  <span class="num">{fmt(v, c.unit === 'h' ? 0 : 0)}{c.unit}</span>
                {/if}
              </td>
            {/each}{/each}
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="note">{tr('lun.desc')}</p>
  </div>
{/if}

<style>
  .lun { margin-block: 1.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: .85rem; table-layout: fixed; }
  th, td { text-align: left; padding: .3rem .4rem; border-bottom: 1px solid #7b9cb34d; vertical-align: middle; overflow-wrap: anywhere; }
  .bar { display: inline-block; height: .6rem; vertical-align: middle; margin-right: .3rem; }
  .ga .bar { background: #0b5cad; } .gb .bar { background: #a15c00; }
  .num { font-variant-numeric: tabular-nums; }
  .note { color: var(--c-muted); font-size: .85rem; }
</style>
