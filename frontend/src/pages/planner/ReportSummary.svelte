<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 1 of the report, the verdict page: title, the two sites and the period, ONE sentence that compares them with the
     numbers, side-by-side cards A | B and at most three bullets. Known yes, known no and unknown are drawn apart in every bar.
     The report is English only (reportText.ts). Nothing is computed here beyond counting samples. -->
<script lang="ts">
  import { rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { utcMinute } from './reportFormat';
  import { hoursText, meaning, pctOf, pctText, siteFigures, triHours, verdict, type SiteFigures, type Tri, type TriKey } from './reportCompare';
  import StatusChip from './StatusChip.svelte';
  import ReportRisks from './ReportRisks.svelte';
  import ReportTotals from './ReportTotals.svelte';
  import type { BudgetEstimate, CarbonEstimate } from './reportPlanning';
  import type { EngineEstimate } from './estimates';
  let { evaluations, missionName, start, days, created, expert = false, decision = '', budget = null, carbon = null, estimates, missionClass }: {
    budget?: BudgetEstimate | null; carbon?: CarbonEstimate | null; estimates?: readonly EngineEstimate[]; missionClass?: string;
    evaluations: readonly RavenEvaluation[]; missionName: string; start: string; days: number | null; created: string; expert?: boolean; decision?: string;
  } = $props();

  const figs = $derived(evaluations.map((e, i) => siteFigures(e, i)));
  const result = $derived(verdict(figs));
  const bullets = $derived(meaning(figs, result));
  type Kind = 'known' | 'knownno' | 'unknown';
  const chip = (x: Tri): Kind => (x.unknown > 0 ? 'unknown' : x.yes === 0 ? 'knownno' : 'known');
  const rows: { key: TriKey; label: string }[] = [
    { key: 'useful', label: rt('kpi.useful') }, { key: 'sun', label: rt('kpi.sun') }, { key: 'earth', label: rt('kpi.earth') }, { key: 'rf', label: rt('kpi.rf') },
  ];
  const width = (part: number, whole: number) => `${whole > 0 ? (part / whole * 100).toFixed(2) : 0}%`;
  const cell = (f: SiteFigures, key: TriKey) => {
    const x = f.tri[key];
    const h = triHours(x, f.stepMin);
    return { x, h, pct: pctOf(x.yes, x.n) };
  };
  const batteryChip = (f: SiteFigures): Kind => (f.minSoc === null || f.minSocScope !== 'all steps' ? 'unknown' : 'known');
</script>

<section class="rp-verdict-page" data-testid="report-summary" aria-labelledby="report-verdict-title">
  <div class="rp-kicker"><span>RAVEN · {rt('kicker')}</span><strong>{rt('preliminary')}</strong></div>
  <h2 class="rp-title">{rt('title', { a: figs[0]?.name ?? '', b: figs[1]?.name ?? '' })}</h2>
  <p class="rp-meta">{missionName} · {utcMinute(start)} · {days ?? '—'} d · {rt('meta.step', { min: evaluations[0]?.window.step_min ?? 0 })} · {rt('meta.calculated')} {utcMinute(created)}</p>
  <h3 id="report-verdict-title">{rt('part1')}</h3>
  <p class="rp-verdict" data-testid="report-verdict">{result.headline}.</p>
  <table class="rp-kpi" data-testid="report-kpi">
    <thead><tr><th scope="col">{rt('kpi.measure')}</th>
      {#each figs as f}<th scope="col" class={f.tag === 'A' ? 'col-a' : 'col-b'}><span class="sc-tag">{f.tag}</span> {f.name}</th>{/each}</tr></thead>
    <tbody>
      {#each rows as row}
        <tr><th scope="row">{row.label}</th>
          {#each figs as f}
            {@const c = cell(f, row.key)}
            <td>
              <span class="big">{row.key === 'useful' ? `${hoursText(c.h.yes)} h` : pctText(c.pct)}</span><span class="chipline"><StatusChip kind={chip(c.x)} /></span>
              {#if row.key === 'useful'}<span class="sub">{pctText(c.pct)} {rt('kpi.of')} {hoursText(c.h.total)} h</span>{/if}
              {#if row.key !== 'useful' && c.x.unknown > 0}<span class="sub" data-testid="kpi-range">{rt('kpi.between', { min: pctText(c.pct), max: pctText(pctOf(c.x.yes + c.x.unknown, c.x.n)) })}</span>{/if}
              {#if row.key === 'useful' && c.x.unknown > 0}<span class="sub" data-testid="useful-range">{rt('kpi.range', { yes: hoursText(c.h.yes), max: hoursText(c.h.yes + c.h.unknown) })}</span>{/if}
              <span class={`bar bar-${f.tag.toLowerCase()}`} role="img" aria-label={rt('bar.label', { yes: hoursText(c.h.yes), no: hoursText(c.h.no), unknown: hoursText(c.h.unknown) })}><span class="seg yes" style:width={width(c.x.yes, c.x.n)}></span><span class="seg no" style:width={width(c.x.no, c.x.n)}></span><span class="seg unk" style:width={width(c.x.unknown, c.x.n)}></span></span>
              {#if expert}<span class="sub">{rt('bar.numbers', { yes: hoursText(c.h.yes), no: hoursText(c.h.no), unknown: hoursText(c.h.unknown) })}</span>{/if}
            </td>
          {/each}
        </tr>
      {/each}
      <tr><th scope="row">{rt('kpi.battery')}</th>
        {#each figs as f}
          <td>
            <span class="big">{f.minSoc === null ? rt('unknown') : pctText(f.minSoc * 100)}</span><span class="chipline"><StatusChip kind={batteryChip(f)} /></span>
            <span class="sub">{rt('kpi.reserve')} {f.reserve === null ? rt('unknown') : pctText(f.reserve * 100)}{f.minSocScope === 'all steps' ? '' : ` · ${rt('kpi.knownOnly')}`}</span>
            <span class={`bar bar-${f.tag.toLowerCase()}`}><span class="seg yes" style:width={f.minSoc === null ? '0%' : `${(f.minSoc * 100).toFixed(2)}%`}></span><span class="seg no" style:width={f.minSoc === null ? '0%' : `${(100 - f.minSoc * 100).toFixed(2)}%`}></span><span class="seg unk" style:width={f.minSoc === null ? '100%' : '0%'}></span></span>
          </td>
        {/each}
      </tr>
    </tbody>
  </table>
  <aside class="rp-legend" data-testid="report-legend" aria-label={rt('legend.title')}>
    <span class="seg-key yes"></span> {rt('legend.yes')} <span class="seg-key no"></span> {rt('legend.no')} <span class="seg-key unk"></span> {rt('legend.unknown')}.
    {rt('legend.rule')}{#if expert}{' '}{rt('legend.expert')}{/if}
  </aside>
  <h4 class="rp-means">{rt('means.title')}</h4>
  <ul class="rp-bullets" data-testid="report-means">{#each bullets as b}<li>{b}</li>{/each}</ul>
  <ReportRisks {evaluations} {expert} />
  <ReportTotals {budget} {carbon} {estimates} {missionClass} {expert} />
  {#if decision.trim()}<p class="rp-decision" data-testid="report-decision"><strong>{rt('decision')}</strong> {decision}</p>{/if}
</section>
