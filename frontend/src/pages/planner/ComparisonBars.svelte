<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { scopedI18n } from '../../i18n/reportScope';
  const { t, formatNumber } = scopedI18n();
  let { label, unit, description, series, rows, fixedMax }: {
    label: string; unit: string; description: string; series: readonly string[];
    rows: readonly { label: string; values: readonly (number | null)[] }[]; fixedMax?: number;
  } = $props();
  const known = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);
  const finite = $derived(rows.flatMap((r) => r.values.filter(known)));
  const low = $derived(Math.min(0, ...finite));
  const high = $derived(Math.max(fixedMax ?? 0, ...finite) > low ? Math.max(fixedMax ?? 0, ...finite) : low + 1);
  const position = (v: number) => (v - low) / (high - low) * 100;
  const text = (v: number | null | undefined) => known(v)
    ? `${formatNumber(v, { maximumSignificantDigits: 4 })} ${unit}` : t('rel.chart.unknown');
  const color = (i: number) => `var(${['--c-action', '--c-power', '--c-muted'][i % 3]})`;
</script>

<figure class="chart comparison-bars" aria-label={label}>
  <figcaption>{label} ({unit})</figcaption>
  <p>{description}</p>
  <ul class="legend rp-legend-line" aria-label={t('rel.chart.legend')}>
    {#each series as name, i}<li><span class="key" style:color={color(i)} aria-hidden="true"></span>{name}</li>{/each}
  </ul>
  {#if finite.length}
    <div class="bar-axis" aria-label={t('rel.chart.scale')}>
      <span>{text(low)}</span><span>{text((low + high) / 2)}</span><span>{text(high)}</span>
    </div>
  {/if}
  {#each rows as row}
    <div class="category">
      <strong>{row.label}</strong>
      {#each series as name, i}
        {@const value = row.values[i]}
        <div class="bar-row">
          <div class="bar-track" aria-hidden="true">
            {#if finite.length}<span class="zero" style:left={`${position(0)}%`}></span>{/if}
            {#if known(value)}
              <span class="bar-fill" class:negative={value < 0} style:color={color(i)}
                style:left={`${position(Math.min(0, value))}%`} style:width={`${Math.abs(value) / (high - low) * 100}%`}></span>
            {/if}
          </div>
          <span class="value"><span class="series-name">{name}: </span>{text(value)}</span>
        </div>
      {/each}
    </div>
  {/each}
</figure>

<style>
  .chart { margin: 1rem 0; min-width: 0; print-color-adjust: exact; }
  figcaption { font-weight: 600; } p { font-size: .85rem; color: var(--c-muted); }
  .legend { display: flex; flex-wrap: wrap; gap: .3rem .8rem; list-style: none; padding: 0; font-size: .75rem; }
  .legend li { display: flex; align-items: center; gap: .3rem; min-width: 0; }
  .key { width: .8rem; height: .45rem; background: currentColor; border: 1px solid currentColor; flex-shrink: 0; }
  .category { margin-top: .5rem; } .category > strong { display: block; font-size: .8rem; overflow-wrap: anywhere; }
  .bar-row { display: grid; grid-template-columns: minmax(0, 1fr) 7rem; gap: .5rem; align-items: center; min-height: 1.15rem; }
  .bar-track { position: relative; height: .7rem; border-bottom: 1px solid var(--c-hairline); }
  .zero { position: absolute; top: -.1rem; bottom: -.1rem; border-left: 1px solid var(--c-control); }
  .bar-fill { position: absolute; top: .1rem; bottom: .1rem; background: currentColor; border-block: 1px solid currentColor; }
  .bar-fill.negative { background: repeating-linear-gradient(135deg, currentColor 0 3px, transparent 3px 5px); }
  .bar-axis { display: flex; justify-content: space-between; gap: .3rem; padding-right: 7.5rem; font-size: .7rem; color: var(--c-muted); }
  .value { font-size: .75rem; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
  .series-name { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
