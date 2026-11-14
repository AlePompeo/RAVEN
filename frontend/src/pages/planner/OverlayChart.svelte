<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- One question, one chart: sites A and B overlaid on common axes, a strip per site under the plot that tells known-yes,
     known-no and unknown apart. Colours are plain attributes (no classes, no var()) so the PDF engine draws what the browser draws. -->
<script lang="ts">
  import { rt, nf } from './reportText';
  import { minusSign } from './reportFormat';
  import { niceAxis, runs, segments, type ReportChart } from './reportCharts';
  import { pieces, CHART_FORMULAS } from './reportFormulas';
  let { chart }: { chart: ReportChart } = $props();

  const W = 300, L = 34, R = 6, TOP = 6, PH = 78;
  const COLOR = { A: '#0066cc', B: '#b25000' } as const;
  const axis = $derived(niceAxis([...chart.lines.flatMap((l) => l.values), ...(chart.bounds ?? []).flatMap((b) => b.upper)], chart.refs.map((r) => r.value), chart.fixed));
  const t0 = $derived(Math.min(...chart.lines.map((l) => l.times[0] ?? Infinity)));
  const t1 = $derived(Math.max(...chart.lines.map((l) => l.times.at(-1) ?? -Infinity)));
  const x = (time: number) => L + (t1 > t0 ? (time - t0) / (t1 - t0) : 0) * (W - L - R);
  const y = (v: number) => TOP + PH - ((v - axis.low) / (axis.high - axis.low || 1)) * PH;
  const days = $derived((t1 - t0) / 86400);
  const dayStep = $derived(Math.max(1, Math.ceil(days / 6)));
  const dayTicks = $derived(Array.from({ length: Math.floor(days / dayStep) + 1 }, (_, i) => i * dayStep));
  const tick = (v: number) => minusSign(nf(v, { maximumFractionDigits: 1 }));
  const stripY = (i: number) => TOP + PH + 6 + i * 8;
  const noValues = $derived(chart.lines.filter((l) => !l.values.some((v) => v !== null && Number.isFinite(v))));
  /** Diagonal lines clipped to the rectangle (x, y, w, h): hatching without SVG patterns, which the PDF engine ignores. dir -1 = "/", 1 = "\". */
  function hatchLines(x0: number, y0: number, w: number, h: number, gap: number, dir: 1 | -1): { x1: number; y1: number; x2: number; y2: number }[] {
    const out: { x1: number; y1: number; x2: number; y2: number }[] = [];
    for (let k = 0; k <= w + h; k += gap) {
      const xa = Math.max(0, k - h), xb = Math.min(w, k);
      if (xb <= xa) continue;
      const fx = (v: number) => (dir === -1 ? x0 + v : x0 + w - v);
      out.push({ x1: fx(xa), y1: y0 + (k - xa), x2: fx(xb), y2: y0 + (k - xb) });
    }
    return out;
  }
  const withStart = (values: readonly (boolean | null)[]) => { let at = 0; return runs(values).map((r) => { const o = { ...r, at }; at += r.length; return o; }); };
  // unknown spans are shown ON the plot too (not only in the strip): a hatched band in the colour of the site
  const spans = $derived(chart.id === 'cum' ? [] : chart.strips.flatMap((st, si) => withStart(st.values).filter((r) => r.value === null).map((r) => ({ tag: st.tag, a: chart.lines[si]!.times[r.at]!, b: r.at + r.length >= chart.lines[si]!.times.length ? t1 : chart.lines[si]!.times[r.at + r.length]! }))));
  const anyUnknown = $derived(chart.strips.some((st) => st.values.some((v) => v === null)));
  const band = (b: NonNullable<typeof chart.bounds>[number], i: number) => {
    const t = chart.lines[i]!.times;
    return [...b.upper.map((v, k) => `${x(t[k]!).toFixed(1)},${y(v).toFixed(1)}`), ...b.lower.map((v, k) => `${x(t[k]!).toFixed(1)},${y(v).toFixed(1)}`).reverse()].join(' ');
  };
  const caption = $derived(CHART_FORMULAS[chart.id].map((l) => pieces(l).map((p) => p.text).join('')).join('; '));
</script>

