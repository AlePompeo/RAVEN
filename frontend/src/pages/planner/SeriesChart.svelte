<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { minusSign, utcMinute } from './reportFormat';
  let {
    label,
    unit,
    values,
    rangeLabel,
    emptyLabel,
    cursorIndex,
    times,
    onselect,
    description,
    timeOffsetSeconds = 0,
  }: { label: string; unit: string; values: readonly (number | null)[]; rangeLabel: string; emptyLabel: string; cursorIndex?: number;
    times?: readonly number[]; onselect?: (index: number) => void; description?: string; timeOffsetSeconds?: number } = $props();

  const finite = $derived(values.filter((v): v is number => v !== null && Number.isFinite(v)));
  const min = $derived(finite.length ? Math.min(...finite) : 0);
  const max = $derived(finite.length ? Math.max(...finite) : 0);
  const low = $derived(unit === '%' ? 0 : Math.min(min, 0));
  const high = $derived(unit === '%' ? 100 : Math.max(max, 0) === low ? low + 1 : Math.max(max, 0));
  const span = $derived(high - low);
  const stamp = (time: number) => utcMinute((time + timeOffsetSeconds) * 1000);
  const text = (value: number) => formatNumber(value, Math.abs(value) > 0 && Math.abs(value) < .1
    ? { maximumSignificantDigits: 3 } : { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const tick = (value: number) => formatNumber(value, { maximumSignificantDigits: 3, notation: Math.abs(value) >= 10000 ? 'compact' : 'standard' });
  const purposeKeys: Record<string, MessageKey> = {
    W: 'planner.powerChartHelp', '%': 'planner.percentChartHelp', '°': 'planner.elevationChartHelp',
    dB: 'planner.marginChartHelp', 'bit/s': 'planner.rateChartHelp',
  };
  const purpose = $derived(description ?? (purposeKeys[unit] ? t(purposeKeys[unit]!) : ''));
  const paths = $derived.by(() => {
    const groups: { x: number; y: number }[][] = [];
    let group: { x: number; y: number }[] = [];
    values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) {
        if (group.length) groups.push(group);
        group = [];
      } else {
        group.push({ x: values.length < 2 ? 300 : (i / (values.length - 1)) * 600, y: 130 - ((v - low) / span) * 120 });
      }
    });
    if (group.length) groups.push(group);
    return groups;
  });
</script>

<figure class="chart">
  <figcaption>{label} ({unit})</figcaption>
  {#if purpose}<p class="purpose">{purpose}</p>{/if}
  {#if finite.length}
    <p>{rangeLabel}: {t('planner.rangeFromTo', { min: minusSign(text(min)), max: minusSign(text(max)), unit })}</p>
    <div class="plot">
      <div class="y-axis" aria-hidden="true"><span>{tick(high)}</span><span>{tick((high + low) / 2)}</span><span>{tick(low)}</span></div>
    <svg viewBox="-4 0 608 140" role="img" aria-label={`${label}: ${t('planner.rangeFromTo', { min: minusSign(text(min)), max: minusSign(text(max)), unit })}`} preserveAspectRatio="none">
      {#each [10, 70, 130] as y}<line class="grid-line" x1="0" x2="600" y1={y} y2={y} />{/each}
      {#each paths as group}
        {#if group.length === 1}
          <circle cx={group[0]!.x} cy={group[0]!.y} r="3" />
        {:else}
          <polyline points={group.map((p) => `${p.x},${p.y}`).join(' ')} />
        {/if}
      {/each}
      {#if cursorIndex !== undefined && values.length > 1}
        <line x1={cursorIndex / (values.length - 1) * 600} x2={cursorIndex / (values.length - 1) * 600} y1="0" y2="140" stroke="currentColor" stroke-dasharray="4 3" />
      {/if}
    </svg>
    </div>
  {:else}
    <p>{emptyLabel}</p>
  {/if}
  {#if values.length}
    <p class="axis-title">{t(times?.length ? 'planner.chartTimeAxis' : 'planner.chartSampleAxis')}</p>
    <div class="axis">
      {#if times?.length}<time>{stamp(times[0]!)}</time><time>{stamp(times.at(-1)!)}</time>
      {:else}<span>1</span><span>{values.length}</span>{/if}
    </div>
    {#if onselect && cursorIndex !== undefined}
      <input type="range" aria-label={label} min="0" max={values.length - 1} step="1" value={cursorIndex}
        disabled={values.length === 1}
        oninput={(e) => onselect?.(Number(e.currentTarget.value))} />
      <output>{times?.[cursorIndex] !== undefined ? `${stamp(times[cursorIndex]!)} · ` : ''}{values[cursorIndex] == null || !Number.isFinite(values[cursorIndex]) ? emptyLabel : `${text(values[cursorIndex]!)} ${unit}`}</output>
    {/if}
  {/if}
</figure>

<style>
  .chart { margin: 1rem 0; }
  figcaption { font-weight: 600; }
  p { color: var(--c-muted); font-size: var(--fs-small); }
  .plot { display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); gap: .4rem; }
  .y-axis { display: flex; flex-direction: column; justify-content: space-between; padding-block: .4rem; text-align: end; font-size: .75rem; color: var(--c-muted); }
  .grid-line { stroke: var(--c-hairline); stroke-dasharray: 3 4; }
  svg { display: block; width: 100%; height: 7rem; border: 1px solid var(--c-hairline); }
  polyline { fill: none; stroke: var(--c-action); stroke-width: 2; vector-effect: non-scaling-stroke; }
  circle { fill: var(--c-action); }
  .axis { display: flex; justify-content: space-between; gap: 1rem; font-size: .7rem; color: var(--c-muted); }
  .axis-title { margin-block: .4rem; }
  .axis > * { min-width: 0; max-width: 48%; overflow-wrap: anywhere; }
  .axis > :last-child { text-align: end; }
  input { width: 100%; min-height: 44px; }
  output { display: block; font-size: .8rem; overflow-wrap: anywhere; }
</style>
