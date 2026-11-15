// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import HorizonProfile from './HorizonProfile.svelte';
import SeriesChart from './SeriesChart.svelte';
import { t, useCatalog, type MessageKey } from '../../i18n/i18n.svelte';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation } from '../../shell/ravenApi';
import JourneyPreview from './JourneyPreview.svelte';
import JourneyResults from './JourneyResults.svelte';
import VisibilityFigures from './VisibilityFigures.svelte';
import { defaultObjectives } from './objectives';
import { RADIO_PRESETS } from './setup';
import type { JourneyRun } from './journey';

beforeEach(() => useCatalog('en', en, en));
afterEach(() => { cleanup(); useCatalog('it', itCatalog, en); });

describe('mission charts', () => {
  it('distinguishes missing future samples from a known unchanged window', () => {
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    evaluation.window.step_min = 30;
    evaluation.steps!.lit[0] = true;
    evaluation.steps!.lit[1] = null;
    evaluation.steps!.earth_el_deg.fill(5);
    evaluation.steps!.earth_horizon_deg.fill(0);
    render(VisibilityFigures, {
      evaluations: [evaluation], countdown: true,
      tr: (key: string, params?: Record<string, string | number>) => t(key as MessageKey, params),
      fmt: (value: number) => String(value),
    });
    expect(screen.getByText('next change unknown: a sample is missing')).toBeTruthy();
    expect(screen.getByText('no sampled change in the window')).toBeTruthy();
    expect(screen.getByText(/Sampled every 30 minutes/)).toBeTruthy();
  });

  it('uses the full percentage scale for a full or partially discharged battery', async () => {
    const { container, rerender } = render(SeriesChart, {
      label: 'Battery', unit: '%', values: [100, 100], rangeLabel: 'Range', emptyLabel: 'Unknown',
    });
    expect(container.querySelector('figcaption')?.textContent).toContain('Battery (%)');
    expect(container.querySelector('polyline')?.getAttribute('points')).toBe('0,10 600,10');
    await rerender({ label: 'Battery', unit: '%', values: [90, 80], rangeLabel: 'Range', emptyLabel: 'Unknown' });
    expect(container.querySelector('polyline')?.getAttribute('points')).toBe('0,22 600,34');
  });

  it('keeps units, timestamps and the selected unknown sample when the whole series is unavailable', () => {
    render(SeriesChart, {
      label: 'Power', unit: 'W', values: [null, null], times: [0, 60], cursorIndex: 1,
      onselect: vi.fn(), rangeLabel: 'Range', emptyLabel: 'Unknown',
    });
    expect(screen.getByRole('slider', { name: 'Power' })).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('1970-01-01 00:01 UTC · Unknown');
    expect(screen.getByText('Power (W)')).toBeTruthy();
  });

  it('timestamps battery charge at interval end rather than at generation step start', () => {
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    evaluation.window.step_min = 60;
    const { container } = render(JourneyPreview, { evaluations: [evaluation], energy: true });
    const charts = container.querySelectorAll('figure');
    const stamp = (time: number) => new Date(time * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    expect(charts[0]!.querySelector('output')?.textContent).toContain(stamp(evaluation.steps!.time_unix[0]!));
    expect(charts[1]!.querySelector('output')?.textContent).toContain(stamp(evaluation.steps!.time_unix[0]! + 3600));
    expect(charts[1]!.textContent).toContain('end of each step');
  });

  it('explains known shadow and distinguishes RF uncertainty from the energy prefix', () => {
    const evaluation = structuredClone(evaluationFixture) as RavenEvaluation;
    const steps = evaluation.steps!;
    evaluation.window.step_min = 60;
    steps.lit.fill(false); steps.gen_w.fill(0);
    steps.soc.fill(null, 2); steps.rf_closes.fill(null, 2); steps.rf_reason.fill('outside_model', 2);
    evaluation.metrics.harvested_wh = 0;
    const run: JourneyRun = {
      key: 'test', createdAt: '2027-01-01T00:00:00Z', requests: [], evaluations: [evaluation],
      config: {
        name: 'Test', decision: '', objectives: defaultObjectives(), radio: RADIO_PRESETS.baseline,
        panel: { array_area_m2: 1, cell_efficiency: .295, orientation: 'horizontal', tilt_deg: 0, tilt_azimuth_deg: 0 },
        input: { mode: 'sites', siteA: evaluation.site.id, siteB: 'haworth', start: '2027-01-01T00:00', startB: '2027-02-01T00:00', days: 1, stepMin: 60 },
      },
    };
    render(JourneyResults, { run, objectives: defaultObjectives(), report: true });
    expect(screen.getByTestId('mission-no-sun').textContent).toContain('known model result');
    expect(screen.getByTestId('mission-energy-prefix').textContent).toContain('first 2.0');
    expect(screen.getByTestId('mission-rf-unknown').textContent).toContain('Unknown is not a failed link');
    expect(screen.getByText('Confirmed useful time')).toBeTruthy();
  });

  it('does not connect a margin series across missing samples', () => {
    const { container } = render(SeriesChart, {
      label: 'Margin', unit: 'dB', values: [1, 2, null, 3, 4], rangeLabel: 'Range', emptyLabel: 'Unavailable',
    });
    expect(container.querySelectorAll('polyline')).toHaveLength(2);
    expect(screen.getByRole('img', { name: 'Margin: from 1.0 to 4.0 dB' })).toBeTruthy();
  });

  it('plots only sampled directions and lists missing data', () => {
    const result = {
      site: { id: 'a', name: 'A' },
      samples: [
        { azimuth_deg: 0, elevation_deg: 2, distance_m: 100, state: 'ok' as const },
        { azimuth_deg: 5, elevation_deg: null, distance_m: null, state: 'missing_dem' as const },
      ],
      dem_product: 'lola', dem_sha256: '', dem_label_sha256: '', lunar_frame: 'MOON_ME', profile_length_m: 10000, profile_spacing_m: 20,
      azimuth_step_deg: 5, observer_height_m: 0, limits: '', dem_policy: '',
    };
    const labels = {
      chart: 'Horizon', table: 'Samples', azimuth: 'Azimuth', elevation: 'Elevation',
      distance: 'Distance', status: 'Status', ok: 'Available', missing_dem: 'Missing DEM', outside_coverage: 'Outside coverage',
    };
    const { container } = render(HorizonProfile, { result, labels });
    expect(container.querySelectorAll('circle')).toHaveLength(1);
    expect(container.querySelector('polyline')).toBeNull();
    expect(screen.getByText('Missing DEM')).toBeTruthy();
  });

  it('selects sampled instants through a keyboard-accessible slider and labels missing values', async () => {
    const onselect = vi.fn();
    render(SeriesChart, { label: 'Power', unit: 'W', values: [2, null, 4], times: [0, 60, 120],
      cursorIndex: 1, onselect, rangeLabel: 'Range', emptyLabel: 'Unknown' });
    expect(screen.getByRole('status').textContent).toContain('1970-01-01 00:01 UTC · Unknown');
    await fireEvent.input(screen.getByRole('slider', { name: 'Power' }), { target: { value: '2' } });
    expect(onselect).toHaveBeenCalledWith(2);
  });
});
