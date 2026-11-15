<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import ExportBar from './ExportBar.svelte';
  import { formatNumber, t } from '../../i18n/i18n.svelte';
  import { intervalSegments, rateLabel, toJson, windowsCsv, windowStats, type AnalysisResult } from './grazing';

  let { result, simple = false }: { result: AnalysisResult; simple?: boolean } = $props();

  const w = $derived(result.windows);
  const s = $derived(windowStats(w));
  const a = $derived(result.series_time_unix[0] ?? 0);
  const b = $derived(a + result.window.days * 86400);
  const strips = $derived([
    { id: 'geom', label: t('analysis.windows.geometric'), iv: w.geometric_intervals_unix, cls: 'geom' },
    { id: 'real', label: t('analysis.windows.link'), iv: w.real_intervals_unix, cls: 'real' },
    { id: 'trans', label: t('analysis.windows.transition'), iv: w.transition_intervals_unix, cls: 'trans' },
  ]);
  const num = (v: number) => formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const hoursText = (v: number) => `${num(v)} h`;
  const pctText = (v: number) => `${num(v)} %`;
  const w2 = (v: number) => `${Math.max(v, 0)}%`;
  const gain = $derived(s.real - s.geometric);
</script>

<h3 id="bars-h">{t('analysis.windows.title')}</h3>
<p class="small muted">
  {t('analysis.windows.help', { rate: rateLabel(w.rate_bps) })}
</p>

<div class="bars" role="img" aria-labelledby="bars-h" aria-describedby="bars-text">
  <div class="row">
    <span class="row-label">{t('analysis.windows.geometric')}</span>
    <div class="bar">
      <span class="seg both" style="width: {w2(s.geometricBar.both)}"></span>
      <span class="seg notc" style="width: {w2(s.geometricBar.notClosing)}"></span>
      <span class="seg none" style="width: {w2(s.geometricBar.blocked)}"></span>
    </div>
    <span class="row-val num">{hoursText(s.geometric)} · {pctText(s.geometricPct)}</span>
  </div>
  <div class="row">
    <span class="row-label">{t('analysis.windows.link')}</span>
    <div class="bar">
      <span class="seg both" style="width: {w2(s.realBar.both)}"></span>
      <span class="seg trans" style="width: {w2(s.realBar.transition)}"></span>
      <span class="seg none" style="width: {w2(s.realBar.closed)}"></span>
    </div>
    <span class="row-val num">{hoursText(s.real)} · {pctText(s.realPct)}</span>
  </div>
</div>

<ul class="legend small" aria-label={t('analysis.windows.legend')}>
  <li><span class="sw both" aria-hidden="true"></span>{t('analysis.windows.both')}</li>
  <li><span class="sw notc" aria-hidden="true"></span>{t('analysis.windows.notClosing')}</li>
  <li><span class="sw trans" aria-hidden="true"></span>{t('analysis.windows.transitionHelp')}</li>
  <li><span class="sw none" aria-hidden="true"></span>{t('analysis.windows.neither')}</li>
</ul>

<p id="bars-text" class="summary" role="status" data-testid="windows-summary">
  {t('analysis.windows.summary', { total: hoursText(s.total), geometric: hoursText(s.geometric), geometricPct: pctText(s.geometricPct), link: hoursText(s.real), linkPct: pctText(s.realPct), transition: hoursText(s.transition), transitionPct: pctText(s.transitionPct) })}
  {t(gain > 0 ? 'analysis.windows.longer' : gain < 0 ? 'analysis.windows.shorter' : 'analysis.windows.same', { hours: hoursText(Math.abs(gain)) })}
</p>

{#if !simple}
<h3>{t('analysis.windows.overTime')}</h3>
<div class="strips" role="img" aria-label={t('analysis.windows.strips')}>
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
  <summary>{t('analysis.windows.table')}</summary>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="table-scroll" tabindex="0" role="region" aria-label={t('analysis.windows.tableRegion')}>
    <table>
      <caption>{t('analysis.windows.caption')}</caption>
      <thead><tr><th scope="col">{t('analysis.windows.quantity')}</th><th scope="col">{t('analysis.windows.hours')}</th><th scope="col">{t('analysis.windows.percent')}</th></tr></thead>
      <tbody>
        <tr><th scope="row">{t('analysis.windows.geometric')}</th><td class="num">{num(s.geometric)}</td><td class="num">{num(s.geometricPct)}</td></tr>
        <tr><th scope="row">{t('analysis.windows.link')}</th><td class="num">{num(s.real)}</td><td class="num">{num(s.realPct)}</td></tr>
        <tr><th scope="row">{t('analysis.windows.transitionHelp')}</th><td class="num">{num(s.transition)}</td><td class="num">{num(s.transitionPct)}</td></tr>
        <tr><th scope="row">{t('analysis.windows.notClosing')}</th><td class="num">{num(s.notClosing)}</td><td class="num">{num(s.total ? (100 * s.notClosing) / s.total : 0)}</td></tr>
        <tr><th scope="row">{t('analysis.windows.both')}</th><td class="num">{num(s.both)}</td><td class="num">{num(s.total ? (100 * s.both) / s.total : 0)}</td></tr>
      </tbody>
    </table>
  </div>
  <p class="small muted">
    {t('analysis.windows.intervalCounts', { geometric: w.geometric_intervals_unix.length, link: w.real_intervals_unix.length, transition: w.transition_intervals_unix.length })}
    {#if w.transition_intervals_unix.length}{t('analysis.windows.transition')}:
      {w.transition_intervals_unix.slice(0, 6).map(([x, y]) => `${new Date((x ?? 0) * 1000).toISOString().slice(5, 16).replace('T', ' ')} - ${new Date((y ?? 0) * 1000).toISOString().slice(5, 16).replace('T', ' ')}`).join('; ')}{w.transition_intervals_unix.length > 6 ? '; ...' : ''}.
    {/if}
  </p>
</details>
<p class="small muted">{t('analysis.windows.rule')}</p>
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
