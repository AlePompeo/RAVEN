// SPDX-License-Identifier: Apache-2.0
// The four charts of the report, as plain data: A and B overlaid on common axes, a strip of known-yes / known-no /
// unknown under each. Pure functions; the SVG is drawn by OverlayChart.svelte.
import { rt } from './reportText';
import type { RavenEvaluation } from '../../shell/ravenApi';
import { earthVisibility } from './journey';
import { shortName } from './reportCompare';

export interface ChartLine { tag: 'A' | 'B'; name: string; values: (number | null)[]; times: number[] }
export interface ChartStrip { tag: 'A' | 'B'; values: (boolean | null)[] }
export interface ChartRef { value: number; label: string; dashed?: boolean }
/** Cumulative useful hours bounded: `lower` counts only confirmed steps, `upper` also counts every unknown step as useful. */
export interface ChartBound { tag: 'A' | 'B'; lower: number[]; upper: number[] }
export interface ReportChart {
  id: 'sun' | 'earth' | 'rf' | 'battery' | 'cum';
  title: string;
  unit: string;
  lines: ChartLine[];
  strips: ChartStrip[];
  bounds?: ChartBound[];
  stripLabel: string;
  refs: ChartRef[];
  read: string;
  formula: string;
  /** Fixed y range (battery 0-100 %); otherwise the range of the data of both sites. */
  fixed?: [number, number];
}

export function reportCharts(evaluations: readonly RavenEvaluation[]): ReportChart[] {
  const tag = (i: number) => (i === 0 ? 'A' : 'B') as 'A' | 'B';
  const lines = (pick: (e: RavenEvaluation) => (number | null)[]): ChartLine[] =>
    evaluations.map((e, i) => ({ tag: tag(i), name: shortName(e.site.name), values: pick(e), times: e.steps!.time_unix.map((u) => u - e.steps!.time_unix[0]!) }));
  const strips = (pick: (e: RavenEvaluation) => (boolean | null)[]): ChartStrip[] => evaluations.map((e, i) => ({ tag: tag(i), values: pick(e) }));
  const required = evaluations[0]?.parameters_used?.scenario.required_margin_db;
  const reserve = evaluations[0]?.parameters_used?.energy.min_soc;
  return [
    { id: 'sun', title: rt('chart.sun.title'), unit: '°', lines: lines((e) => e.steps!.sun_el_deg), strips: strips((e) => e.steps!.lit),
      stripLabel: rt('chart.sun.strip'), refs: [{ value: 0, label: rt('chart.sun.ref') }],
      read: rt('chart.sun.read'), formula: rt('chart.sun.formula') },
    { id: 'earth', title: rt('chart.earth.title'), unit: '°', lines: lines((e) => e.steps!.earth_el_deg), strips: strips(earthVisibility),
      stripLabel: rt('chart.earth.strip'), refs: [{ value: 0, label: rt('chart.earth.ref') }],
      read: rt('chart.earth.read'), formula: rt('chart.earth.formula') },
    { id: 'rf', title: rt('chart.rf.title'), unit: 'dB', lines: lines((e) => e.steps!.margin_db), strips: strips((e) => e.steps!.rf_closes),
      stripLabel: rt('chart.rf.strip'),
      refs: [{ value: 0, label: rt('chart.rf.ref0') }, ...(typeof required === 'number' && required > 0 ? [{ value: required, label: rt('chart.rf.refReq', { db: String(required) }), dashed: true }] : [])],
      read: rt('chart.rf.read'), formula: rt('chart.rf.formula') },
    { id: 'battery', title: rt('chart.battery.title'), unit: '%', lines: lines((e) => e.steps!.soc.map((v) => (v === null ? null : v * 100))),
      strips: strips((e) => e.steps!.state.map((s) => (s === 'unknown' ? null : s === 'operational'))), stripLabel: rt('chart.battery.strip'),
      refs: typeof reserve === 'number' ? [{ value: reserve * 100, label: rt('chart.battery.ref', { pct: String(Math.round(reserve * 1000) / 10) }), dashed: true }] : [],
      read: rt('chart.battery.read'), formula: rt('chart.battery.formula'), fixed: [0, 100] },
    { id: 'cum', title: rt('chart.cum.title'), unit: 'h', lines: lines(cumulativeUseful(evaluations)), strips: strips((e) => e.steps!.useful),
      stripLabel: rt('chart.cum.strip'), refs: [], read: rt('chart.cum.read'), formula: rt('chart.cum.formula'), bounds: evaluations.map((e, i) => ({ tag: tag(i), ...usefulBounds(e) })) },
  ];
}

