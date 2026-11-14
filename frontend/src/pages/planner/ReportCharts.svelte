<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Selected report charts, each titled with the question it answers, A and B overlaid on common axes. -->
<script lang="ts">
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { reportCharts } from './reportCharts';
  import OverlayChart from './OverlayChart.svelte';
  import type { ReportChart } from './reportCharts';
  let { evaluations, ids }: { evaluations: readonly RavenEvaluation[]; ids?: readonly ReportChart['id'][] } = $props();
  const charts = $derived(reportCharts(evaluations).filter((chart) => !ids || ids.includes(chart.id)));
</script>

<div class="rp-charts" data-testid="report-charts">
  {#each charts as chart (chart.id)}<OverlayChart {chart} />{/each}
</div>
