<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Where are the Sun and the Earth compared with the horizon? One panel per site: azimuth on x, elevation on y, one mark per step for the Sun
     (circle) and the Earth (square), filled when the body is above the terrain horizon at its azimuth, open when below; the terrain horizon at the
     azimuth of each body is drawn as a line. The azimuth axis is cut at the largest empty gap of the data (near the poles the Sun crosses north), so
     what happens stays together. Unknown steps are left out and counted. Plain SVG attributes (no patterns, no classes) so the PDF engine draws what
     the browser draws. -->
<script lang="ts">
  import { rt, nf } from './reportText';
  import { minusSign } from './reportFormat';
  import { niceAxis, cutAxis } from './reportCharts';
  import { shortName } from './reportCompare';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  let { evaluations }: { evaluations: readonly RavenEvaluation[] } = $props();

  const W = 300, L = 30, R = 16, TOP = 16, PH = 92, MAXMARKS = 110, MINSPAN = 30;
  const SUN = '#b25000', EARTH = '#0066cc', HORIZON = '#4b5563';
  interface Pt { az: number; rel: number; el: number; hz: number }
  const finite = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);
  const norm = (a: number) => ((a % 360) + 360) % 360;

  function track(az: readonly (number | null)[], el: readonly (number | null)[], hz: readonly (number | null)[]): { pts: { az: number; el: number; hz: number }[]; unknown: number } {
    const pts: { az: number; el: number; hz: number }[] = [];
    let unknown = 0;
    for (let i = 0; i < az.length; i++) {
      if (finite(az[i]) && finite(el[i]) && finite(hz[i])) pts.push({ az: norm(az[i]!), el: el[i]!, hz: hz[i]! }); else unknown += 1;
    }
    return { pts, unknown };
  }
  const thin = <T,>(a: readonly T[]): T[] => { const k = Math.max(1, Math.ceil(a.length / MAXMARKS)); return a.filter((_, i) => i % k === 0); };
  const panels = $derived(evaluations.slice(0, 2).map((e, i) => {
    const s = e.steps!;
    const sun = track(s.sun_az_deg, s.sun_el_deg, s.sun_horizon_deg);
    const earth = track(s.earth_az_deg, s.earth_el_deg, s.earth_horizon_deg);
    const raw = [...sun.pts, ...earth.pts];
    const { start, span } = cutAxis(raw.map((p) => p.az));
    const width = Math.max(MINSPAN, span);
    const pad = Math.max(3, width * 0.06);
    const lo = -pad - (width - span) / 2, hi = span + pad + (width - span) / 2;
    const rel = (a: number) => norm(a - start);
    const withRel = (pts: { az: number; el: number; hz: number }[]): Pt[] => pts.map((p) => ({ ...p, rel: rel(p.az) }));
    const axis = niceAxis(raw.flatMap((p) => [p.el, p.hz]), [0]);
    return { tag: i === 0 ? 'A' : 'B', name: shortName(e.site.name), sun: { pts: withRel(sun.pts), unknown: sun.unknown }, earth: { pts: withRel(earth.pts), unknown: earth.unknown }, start, lo, hi, axis, none: raw.length === 0 };
  }));
  type Panel = (typeof panels)[number];
  const X = (rel: number, p: Pick<Panel, 'lo' | 'hi'>) => L + ((rel - p.lo) / (p.hi - p.lo || 1)) * (W - L - R);
  const Y = (v: number, p: Pick<Panel, 'axis'>) => TOP + PH - ((v - p.axis.low) / (p.axis.high - p.axis.low || 1)) * PH;
  const tick = (v: number) => minusSign(nf(v, { maximumFractionDigits: 1 }));
  /** Ticks at round azimuths that fall inside the axis. */
  const azTicks = (p: Panel): { rel: number; label: number }[] => {
    const step = [5, 10, 15, 20, 30, 45, 60, 90].find((s) => (p.hi - p.lo) / s <= 6) ?? 90;
    const out: { rel: number; label: number }[] = [];
    for (let a = 0; a < 360; a += step) {
      let r = norm(a - p.start);
      if (r > p.hi) r -= 360;
      if (r >= p.lo && r <= p.hi) out.push({ rel: r, label: a });
    }
    return out;
  };
  const line = (pts: readonly Pt[], p: Panel) => [...pts].sort((a, b) => a.rel - b.rel).map((q) => `${X(q.rel, p).toFixed(1)},${Y(q.hz, p).toFixed(1)}`).join(' ');
