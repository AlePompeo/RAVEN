<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { scenarioStore } from '../../shell/scenario';
  import { raven, type RavenSites } from '../../shell/ravenApi';
  import ChartBox, { type Spec } from '../grazinglink/ChartBox.svelte';
  import { MAX_LINK_CSV_BYTES, parseLinkCsv, type LinkSample } from './linkCsv';
  import { compareLink, comparisonRequest, predictionFromRaven, simulateLink, type LinkComparison, type PredictionSeries } from './linkComparison';

  let { onContext }: { onContext: (params: Record<string, string | number> | null) => void } = $props();

  let samples = $state.raw<LinkSample[]>([]);
  let filename = $state('');
  let simulated = $state(false);
  let error = $state('');
  let status = $state.raw<RavenSites | null>(null);
  let statusError = $state(false);
  let site = $state('');
  let comparing = $state(false);
  let comparisonError = $state('');
  let comparison = $state.raw<LinkComparison | null>(null);
  let model = $state.raw<PredictionSeries | null>(null);
  let runStation = $state('');
  let runGain = $state<number | null>(null);
  let controller: AbortController | null = null;
  let generation = 0;

  $effect(() => {
    const last = samples.at(-1);
    onContext(last ? {
      link_provenienza: simulated ? 'simulati dal modello, non misure' : 'CSV, provenienza non verificata',
      link_campioni: samples.length,
      link_ultimo_istante_utc: last.t_utc,
      link_ultimo_margine_db: Number(last.margin_db.toFixed(2)),
      ...(site ? { link_sito_selezionato: site } : {}),
      ...(comparison ? { link_campioni_confrontati: comparison.count } : {}),
      ...(comparison?.bias_db != null ? { link_bias_db: Number(comparison.bias_db.toFixed(2)) } : {}),
      ...(comparison?.rmse_db != null ? { link_rmse_db: Number(comparison.rmse_db.toFixed(2)) } : {}),
    } : null);
  });

  onMount(() => {
    let active = true;
    void raven.sites().then((response) => {
      if (!active) return;
      if (!response.ok) {
        statusError = true;
        return;
      }
      status = response.data;
      const current = scenarioStore().reload().site;
      site = status.sites.find((s) => s.id === current && s.dem_covered)?.id ?? '';
    });
    return () => {
      active = false;
      generation++;
      controller?.abort();
    };
  });

  function clearComparison() {
    generation++;
    controller?.abort();
    controller = null;
    comparing = false;
    comparison = null;
    model = null;
    comparisonError = '';
  }

  async function load(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    clearComparison();
    const current = ++generation;
    samples = [];
    filename = '';
    simulated = false;
    error = '';
    if (!file) return;
    if (file.size > MAX_LINK_CSV_BYTES) {
      error = t('telemetry.csvSize');
      return;
    }
    let text: string;
    try {
      text = await file.text();
    } catch {
      if (current === generation) error = t('telemetry.csvRead');
      return;
    }
    if (current !== generation) return;
    const result = parseLinkCsv(text);
    if (!result.ok) {
      const key = {
        header: 'telemetry.csvHeaderError',
        row: 'telemetry.csvRowError',
        order: 'telemetry.csvOrderError',
        empty: 'telemetry.csvEmpty',
        size: 'telemetry.csvSize',
      } as const;
      error = t(key[result.reason], { line: result.line ?? 0 });
      return;
    }
    samples = result.samples;
    filename = file.name;
  }

  async function compare() {
    clearComparison();
    const snapshot = scenarioStore().get();
    const request = comparisonRequest(samples, snapshot, site);
    if (!request) {
      comparisonError = t('telemetry.compareRange');
      return;
    }
    const current = ++generation;
    const abort = new AbortController();
    controller = abort;
    comparing = true;
    const response = await raven.evaluate(request, { signal: abort.signal });
    if (current !== generation) return;
    controller = null;
    comparing = false;
    if (!response.ok) {
      comparisonError = t('telemetry.compareError', { reason: response.kind });
      return;
    }
    if (response.data.site.id !== request.site_id) {
      comparisonError = t('telemetry.compareMismatch');
      return;
    }
    const prediction = predictionFromRaven(response.data);
    if (!prediction) { comparisonError = t('telemetry.compareMismatch'); return; }
    model = prediction;
    runStation = snapshot.station;
    runGain = snapshot.gain;
    comparison = compareLink(samples, prediction);
  }

  function changeSite() {
    clearComparison();
    scenarioStore().set({ site: site || null });
    if (simulated) {
      samples = [];
      simulated = false;
    }
  }

  async function simulate() {
    clearComparison();
    const snapshot = scenarioStore().get();
    const start = snapshot.t ?? new Date().toISOString();
    const request = comparisonRequest([{ t_utc: start, margin_db: 0, elevation_deg: 0, rate_bps: 1 }], snapshot, site);
    if (!request) {
      comparisonError = t('telemetry.compareRange');
      return;
    }
    const current = ++generation;
    const abort = new AbortController();
    controller = abort;
    comparing = true;
    const response = await raven.evaluate(request, { signal: abort.signal });
    if (current !== generation) return;
    controller = null;
    comparing = false;
    if (!response.ok) {
      comparisonError = t('telemetry.compareError', { reason: response.kind });
      return;
    }
    if (response.data.site.id !== request.site_id) {
      comparisonError = t('telemetry.compareMismatch');
      return;
    }
    const prediction = predictionFromRaven(response.data);
    if (!prediction) { comparisonError = t('telemetry.compareMismatch'); return; }
    const rows = simulateLink(prediction, snapshot.bitrate ?? prediction.rate_bps);
    if (!rows) {
      comparisonError = t('telemetry.simulateError');
      return;
    }
    samples = rows;
    filename = '';
    simulated = true;
    error = '';
    model = prediction;
    runStation = snapshot.station;
    runGain = snapshot.gain;
    comparison = compareLink(rows, prediction);
  }

  const chartSeries = $derived<Spec[]>([
    { label: t('telemetry.csvMargin'), token: '--c-uplink' },
    { label: t('telemetry.comparePrediction'), token: '--c-power', dash: [6, 4] },
  ]);
  const chartTime = $derived(Float64Array.from(comparison?.rows ?? [], (row) => Date.parse(row.t_utc) / 1000));
  const chartObserved = $derived(Float64Array.from(comparison?.rows ?? [], (row) => row.margin_db));
  const chartPredicted = $derived(Float64Array.from(comparison?.rows ?? [], (row) => row.prediction_db ?? NaN));
  const number = (n: number | null | undefined) => n == null ? '—' : n.toFixed(2);
