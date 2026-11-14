<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ChartBox, { type Spec } from './ChartBox.svelte';
  import ExportBar from './ExportBar.svelte';
  import {
    diffractionCsv,
    diffractionCurve,
    finiteRange,
    heatCsv,
    heatmap,
    nearestIndex,
    toJson,
    type AnalysisResult,
    type Compensation,
    type Series,
  } from './grazing';

  let { result, comp, compError }: { result: AnalysisResult; comp: Compensation | null; compError: string } = $props();

  const nuSeries = $derived((result.series.nu ?? []) as Series);
  const curve = $derived(diffractionCurve(nuSeries));
  const range = $derived(finiteRange(nuSeries));
  const specs: Spec[] = [
    { label: 'J(ν) esatto (bordo a lama, Fresnel)', token: '--c-uplink' },
    { label: 'J(ν) approssimazione ITU-R P.526', token: '--c-power', dash: [8, 5] },
    { label: 'Punti di funzionamento', token: '--c-text', points: true },
  ];
  const heat = $derived(comp ? heatmap(comp) : null);
  const c = $derived(result.flags.correction);
  const medR = $derived(result.flags.ridge_radius_median_m);
  const rowOf = $derived(heat && medR !== null ? nearestIndex(heat.radius, medR) : -1);
  const colA = $derived(heat && range ? nearestIndex(heat.nu, range[0]) : -1);
  const colB = $derived(heat && range ? nearestIndex(heat.nu, range[1]) : -1);

  // geometria della mappa (unità del viewBox)
  const CW = 14;
  const RH = 34;
  const ML = 64;
  const MT = 8;
  const f2 = (v: number) => v.toFixed(2).replace('.', ',');
  const tint = (t: number) => `color-mix(in srgb, var(--c-power) ${Math.round(8 + t * 82)}%, var(--c-bg))`;
</script>

<h3>Perdita di diffrazione J(ν): lama esatta contro approssimazione ITU</h3>
<p class="small muted">
  ν è il parametro di Fresnel del crinale dominante (positivo: la cima supera la linea di vista). La curva esatta usa gli
  integrali di Fresnel; l’approssimazione segue ITU-R P.526-9, §4.1, eq. (27), per ν &gt; −0,78.
  Sotto tale soglia lo zero è una scelta del codice, non una prescrizione dell’equazione.
</p>
<ChartBox
  series={specs}
  x={curve.nu}
  ys={[curve.exact, curve.itu, curve.points]}
  xNumeric
  xLabel="ν (parametro di Fresnel)"
  axisLabels={{ y: 'perdita J (dB)' }}
  label="Grafico della perdita di diffrazione J in dB contro ν: curva esatta, approssimazione ITU e punti di funzionamento dell’analisi; i valori sono nella tabella sotto"
/>
<ul class="legend small" aria-label="Legenda">
  <li><span class="key" style="background: var(--c-uplink)" aria-hidden="true"></span>esatta (Fresnel)</li>
  <li><span class="key dashed" aria-hidden="true"></span>ITU-R P.526-9, eq. (27), con zero convenzionale per ν ≤ −0,78</li>
  <li><span class="dot" aria-hidden="true"></span>punti di funzionamento</li>
