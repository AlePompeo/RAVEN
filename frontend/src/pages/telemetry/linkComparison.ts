// SPDX-License-Identifier: Apache-2.0
import type { EvaluateIn, RavenEvaluation } from '../../shell/ravenApi';
import type { Scenario } from '../../shell/scenario';
import type { LinkSample } from './linkCsv';

const DAY_MINUTES = 1440;
const MAX_MODEL_POINTS = 1400;

export function comparisonRequest(samples: readonly LinkSample[], scenario: Scenario, site: string): EvaluateIn | null {
  if (!samples.length || !site) return null;
  const first = Date.parse(samples[0]!.t_utc);
  const last = Date.parse(samples[samples.length - 1]!.t_utc);
  const start = Math.floor(first / 1000) * 1000;
  const durationMin = (last - start) / 60_000;
  const step = Math.max(1, Math.ceil(durationMin / (MAX_MODEL_POINTS - 2)));
  const days = Math.max(0.04, (durationMin + 2 * step) / DAY_MINUTES);
  if (!Number.isFinite(days) || days > 90) return null;
  const overrides: Record<string, number> = {};
  if (scenario.gain !== null) overrides.tx_gain_dbi = scenario.gain;
  if (scenario.k !== null) overrides.compensator_k = scenario.k;
  return { site_id: site, start_utc: new Date(start).toISOString(), days, step_min: step,
    station: scenario.station, rate_bps: scenario.bitrate ?? 100000, rf_overrides: overrides,
    ...(scenario.mast !== null ? { antenna_height_m: scenario.mast } : {}), include_steps: true };
}

export interface ComparedSample extends LinkSample {
  prediction_db: number | null;
  residual_db: number | null;
}

export interface LinkComparison {
  rows: ComparedSample[];
  count: number;
  bias_db: number | null;
  rmse_db: number | null;
  coverage_pct: number | null;
  outages: number;
  outageStarts: string[];
}

export interface PredictionSeries {
  site_id: string;
  time_unix: number[];
  margins: Record<string, (number | null)[]>;
  earth_el_deg: (number | null)[];
  k: number; sigma_db: number; gain: number; rate_bps: number; step_min: number;
  model_version: string;
}

export function predictionFromRaven(e: RavenEvaluation): PredictionSeries | null {
  const s = e.steps;
  const rf = e.parameters_used?.rf;
  if (!s || !rf || !e.rf_series) return null;
  const { compensator_k: k, compensator_sigma_db: sigma, tx_gain_dbi: gain, rate_bps: rate } = rf;
  if (typeof k !== 'number' || typeof sigma !== 'number' || typeof gain !== 'number' || typeof rate !== 'number' ||
      ![k, sigma, gain, rate].every(Number.isFinite) ||
      !Array.isArray(s.time_unix) || !s.time_unix.length ||
      !s.time_unix.every((t, i) => Number.isFinite(t) && (i === 0 || t > s.time_unix[i - 1]!)) ||
      s.earth_el_deg.length !== s.time_unix.length ||
      !Object.values(e.rf_series).every((values) => Array.isArray(values) &&
        values.length === s.time_unix.length && values.every((v) => v === null || (typeof v === 'number' && Number.isFinite(v))))) return null;
  return { site_id: e.site.id, time_unix: s.time_unix, margins: e.rf_series,
    earth_el_deg: s.earth_el_deg, k, sigma_db: sigma,
    gain, rate_bps: rate, step_min: e.window.step_min, model_version: e.model_version };
}

function interpolate(times: number[], values: (number | null)[], t: number): number | null {
  let low = 0;
  let high = times.length - 1;
  if (!times.length || t < times[0]! || t > times[high]!) return null;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (times[mid]! < t) low = mid + 1;
    else high = mid;
  }
  const right = values[low];
  if (right == null || !Number.isFinite(right)) return null;
  if (times[low] === t) return right;
  const left = values[low - 1];
  const span = times[low]! - times[low - 1]!;
  if (left == null || !Number.isFinite(left) || span <= 0) return null;
  return left + ((t - times[low - 1]!) / span) * (right - left);
}

export function compareLink(samples: readonly LinkSample[], result: PredictionSeries): LinkComparison {
  const threshold = result.k * result.sigma_db;
  let sum = 0;
  let squares = 0;
  let covered = 0;
  let count = 0;
  let outages = 0;
  const outageStarts: string[] = [];
  let inOutage = false;
  const rows = samples.map((sample): ComparedSample => {
    if (sample.margin_db < 0 && !inOutage) {
      outages++;
      outageStarts.push(sample.t_utc);
    }
    inOutage = sample.margin_db < 0;
    const series = result.margins[String(sample.rate_bps)];
    const prediction = !series ? null : interpolate(result.time_unix, series, Date.parse(sample.t_utc) / 1000);
    const residual = prediction === null ? null : sample.margin_db - prediction;
    if (residual !== null) {
      count++;
      sum += residual;
      squares += residual * residual;
      if (Math.abs(residual) <= threshold) covered++;
    }
    return { ...sample, prediction_db: prediction, residual_db: residual };
  });
  return {
    rows,
    count,
    bias_db: count ? sum / count : null,
    rmse_db: count ? Math.sqrt(squares / count) : null,
    coverage_pct: count && Number.isFinite(threshold) && threshold >= 0 ? (100 * covered) / count : null,
    outages,
    outageStarts,
  };
}

export function simulateLink(result: PredictionSeries, rate: number, random = Math.random): LinkSample[] | null {
  const margins = result.margins[String(rate)];
  const elevation = result.earth_el_deg;
  const sigma = result.sigma_db;
  if (!margins || !Number.isFinite(sigma) || sigma < 0) return null;
  const rows: LinkSample[] = [];
  for (let i = 0; i < result.time_unix.length; i++) {
    const time = result.time_unix[i];
    const margin = margins[i];
    const el = elevation[i];
    if (time == null || !Number.isFinite(time) || margin == null || !Number.isFinite(margin) || el == null || !Number.isFinite(el)) return null;
    const noise = sigma * Math.sqrt(-2 * Math.log(Math.max(Number.MIN_VALUE, random()))) * Math.cos(2 * Math.PI * random());
    const date = new Date(time * 1000);
    if (!Number.isFinite(date.getTime()) || !Number.isFinite(noise)) return null;
    rows.push({ t_utc: date.toISOString(), margin_db: margin + noise, elevation_deg: el, rate_bps: rate });
  }
  return rows.length ? rows : null;
}
