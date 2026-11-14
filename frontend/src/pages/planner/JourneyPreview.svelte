<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import SeriesChart from './SeriesChart.svelte';
  let { evaluations, energy }: { evaluations: RavenEvaluation[]; energy: boolean } = $props();
  let scenario = $state(0);
  let index = $state(0);
  const active = $derived(evaluations[scenario] ?? evaluations[0]!);
  const samples = $derived(active.steps!);
  const cursor = $derived(Math.min(index, samples.time_unix.length - 1));
</script>

<div data-testid="journey-preview-charts">
  <div class="choices">
    {#each evaluations as e, i}<button type="button" aria-pressed={scenario === i} onclick={() => { scenario = i; index = 0; }}>{i === 0 ? 'A' : 'B'} — {e.site.name}</button>{/each}
  </div>
  <p class="note">{t('journey.previewScope', { step: active.window.step_min })}</p>
  {#each energy ? [
    { label: t('planner.powerChart'), unit: 'W', values: samples.gen_w },
    { label: t('planner.socChart'), unit: '%', values: samples.soc.map((v) => v === null ? null : v * 100),
      description: t('planner.socChartHelp'), timeOffsetSeconds: active.window.step_min * 60 },
  ] : [
    { label: t('planner.sun'), unit: '°', values: samples.sun_el_deg },
    { label: t('planner.earth'), unit: '°', values: samples.earth_el_deg },
  ] as chart}
    <SeriesChart {...chart} times={samples.time_unix} cursorIndex={cursor} onselect={(i) => index = i}
      rangeLabel={t('planner.chartRange')} emptyLabel={t('planner.chartEmpty')} />
  {/each}
</div>

<style>
  .choices { display: flex; flex-wrap: wrap; gap: .5rem; }
  button { min-height: 44px; } button[aria-pressed='true'] { border-color: var(--c-action); }
  .note { font-size: .85rem; color: var(--c-muted); }
</style>