</script>

<section class="panel" aria-labelledby="link-csv-heading">
  <h2 id="link-csv-heading">{t('telemetry.csvTitle')}</h2>
  <p>{t('telemetry.csvHelp')}</p>
  <p class="small muted">{t('telemetry.csvProvenance')}</p>
  <label for="link-csv">{t('telemetry.csvSelect')}</label>
  <input id="link-csv" type="file" accept=".csv,text/csv" onchange={load} />
  {#if error}<p role="alert">{error}</p>{/if}
  <p class="small muted">{t('telemetry.compareAssumptions')}</p>
  {#if statusError}
    <p role="alert">{t('telemetry.compareStatusError')}</p>
  {:else if status}
    <label for="link-site">{t('telemetry.compareSite')}</label>
    <select id="link-site" bind:value={site} onchange={changeSite} disabled={comparing}>
      <option value="">{t('telemetry.compareChooseSite')}</option>
      {#each status.sites.filter((s) => s.dem_covered) as option (option.id)}
        <option value={option.id}>{option.name}</option>
      {/each}
    </select>
    <button type="button" class="btn" disabled={!site || comparing} onclick={simulate}>{t('telemetry.simulateStart')}</button>
    {#if samples.length}
      <button type="button" class="btn--primary" disabled={!site || comparing} onclick={compare}>{t('telemetry.compareStart')}</button>
    {/if}
    {#if comparing}<p role="status">{t('telemetry.compareRunning')}</p>{/if}
  {:else}
    <p role="status">{t('telemetry.compareLoading')}</p>
  {/if}
  {#if comparisonError}<p role="alert">{comparisonError}</p>{/if}
  {#if samples.length}
    {@const latest = samples[samples.length - 1]!}
    {#if simulated}
      <p role="status">{t('telemetry.simulateProvenance', { count: samples.length })}</p>
    {:else}
      <p role="status">{t('telemetry.csvLoaded', { name: filename, count: samples.length })}</p>
    {/if}
    <p>{t('telemetry.csvLast', { time: latest.t_utc, margin: number(latest.margin_db) })}</p>
    {#if comparison && model}
      <p role="status">{t('telemetry.compareSummary', { matched: comparison.count, total: comparison.rows.length })}</p>
      <p class="small muted">
        {t('telemetry.compareSettings', { site: model.site_id, station: runStation, gain: runGain ?? model.gain, step: model.step_min })}
      </p>
      <p class="small muted">{t('telemetry.compareInterpolation')}</p>
      <p>{model.model_version}</p>
      <p>{t('telemetry.compareStats', { bias: number(comparison.bias_db), rmse: number(comparison.rmse_db), coverage: number(comparison.coverage_pct), k: model.k, sigma: model.sigma_db, outages: comparison.outages })}</p>
      <p class="small muted">{t('telemetry.compareOutageNote')}</p>
      {#if comparison.outageStarts.length}
        <details>
          <summary>{t('telemetry.compareOutages')}</summary>
          <ol>
            {#each comparison.outageStarts.slice(0, 50) as time (time)}<li>{time}</li>{/each}
          </ol>
        </details>
      {/if}
      {#if comparison.count}
        <p class="small">{t('telemetry.compareLegend')}</p>
        <ChartBox series={chartSeries} x={chartTime} ys={[chartObserved, chartPredicted]} axisLabels={{ y: 'dB' }} label={t('telemetry.compareChart')} />
      {/if}
    {:else}
      <p class="small muted">{t('telemetry.csvNotCompared')}</p>
    {/if}
    <div class="table-scroll">
      <table>
        <caption>{t('telemetry.csvCaption')}</caption>
        <thead>
          <tr>
            <th scope="col">UTC</th>
            <th scope="col">{t('telemetry.csvMargin')}</th>
            <th scope="col">{t('telemetry.csvElevation')}</th>
            <th scope="col">{t('telemetry.csvRate')}</th>
            {#if comparison}<th scope="col">{t('telemetry.comparePrediction')}</th><th scope="col">{t('telemetry.compareResidual')}</th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each samples.slice(0, 50) as sample, i (sample.t_utc)}
            <tr>
              <th scope="row">{sample.t_utc}</th>
              <td>{sample.margin_db}</td>
              <td>{sample.elevation_deg}</td>
              <td>{sample.rate_bps}</td>
              {#if comparison}<td>{number(comparison.rows[i]?.prediction_db)}</td><td>{number(comparison.rows[i]?.residual_db)}</td>{/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  input[type='file'] {
    max-width: 100%;
    min-height: 44px;
  }
  input[type='file']::file-selector-button {
    min-height: 44px;
  }
</style>