</script>

{#if panels.length}
  <figure class="rp-sky" data-testid="report-sky" aria-label={rt('sky.q')}>
    <figcaption>{rt('sky.q')}</figcaption>
    {#each panels as p}
      <svg viewBox={`0 0 ${W} ${TOP + PH + 12}`} role="img" aria-label={rt('sky.alt', { id: p.tag })} data-sky={p.tag}>
        <text x={L} y="10" font-size="9" font-weight="700" fill="#1d1d1f">{p.tag} {p.name}</text>
        <rect x={L} y={TOP} width={W - L - R} height={PH} fill="#ffffff" stroke="#8d939c" stroke-width="0.5" />
        {#each p.axis.ticks as v}
          <line x1={L} x2={W - R} y1={Y(v, p)} y2={Y(v, p)} stroke="#d7dbe0" stroke-width="0.4" />
          <text x={L - 3} y={Y(v, p) + 3} text-anchor="end" font-size="8" fill="#1d1d1f">{tick(v)}</text>
        {/each}
        {#each azTicks(p) as a}
          <text x={X(a.rel, p)} y={TOP + PH + 9} text-anchor="middle" font-size="8" fill="#1d1d1f">{a.label}°</text>
        {/each}
        <line x1={L} x2={W - R} y1={Y(0, p)} y2={Y(0, p)} stroke="#1d1d1f" stroke-width="0.7" />
        {#if p.sun.pts.length > 1}<polyline fill="none" stroke={HORIZON} stroke-width="1" points={line(p.sun.pts, p)} />{/if}
        {#if p.earth.pts.length > 1}<polyline fill="none" stroke={HORIZON} stroke-width="1" stroke-dasharray="3 2" points={line(p.earth.pts, p)} />{/if}
        {#each thin(p.sun.pts) as q}
          <circle cx={X(q.rel, p)} cy={Y(q.el, p)} r="1.6" fill={q.el >= q.hz ? SUN : '#ffffff'} stroke={SUN} stroke-width="0.7" />
        {/each}
        {#each thin(p.earth.pts) as q}
          <rect x={X(q.rel, p) - 1.5} y={Y(q.el, p) - 1.5} width="3" height="3" fill={q.el >= q.hz ? EARTH : '#ffffff'} stroke={EARTH} stroke-width="0.7" />
        {/each}
        {#if p.none}<text x={(L + W - R) / 2} y={TOP + PH / 2} text-anchor="middle" font-size="9" fill="#1d1d1f">{rt('sky.none')}</text>{/if}
      </svg>
      {#if p.sun.unknown + p.earth.unknown > 0}<p class="rp-legend-line">{p.tag}: {rt('sky.unknown', { sun: p.sun.unknown, earth: p.earth.unknown })}</p>{/if}
    {/each}
    <p class="rp-legend-line"><span style:color={SUN}>●</span> {rt('sky.sun')} <span style:color={EARTH}>■</span> {rt('sky.earth')} · {rt('sky.key')}</p>
    <p class="rp-read">{rt('sky.read')}</p>
  </figure>
{/if}

<style>
  .rp-sky { margin: 1rem 0; break-inside: avoid; } figcaption { font-weight: 600; }
  svg { display: block; width: 100%; max-width: 26rem; height: auto; margin: .25rem auto; }
</style>
