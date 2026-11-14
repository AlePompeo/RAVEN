// SPDX-License-Identifier: Apache-2.0
import type { Telemetry } from '../../contracts/telemetry';

export const MAX_SAMPLES = 120;
export const TABLE_ROWS = 10;

export interface TableModel {
  caption: string;
  headers: string[];
  rows: string[][];
}

/** Aggiunge un campione mantenendo al più `max` elementi (non muta l'input). */
export function pushSample(buf: readonly Telemetry[], s: Telemetry, max = MAX_SAMPLES): Telemetry[] {
  const next = buf.length >= max ? buf.slice(buf.length - max + 1) : buf.slice();
  next.push(s);
  return next;
}

/** Ultimi `n` campioni, più recente per primo, equivalente testuale del grafico. */
export function buildTable(samples: readonly Telemetry[], n = TABLE_ROWS): TableModel {
  const last = samples.slice(-n).reverse();
  return {
    caption: `Ultimi ${last.length} campioni di telemetria (più recente per primo)`,
    headers: ['Istante (UTC)', 'Sito', 'Potenza (W)', 'Margine di link (dB)'],
    rows: last.map((s) => [
      s.t_utc,
      s.site_id ?? '—',
      s.power_w.toFixed(1),
      s.link_margin_db === undefined ? '—' : s.link_margin_db.toFixed(1),
    ]),
  };
}

export interface ChartData {
  time: Float64Array;
  power_w: Float64Array;
  link_margin_db: Float64Array;
}

/** Serie per uPlot: tempo in secondi epoch; margine mancante -> NaN (buco nella linea). */
export function toChartData(samples: readonly Telemetry[]): ChartData {
  const n = samples.length;
  const d: ChartData = { time: new Float64Array(n), power_w: new Float64Array(n), link_margin_db: new Float64Array(n) };
  samples.forEach((s, i) => {
    d.time[i] = Date.parse(s.t_utc) / 1000;
    d.power_w[i] = s.power_w;
    d.link_margin_db[i] = s.link_margin_db ?? NaN;
  });
  return d;
}
