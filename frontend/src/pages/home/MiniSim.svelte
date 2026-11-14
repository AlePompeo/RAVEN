<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mini-simulatore della home (chunk pigro, caricato quando la sezione si avvicina allo schermo): due cursori (Terra nel
  cielo, crinale) guidano lo stesso modello del browser di Simula (linkModel.computeLink, stessa tabella della
  correzione) e una vista di lato in Canvas 2D (lander, crinale, linea di vista, zona di Fresnel, Terra): niente WebGL,
  funziona ovunque. Con reduced motion l'impulso lungo il segnale non si muove; fuori schermo il disegno si ferma.
  Indicatore e frase riusano Gauge e sentence() di Simula; il pulsante porta i due valori in /simula (?el=&rh=).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../components/ui/Button.svelte';
  import { withBase } from '../../shell/router';
  import { modeNow } from '../../shell/modeState.svelte';
  import Gauge from '../simula/Gauge.svelte';
  import NumSlider from '../simula/NumSlider.svelte';
  import { computeLink, DEFAULT_INPUT, parseCompTable, type CompTable } from '../simula/linkModel';
  import { sentence } from '../simula/simState';
  import { formatNumber, t } from '../../i18n/i18n.svelte';
  import { pointAt, sideGeometry, simulaHref, type Pt } from './sideView';

  const fmt = (n: number, digits = 1) => formatNumber(n, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const STR = $derived({
    el: t('home.mini.el'),
    ridge: t('home.mini.ridge'),
    tipEl: t('home.mini.tipEl'),
    tipRidge: t('home.mini.tipRidge'),
    open: t('home.mini.open'),
    desc: (el: string, rh: string, w: string, bent: boolean) =>
      t('home.mini.desc', { el, rh, state: w, path: t(bent ? 'home.mini.pathBent' : 'home.mini.pathClear') }),
    legend: { los: t('home.mini.los'), fresnel: t('home.mini.fresnel'), bent: t('home.mini.bent') },
    scale: t('home.mini.scale'),
    tech: (nu: string, ld: string, r1: string, fspl: string) => t('home.mini.tech', { nu, ld, r1, fspl }),
  });
  const sentences = $derived({
    below: t('home.mini.sentence.below'),
    open: (m: string, r: string) => t('home.mini.sentence.open', { m, r }),
    transition: (m: string, r: string) => t('home.mini.sentence.transition', { m, r }),
    blockedSome: (m: string, r: string, max: string) => t('home.mini.sentence.blockedSome', { m, r, max }),
    blockedNone: (m: string) => t('home.mini.sentence.blockedNone', { m }),
  });

  let el = $state(DEFAULT_INPUT.earthElDeg);
  let rh = $state(DEFAULT_INPUT.ridgeHeightM ?? 33);
  let table = $state.raw<CompTable | null>(null);

  const out = $derived(computeLink({ earthElDeg: el, ridgeHeightM: rh }, table));
  const said = $derived(sentence(out, sentences, fmt));
  const reasons = $derived(out.validity.reasons.map((c) => t(`home.mini.flag.${c}`)));
  const href = $derived(withBase(simulaHref('/simula', el, rh), import.meta.env.BASE_URL));
  const desc = $derived(STR.desc(fmt(el, 1), fmt(rh, 0), t(`sim.gauge.state.${out.state}`), out.blocksLos));

  let canvas: HTMLCanvasElement | undefined = $state();
  let box: HTMLElement | undefined = $state();
  let size = $state({ w: 0, h: 0, dpr: 1 });
  let visible = false;
  let reduce = false;
  let raf = 0;
  let t0 = 0;

  const COL = { open: '#30d158', transition: '#ffb340', blocked: '#ff453a' } as const;

  function draw(now = 0) {
    const c = canvas;
    const ctx = c?.getContext('2d');
    if (!c || !ctx || size.w < 2) return;
    const { w, h, dpr } = size;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const g = sideGeometry(
      { earthElDeg: out.input.earthElDeg, ridgeHeightM: rh, ridgeDistanceM: out.input.ridgeDistanceM, mastM: out.input.mastM, fresnelR1M: out.fresnelR1M, blocksLos: out.blocksLos },
      w,
      h,
    );
    const poly = (pts: readonly Pt[], close = false) => {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (close) ctx.closePath();
    };
    // cielo nero, stelle fisse (deterministiche)
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.55)';
    for (let i = 0; i < 40; i++) ctx.fillRect(((i * 97) % 100) * (w / 100), ((i * 53) % 60) * (g.groundY / 100), 1.2, 1.2);
    // Terra
    const { x: ex, y: ey, r: er } = g.earth;
    const grad = ctx.createRadialGradient(ex - er * 0.4, ey - er * 0.4, er * 0.1, ex, ey, er);
    grad.addColorStop(0, '#9cc8ff');
    grad.addColorStop(0.55, '#2f6fd1');
    grad.addColorStop(1, '#0b2a5c');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(ex, ey, er, 0, Math.PI * 2);
    ctx.fill();
    // zona di Fresnel
    ctx.fillStyle = 'rgba(120,180,255,0.22)';
    poly(g.fresnel, true);
    ctx.fill();
    // linea di vista
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 5]);
    poly(g.los);
    ctx.stroke();
    ctx.setLineDash([]);
    // suolo e crinale
    ctx.fillStyle = '#5b5955';
    ctx.beginPath();
    ctx.moveTo(0, h);
    ctx.lineTo(0, g.groundY);
    for (const [x, y] of g.ridge) ctx.lineTo(x, Math.min(y, g.groundY));
    ctx.lineTo(w, g.groundY);
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#a9a59d';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, g.groundY);
    for (const [x, y] of g.ridge) ctx.lineTo(x, Math.min(y, g.groundY));
    ctx.lineTo(w, g.groundY);
    ctx.stroke();
    // lander: corpo, gambe, antenna
    const [lx, ly] = g.lander;
    const u = Math.max(6, h * 0.035);
    ctx.fillStyle = '#d9b24a';
    ctx.fillRect(lx - u, ly - u * 1.6, u * 2, u * 1.1);
    ctx.strokeStyle = '#d9b24a';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(lx - u, ly - u * 0.5);
    ctx.lineTo(lx - u * 1.5, ly);
    ctx.moveTo(lx + u, ly - u * 0.5);
    ctx.lineTo(lx + u * 1.5, ly);
    ctx.moveTo(lx, ly - u * 1.6);
    ctx.lineTo(g.antenna[0], g.antenna[1]);
    ctx.stroke();
    // segnale: diritto o piegato, nel colore dello stato (lo stato è anche scritto in parola sotto)
    const col = COL[out.state];
    ctx.strokeStyle = col;
    ctx.lineWidth = 3;
    if (g.bent) ctx.setLineDash([9, 6]);
    poly(g.path);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(g.antenna[0], g.antenna[1], 4, 0, Math.PI * 2);
    ctx.fill();
    if (g.bent) {
      ctx.beginPath();
      ctx.arc(g.tip[0], g.tip[1], 4, 0, Math.PI * 2);
      ctx.fill();
    }
    // impulso che corre verso la Terra (solo senza reduced motion)
    if (!reduce && now > 0) {
      const [px, py] = pointAt(g.path, ((now - t0) % 2400) / 2400);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.arc(px, py, 4.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function loop(now: number) {
    raf = 0;
    draw(now);
    if (visible && !reduce) raf = requestAnimationFrame(loop);
  }
  function kick() {
    if (!raf && visible && !reduce) raf = requestAnimationFrame(loop);
    else if (!visible || reduce) draw();
  }

  // ridisegno a ogni cambio dei controlli o della dimensione (anche con l'animazione ferma)
  $effect(() => {
    void out;
    void size;
    draw(reduce || !visible ? 0 : performance.now());
  });

  onMount(() => {
    const mql = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
    reduce = !!mql?.matches;
    const onMotion = () => {
      reduce = !!mql?.matches;
      kick();
    };
    mql?.addEventListener?.('change', onMotion);
    t0 = performance.now();
    const ro =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            const r = box?.getBoundingClientRect();
            if (!r || !canvas) return;
            const dpr = Math.min(2, window.devicePixelRatio || 1);
            canvas.width = Math.round(r.width * dpr);
            canvas.height = Math.round(r.height * dpr);
            size = { w: r.width, h: r.height, dpr };
          })
        : null;
    if (box) ro?.observe(box);
    const io =
      typeof IntersectionObserver !== 'undefined'
        ? new IntersectionObserver((es) => {
            visible = es.some((e) => e.isIntersecting);
            kick();
          })
        : null;
    if (box) io?.observe(box);
    else visible = true;
    // stessa tabella della correzione di Simula: stessi numeri; senza, la correzione è omessa (indicata dalla validità)
    let alive = true;
    void fetch('/api/raven/compensation')
      .then((r) => (r.ok ? r.json() : null))
      .then((j: unknown) => {
        if (alive && j) table = parseCompTable(j);
      })
      .catch(() => {});
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      ro?.disconnect();
      io?.disconnect();
      mql?.removeEventListener?.('change', onMotion);
    };
  });
