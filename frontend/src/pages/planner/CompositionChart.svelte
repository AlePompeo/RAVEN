<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { scopedI18n } from '../../i18n/reportScope';
  const { t, formatNumber } = scopedI18n();
  let { label, description, total, unit, slices }: {
    label: string; description: string; total: number; unit: string;
    slices: readonly { label: string; value: number | null }[];
  } = $props();
  const sum = $derived(slices.reduce((sum, s) => sum + (s.value ?? 0), 0));
  const complete = $derived(Number.isFinite(total) && total > 0 &&
    slices.every((s) => s.value !== null && Number.isFinite(s.value) && s.value >= 0) &&
    Math.abs(sum - total) <= Math.max(total, 1) * 1e-9);
  const text = (v: number | null) => v === null || !Number.isFinite(v) ? t('rel.chart.unknown') : formatNumber(v, { maximumSignificantDigits: 4 });
  const color = (i: number) => `var(${['--c-success', '--c-power', '--c-muted'][i % 3]})`;
  const offset = (index: number) => -slices.slice(0, index).reduce((sum, s) => sum + (s.value ?? 0), 0) / total * 100;
</script>

<figure class="chart composition-chart" aria-label={label}>
  <figcaption>{label}</figcaption>
  <p>{description}</p>
  <div class="donut-layout">
    {#if complete}
      <svg viewBox="0 0 120 120" role="img" aria-label={`${label}: ${text(total)} ${unit}`}>
        {#each slices as slice, i}
          {#if slice.value !== null && slice.value > 0}
            <circle cx="60" cy="60" r="44" pathLength="100" fill="none" stroke={color(i)} stroke-width="12"
              stroke-dasharray={`${slice.value / total * 100} ${100 - slice.value / total * 100}`}
              stroke-dashoffset={offset(i)} transform="rotate(-90 60 60)" />
          {/if}
        {/each}
        <text x="60" y="58" text-anchor="middle">{text(total)}</text>
        <text x="60" y="74" text-anchor="middle">{unit}</text>
      </svg>
    {:else}<p class="status">{t('stats.noPartition')}</p>{/if}
    <ul class="legend">
      {#each slices as slice, i}
        <li><span class="key" style:color={color(i)} aria-hidden="true"></span>
          <span>{slice.label}: <strong>{text(slice.value)} {unit}</strong>
            {#if complete && slice.value !== null} · {text(slice.value / total * 100)}%{/if}
          </span>
        </li>
      {/each}
    </ul>
  </div>
</figure>

<style>
  .chart { margin: 1rem 0; min-width: 0; print-color-adjust: exact; }
  figcaption { font-weight: 600; } p { font-size: .85rem; color: var(--c-muted); }
  .donut-layout { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
  svg { display: block; width: 8rem; height: 8rem; max-width: 100%; flex-shrink: 0; }
  text { fill: currentColor; font-size: 13px; font-variant-numeric: tabular-nums; }
  .legend { flex: 1; min-width: 7rem; list-style: none; padding: 0; margin: 0; font-size: .8rem; }
  li { display: flex; gap: .4rem; margin-block: .4rem; } .key { width: .7rem; height: .7rem; background: currentColor; flex-shrink: 0; margin-top: .2rem; }
</style>
