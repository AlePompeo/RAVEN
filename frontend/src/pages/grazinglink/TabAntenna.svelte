<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ChartBox, { type Spec } from './ChartBox.svelte';
  import ExportBar from './ExportBar.svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { dishesCsv, pointingCsv, rateLabel, toJson, type AnalysisResult, type AntennaReport } from './grazing';

  let { result, report, error }: { result: AnalysisResult; report: AntennaReport | null; error: string } = $props();

  const a = $derived(result.antenna);
  const f = (v: number, d = 2) => v.toFixed(d).replace('.', ',');
  const dishes = $derived(report ? [...report.dishes].sort((x, y) => x.diameter_m - y.diameter_m) : []);
  const specs: Spec[] = [
    { label: 'Guadagno (dBi)', token: '--c-uplink', scale: 'g' },
    { label: 'HPBW dello script, 70 λ/D (°)', token: '--c-power', scale: 'h', dash: [8, 5] },
    { label: 'HPBW uniforme, 58,96 λ/D (°)', token: '--c-success', scale: 'h' },
  ];
  const sel = $state({ i: 0 });
  const dish = $derived(dishes[Math.min(sel.i, Math.max(dishes.length - 1, 0))]);
</script>

<h3>Antenna del rover nell’analisi</h3>
<ul class="facts small">
  <li>Diametro derivato dal guadagno: <strong>{f(a.diameter_m, 3)} m</strong>, guadagno {f(a.rover_gain_dbi, 1)} dBi (tag I), montaggio «{t(a.mount === 'tracking' ? 'analysis.mountTracking' : a.mount === 'gimbal' ? 'analysis.mountGimbal' : 'analysis.mountFixed')}».</li>
  {#if a.mount === 'gimbal'}
    <li>{t('analysis.gimbalHint')} {#if a.gimbal_mechanical_limit_fraction != null}{t('analysis.gimbalLimit', { percent: f(a.gimbal_mechanical_limit_fraction * 100, 1) })}{/if}</li>
  {/if}
  <li>HPBW: <strong>{f(a.hpbw_script_70_deg)}°</strong> con la formula dello script (70 λ/D) e <strong>{f(a.hpbw_uniform_deg)}°</strong> con la formula per apertura uniforme (58,96 λ/D): rapporto {f(a.hpbw_script_70_deg / a.hpbw_uniform_deg, 3)}.</li>
  <li>Stazione di terra: {a.station.name}, {f(a.station.diameter_m, 0)} m, {f(a.station.gain_dbi, 1)} dBi (tag {a.station.gain_tag}).</li>
  <li>
    Escursione della Terra per librazione, dalle efemeridi: <strong>{f(a.libration_excursion_deg)}°</strong>. Con un montaggio
    fisso la perdita di puntamento massima è {f(a.gimbal.fixed_mount_loss_db)} dB (budget {f(a.gimbal.max_loss_budget_db, 1)} dB):
    <strong>{a.gimbal.gimbal_needed ? 'serve un gimbal' : 'il gimbal non serve'}</strong>.
    Con l’errore consentito al budget a {f(a.gimbal.max_error_for_budget_deg)}°.
  </li>
  <li>Perdita di puntamento massima nella finestra: {f(a.pointing_loss_max_db)} dB (gaussiana esatta). Differenza massima tra la variante dello script e quella corretta: {f(a.pointing_script_minus_gaussian_max_db)} dB.</li>
</ul>

{#if error}
  <p role="alert">{error}</p>
{:else if !report}
  <p role="status">Calcolo della scheda antenna...</p>
{:else}
  <h3>Guadagno e HPBW contro il diametro</h3>
  <p class="small muted">
    A {f(report.frequency_ghz, 1)} GHz. Il guadagno cresce con il diametro, il fascio si restringe: più stretto è il fascio,
    più conta il puntamento. Tag I per rendimento e diametri.
  </p>
  <ChartBox
    series={specs}
    x={Float64Array.from(dishes.map((d) => d.diameter_m))}
    ys={[Float64Array.from(dishes.map((d) => d.gain_dbi)), Float64Array.from(dishes.map((d) => d.hpbw_script_70_deg)), Float64Array.from(dishes.map((d) => d.hpbw_uniform_deg))]}
    xNumeric
    xLabel="diametro (m)"
    axisLabels={{ g: 'guadagno (dBi)', h: 'HPBW (°)' }}
    label="Grafico del guadagno e della larghezza di fascio a metà potenza contro il diametro dell’antenna; i valori sono nella tabella sotto"
  />
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella delle antenne">
    <table>
      <caption>Antenne: guadagno, HPBW (script e uniforme) e necessità del gimbal con l’escursione di {f(report.excursion_deg)}°</caption>
      <thead>
        <tr>
          <th scope="col">Diametro (m)</th><th scope="col">Guadagno (dBi)</th><th scope="col">HPBW script (°)</th>
          <th scope="col">HPBW uniforme (°)</th><th scope="col">Rapporto</th><th scope="col">Perdita montaggio fisso (dB)</th><th scope="col">Gimbal</th>
        </tr>
      </thead>
      <tbody>
        {#each dishes as d (d.diameter_m)}
          <tr>
            <th scope="row">{f(d.diameter_m)}</th><td class="num">{f(d.gain_dbi, 1)}</td><td class="num">{f(d.hpbw_script_70_deg)}</td>
            <td class="num">{f(d.hpbw_uniform_deg)}</td><td class="num">{f(d.hpbw_ratio, 3)}</td>
            <td class="num">{f(d.gimbal.fixed_mount_loss_db)}</td><td>{d.gimbal.gimbal_needed ? 'serve' : 'non serve'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <ExportBar name="raven-antenna" csv={() => dishesCsv(report)} json={() => toJson({ rover: a, report })} />

  <h3>Perdita di puntamento: script e variante corretta</h3>
  <p class="small muted">
    Stesso errore di puntamento, due formule: lo script usa 12 (x/HPBW)², la gaussiana esatta 12,04 (x/HPBW)². Le colonne a
    destra mostrano la differenza in dB e, per confronto, la perdita esatta di un’apertura circolare (Airy).
  </p>
  {#if dish}
    <p class="field">
      <label for="dish-sel">Antenna</label>
      <select id="dish-sel" bind:value={sel.i}>
        {#each dishes as d, i (d.diameter_m)}<option value={i}>{f(d.diameter_m)} m</option>{/each}
      </select>
    </p>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella della perdita di puntamento">
      <table data-testid="pointing-table">
        <caption>Perdita di puntamento per l’antenna da {f(dish.diameter_m)} m</caption>
        <thead>
          <tr>
            <th scope="col">Errore (°)</th><th scope="col">Script (dB)</th><th scope="col">Gaussiana, HPBW script (dB)</th>
            <th scope="col">Differenza (dB)</th><th scope="col">Gaussiana, HPBW uniforme (dB)</th><th scope="col">Airy esatta (dB)</th>
          </tr>
        </thead>
        <tbody>
          {#each dish.pointing as p (p.err_deg)}
            <tr>
              <th scope="row">{f(p.err_deg, 3)}</th><td class="num">{f(p.script_db, 3)}</td><td class="num">{f(p.gaussian_hpbw70_db, 3)}</td>
              <td class="num">{f(p.constant_difference_db, 3)}</td><td class="num">{f(p.gaussian_hpbw_uniform_db, 3)}</td><td class="num">{f(p.airy_exact_db, 3)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="small summary" role="status">
      Con {f(dish.diameter_m)} m: HPBW {f(dish.hpbw_script_70_deg)}° (script) contro {f(dish.hpbw_uniform_deg)}° (uniforme). Con l’escursione di
      librazione {f(report.excursion_deg)}° la perdita fissa è {f(dish.gimbal.fixed_mount_loss_db)} dB:
      {dish.gimbal.gimbal_needed ? 'serve il gimbal' : 'basta un montaggio fisso'}.
    </p>
  {/if}
  <ExportBar name="raven-puntamento" csv={() => pointingCsv(report)} json={() => toJson(report.dishes.map((d) => ({ diameter_m: d.diameter_m, pointing: d.pointing })))} />

  <h3>Guadagno richiesto per velocità</h3>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella del guadagno richiesto">
    <table>
      <caption>Guadagno necessario del rover per ciascuna velocità di trasmissione</caption>
      <thead><tr><th scope="col">Velocità</th><th scope="col">Guadagno richiesto (dBi)</th><th scope="col">Tipo</th><th scope="col">Diametro (m)</th><th scope="col">HPBW script (°)</th></tr></thead>
      <tbody>
        {#each report.required_gain as g (g.rate_bps)}
          <tr>
            <th scope="row">{rateLabel(g.rate_bps)}</th><td class="num">{f(g.required_gain_dbi, 1)}</td><td>{g.type}</td>
            <td class="num">{g.diameter_m === null ? '—' : f(g.diameter_m)}</td><td class="num">{g.hpbw_script_deg === null ? '—' : f(g.hpbw_script_deg)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="small muted">{report.note}</p>
{/if}

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .facts {
    margin: 0;
    padding-left: 1.2rem;
    display: grid;
    gap: var(--space-1);
  }
  .field select {
    min-width: 8rem;
  }
  .summary {
    margin: var(--space-3) 0;
  }
  td,
  th {
    padding-right: var(--space-3);
  }
</style>
