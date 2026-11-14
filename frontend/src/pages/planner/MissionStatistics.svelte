<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import CompositionChart from './CompositionChart.svelte';
  import ComparisonBars from './ComparisonBars.svelte';
  let { evaluations }: { evaluations: readonly RavenEvaluation[] } = $props();
  const allZero = $derived(evaluations.length > 0 && evaluations.every((e) => e.metrics.harvested_wh === 0 && e.metrics.unmet_wh === 0));
</script>

<section data-testid="mission-statistics">
  <h3>{t('stats.missionTitle')}</h3>
  <div class="graphs">
    {#each evaluations as e, i}
      <CompositionChart label={t('stats.partitionTitle', { scenario: i === 0 ? 'A' : 'B', site: e.site.name })}
        description={t('stats.partitionScope')} unit="h" total={e.window.n_steps * (e.window.step_min / 60)}
        slices={[
          { label: t('stats.confirmedUseful'), value: e.metrics.useful_hours },
          { label: t('stats.confirmedNotUseful'), value: e.metrics.known_steps * (e.window.step_min / 60) - e.metrics.useful_hours },
          { label: t('stats.unknownTime'), value: e.metrics.unknown_hours },
        ]} />
    {/each}
    {#if allZero}<p class="energy-comparison note" data-testid="energy-all-zero">{t('stats.energyAllZero')}</p>{:else}<div class="energy-comparison">
      <ComparisonBars label={t('stats.energyTitle')} description={t('stats.energyScope')} unit="Wh"
        series={evaluations.map((_e, i) => i === 0 ? 'A' : 'B')}
        rows={[
          { label: t('planner.energyHarvested'), values: evaluations.map((e) => e.metrics.harvested_wh) },
          { label: t('stats.unmetEnergy'), values: evaluations.map((e) => e.metrics.unmet_wh) },
        ]} />
    </div>{/if}
  </div>
</section>

<style>
  .graphs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem 1.5rem; }
  .energy-comparison { grid-column: 1 / -1; min-width: 0; }
  @media (max-width: 650px) { .graphs { grid-template-columns: 1fr; } }
</style>