</ul>
<p class="summary" role="status">
  {#if range}ν di funzionamento tra {f2(range[0])} e {f2(range[1])}: perdita esatta tra {f2(Math.min(...curve.points.filter((v) => !Number.isNaN(v))))} e
    {f2(Math.max(...curve.points.filter((v) => !Number.isNaN(v))))} dB.{:else}Nessun valore di ν nella finestra (Terra sotto l’orizzonte).{/if}
</p>
<details class="alt">
  <summary>Tabella della curva (campione)</summary>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella di J contro nu">
    <table>
      <caption>J(ν) in dB: esatta e approssimazione ITU, ogni 0,5 in ν</caption>
      <thead><tr><th scope="col">ν</th><th scope="col">Esatta (dB)</th><th scope="col">ITU (dB)</th></tr></thead>
      <tbody>
        {#each Array.from(curve.nu, (v, i) => i).filter((i) => Math.abs(((curve.nu[i] ?? 0) * 2) % 1) < 1e-6) as i (i)}
          <tr><th scope="row">{f2(curve.nu[i] ?? 0)}</th><td class="num">{f2(curve.exact[i] ?? 0)}</td><td class="num">{f2(curve.itu[i] ?? 0)}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</details>
<ExportBar name="raven-diffrazione" csv={() => diffractionCsv(curve)} json={() => toJson({ nu: Array.from(curve.nu), exact_db: Array.from(curve.exact), itu_db: Array.from(curve.itu), operating_nu: nuSeries })} />

<h3>Correzione per cresta arrotondata: ν contro raggio</h3>
<p class="small muted">
  Tabella split-step R(ν, raggio) in dB, simulata e <strong>non validata</strong>: è il confronto (banda di incertezza);
  la correzione applicata è T(m,n) di ITU-R P.526-9 par. 4.2. Le celle con
  «!» sono anomalie segnalate dal generatore; tra le celle si interpola.
</p>
{#if compError}
  <p role="alert">{compError}</p>
{:else if !heat}
  <p role="status">Caricamento della tabella di compensazione...</p>
{:else}
  <svg
    class="heat"
    viewBox="0 0 {ML + heat.nu.length * CW + 6} {MT + heat.radius.length * RH + 34}"
    role="img"
    aria-label="Mappa di calore della correzione per cresta arrotondata, ν sulle colonne e raggio sulle righe; i valori sono nella tabella sotto"
  >
    {#each heat.cells as cell (`${cell.ri}-${cell.ni}`)}
      <g>
        <title>raggio {cell.radius} m, ν {f2(cell.nu)}: {f2(cell.value)} dB (inviluppo di oscillazione {f2(cell.envelope)} dB){cell.anomaly ? ', anomalia' : ''}</title>
        <rect x={ML + cell.ni * CW} y={MT + cell.ri * RH} width={CW} height={RH} fill={tint(cell.t)} />
        {#if cell.anomaly}
          <rect x={ML + cell.ni * CW + 0.75} y={MT + cell.ri * RH + 0.75} width={CW - 1.5} height={RH - 1.5} class="anom" />
          <text x={ML + cell.ni * CW + CW / 2} y={MT + cell.ri * RH + RH / 2 + 4} class="bang" text-anchor="middle">!</text>
        {/if}
      </g>
    {/each}
    {#each heat.radius as r, ri (r)}
      <text x={ML - 6} y={MT + ri * RH + RH / 2 + 4} text-anchor="end" class="axis">{r} m</text>
    {/each}
    {#each heat.nu as v, ni (ni)}
      {#if Math.abs(v * 2 - Math.round(v * 2)) < 1e-6}
        <text x={ML + ni * CW + CW / 2} y={MT + heat.radius.length * RH + 14} text-anchor="middle" class="axis">{f2(v)}</text>
      {/if}
    {/each}
    <text x={ML + (heat.nu.length * CW) / 2} y={MT + heat.radius.length * RH + 30} text-anchor="middle" class="axis">ν</text>
    {#if rowOf >= 0 && colA >= 0}
      <rect
        class="op"
        x={ML + colA * CW}
        y={MT + rowOf * RH}
        width={(colB - colA + 1) * CW}
        height={RH}
      />
    {/if}
  </svg>
  <p class="small">
    Scala: da 0 dB (chiaro) a {f2(heat.max)} dB (scuro). Anomalie: {heat.anomalies}.
    {#if rowOf >= 0}Il riquadro nero segna il raggio mediano della cresta ({medR !== null ? f2(medR) : '—'} m) sull’intervallo di ν dell’analisi.{/if}
  </p>
  <details class="alt">
    <summary>Tabella della mappa (raggio × ν)</summary>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella della correzione per cresta arrotondata">
      <table>
        <caption>Correzione in dB (anomalie con «!»), ogni 0,5 in ν</caption>
        <thead>
          <tr>
            <th scope="col">Raggio (m)</th>
            {#each heat.nu.filter((v) => Math.abs(v * 2 - Math.round(v * 2)) < 1e-6) as v (v)}<th scope="col">ν {f2(v)}</th>{/each}
          </tr>
        </thead>
        <tbody>
          {#each heat.radius as r, ri (r)}
            <tr>
              <th scope="row">{r}</th>
              {#each heat.cells.filter((x) => x.ri === ri && Math.abs(x.nu * 2 - Math.round(x.nu * 2)) < 1e-6) as x (x.ni)}
                <td class="num">{f2(x.value)}{x.anomaly ? ' !' : ''}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </details>
  <ExportBar name="raven-compensazione" csv={() => heatCsv(heat)} json={() => toJson(comp)} />
{/if}

<h3>Incertezza</h3>
<ul class="facts small">
  <li>Passi con raggio della cresta noto: <strong>{c.steps_with_radius}</strong> su {result.window.n_steps}; raggio risolto: <strong>{result.flags.radius_resolved ? 'sì' : 'no'}</strong> ({(100 * result.flags.radius_resolved_fraction).toFixed(0)} % dei passi).</li>
  <li>Incertezza massima della correzione: <strong>{f2(c.max_uncertainty_db)} dB</strong>; anomalie nei passi: {c.anomaly_steps}; valori limitati ai bordi della tabella: {c.clamped_steps}.</li>
  <li>Passi con geometria fuori dall’intervallo della tabella (estrapolati): <strong>{c.geometry_extrapolated_steps}</strong>.</li>
  <li>La tabella split-step è calcolata per d1 = 2000 m, λ = 0,0357 m e onda piana: fuori da questi valori la banda è indicativa (la formula ITU usa d1 e λ reali). {result.correction_inconsistency.text}</li>
</ul>

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    list-style: none;
    margin: var(--space-2) 0;
    padding: 0;
  }
  .legend li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .key {
    display: inline-block;
    width: 1.5rem;
    height: 3px;
  }
  .key.dashed {
    background: repeating-linear-gradient(90deg, var(--c-power) 0 6px, transparent 6px 10px);
  }
  .dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: var(--c-text);
  }
  .summary {
    margin: var(--space-2) 0;
  }
  .heat {
    display: block;
    width: 100%;
    height: auto;
    color: var(--c-text);
    background: var(--c-bg);
    border: 1px solid var(--c-hairline);
  }
  .axis {
    font-size: 11px;
    fill: currentColor;
  }
  .anom {
    fill: none;
    stroke: var(--c-text);
    stroke-width: 1;
    stroke-dasharray: 2 1.5;
  }
  .bang {
    font-size: 12px;
    font-weight: 700;
    fill: var(--c-text);
  }
  .op {
    fill: none;
    stroke: var(--c-text);
    stroke-width: 2;
  }
  .facts {
    margin: 0;
    padding-left: 1.2rem;
    display: grid;
    gap: var(--space-1);
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