</script>

<div class="mini" data-testid="mini-sim" data-state={out.state}>
  <figure class="stage-wrap">
    <div class="stage" bind:this={box} role="img" aria-label={desc} data-testid="mini-stage" data-state={out.state} data-bent={out.blocksLos ? '1' : '0'}>
      <canvas bind:this={canvas} aria-hidden="true"></canvas>
    </div>
    <figcaption>
      <ul class="legend">
        <li><span class="sw sw-los" aria-hidden="true"></span>{STR.legend.los}</li>
        <li><span class="sw sw-fresnel" aria-hidden="true"></span>{STR.legend.fresnel}</li>
        <li><span class="sw sw-bent" aria-hidden="true"></span>{STR.legend.bent}</li>
      </ul>
      <p class="small">{STR.scale}</p>
    </figcaption>
  </figure>
  <div class="ctrls">
    <NumSlider id="home-el" label={STR.el} bind:value={el} min={0} max={10} step={0.05} unit="°" tip={STR.tipEl} testid="mini-el" />
    <NumSlider id="home-ridge" label={STR.ridge} bind:value={rh} min={0} max={150} step={0.5} unit="m" digits={1} tip={STR.tipRidge} testid="mini-ridge" />
    <Gauge margin={out.marginDb} state={out.state} validity={out.validity.level} {reasons} sentence={said} />
    {#if modeNow.advanced}
      <p class="small tech" data-testid="mini-tech">{STR.tech(fmt(out.nu, 2), fmt(out.diffractionLossDb, 1), fmt(out.fresnelR1M, 1), fmt(out.fsplDb, 1))}</p>
    {/if}
    <p class="go"><Button {href} variant="ghost">{STR.open}</Button></p>
  </div>
</div>

<style>
  .mini {
    display: grid;
    grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
    gap: var(--space-5);
    align-items: start;
  }
  .stage-wrap {
    margin: 0;
  }
  .stage {
    position: relative;
    aspect-ratio: 16 / 10;
    border-radius: var(--radius-md, 12px);
    overflow: hidden;
    background: #000;
  }
  canvas {
    position: absolute;
    inset: 0;
    inline-size: 100%;
    block-size: 100%;
    display: block;
  }
  figcaption {
    margin-block-start: var(--space-2);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--fs-small);
  }
  .legend li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .sw {
    display: inline-block;
    inline-size: 1.6rem;
    block-size: 0.7rem;
    border-radius: 2px;
  }
  .sw-los {
    block-size: 0;
    border-block-start: 2px dashed var(--c-text);
  }
  .sw-fresnel {
    background: rgba(120, 180, 255, 0.45);
  }
  .sw-bent {
    block-size: 0;
    border-block-start: 3px dashed var(--c-muted);
  }
  .small {
    margin: var(--space-1) 0 0;
    font-size: var(--fs-small);
    color: var(--c-muted);
  }
  .ctrls {
    display: grid;
    gap: var(--space-3);
  }
  .go {
    margin: 0;
  }
  .tech {
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 899px) {
    .mini {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 599px) {
    .stage {
      aspect-ratio: 4 / 3;
    }
  }
</style>
