<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Grafico uPlot (caricato a parte) con i colori dei token del design system. Il testo alternativo e le tabelle stanno
  accanto al grafico, nella scheda che lo usa. Il grafico e' decorativo per le tecnologie assistive (role=img + etichetta).
-->
<script lang="ts">
  import type { LineChart } from '../../charts/lineChart';

  export interface Spec {
    label: string;
    /** nome del token colore (es. '--c-uplink') */
    token: string;
    scale?: string;
    dash?: number[];
    points?: boolean;
  }
  let {
    series,
    x,
    ys,
    label,
    axisLabels = {},
    xNumeric = false,
    xLabel = '',
    height = 260,
  }: {
    series: Spec[];
    x: Float64Array;
    ys: Float64Array[];
    label: string;
    axisLabels?: Record<string, string>;
    xNumeric?: boolean;
    xLabel?: string;
    height?: number;
  } = $props();

  let el: HTMLElement | undefined = $state();
  let chart: LineChart | null = $state.raw(null);
  let failed = $state(false);

  $effect(() => {
    const host = el;
    if (!host) return;
    let alive = true;
    let made: LineChart | undefined;
    const css = getComputedStyle(host);
    const v = (n: string, f: string) => css.getPropertyValue(n).trim() || f;
    void import('../../charts/lineChart')
      .then(async ({ createLineChart }) => {
        const c = await createLineChart(host, {
          series: series.map((s) => ({
            label: s.label,
            stroke: v(s.token, '#0066cc'),
            ...(s.scale ? { scale: s.scale } : {}),
            ...(s.dash ? { dash: s.dash } : {}),
            ...(s.points ? { points: true } : {}),
          })),
          axisLabels,
          xNumeric,
          xLabel,
          height,
          axisStroke: v('--c-muted', '#6e6e73'),
          gridStroke: v('--c-hairline', '#d2d2d7'),
          font: `13px ${css.fontFamily || 'system-ui'}`,
        });
        if (!alive) return c.destroy();
        made = c;
        chart = c;
      })
      .catch(() => {
        if (alive) failed = true;
      });
    return () => {
      alive = false;
      chart = null;
      made?.destroy();
    };
  });

  $effect(() => {
    chart?.setData(x, ys);
  });
</script>

<div bind:this={el} class="chart" role="img" aria-label={label} data-ready={chart ? '1' : undefined}></div>
{#if failed}<p role="alert">Impossibile caricare il grafico: usa la tabella qui sotto.</p>{/if}

<style>
  .chart {
    min-height: 200px;
    width: 100%;
  }
  .chart :global(.u-legend) {
    display: none;
  }
</style>
