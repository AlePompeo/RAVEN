<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ChartBox, { type Spec } from './ChartBox.svelte';
  import ExportBar from './ExportBar.svelte';
  import { chosenRateData, toJson, tradeCsv, tradeData, type AnalysisResult } from './grazing';

  let { result }: { result: AnalysisResult } = $props();

  const comp = $derived(result.compensator);
  const trade = $derived(tradeData(comp.tradeoff));
  const chosen = $derived(chosenRateData(result));
  const f = (v: number, d = 2) => v.toFixed(d).replace('.', ',');
  const tradeSpecs: Spec[] = [
    { label: 'Interruzioni (%)', token: '--c-danger', scale: 'o' },
    { label: 'Dati consegnati (% del programmato dal k scelto)', token: '--c-uplink', scale: 'd' },
  ];
  const rateSpec: Spec[] = [{ label: 'Velocità scelta (kbit/s)', token: '--c-uplink' }];
  const declaredPct = $derived(chosen.kbps.length ? (100 * chosen.kbps.filter((v) => v > 0).length) / chosen.kbps.length : 0);
</script>

<p class="small muted">
  Regola: la velocità è la massima tra quelle candidate per cui il margine previsto meno k·σ è almeno 0 dB; se nessuna soddisfa la regola
  il link non è dichiarato. Interruzione: margine vero + rumore N(0, σ) sotto 0 dB. È un controllo in avanti con margine statistico,
  non apprendimento per rinforzo. σ = {f(comp.sigma_db, 1)} dB e k sono ipotesi illustrative (tag I).
</p>

<h3>Interruzioni e dati contro k</h3>
<ChartBox
  series={tradeSpecs}
  x={trade.k}
  ys={[trade.outage, trade.data]}
  xNumeric
  xLabel="k (margine di sicurezza in σ)"
  axisLabels={{ o: 'interruzioni (%)', d: 'dati relativi (%)' }}
  height={240}
  label="Grafico del compromesso: percentuale di interruzioni e dati consegnati contro il margine k; i valori sono nella tabella sotto"
/>
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="table-scroll" tabindex="0" role="region" aria-label="Tabella del compromesso">
  <table data-testid="tradeoff-table">
    <caption>Compromesso interruzioni e dati per valore di k (k scelto: {f(comp.k)})</caption>
    <thead>
      <tr>
        <th scope="col">k</th><th scope="col">Backoff (dB)</th><th scope="col">Passi dichiarati</th><th scope="col">Interruzioni (%)</th>
        <th scope="col">Interruzioni teoriche gaussiane (%)</th><th scope="col">Dati relativi (%)</th><th scope="col">Velocità media (kbit/s)</th>
      </tr>
    </thead>
    <tbody>
      {#each [...comp.tradeoff].sort((a, b) => a.k - b.k) as r (r.k)}
        <tr class:chosen={r.k === comp.k}>
          <th scope="row">{f(r.k)}{r.k === comp.k ? ' (scelto)' : ''}</th><td class="num">{f(r.backoff_db)}</td><td class="num">{r.declared_steps}</td>
          <td class="num">{f(r.outage_pct, 3)}</td><td class="num">{f(r.gaussian_outage_pct, 3)}</td>
          <td class="num">{r.relative_data === null ? '—' : f(100 * r.relative_data, 1)}</td><td class="num">{f(r.mean_rate_bps / 1e3, 1)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<p class="small summary" role="status">
  Con k = {f(comp.k)}: {f(comp.chosen.outage_pct, 3)} % di interruzioni su {comp.chosen.declared_steps} passi dichiarati, dati consegnati
  {comp.chosen.relative_data === null ? 'non definiti' : `${f(100 * comp.chosen.relative_data, 1)} % del riferimento`}.
</p>
<ExportBar name="raven-compensatore-k" csv={() => tradeCsv(comp.tradeoff)} json={() => toJson(comp)} />

<h3>Velocità scelta nel tempo</h3>
<ChartBox
  series={rateSpec}
  x={chosen.time}
  ys={[chosen.kbps]}
  axisLabels={{ y: 'kbit/s' }}
  height={220}
  label="Grafico della velocità di trasmissione scelta dal compensatore nel tempo; 0 significa link non dichiarato"
/>
<p class="small summary" role="status">
  Link dichiarato nel {f(declaredPct, 1)} % dei punti della serie (0 kbit/s = nessuna velocità soddisfa la regola).
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