<figure class="rp-chart" data-chart={chart.id}>
  <figcaption>{chart.title}</figcaption>
  <svg viewBox={`0 0 ${W} ${TOP + PH + 8 + chart.strips.length * 8 + 12}`} role="img" aria-label={`${chart.title} (${chart.unit})`}>
    <rect x={L} y={TOP} width={W - L - R} height={PH} fill="#ffffff" stroke="#8d939c" stroke-width="0.5" />
    {#each axis.ticks as v}
      <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#d7dbe0" stroke-width="0.4" />
      <text x={L - 3} y={y(v) + 3} text-anchor="end" font-size="8" fill="#1d1d1f">{tick(v)}</text>
    {/each}
    {#each spans as sp}
      {#each hatchLines(x(sp.a), TOP, Math.max(0.6, x(sp.b) - x(sp.a)), PH, 5, sp.tag === 'A' ? -1 : 1) as l}
        <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke={COLOR[sp.tag]} stroke-width="0.6" stroke-opacity="0.6" />
      {/each}
    {/each}
    {#each chart.bounds ?? [] as b, bi}
      <polygon points={band(b, bi)} fill={COLOR[b.tag]} fill-opacity="0.18" stroke="none" />
      <polyline fill="none" stroke={COLOR[b.tag]} stroke-width="0.8" stroke-dasharray="1.5 2" points={b.upper.map((v, k) => `${x(chart.lines[bi]!.times[k]!).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} />
    {/each}
    {#each chart.refs as r}
      <line x1={L} x2={W - R} y1={y(r.value)} y2={y(r.value)} stroke="#1d1d1f" stroke-width="0.8" stroke-dasharray={r.dashed ? '4 3' : '0'} />
    {/each}
    {#each chart.lines as line}
      {#each segments(line.values) as seg}
        {#if seg.length === 1}<circle cx={x(line.times[seg[0]!]!)} cy={y(line.values[seg[0]!]!)} r="1.2" fill={COLOR[line.tag]} />
        {:else}<polyline fill="none" stroke={COLOR[line.tag]} stroke-width="1.3" stroke-dasharray={line.tag === 'B' ? '4 2' : '0'}
          points={seg.map((i) => `${x(line.times[i]!).toFixed(1)},${y(line.values[i]!).toFixed(1)}`).join(' ')} />{/if}
      {/each}
    {/each}
    {#each chart.strips as strip, si}
      {@const line = chart.lines[si]!}
      {@const sy = stripY(si)}
      <text x={L - 3} y={sy + 5.5} text-anchor="end" font-size="8" font-weight="700" fill={COLOR[strip.tag]}>{strip.tag}</text>
      {#each (() => { let at = 0; return runs(strip.values).map((r) => { const o = { ...r, at }; at += r.length; return o; }); })() as r}
        {@const a = x(line.times[r.at]!)}
        {@const b = r.at + r.length >= line.times.length ? x(t1) : x(line.times[r.at + r.length]!)}
        <rect x={a} y={sy} width={Math.max(0.6, b - a)} height="6" stroke="#1d1d1f" stroke-width="0.25"
          fill={r.value === true ? COLOR[strip.tag] : r.value === false ? '#ffffff' : '#eceef1'} />
        {#if r.value === null}
          {#each hatchLines(a, sy, Math.max(0.6, b - a), 6, 2.4, -1) as l}<line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="#4b5563" stroke-width="0.5" />{/each}
        {/if}
      {/each}
    {/each}
    {#each dayTicks as d}
      <text x={x(t0 + d * 86400)} y={TOP + PH + 8 + chart.strips.length * 8 + 8} text-anchor="middle" font-size="8" fill="#1d1d1f">{d} d</text>
    {/each}
  </svg>
  <p class="rp-legend-line"><span class="rp-key rp-key-a"></span>A {chart.lines[0]?.name} <span class="rp-key rp-key-b"></span>B {chart.lines[1]?.name} · {chart.unit} · {rt('chart.xaxis')}
    {#each noValues as l}<strong> · {rt('chart.noValues', { id: l.tag })}</strong>{/each}
    {#if chart.bounds && anyUnknown} · {rt('chart.bandKey')}{:else if anyUnknown} · {rt('chart.hatchKey')}{/if}</p>
  <p class="rp-read">{chart.read}</p>
  <p class="rp-formula">{caption}. {chart.formula}</p>
</figure>
