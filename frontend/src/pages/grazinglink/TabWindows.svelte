<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ExportBar from './ExportBar.svelte';
  import { hoursText, intervalSegments, pctText, rateLabel, toJson, windowsCsv, windowStats, type AnalysisResult } from './grazing';

  let { result, simple = false }: { result: AnalysisResult; simple?: boolean } = $props();

  const w = $derived(result.windows);
  const s = $derived(windowStats(w));
  const a = $derived(result.series_time_unix[0] ?? 0);
  const b = $derived(a + result.window.days * 86400);
  const strips = $derived([
    { id: 'geom', label: 'Geometrica', iv: w.geometric_intervals_unix, cls: 'geom' },
    { id: 'real', label: 'Reale', iv: w.real_intervals_unix, cls: 'real' },
    { id: 'trans', label: 'Transizione', iv: w.transition_intervals_unix, cls: 'trans' },
  ]);
  const w2 = (v: number) => `${Math.max(v, 0)}%`;
  const gain = $derived(s.real - s.geometric);
</script>

<h3 id="bars-h">Finestra geometrica contro finestra reale</h3>
<p class="small muted">
  Geometrica: la Terra sta sopra la linea del crinale dominante. Reale: il margine di link, con la perdita di diffrazione,
  è almeno 0 dB al rate scelto ({rateLabel(w.rate_bps)}).
</p>

<div class="bars" role="img" aria-labelledby="bars-h" aria-describedby="bars-text">
  <div class="row">
    <span class="row-label">Geometrica</span>
    <div class="bar">
      <span class="seg both" style="width: {w2(s.geometricBar.both)}"></span>
      <span class="seg notc" style="width: {w2(s.geometricBar.notClosing)}"></span>
      <span class="seg none" style="width: {w2(s.geometricBar.blocked)}"></span>
    </div>
    <span class="row-val num">{hoursText(s.geometric)} · {pctText(s.geometricPct)}</span>
  </div>
  <div class="row">
    <span class="row-label">Reale</span>
    <div class="bar">
      <span class="seg both" style="width: {w2(s.realBar.both)}"></span>
      <span class="seg trans" style="width: {w2(s.realBar.transition)}"></span>
      <span class="seg none" style="width: {w2(s.realBar.closed)}"></span>
    </div>
    <span class="row-val num">{hoursText(s.real)} · {pctText(s.realPct)}</span>
  </div>
</div>

<ul class="legend small" aria-label="Legenda delle barre">
  <li><span class="sw both" aria-hidden="true"></span>Geometria libera e link chiuso</li>
  <li><span class="sw notc" aria-hidden="true"></span>Geometria libera ma il link non chiude</li>
  <li><span class="sw trans" aria-hidden="true"></span><strong>Zona di transizione</strong>: la geometria dice bloccato, il link chiude</li>
  <li><span class="sw none" aria-hidden="true"></span>Né geometria né link</li>
</ul>