/** Useful hours accumulated up to each sample. From the first unknown step on the total is unknown (null, the line stops): it is never carried on as if the unknown steps were zero. */
const cumulativeUseful = (_evaluations: readonly RavenEvaluation[]) => (e: RavenEvaluation): (number | null)[] => {
  const h = e.window.step_min / 60;
  let total = 0;
  let unknown = false;
  return e.steps!.useful.map((u) => { if (u === null) unknown = true; if (unknown) return null; if (u === true) total += h; return Math.round(total * 1000) / 1000; });
};

/** Lower and upper cumulative useful hours at every sample: unknown steps add nothing to the lower and the full step to the upper bound. */
export function usefulBounds(e: RavenEvaluation): { lower: number[]; upper: number[] } {
  const h = e.window.step_min / 60;
  let lo = 0, up = 0;
  const lower: number[] = [], upper: number[] = [];
  for (const u of e.steps!.useful) {
    if (u === true) { lo += h; up += h; } else if (u === null) up += h;
    lower.push(Math.round(lo * 1000) / 1000); upper.push(Math.round(up * 1000) / 1000);
  }
  return { lower, upper };
}

export interface Axis { low: number; high: number; ticks: number[] }
/** Common y axis of both sites: round tick steps, 0 included when the data cross it. Unknown values are ignored, never read as 0. */
export function niceAxis(values: readonly (number | null)[], refs: readonly number[], fixed?: [number, number]): Axis {
  if (fixed) return { low: fixed[0], high: fixed[1], ticks: [fixed[0], (fixed[0] + fixed[1]) / 2, fixed[1]] };
  const all = [...values.filter((v): v is number => v !== null && Number.isFinite(v)), ...refs];
  if (!all.length) return { low: 0, high: 1, ticks: [0, 1] };
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const low = Math.floor(lo / step) * step;
  const high = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = low; v <= high + step / 2; v += step) ticks.push(Math.round(v / step) * step);
  return { low, high, ticks };
}

/** Runs of consecutive equal states, for the strips (and to test that unknown stays apart from no). */
export function runs(values: readonly (boolean | null)[]): { value: boolean | null; length: number }[] {
  const out: { value: boolean | null; length: number }[] = [];
  for (const v of values) {
    const last = out.at(-1);
    if (last && last.value === v) last.length += 1; else out.push({ value: v, length: 1 });
  }
  return out;
}

/** Polyline segments of a series: unknown samples break the line, they are never bridged or drawn as 0. */
export function segments(values: readonly (number | null)[]): number[][] {
  const out: number[][] = [];
  let cur: number[] = [];
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) { if (cur.length) out.push(cur); cur = []; } else cur.push(i);
  });
  if (cur.length) out.push(cur);
  return out;
}

/** Start of an azimuth axis (the first value after the largest empty gap on the circle) and the span the data cover: near the poles the Sun
 *  crosses north, and an axis cut there would put the same movement at both ends. */
export function cutAxis(azimuths: readonly number[]): { start: number; span: number } {
  if (!azimuths.length) return { start: 0, span: 360 };
  const norm = (a: number) => ((a % 360) + 360) % 360;
  const s = [...new Set(azimuths.map((a) => Math.round(norm(a) * 10) / 10))].sort((a, b) => a - b);
  let best = 360 - s[s.length - 1]! + s[0]!, at = 0; // the gap across north
  for (let i = 1; i < s.length; i++) { const g = s[i]! - s[i - 1]!; if (g > best) { best = g; at = i; } }
  return { start: s[at]!, span: Math.max(0, 360 - best) };
}
