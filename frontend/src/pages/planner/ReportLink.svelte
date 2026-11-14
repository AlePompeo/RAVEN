<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 2, link figures from the engine steps of A and B: where the signal stops arriving (margin against the Earth elevation),
     how many hours the link comes from the line of sight or from diffraction, and (Expert) the mean loss terms. -->
<script lang="ts">
  import { nf, rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import ComparisonBars from './ComparisonBars.svelte';
  import { elevationMargin, linkHours, linkTerms, medianHorizon } from './reportLink';
  let { evaluations, expert = true }: { evaluations: readonly RavenEvaluation[]; expert?: boolean } = $props();

  const names = $derived(evaluations.map((e, i) => `${i === 0 ? 'A' : 'B'}: ${e.site.name}`));
  const data = $derived(evaluations.map((e) => ({ points: elevationMargin(e), horizon: medianHorizon(e), hours: linkHours(e), terms: linkTerms(e) })));
  const anyPoints = $derived(data.some((d) => d.points.length > 0));
  const W = 640, H = 280, L = 44, R = 12, T = 12, B = 36;
  const all = $derived(data.flatMap((d) => d.points));
  const xLo = $derived(all.length ? Math.floor(Math.min(...all.map((p) => p.el))) : 0);
  const xHi = $derived(all.length ? Math.ceil(Math.max(...all.map((p) => p.el))) : 1);
  const yLo = $derived(all.length ? Math.floor(Math.min(0, ...all.map((p) => p.margin)) / 5) * 5 : 0);
  const yHi = $derived(all.length ? Math.ceil(Math.max(0, ...all.map((p) => p.margin)) / 5) * 5 : 1);
  const X = (v: number) => L + ((v - xLo) / Math.max(1e-9, xHi - xLo)) * (W - L - R);
  const Y = (v: number) => T + (1 - (v - yLo) / Math.max(1e-9, yHi - yLo)) * (H - T - B);
  const colors = ['#0b5cad', '#a15c00']; // fixed hues: the PDF has no page theme variables
  const hours = (v: number | undefined) => (v === undefined ? null : v);
  const fmt = (v: number | null, d = 1) => (v === null ? rt('unknown') : nf(Math.abs(v) < 0.5 * 10 ** -d ? 0 : v, { maximumFractionDigits: d }));
  const db = (v: number | null) => (v === null ? rt('unknown') : `${fmt(v)} dB`);
  const hasHours = $derived(data.some((d) => d.hours !== null));
</script>

<div class="rp-link" data-testid="report-link">
  {#if anyPoints}
    <figure class="rp-elev" aria-label={rt('lnk.q.elev')}>
      <figcaption>{rt('lnk.q.elev')}</figcaption>
      <p class="rp-how">{rt('lnk.d.elev')}</p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={rt('lnk.q.elev')}>
        <line x1={L} y1={Y(0)} x2={W - R} y2={Y(0)} stroke="#4a4f57" stroke-dasharray="4 3" />
        {#each data as d, i}
          {#if d.horizon !== null && d.horizon >= xLo && d.horizon <= xHi}
            <line x1={X(d.horizon)} y1={T} x2={X(d.horizon)} y2={H - B} stroke-dasharray="6 3" stroke-width="1.5" style:stroke={colors[i % 2]} />
          {/if}
          {#each d.points as p}
            {#if i === 0}<circle cx={X(p.el)} cy={Y(p.margin)} r="2.2" style:fill={colors[0]} />
            {:else}<rect x={X(p.el) - 2} y={Y(p.margin) - 2} width="4" height="4" style:fill={colors[1]} />{/if}
          {/each}
        {/each}
        <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="#4a4f57" stroke-width="1" /><line x1={L} y1={T} x2={L} y2={H - B} stroke="#4a4f57" stroke-width="1" />
        <text x={L} y={H - 20} fill="#1d1d1f" font-size="11">{xLo}°</text><text x={W - R} y={H - 20} fill="#1d1d1f" font-size="11" text-anchor="end">{xHi}°</text>
        <text x={L - 4} y={Y(yHi) + 8} fill="#1d1d1f" font-size="11" text-anchor="end">{yHi}</text><text x={L - 4} y={Y(yLo)} fill="#1d1d1f" font-size="11" text-anchor="end">{yLo}</text>
        <text x={(L + W - R) / 2} y={H - 4} fill="#1d1d1f" font-size="11" text-anchor="middle">{rt('lnk.x')}</text>
        <text x="4" y="10" fill="#1d1d1f" font-size="11">{rt('lnk.y')}</text>
      </svg>
      <ul class="legend rp-legend-line" aria-label={rt('lnk.legend')}>
        {#each names as n, i}<li><span class="key" style:color={colors[i % 2]}>{i === 0 ? '●' : '■'}</span>{n}</li>{/each}
        <li>{rt('lnk.zero')}</li><li>{rt('lnk.horizon')}</li>
      </ul>
    </figure>
  {/if}

  {#if hasHours}
    <ComparisonBars label={rt('lnk.q.hours')} unit="h" description={rt('lnk.d.hours')} series={names}
      rows={[
        { label: rt('lnk.hours.geo'), values: data.map((d) => hours(d.hours?.geometric)) },
        { label: rt('lnk.hours.avail'), values: data.map((d) => hours(d.hours?.available)) },
        { label: rt('lnk.hours.beyond'), values: data.map((d) => hours(d.hours?.beyondLos)) },
      ]} />
    {#if data.some((d) => (d.hours?.unknown ?? 0) > 0)}
      <p class="rp-how">{rt('lnk.unknown', { a: fmt(data[0]?.hours?.unknown ?? null), b: fmt(data[1]?.hours?.unknown ?? null) })}</p>
    {/if}
  {/if}

  {#if expert && data.some((d) => d.terms)}
    <table class="rp-risktable" data-testid="link-terms">
      <thead><tr><th scope="col">{rt('lnk.terms')}</th>{#each names as n}<th scope="col">{n}</th>{/each}</tr></thead>
      <tbody>
        <tr><th scope="row">{rt('lnk.term.fs')}</th>{#each data as d}<td>{db(d.terms?.freeSpaceDb ?? null)}</td>{/each}</tr>
        <tr><th scope="row">{rt('lnk.term.diff')}</th>{#each data as d}<td>{db(d.terms?.diffractionDb ?? null)}</td>{/each}</tr>
        <tr><th scope="row">{rt('lnk.term.mp')}</th>{#each data as d}<td>{db(d.terms?.multipathDb ?? null)}</td>{/each}</tr>
        <tr><th scope="row">{rt('lnk.term.margin')}</th>{#each data as d}<td>{db(d.terms?.marginDb ?? null)} ({d.terms?.knownSteps ?? 0} steps)</td>{/each}</tr>
      </tbody>
    </table>
  {/if}
</div>

<style>
  .rp-elev { margin: 1rem 0; break-inside: avoid; } figcaption { font-weight: 600; }
  svg { width: 100%; max-width: 44rem; height: auto; display: block; }
  .legend { display: flex; flex-wrap: wrap; gap: .3rem .8rem; list-style: none; padding: 0; font-size: .75rem; }
  .key { margin-right: .3rem; }
</style>