<p id="bars-text" class="summary" role="status" data-testid="windows-summary">
  Su {hoursText(s.total)} di finestra: geometrica {hoursText(s.geometric)} ({pctText(s.geometricPct)}), reale {hoursText(s.real)}
  ({pctText(s.realPct)}). Zona di transizione: {hoursText(s.transition)} ({pctText(s.transitionPct)}), ore in cui un
  strumento solo geometrico direbbe «bloccato» e il link invece chiude.
  {#if gain > 0}La finestra stimata è più lunga di {hoursText(gain)}.{:else if gain < 0}La finestra stimata è più breve di {hoursText(-gain)}.{:else}Le due finestre hanno la stessa durata.{/if}
</p>

{#if !simple}
<h3>Nel tempo</h3>
<div class="strips" role="img" aria-label="Intervalli della finestra geometrica, reale e di transizione lungo la durata dell’analisi; gli intervalli sono nella tabella sotto">
  {#each strips as st (st.id)}
    <div class="strip-row">
      <span class="row-label">{st.label}</span>
      <div class="strip">
        {#each intervalSegments(st.iv, a, b) as seg, i (i)}
          <span class="mark {st.cls}" style="left: {seg.left}%; width: {seg.width}%"></span>
        {/each}
      </div>
    </div>
  {/each}
</div>
{/if}

<details class="alt">
  <summary>Tabella delle ore e degli intervalli</summary>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label="Tabella delle finestre">
    <table>
      <caption>Ore e percentuale della finestra analizzata</caption>
      <thead><tr><th scope="col">Grandezza</th><th scope="col">Ore</th><th scope="col">% della finestra</th></tr></thead>
      <tbody>
        <tr><th scope="row">Finestra geometrica</th><td class="num">{s.geometric.toFixed(1)}</td><td class="num">{s.geometricPct.toFixed(1)}</td></tr>
        <tr><th scope="row">Finestra reale</th><td class="num">{s.real.toFixed(1)}</td><td class="num">{s.realPct.toFixed(1)}</td></tr>
        <tr><th scope="row">Transizione (bloccato ma il link chiude)</th><td class="num">{s.transition.toFixed(1)}</td><td class="num">{s.transitionPct.toFixed(1)}</td></tr>
        <tr><th scope="row">Libera ma il link non chiude</th><td class="num">{s.notClosing.toFixed(1)}</td><td class="num">{(s.total ? (100 * s.notClosing) / s.total : 0).toFixed(1)}</td></tr>
        <tr><th scope="row">Entrambe</th><td class="num">{s.both.toFixed(1)}</td><td class="num">{(s.total ? (100 * s.both) / s.total : 0).toFixed(1)}</td></tr>
      </tbody>
    </table>
  </div>
  <p class="small muted">
    Intervalli (inizio e fine, UTC):
    geometrica {w.geometric_intervals_unix.length}, reale {w.real_intervals_unix.length}, transizione {w.transition_intervals_unix.length}.
    {#if w.transition_intervals_unix.length}Transizione:
      {w.transition_intervals_unix.slice(0, 6).map(([x, y]) => `${new Date((x ?? 0) * 1000).toISOString().slice(5, 16).replace('T', ' ')} - ${new Date((y ?? 0) * 1000).toISOString().slice(5, 16).replace('T', ' ')}`).join('; ')}{w.transition_intervals_unix.length > 6 ? '; ...' : ''}.
    {/if}
  </p>
</details>
<p class="small muted">{w.rule}</p>
{#if !simple}<ExportBar name="raven-finestre" csv={() => windowsCsv(w)} json={() => toJson({ windows: w, stats: s })} />{/if}

<style>
  h3 {
    font-size: var(--fs-body);
    margin: var(--space-4) 0 var(--space-2);
  }
  .small {
    font-size: var(--fs-small);
  }
  .bars,
  .strips {
    display: grid;
    gap: var(--space-3);
  }
  .row,
  .strip-row {
    display: grid;
    grid-template-columns: 6.5rem minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
  }
  .strip-row {
    grid-template-columns: 6.5rem minmax(0, 1fr);
  }
  .row-label {
    font-weight: 600;
    font-size: var(--fs-small);
  }
  .row-val {
    font-size: var(--fs-small);
    white-space: nowrap;
  }
  .bar {
    display: flex;
    height: 2.25rem;
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-xs);
    overflow: hidden;
    background: var(--c-bg-alt);
  }
  .seg {
    height: 100%;
    min-width: 0;
  }
  .both,
  .sw.both {
    background: var(--c-uplink);
  }
  .notc,
  .sw.notc {
    background: repeating-linear-gradient(135deg, var(--c-muted) 0 3px, transparent 3px 7px);
  }
  .trans,
  .sw.trans {
    background: repeating-linear-gradient(45deg, var(--c-power) 0 5px, color-mix(in srgb, var(--c-power) 35%, transparent) 5px 9px);
    outline: 2px solid var(--c-power);
    outline-offset: -2px;
  }
  .none,
  .sw.none {
    background: var(--c-bg-alt);
  }
  .legend {
    list-style: none;
    margin: var(--space-3) 0;
    padding: 0;
    display: grid;
    gap: var(--space-1);
  }
  .legend li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .sw {
    flex: none;
    width: 1.25rem;
    height: 1rem;
    border: 1px solid var(--c-hairline);
    border-radius: 2px;
  }
  .summary {
    margin: var(--space-3) 0;
  }
  .strip {
    position: relative;
    height: 1.1rem;
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-xs);
    background: var(--c-bg-alt);
  }
  .mark {
    position: absolute;
    top: 0;
    bottom: 0;
  }
  .mark.geom {
    background: var(--c-muted);
  }
  .mark.real {
    background: var(--c-uplink);
  }
  .mark.trans {
    outline: none;
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
  @media (max-width: 639px) {
    .row {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-1);
    }
    .strip-row {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-1);
    }
  }
</style>
