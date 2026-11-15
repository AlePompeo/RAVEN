<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ChartBox, { type Spec } from './ChartBox.svelte';
  import ExportBar from './ExportBar.svelte';
  import { formatNumber, t } from '../../i18n/i18n.svelte';
  import { chosenRateData, toJson, tradeCsv, tradeData, type AnalysisResult } from './grazing';

  let { result }: { result: AnalysisResult } = $props();

  const comp = $derived(result.compensator);
  const trade = $derived(tradeData(comp.tradeoff));
  const chosen = $derived(chosenRateData(result));
  const f = (v: number, d = 2) => formatNumber(v, { minimumFractionDigits: d, maximumFractionDigits: d });
  const tradeSpecs = $derived<Spec[]>([
    { label: t('analysis.comp.outages'), token: '--c-danger', scale: 'o' },
    { label: t('analysis.comp.deliveredSeries'), token: '--c-uplink', scale: 'd' },
  ]);
  const rateSpec = $derived<Spec[]>([{ label: t('analysis.comp.selectedRate'), token: '--c-uplink' }]);
  const knownRates = $derived(chosen.kbps.filter(Number.isFinite));
  const unknownRates = $derived(chosen.kbps.length - knownRates.length);
  const declaredPct = $derived(knownRates.length ? (100 * knownRates.filter((v) => v > 0).length) / knownRates.length : null);
</script>

<p class="small muted">
  {t('analysis.comp.help', { sigma: f(comp.sigma_db, 1) })}
</p>

<h3>{t('analysis.comp.title')}</h3>
<ChartBox
  series={tradeSpecs}
  x={trade.k}
  ys={[trade.outage, trade.data]}
  xNumeric
  xLabel={t('analysis.comp.kAxis')}
  axisLabels={{ o: t('analysis.comp.outageAxis'), d: t('analysis.comp.dataAxis') }}
  height={240}
  label={t('analysis.comp.chart')}
/>
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="table-scroll" tabindex="0" role="region" aria-label={t('analysis.comp.table')}>
  <table data-testid="tradeoff-table">
    <caption>{t('analysis.comp.caption', { k: f(comp.k) })}</caption>
    <thead>
      <tr>
        <th scope="col">k</th><th scope="col">Backoff (dB)</th><th scope="col">{t('analysis.comp.declaredSteps')}</th><th scope="col">{t('analysis.comp.outages')}</th>
        <th scope="col">{t('analysis.comp.gaussianOutages')}</th><th scope="col">{t('analysis.comp.relativeData')}</th><th scope="col">{t('analysis.comp.meanRate')}</th>
      </tr>
    </thead>
    <tbody>
      {#each [...comp.tradeoff].sort((a, b) => a.k - b.k) as r (r.k)}
        <tr class:chosen={r.k === comp.k}>
          <th scope="row">{f(r.k)}{r.k === comp.k ? ` (${t('analysis.comp.selected')})` : ''}</th><td class="num">{f(r.backoff_db)}</td><td class="num">{r.declared_steps}</td>
          <td class="num">{f(r.outage_pct, 3)}</td><td class="num">{f(r.gaussian_outage_pct, 3)}</td>
          <td class="num">{r.relative_data === null ? '—' : f(100 * r.relative_data, 1)}</td><td class="num">{f(r.mean_rate_bps / 1e3, 1)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<p class="small summary" role="status">
  {t('analysis.comp.summary', { k: f(comp.k), outages: f(comp.chosen.outage_pct, 3), steps: comp.chosen.declared_steps,
    data: comp.chosen.relative_data === null ? t('analysis.comp.undefined') : t('analysis.comp.reference', { percent: f(100 * comp.chosen.relative_data, 1) }) })}
</p>
<ExportBar name="raven-compensatore-k" csv={() => tradeCsv(comp.tradeoff)} json={() => toJson(comp)} />

<h3>{t('analysis.comp.rateTitle')}</h3>
<ChartBox
  series={rateSpec}
  x={chosen.time}
  ys={[chosen.kbps]}
  axisLabels={{ y: 'kbit/s' }}
  height={220}
  label={t('analysis.comp.rateChart')}
/>
<p class="small summary" role="status">
  {#if declaredPct === null}
    {t('analysis.comp.noKnown', { unknown: unknownRates })}
  {:else}
    {t('analysis.comp.declaredSummary', { percent: f(declaredPct, 1), known: knownRates.length, unknown: unknownRates })}
  {/if}
</p>
<ExportBar
  name="raven-velocita-scelta"
  csv={() => 'time_unix,chosen_rate_kbps\n' + Array.from(chosen.time, (t, i) => `${t},${Number.isNaN(chosen.kbps[i]) ? '' : chosen.kbps[i]}`).join('\n') + '\n'}
  json={() => toJson({ time_unix: Array.from(chosen.time), chosen_rate_kbps: Array.from(chosen.kbps, (v) => (Number.isNaN(v) ? null : v)) })}
/>

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .summary {
    margin: var(--space-3) 0;
  }
  tr.chosen th,
  tr.chosen td {
    font-weight: 700;
  }
  td,
  th {
    padding-right: var(--space-3);
  }
</style>
