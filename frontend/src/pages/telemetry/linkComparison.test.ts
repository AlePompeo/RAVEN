// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { DEFAULT_SCENARIO } from '../../shell/scenario';
import type { RavenEvaluation } from '../../shell/ravenApi';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { LinkSample } from './linkCsv';
import { compareLink, comparisonRequest, predictionFromRaven, simulateLink } from './linkComparison';

const sample = (second: number, margin: number, rate = 100000): LinkSample => ({
  t_utc: new Date(Date.UTC(2026, 9, 12, 0, 0, second)).toISOString(),
  margin_db: margin,
  elevation_deg: 1,
  rate_bps: rate,
});
const result = {
  time_unix: [Date.UTC(2026, 9, 12) / 1000, Date.UTC(2026, 9, 12, 0, 1) / 1000],
  margins: { '100000': [2, 4], '300000': [null, 8] }, earth_el_deg: [1, 2],
  k: 2, sigma_db: 1, gain: 15, rate_bps: 100000, step_min: 1, site_id: 'shackleton', model_version: 'raven-core-1',
};

describe('telemetry prediction comparison', () => {
  it('adapts authoritative multirate samples and actual RF parameters without filling unknowns', () => {
    const evaluation: RavenEvaluation = {
      ...evaluationFixture, rf_series: { '100000': [1, null, 3, 4], '300000': [null, 2, null, 5] },
    };
    const prediction = predictionFromRaven(evaluation)!;
    expect(prediction.margins).toEqual(evaluation.rf_series);
    expect(prediction.time_unix).toEqual(evaluation.steps!.time_unix);
    expect(prediction.k).toBe(evaluation.parameters_used!.rf.compensator_k);
    expect(prediction.sigma_db).toBe(evaluation.parameters_used!.rf.compensator_sigma_db);
    expect(predictionFromRaven(evaluationFixture)).toBeNull();
    expect(predictionFromRaven({ ...evaluation, rf_series: { '100000': [1] } })).toBeNull();
  });

  it('interpolates only inside model data and computes residuals at the sample rate', () => {
    const c = compareLink([sample(0, 3), sample(30, 1), sample(60, -1), sample(90, -2)], result);
    expect(c.rows.map((r) => r.prediction_db)).toEqual([2, 3, 4, null]);
    expect(c.rows.map((r) => r.residual_db)).toEqual([1, -2, -5, null]);
    expect(c.count).toBe(3);
    expect(c.bias_db).toBe(-2);
    expect(c.rmse_db).toBeCloseTo(Math.sqrt(10));
    expect(c.coverage_pct).toBeCloseTo(200 / 3);
    expect(c.outages).toBe(1);
    expect(c.outageStarts).toEqual([sample(60, -1).t_utc]);
  });

  it('does not invent predictions for unsupported rates or missing model points', () => {
    const c = compareLink([sample(0, 1, 200000), sample(30, 1, 300000), sample(60, 9, 300000)], result);
    expect(c.rows.map((r) => r.prediction_db)).toEqual([null, null, 8]);
    expect(c.count).toBe(1);
  });

  it('requests a bounded, non-decimated series covering the file and uses the captured scenario', () => {
    const req = comparisonRequest([sample(0, 1), sample(86400 * 30, 1)], { ...DEFAULT_SCENARIO, gain: 12, k: 2 }, 'shackleton')!;
    expect(req.site_id).toBe('shackleton');
    expect(req.rf_overrides).toEqual({ tx_gain_dbi: 12, compensator_k: 2 });
    expect(req.station).toBe('dsn34');
    expect(Math.floor(req.days * 1440 / req.step_min)).toBeLessThanOrEqual(1500);
    expect(req.days * 1440).toBeGreaterThan(30 * 1440);
    expect(comparisonRequest([sample(0, 1), sample(86400 * 91, 1)], DEFAULT_SCENARIO, 'shackleton')).toBeNull();
  });

  it('generates explicitly simulated model samples with noise and refuses missing series', () => {
    const rows = simulateLink(result, 100000, () => 0.5)!;
    expect(rows).toHaveLength(2);
    expect(rows[0]!.margin_db).toBeCloseTo(2 - Math.sqrt(-2 * Math.log(0.5)));
    expect(rows[0]!.elevation_deg).toBe(1);
    expect(simulateLink(result, 123, () => 0.5)).toBeNull();
    expect(simulateLink(result, 300000, () => 0.5)).toBeNull();
  });
});
