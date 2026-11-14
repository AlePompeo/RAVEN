<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Horizontal ranges (min to max, typical as a tick). A missing bound is drawn as an open (dashed) end and written "unknown";
     a row with no bound at all is written "unknown", never drawn as zero. A table is used for the layout so that the
     PDF engine (no CSS grid) draws the same figure as the browser. -->
<script lang="ts">
  import { nf, rt } from './reportText';
  import type { RangeRow } from './rangeRow';
  let { title, unit, description, rows, digits = 0, compact = false }: { title: string; unit: string; description: string; rows: readonly RangeRow[]; digits?: number; compact?: boolean } = $props();
  const vals = $derived(rows.flatMap((r) => [r.min, r.typical, r.max]).filter((v): v is number => v !== null));
  const high = $derived(vals.length ? Math.max(...vals) : 1);
  const pos = (v: number) => `${(v / high) * 100}%`;
  const text = (v: number | null) => (v === null ? rt('unknown') : nf(v, { maximumFractionDigits: digits }));
  const lo = (r: RangeRow) => r.min ?? r.typical ?? r.max;
  const hi = (r: RangeRow) => r.max ?? r.typical ?? r.min;
  const onlyTypical = (r: RangeRow) => r.min === null && r.max === null;
</script>

<figure class="rp-range" aria-label={title}>
  <figcaption>{title} ({unit})</figcaption>
  {#if !compact}<p class="rp-how">{description}</p>{/if}
  <table class="rp-rangetable">
    <tbody>
      {#each rows as r}
        {@const a = lo(r)}{@const b = hi(r)}
        <tr class:sel={r.highlight}>
          <th scope="row">{r.label}</th>
          <td class="cell"><div class="track" aria-hidden="true">
            {#if a !== null && b !== null}
              <span class="bar" class:open-start={r.min === null && !onlyTypical(r)} class:open-end={r.max === null && !onlyTypical(r)}
                style:left={pos(a)} style:width={onlyTypical(r) ? '1.5%' : `max(${pos(b - a)}, 2%)`}></span>
              {#if r.typical !== null}<span class="tick" style:left={pos(r.typical)}></span>{/if}
            {/if}
          </div></td>
          <td class="value">{#if a === null}{rt('unknown')}{:else if onlyTypical(r)}{text(r.typical)}{:else}{text(r.min)} – {text(r.max)}{r.typical !== null ? ` (${rt('tot.typical')} ${text(r.typical)})` : ''}{/if}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</figure>

<style>
  .rp-range { margin: 1rem 0; min-width: 0; print-color-adjust: exact; break-inside: avoid; }
  figcaption { font-weight: 600; }
  .rp-rangetable { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: .85rem; }
  .rp-rangetable th { width: 28%; text-align: left; font-weight: 600; padding: .25rem .4rem .25rem 0; overflow-wrap: anywhere; }
  .rp-rangetable td.cell { width: 34%; padding: .25rem .5rem; }
  .rp-rangetable td.value { width: 38%; font-variant-numeric: tabular-nums; padding: .25rem 0; }
  tr.sel th { text-decoration: underline; text-underline-offset: 3px; }
  .track { position: relative; height: .8rem; border-bottom: 1px solid var(--c-hairline); }
  .bar { position: absolute; top: .15rem; bottom: .15rem; background: var(--c-action); border: 1px solid var(--c-action); }
  .bar.open-end { background: repeating-linear-gradient(90deg, var(--c-action) 0 4px, transparent 4px 7px); }
  .bar.open-start { background: repeating-linear-gradient(270deg, var(--c-action) 0 4px, transparent 4px 7px); }
  .tick { position: absolute; top: -.05rem; bottom: -.05rem; border-left: 2px solid var(--c-power); }
</style>
