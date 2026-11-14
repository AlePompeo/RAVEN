<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Grafico 2D (uPlot caricato a parte tramite ChartBox): margine contro elevazione della Terra con i parametri correnti,
  il punto corrente, la soglia di 0 dB e l'orizzonte geometrico del crinale, così si vede DOVE il link smette di
  funzionare. Il tratto dove il crinale copre la Terra è tratteggiato a parte. La frase sotto dice gli stessi numeri.
-->
<script lang="ts">
  import ChartBox, { type Spec } from '../grazinglink/ChartBox.svelte';
  import type { MarginChart } from './linkModel';
  import { fmt } from './simState';

  let { data, note = '' }: { data: MarginChart; note?: string } = $props();

  const STR = {
    title: 'Dove il segnale smette di arrivare',
    label: 'Grafico del margine di link contro l’elevazione della Terra, con il punto corrente, la soglia di 0 dB e l’orizzonte geometrico del crinale.',
    margin: 'Margine (dB)',
    covered: 'Terra dietro il crinale',
    zero: 'Soglia 0 dB',
    current: 'Punto corrente',
    horizon: 'Orizzonte geometrico del crinale',
    x: 'Elevazione della Terra (°)',
    fail: (f: string, h: string) => `Il margine scende sotto 0 dB sotto ${f}°; la cima del crinale è a ${h}° (orizzonte geometrico): tra i due il segnale arriva piegato.`,
    never: (h: string) => `Con questi parametri il margine resta sopra 0 dB in tutto l’intervallo; la cima del crinale è a ${h}°.`,
    always: (h: string) => `Con questi parametri il margine resta sotto 0 dB in tutto l’intervallo; la cima del crinale è a ${h}°.`,
  } as const;
  const series: Spec[] = [
    { label: STR.margin, token: '--c-uplink' },
    { label: STR.covered, token: '--c-danger', dash: [6, 4] },
    { label: STR.zero, token: '--c-muted', dash: [2, 4] },
    { label: STR.current, token: '--c-text', points: true },
    { label: STR.horizon, token: '--c-power', points: true },
  ];
  // uPlot vuole null per i buchi: un NaN in una serie a linea rompe il calcolo della scala Y (grafico vuoto)
  const gaps = (a: Float64Array) => Array.from(a, (v) => (Number.isNaN(v) ? null : v)) as unknown as Float64Array;
  const ys = $derived([data.margin, gaps(data.covered), data.zero, gaps(data.current), gaps(data.horizon)]);
  const text = $derived.by(() => {
    const h = fmt(data.horizonDeg, 2);
    if (data.failDeg === null) return STR.never(h);
    if (data.failDeg >= data.x[data.x.length - 1]!) return STR.always(h);
    return STR.fail(fmt(data.failDeg, 2), h);
  });
</script>

<section class="mchart" aria-labelledby="mchart-h" data-testid="margin-chart" data-fail={data.failDeg ?? ''} data-current={Array.from(data.current).find((v) => !Number.isNaN(v))?.toFixed(2) ?? ''}>
  <h2 id="mchart-h">{STR.title}</h2>
  <ul class="keys" aria-hidden="true">
    <li><span class="k k-line"></span>{STR.margin}</li>
    <li><span class="k k-dash"></span>{STR.covered}</li>
    <li><span class="k k-dot"></span>{STR.zero}</li>
    <li><span class="k k-pt"></span>{STR.current}</li>
    <li><span class="k k-hz"></span>{STR.horizon}</li>
  </ul>
  <ChartBox {series} x={data.x} {ys} label={STR.label} xNumeric xLabel={STR.x} axisLabels={{ y: 'dB' }} height={240} />
  <p class="small" data-testid="chart-text">{text}{note ? ` ${note}` : ''}</p>
</section>

<style>
  .mchart {
    min-inline-size: 0;
    overflow: hidden;
    display: grid;
    gap: var(--space-2);
  }
  h2 {
    margin: 0;
  }
  .keys {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--fs-small, 0.85rem);
  }
  .keys li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .k {
    display: inline-block;
    inline-size: 1.4rem;
    block-size: 0;
    border-block-start: 3px solid var(--c-uplink);
  }
  .k-dash {
    border-block-start: 3px dashed var(--c-danger);
  }
  .k-dot {
    border-block-start: 3px dotted var(--c-muted);
  }
  .k-pt,
  .k-hz {
    inline-size: 0.7rem;
    block-size: 0.7rem;
    border: 0;
    border-radius: 50%;
    background: var(--c-text);
  }
  .k-hz {
    background: var(--c-power);
  }
</style>
