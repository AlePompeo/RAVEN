<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 3: sustainability and cost, computed by the RAVEN core (GET /api/raven/report/estimate) and by the engine results.
     Three charts, each titled with the question it answers. A bound with no source is "unknown", never zero. -->
<script lang="ts">
  import { nf, rt } from './reportText';
  import type { RavenEconomics, RavenEvaluation } from '../../shell/ravenApi';
  import RangeChart from './RangeChart.svelte';
  import type { RangeRow } from './rangeRow';
  import ComparisonBars from './ComparisonBars.svelte';
  let { evaluations, economics, expert = true }: { evaluations: readonly RavenEvaluation[]; economics: RavenEconomics | null; expert?: boolean } = $props();

  const co2 = $derived(economics?.co2e ?? null);
  const co2Rows = $derived<RangeRow[]>(co2 ? [
    ...(co2.launch ? [{ label: rt('sus.row.launch'), ...co2.launch }] : []),
    { label: rt('sus.row.production'), ...co2.production },
    ...(co2.total ? [{ label: rt('sus.row.total'), ...co2.total, highlight: true }] : []),
  ] : []);
  const costRows = $derived<RangeRow[]>(economics ? economics.context.map((c) => ({
    label: rt(`sus.class.${c.mission_class}`), ...c.cost, highlight: c.mission_class === economics.mission_class })) : []);
  const names = $derived(evaluations.map((e, i) => `${i === 0 ? 'A' : 'B'}: ${e.site.name}`));
  const harvested = $derived(evaluations.map((e) => (e.metrics.harvested_wh === null ? null : e.metrics.harvested_wh / 1000)));
  // typical CO2e of the mission (total when known, else the launch alone) over the confirmed useful hours of the window
  const typicalT = $derived(co2?.total?.typical ?? co2?.launch?.typical ?? null);
  const perHour = $derived(evaluations.map((e) => (typicalT === null || e.metrics.useful_hours <= 0 ? null : (typicalT * 1000) / e.metrics.useful_hours)));
  const band = (b: { min: number | null; typical: number | null; max: number | null }, unit: string) =>
    b.min === null && b.typical === null && b.max === null ? rt('unknown')
      : b.min === null && b.max === null ? `${nf(b.typical!)} ${unit}`
      : `${b.min === null ? rt('unknown') : nf(b.min)} – ${b.max === null ? rt('unknown') : nf(b.max)} ${unit}${b.typical === null ? '' : ` (${rt('tot.typical')} ${nf(b.typical)})`}`;
</script>

<div class="rp-sust" data-testid="report-sustainability">
  <p class="rp-how">{rt(expert ? 'sus.intro' : 'sus.intro.short')}</p>
  {#if !economics}
    <p role="status" class="rp-how">{rt('sus.pending')}</p>
  {:else}
    <RangeChart title={rt('sus.q.co2')} unit={economics.co2e.unit} description={rt('sus.d.co2')} rows={co2Rows} compact={!expert} />

    {#if expert && evaluations.length}
      <h4 class="rp-means">{rt('sus.q.site')}</h4>
      <ComparisonBars label={rt('sus.series.harvest')} unit={rt('sus.unit.kwh')} description={rt('sus.d.harvest')} series={names}
        rows={[{ label: ' ', values: harvested }]} />
      <ComparisonBars label={rt('sus.series.perhour')} unit={rt('sus.unit.kgh')} description={rt('sus.d.perhour')} series={names}
        rows={[{ label: ' ', values: perHour }]} />
    {/if}

    <RangeChart title={rt('sus.q.cost')} unit={economics.cost.unit} description={rt('sus.d.cost')} rows={costRows} compact={!expert} />
    {#if expert}
    <table class="rp-risktable">
      <tbody>
        <tr><th scope="row">{rt('sus.devtime')}</th><td>{band(economics.development_years, economics.development_years.unit)}</td></tr>
        <tr><th scope="row">{rt('sus.vehicle')}</th><td>{band(economics.launch_mass, economics.launch_mass.unit)}; {economics.launch_class}</td></tr>
      </tbody>
    </table>
      <table class="rp-risktable" data-testid="sustainability-sources">
        <thead><tr><th scope="col"></th><th scope="col">{rt('sus.tag')}</th><th scope="col">{rt('sus.source')}</th></tr></thead>
        <tbody>
          <tr><th scope="row">{rt('sus.q.cost')}</th><td>{economics.cost.tag}</td><td>{economics.cost.source}</td></tr>
          {#if economics.co2e.launch}<tr><th scope="row">{rt('sus.row.launch')}</th><td>{economics.co2e.launch.tag}</td><td>{economics.co2e.launch.source}</td></tr>{/if}
          <tr><th scope="row">{rt('sus.row.production')}</th><td>{economics.co2e.production.tag}</td><td>{economics.co2e.production.source}</td></tr>
        </tbody>
      </table>
    <div class="rp-limit-box"><ul>{#each economics.limits as limit}<li>{limit}</li>{/each}</ul></div>
    {/if}
  {/if}
</div>
