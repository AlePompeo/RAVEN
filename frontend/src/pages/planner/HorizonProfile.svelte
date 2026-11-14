<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { validHorizonSamples, type HorizonResult } from './horizon';

  let {
    result,
    labels,
  }: {
    result: HorizonResult;
    labels: {
      chart: string;
      table: string;
      azimuth: string;
      elevation: string;
      distance: string;
      status: string;
      ok: string;
      missing_dem: string;
      outside_coverage: string;
    };
  } = $props();

  const valid = $derived(validHorizonSamples(result.samples));
  const low = $derived(Math.floor(Math.min(0, ...valid.map((s) => s.elevation_deg ?? 0)) / 5) * 5 - 5);
  const high = $derived(Math.ceil(Math.max(0, ...valid.map((s) => s.elevation_deg ?? 0)) / 5) * 5 + 5);
  const x = (azimuth: number) => 38 + (azimuth / 360) * 552;
  const y = (elevation: number) => 10 + ((high - elevation) / (high - low)) * 120;
</script>

{#if valid.length}
  <svg viewBox="0 0 600 160" role="img" aria-label={labels.chart}>
    <line x1="38" y1="10" x2="38" y2="130" />
    <line x1="38" y1={y(0)} x2="590" y2={y(0)} />
    <text x="0" y="13">{high}°</text>
    <text x="0" y="130">{low}°</text>
    <text x="38" y="152">0°</text>
    <text x="300" y="152">180°</text>
    <text x="565" y="152">360°</text>
    {#each valid as sample (sample.azimuth_deg)}
      <circle cx={x(sample.azimuth_deg)} cy={y(sample.elevation_deg ?? 0)} r="2.5" />
    {/each}
  </svg>
{/if}
<details>
  <summary>{labels.table}</summary>
  <div class="table-wrap">
    <table>
      <thead><tr><th>{labels.azimuth}</th><th>{labels.elevation}</th><th>{labels.distance}</th><th>{labels.status}</th></tr></thead>
      <tbody>
        {#each result.samples as sample (sample.azimuth_deg)}
          <tr>
            <td>{sample.azimuth_deg}°</td>
            <td>{sample.elevation_deg === null ? '—' : `${sample.elevation_deg.toFixed(2)}°`}</td>
            <td>{sample.distance_m === null ? '—' : `${sample.distance_m.toFixed(0)} m`}</td>
            <td>{labels[sample.state]}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</details>

<style>
  svg { width: 100%; max-height: 15rem; overflow: visible; }
  line { stroke: var(--c-muted); stroke-width: 1; }
  circle { fill: var(--c-action); }
  text { fill: currentColor; font-size: 11px; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: .4rem; text-align: start; border-bottom: 1px solid var(--c-hairline); }
</style>
