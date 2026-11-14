<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 2: four charts, each titled with the question it answers, A and B overlaid on common axes. -->
<script lang="ts">
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { reportCharts } from './reportCharts';
  import OverlayChart from './OverlayChart.svelte';
  let { evaluations }: { evaluations: readonly RavenEvaluation[] } = $props();
  const charts = $derived(reportCharts(evaluations));
</script>

<div class="rp-charts" data-testid="report-charts">
  {#each charts as chart (chart.id)}<OverlayChart {chart} />{/each}
</div>
