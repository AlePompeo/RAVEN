<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mappa di validità: elevazione della Terra (asse orizzontale) contro quota del crinale (verticale), 60 x 40 celle
  calcolate nel browser. Colore = stato del link (verde / ambra / rosso), trama = validità (nessuna: affidabile;
  righe oblique: incerto; quadrettato: fuori modello), quindi mai il solo colore. Clic o trascinamento sul grafico, o
  frecce con il focus, spostano il punto corrente e i controlli. Alternativa testuale: riepilogo + tabella ridotta.
-->
<script lang="ts">
  import { heatPick, type Heat, type LinkState, type ValidityLevel } from './linkModel';
  import { fmt, STR as S } from './simState';

  let { heat, el, ridge, ms, onpick }: { heat: Heat; el: number; ridge: number; ms: number; onpick: (el: number, ridge: number) => void } = $props();

  const STR = {
    title: 'Mappa di validità',
    lead: 'Dove la risposta vale: ogni cella è una combinazione di elevazione della Terra e quota del crinale, con gli altri parametri attuali.',
    aria: 'Mappa di validità, elevazione della Terra da 0 a 10 gradi in orizzontale, quota del crinale da 0 a 150 metri in verticale. Clic o frecce per spostare il punto corrente.',
    help: 'Con il focus sulla mappa: frecce sinistra e destra cambiano l’elevazione della Terra, su e giù la quota del crinale.',
    x: 'Elevazione della Terra (°)',
    y: 'Quota del crinale (m)',
    legendState: 'Colore: stato del link',
    legendValid: 'Trama: validità del modello',
    summary: (r: number, u: number, o: number) => `Celle affidabili ${r} %, incerte ${u} %, fuori modello ${o} %.`,
    table: 'Tabella ridotta della mappa (stato e validità)',
    current: (e: string, h: string) => `Punto corrente: Terra a ${e}°, crinale a ${h} m.`,
    computed: (t: string) => `Calcolata nel browser in ${t} ms.`,
  } as const;
  const FILL: Record<LinkState, string> = { open: '#30d158', transition: '#ffb340', blocked: '#ff6961' };
  const PAD = { l: 48, r: 10, t: 10, b: 36 };

  let canvas: HTMLCanvasElement | undefined = $state();
  let wrap: HTMLElement | undefined = $state();
  let width = $state(600);

  $effect(() => {
    const w = wrap;
    if (!w || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => (width = Math.max(240, w.clientWidth)));
    ro.observe(w);
    width = Math.max(240, w.clientWidth);
    return () => ro.disconnect();
  });

  const height = $derived(Math.round(Math.max(220, Math.min(380, width * 0.5))));

  function pattern(ctx: CanvasRenderingContext2D, kind: ValidityLevel): CanvasPattern | null {
    if (kind === 'reliable') return null;
    const p = document.createElement('canvas');
    p.width = p.height = 8;
    const c = p.getContext('2d');
    if (!c) return null;
    c.strokeStyle = 'rgba(0,0,0,0.65)';
    c.lineWidth = 1.4;
    c.beginPath();
    c.moveTo(0, 8);
    c.lineTo(8, 0);
    if (kind === 'outside') {
      c.moveTo(0, 0);
      c.lineTo(8, 8);
    }
    c.stroke();
    return ctx.createPattern(p, 'repeat');
  }

  $effect(() => {
    const c = canvas;
    const h = heat;
    const W = width;
    const H = height;
    const e0 = el;
    const r0 = ridge;
    if (!c) return;
    const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
    c.width = Math.round(W * dpr);
    c.height = Math.round(H * dpr);
    c.style.width = `${W}px`;
    c.style.height = `${H}px`;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const pw = W - PAD.l - PAD.r;
    const ph = H - PAD.t - PAD.b;
    const cw = pw / h.cols;
    const chh = ph / h.rows;
    const pats = { uncertain: pattern(ctx, 'uncertain'), outside: pattern(ctx, 'outside') };
    for (let k = 0; k < h.cells.length; k++) {
      const cell = h.cells[k]!;
      const i = k % h.cols;
      const j = Math.floor(k / h.cols);
      const x = PAD.l + i * cw;
      const y = PAD.t + ph - (j + 1) * chh;
      ctx.fillStyle = FILL[cell.state];
      ctx.fillRect(x, y, cw + 0.5, chh + 0.5);
      if (cell.validity !== 'reliable') {
        const pat = pats[cell.validity];
        if (pat) {
          ctx.fillStyle = pat;
          ctx.fillRect(x, y, cw + 0.5, chh + 0.5);
        }
        if (cell.validity === 'outside') {
          ctx.fillStyle = 'rgba(0,0,0,0.25)';
          ctx.fillRect(x, y, cw + 0.5, chh + 0.5);
        }
      }
    }
    // assi
    const css = getComputedStyle(c);
    const ink = css.getPropertyValue('--c-text').trim() || '#1d1d1f';
    ctx.strokeStyle = ink;
    ctx.fillStyle = ink;
    ctx.lineWidth = 1;
    ctx.font = `12px ${css.fontFamily || 'system-ui'}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let v = 0; v <= 10; v += 2) {
      const x = PAD.l + ((v - h.elRange[0]) / (h.elRange[1] - h.elRange[0])) * pw;
      ctx.fillText(String(v), x, PAD.t + ph + 4);
    }
    ctx.fillText(STR.x, PAD.l + pw / 2, PAD.t + ph + 19);
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let v = 0; v <= 150; v += 30) {
      const y = PAD.t + ph - ((v - h.ridgeRange[0]) / (h.ridgeRange[1] - h.ridgeRange[0])) * ph;
      ctx.fillText(String(v), PAD.l - 6, y);
    }
    ctx.save();
    ctx.translate(12, PAD.t + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillText(STR.y, 0, 0);
    ctx.restore();
    // punto corrente
    const px = PAD.l + ((Math.min(10, Math.max(0, e0)) - h.elRange[0]) / (h.elRange[1] - h.elRange[0])) * pw;
    const py = PAD.t + ph - ((Math.min(150, Math.max(0, r0)) - h.ridgeRange[0]) / (h.ridgeRange[1] - h.ridgeRange[0])) * ph;
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#000';
    ctx.beginPath();
    ctx.arc(px, py, 9, 0, 2 * Math.PI);
    ctx.stroke();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#fff';
    ctx.beginPath();
    ctx.arc(px, py, 9, 0, 2 * Math.PI);
    ctx.moveTo(px - 14, py);
    ctx.lineTo(px + 14, py);
    ctx.moveTo(px, py - 14);
    ctx.lineTo(px, py + 14);
    ctx.stroke();
  });

  let dragging = false;
  function pick(e: PointerEvent) {
    const c = canvas;
    if (!c) return;
    const r = c.getBoundingClientRect();
    const fx = (e.clientX - r.left - PAD.l) / (r.width - PAD.l - PAD.r);
    const fy = 1 - (e.clientY - r.top - PAD.t) / (r.height - PAD.t - PAD.b);
    const p = heatPick(heat, fx, fy);
    onpick(p.earthElDeg, p.ridgeHeightM);
  }
  function down(e: PointerEvent) {
    dragging = true;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    pick(e);
  }
  function move(e: PointerEvent) {
    if (dragging) pick(e);
  }
  function up() {
    dragging = false;
  }
  function key(e: KeyboardEvent) {
    const dx = (heat.elRange[1] - heat.elRange[0]) / heat.cols;
    const dy = (heat.ridgeRange[1] - heat.ridgeRange[0]) / heat.rows;
    const rtl = getComputedStyle(e.currentTarget as HTMLElement).direction === 'rtl';
    let ne = el;
    let nr = ridge;
    if (e.key === 'ArrowRight') ne += rtl ? -dx : dx;
    else if (e.key === 'ArrowLeft') ne -= rtl ? -dx : dx;
    else if (e.key === 'ArrowUp') nr += dy;
    else if (e.key === 'ArrowDown') nr -= dy;
    else return;
    e.preventDefault();
    const p = heatPick(heat, (ne - heat.elRange[0]) / (heat.elRange[1] - heat.elRange[0]), (nr - heat.ridgeRange[0]) / (heat.ridgeRange[1] - heat.ridgeRange[0]));
    onpick(p.earthElDeg, p.ridgeHeightM);
  }

  const counts = $derived.by(() => {
    const n = heat.cells.length || 1;
    const c = { reliable: 0, uncertain: 0, outside: 0 };
    for (const x of heat.cells) c[x.validity]++;
    return { r: Math.round((100 * c.reliable) / n), u: Math.round((100 * c.uncertain) / n), o: Math.round((100 * c.outside) / n) };
  });
  // tabella ridotta: 6 colonne di elevazione x 6 righe di quota
  const TCOLS = [0.5, 1, 2, 4, 6, 9];
  const TROWS = [140, 100, 70, 40, 20, 5];
  function cellAt(e: number, r: number) {
    const i = Math.min(heat.cols - 1, Math.floor(((e - heat.elRange[0]) / (heat.elRange[1] - heat.elRange[0])) * heat.cols));
    const j = Math.min(heat.rows - 1, Math.floor(((r - heat.ridgeRange[0]) / (heat.ridgeRange[1] - heat.ridgeRange[0])) * heat.rows));
    return heat.cells[j * heat.cols + i]!;
  }
</script>

<section class="vmap" aria-labelledby="vmap-h" data-testid="validity-map" data-ms={ms.toFixed(1)}>
  <h2 id="vmap-h">{STR.title}</h2>
  <p class="lead">{STR.lead}</p>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div
    class="wrap"
    bind:this={wrap}
    tabindex="0"
    role="group"
    aria-roledescription="mappa"
    aria-label={STR.aria}
    aria-describedby="vmap-help vmap-sum"
    data-testid="validity-canvas"
    data-spatial-skip
    onkeydown={key}
  >
    <canvas bind:this={canvas} aria-hidden="true" onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}></canvas>
  </div>
  <p id="vmap-help" class="visually-hidden">{STR.help}</p>
  <div class="legend">
    <p><strong>{STR.legendState}:</strong>
      {#each ['open', 'transition', 'blocked'] as const as s (s)}
        <span class="sw" style:background={FILL[s]} aria-hidden="true"></span> {S.state[s].symbol} {S.state[s].word}
      {/each}
    </p>
    <p><strong>{STR.legendValid}:</strong>
      <span class="sw pat-reliable" aria-hidden="true"></span> {S.validity.reliable.symbol} {S.validity.reliable.word}
      <span class="sw pat-uncertain" aria-hidden="true"></span> {S.validity.uncertain.symbol} {S.validity.uncertain.word}
      <span class="sw pat-outside" aria-hidden="true"></span> {S.validity.outside.symbol} {S.validity.outside.word}
    </p>
  </div>
  <p id="vmap-sum" class="small" data-testid="vmap-summary">
    {STR.summary(counts.r, counts.u, counts.o)} {STR.current(fmt(el, 2), fmt(ridge, 1))} {STR.computed(fmt(ms, 0))}
  </p>
  <details>
    <summary>{STR.table}</summary>
    <div class="tw">
      <table>
        <thead><tr><th scope="col">{STR.y} \ {STR.x}</th>{#each TCOLS as c (c)}<th scope="col">{fmt(c, 1)}°</th>{/each}</tr></thead>
        <tbody>
          {#each TROWS as r (r)}
            <tr>
              <th scope="row">{r} m</th>
              {#each TCOLS as c (c)}
                {@const x = cellAt(c, r)}
                <td>{S.state[x.state].symbol} {S.state[x.state].word}, {S.validity[x.validity].symbol} {S.validity[x.validity].word}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </details>
</section>

<style>
  .vmap {
    display: grid;
    gap: var(--space-2);
  }
  h2 {
    margin: 0;
  }
  .lead {
    margin: 0;
  }
  .vmap {
    min-inline-size: 0;
  }
  .wrap {
    inline-size: 100%;
    min-inline-size: 0;
    overflow: hidden;
  }
  canvas {
    display: block;
    touch-action: none;
    cursor: crosshair;
    border-radius: var(--radius-xs);
  }
  .wrap:focus-visible {
    outline: 3px solid var(--c-focus);
    outline-offset: 2px;
  }
  .legend p {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .sw {
    display: inline-block;
    inline-size: 1.1rem;
    block-size: 1.1rem;
    border: 1px solid var(--c-text);
    vertical-align: middle;
  }
  .pat-reliable {
    background: var(--c-bg);
  }
  .pat-uncertain {
    background: repeating-linear-gradient(135deg, var(--c-text) 0 1.5px, transparent 1.5px 6px);
  }
  .pat-outside {
    background:
      repeating-linear-gradient(135deg, var(--c-text) 0 1.5px, transparent 1.5px 6px),
      repeating-linear-gradient(45deg, var(--c-text) 0 1.5px, transparent 1.5px 6px);
  }
  .tw {
    overflow-x: auto;
  }
  table {
    border-collapse: collapse;
    font-size: var(--fs-small, 0.85rem);
  }
  th,
  td {
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--c-hairline);
    text-align: start;
  }
  summary {
    min-block-size: 44px;
    display: flex;
    align-items: center;
    cursor: pointer;
  }
</style>
