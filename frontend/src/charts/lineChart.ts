// SPDX-License-Identifier: Apache-2.0
import type uPlotNS from 'uplot';

export interface SeriesSpec {
  label: string;
  stroke: string;
  /** Scala dell'asse Y (default 'y'). */
  scale?: string;
  /** Tratteggio (lunghezze in px), per distinguere le serie senza il solo colore. */
  dash?: number[];
  /** Solo marcatori, nessuna linea. */
  points?: boolean;
}

export interface LineChartOptions {
  series: SeriesSpec[];
  /** Etichetta degli assi Y per scala. */
  axisLabels?: Record<string, string>;
  height?: number;
  /** Colore di etichette e tacche degli assi (default: nero di uPlot). */
  axisStroke?: string;
  /** Colore della griglia. */
  gridStroke?: string;
  /** Famiglia/dimensione delle etichette degli assi (sintassi `font` del canvas). */
  font?: string;
  /** Asse X numerico (default: tempo in secondi epoch). */
  xNumeric?: boolean;
  /** Etichetta dell'asse X (solo asse numerico). */
  xLabel?: string;
}

export interface LineChart {
  /** `time` in secondi epoch (o valori X con `xNumeric`); una Float64Array per serie, stessa lunghezza. */
  setData(time: Float64Array, series: Float64Array[]): void;
  destroy(): void;
}

function axisStyle(o: LineChartOptions) {
  return {
    ...(o.axisStroke ? { stroke: o.axisStroke, ticks: { stroke: o.gridStroke ?? o.axisStroke, width: 1 } } : {}),
    ...(o.font ? { font: o.font, labelFont: o.font } : {}),
  };
}

function grid(o: LineChartOptions) {
  return o.gridStroke ? { stroke: o.gridStroke, width: 1 } : {};
}

/** uPlot e il suo CSS sono caricati lazy (chunk separato). */
export async function createLineChart(el: HTMLElement, opts: LineChartOptions): Promise<LineChart> {
  const [{ default: uPlot }] = await Promise.all([import('uplot'), import('uplot/dist/uPlot.min.css')]);
  const height = opts.height ?? 280;
  const scales = [...new Set(opts.series.map((s) => s.scale ?? 'y'))];
  const width = () => Math.max(200, el.clientWidth);

  const plot: uPlotNS = new uPlot(
    {
      width: width(),
      height,
      series: [
        {},
        ...opts.series.map((s) => ({
          label: s.label,
          stroke: s.stroke,
          width: 2,
          scale: s.scale ?? 'y',
          ...(s.dash ? { dash: s.dash } : {}),
          ...(s.points ? { paths: () => null, points: { show: true, size: 7, stroke: s.stroke, fill: s.stroke } } : {}),
        })),
      ],
      scales: {
        x: { time: !opts.xNumeric },
      },
      axes: [
        { ...axisStyle(opts), grid: grid(opts), ...(opts.xNumeric ? { label: opts.xLabel ?? '' } : {}) },
        ...scales.map((sc, i) => ({
          ...axisStyle(opts),
          scale: sc,
          side: (i === 0 ? 3 : 1) as 1 | 3,
          label: opts.axisLabels?.[sc] ?? '',
          grid: i === 0 ? grid(opts) : { show: false },
        })),
      ],
    },
    [new Float64Array(0), ...opts.series.map(() => new Float64Array(0))] as unknown as uPlotNS.AlignedData,
    el,
  );

  let ro: ResizeObserver | null = null;
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => plot.setSize({ width: width(), height }));
    ro.observe(el);
  }
  let destroyed = false;
  return {
    setData(time, series) {
      if (destroyed) return;
      const t0 = time[0];
      if (time.length === 1 && t0 !== undefined && !opts.xNumeric) {
        // un solo campione: finestra di ±30 s invece dell'intervallo di anni scelto da uPlot
        plot.setData([time, ...series] as unknown as uPlotNS.AlignedData, false);
        plot.setScale('x', { min: t0 - 30, max: t0 + 30 });
      } else plot.setData([time, ...series] as unknown as uPlotNS.AlignedData);
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      ro?.disconnect();
      plot.destroy();
    },
  };
}
