<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ChartBox, { type Spec } from './ChartBox.svelte';
  import ExportBar from './ExportBar.svelte';
  import { t as translate } from '../../i18n/i18n.svelte';
  import { rateLabel, timeCsv, timeData, toJson, finiteRange, type AnalysisResult } from './grazing';

  let { result, simple = false }: { result: AnalysisResult; simple?: boolean } = $props();

  const t = $derived(timeData(result));
  const TOKENS = ['--c-uplink', '--c-power', '--c-success', '--c-danger', '--c-text', '--c-muted'];
  const elSeries: Spec[] = [
    { label: 'Terra (elevazione)', token: '--c-uplink' },
    { label: 'Cresta (elevazione)', token: '--c-power', dash: [8, 5] },
  ];
  const marginSeries = $derived<Spec[]>([
    ...result.rates_bps.map((r, j) => ({ label: rateLabel(r), token: TOKENS[j % TOKENS.length] as string, ...(j % 2 ? { dash: [6, 4] } : {}) })),
    { label: 'soglia 0 dB', token: '--c-muted', dash: [2, 4] },
  ]);
  const margin0 = $derived(finiteRange(Array.from(t.margins[result.rates_bps.indexOf(result.windows.rate_bps)] ?? [])));
  const chosenIndex = $derived(result.rates_bps.indexOf(result.windows.rate_bps));
  const stats = $derived.by(() => {
    const e = finiteRange(Array.from(t.earthEl));
    const r = finiteRange(Array.from(t.ridgeEl));
    return { e, r };
  });
  const f1 = (v: number | undefined) => (v === undefined ? '—' : v.toFixed(2).replace('.', ','));
  // tabella riassuntiva: al massimo 12 righe equispaziate
  const sample = $derived.by(() => {
    const n = t.time.length;
    const step = Math.max(1, Math.ceil(n / 12));
    return Array.from({ length: Math.ceil(n / step) }, (_, i) => i * step);
  });
</script>

{#if !simple}
<h3>Elevazione della Terra e della cresta</h3>
<p class="small muted">
  Quando la linea della Terra sta sotto quella della cresta la geometria dice «bloccato». Gradi sull’orizzonte, visti dall’antenna.
</p>
<ChartBox
  series={elSeries}
  x={t.time}
  ys={[t.earthEl, t.ridgeEl]}
  axisLabels={{ y: 'elevazione (°)' }}
  label="Grafico dell’elevazione della Terra e della cresta dominante nel tempo; i valori sono nella tabella sotto"
/>
<p class="legend-line small">
  <span class="key" style="background: var(--c-uplink)" aria-hidden="true"></span>Terra
  <span class="key key--dash" style="--k: var(--c-power)" aria-hidden="true"></span>Cresta
</p>
{/if}

<h3>{simple ? translate('analysis.simpleMargin') : 'Margine di link per velocità di trasmissione'}</h3>
<p class="small muted">{simple ? translate('analysis.simpleMarginHelp') : 'Margine = Eb/N0 disponibile meno quello richiesto (dB). Sopra 0 dB il link chiude.'}</p>
{#if !simple || chosenIndex >= 0}
<ChartBox
  series={simple ? [marginSeries[chosenIndex]!, marginSeries[marginSeries.length - 1]!] : marginSeries}
  x={t.time}
  ys={simple ? [t.margins[chosenIndex]!, t.zero] : [...t.margins, t.zero]}
  axisLabels={{ y: 'margine (dB)' }}
  label={simple ? translate('analysis.simpleMarginChart') : 'Grafico del margine di link in dB per ciascuna velocità di trasmissione nel tempo; i valori sono nella tabella sotto'}
/>
{:else}
  <p role="status">{translate('analysis.marginUnavailable')}</p>
{/if}
<ul class="legend-list small" aria-label="Legenda delle velocità">
  {#each result.rates_bps as r, j (r)}
    {#if !simple || j === chosenIndex}
    <li><span class="key" class:key--dash={j % 2 === 1} style="--k: {`var(${TOKENS[j % TOKENS.length]})`}; background: var(--k)" aria-hidden="true"></span>{rateLabel(r)}</li>
    {/if}
  {/each}
</ul>

<p class="summary" role="status">
  {#if !simple}Terra tra {f1(stats.e?.[0])}° e {f1(stats.e?.[1])}°; cresta tra {f1(stats.r?.[0])}° e {f1(stats.r?.[1])}° sull’orizzonte.{/if}
  {#if margin0}Margine al rate scelto ({rateLabel(result.windows.rate_bps)}): da {f1(margin0[0])} a {f1(margin0[1])} dB.{/if}
  Serie decimate dal server ({result.series_step_min} min per punto, medie dei blocchi).
</p>

<details class="alt">
  <summary>Tabella dei valori</summary>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella dei valori nel tempo">
    <table>
      <caption>Elevazioni e margini (campione ogni {sample.length > 0 ? Math.ceil(t.time.length / sample.length) : 1} punti della serie)</caption>
      <thead>
        <tr>
          <th scope="col">Istante (UTC)</th><th scope="col">Terra (°)</th><th scope="col">Cresta (°)</th>
          {#each result.rates_bps as r (r)}<th scope="col">{rateLabel(r)} (dB)</th>{/each}
        </tr>
      </thead>
      <tbody>
        {#each sample as i (i)}
          <tr>
            <th scope="row">{new Date((t.time[i] ?? 0) * 1000).toISOString().slice(0, 16).replace('T', ' ')}</th>
            <td class="num">{f1(t.earthEl[i])}</td><td class="num">{f1(t.ridgeEl[i])}</td>
            {#each t.margins as m, j (j)}<td class="num">{Number.isNaN(m[i]) ? '—' : f1(m[i])}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</details>
{#if !simple}<ExportBar name="raven-margine-nel-tempo" csv={() => timeCsv(result)} json={() => toJson({ window: result.window, time_unix: result.series_time_unix, series: result.series, rates_bps: result.rates_bps })} />{/if}

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .legend-line,
  .legend-list {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-3);
    margin: var(--space-2) 0;
    padding: 0;
    list-style: none;
  }
  .legend-list li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .key {
    display: inline-block;
    width: 1.5rem;
    height: 3px;
    border-radius: 2px;
  }
  .key--dash {
    background: repeating-linear-gradient(90deg, var(--k, currentColor) 0 6px, transparent 6px 10px) !important;
  }
  .summary {
    margin: var(--space-3) 0;
  }
  .alt summary {
    min-height: var(--target);
    display: flex;
    align-items: center;
    cursor: pointer;
    font-weight: 600;
  }
  td,
  th {
    padding-right: var(--space-3);
  }
</style>
