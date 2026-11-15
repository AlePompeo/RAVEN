// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import fixture from '../../shell/fixtures/raven/evaluate.json';
import { createRavenClient, raven, ravenSteps, type EvaluateIn, type RavenEvaluation, type RavenSiteInfo } from '../../shell/ravenApi';
import { useCatalog } from '../../i18n/i18n.svelte';
import enPages from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import MissionRecovery from './MissionRecovery.svelte';
import { assess, lunarDistanceKm, recover, recoveryInput, type RecoveryOption } from './recovery';

const original = fixture as RavenEvaluation;
const start = Date.parse(original.window.start_utc);
const request: EvaluateIn = { site_id: original.site.id, start_utc: original.window.start_utc, days: 1, step_min: 360,
  include_steps: true, include_windows: false };
const sites: RavenSiteInfo[] = [
  { ...original.site, id: 'near', name: 'Near', lat_deg: original.site.lat_deg + .1, dem_covered: true },
  { ...original.site, id: 'far', name: 'Far', lat_deg: original.site.lat_deg + .2, dem_covered: true },
];
afterEach(() => { cleanup(); vi.restoreAllMocks(); useCatalog('it', itCatalog, enPages); });

function evaluation(q: EvaluateIn, flags: (time: number, site: string) => boolean | null): RavenEvaluation {
  const e = structuredClone(original);
  const n = ravenSteps(q.days, q.step_min);
  e.site = { ...e.site, id: q.site_id, name: q.site_id };
  e.window = { start_utc: q.start_utc, step_min: q.step_min, n_steps: n };
  e.base_start_utc = q.start_utc;
  e.mission_shift_days = 0;
  for (const value of Object.values(e.steps!)) {
    if (Array.isArray(value)) {
      const first = value[0];
      value.splice(0, value.length, ...Array(n).fill(first));
    }
  }
  e.steps!.time_unix = Array.from({ length: n }, (_, i) => Date.parse(q.start_utc) / 1000 + i * q.step_min * 60);
  e.steps!.lit = e.steps!.time_unix.map((time) => flags(time * 1000, q.site_id));
  e.steps!.earth_el_deg = Array(n).fill(2);
  e.steps!.earth_horizon_deg = Array(n).fill(1);
  delete e.windows;
  return e;
}

describe('mission recovery', () => {
  it('distinguishes unknown from an obstruction and does not qualify unknown samples', () => {
    const e = evaluation(request, (_, __) => null);
    expect(assess(e)).toMatchObject({ status: 'unknown', firstProblem: { cause: 'unknown' } });
    e.steps!.lit[2] = false;
    expect(assess(e)).toMatchObject({ status: 'blocked', firstProblem: { cause: 'sun', time: e.steps!.time_unix[2] } });
    e.steps!.earth_el_deg[2] = 0;
    expect(assess(e).firstProblem?.cause).toBe('both');
  });

  it('rechecks the first sampled departure and checks nearby sites in distance order', async () => {
    const calls: EvaluateIn[] = [];
    const client = { evaluate: async (q: EvaluateIn) => {
      calls.push(q);
      return { ok: true as const, data: evaluation(q, (time, site) =>
        site === 'near' ? null : site === 'far' ? true : time >= start + 12 * 3600000) };
    } };
    const outcome = await recover(client, original, request, 6, sites, null, new AbortController().signal);
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) return;
    expect(outcome.data.assessment.status).toBe('blocked');
    expect(outcome.data.time?.request.start_utc).toBe('2027-01-01T12:00:00Z');
    expect(outcome.data.site?.request.site_id).toBe('far');
    expect(outcome.data.sitesChecked).toBe(2);
    expect(outcome.data.searchHours).toBe(168);
    expect(calls.map((q) => [q.site_id, q.start_utc, q.days])).toEqual([
      [request.site_id, '2027-01-01T06:00:00Z', 1],
      [request.site_id, '2027-01-01T06:00:00Z', 8],
      [request.site_id, '2027-01-01T12:00:00Z', 1],
      ['near', '2027-01-01T06:00:00Z', 1],
      ['far', '2027-01-01T06:00:00Z', 1],
    ]);
    expect(outcome.data.site?.kind === 'site' && outcome.data.site.distanceKm).toBeCloseTo(lunarDistanceKm(original.site, sites[1]!), 5);
  });

  it('reports bounded absence and rejects unknown-only alternatives', async () => {
    const client = { evaluate: async (q: EvaluateIn) => ({ ok: true as const, data: evaluation(q, () => null) }) };
    const range = { start_utc: request.start_utc, end_utc: '2027-01-02T18:00:00Z' };
    const outcome = await recover(client, original, request, 6, sites, range, new AbortController().signal);
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) return;
    expect(outcome.data).toMatchObject({ assessment: { status: 'unknown' }, searchHours: 12, time: null, site: null, sitesChecked: 2 });
  });

  it('respects the sample cap and starts the delay from an already-shifted scenario', async () => {
    const shifted = structuredClone(original);
    shifted.window.start_utc = '2027-01-04T00:00:00Z';
    const q = { ...request, days: 1500 * 10 / 1440, step_min: 10, mission_shift_days: 3 as const };
    const calls: EvaluateIn[] = [];
    const client = { evaluate: async (body: EvaluateIn) => {
      calls.push(body);
      return { ok: true as const, data: evaluation(body, () => null) };
    } };
    const outcome = await recover(client, shifted, q, 6, [], null, new AbortController().signal);
    expect(outcome).toMatchObject({ ok: true, data: { searchHours: 0, time: null, site: null } });
    expect(calls).toHaveLength(1);
    expect(calls[0]!.start_utc).toBe('2027-01-04T06:00:00Z');
    expect(calls[0]!.mission_shift_days).toBeUndefined();
  });

  it('propagates failed, aborted and out-of-range evaluations instead of claiming no alternatives', async () => {
    const failure = { evaluate: async () => ({ ok: false as const, kind: 'unavailable' as const, detail: 'needs_download' as const }) };
    expect(await recover(failure, original, request, 6, sites, null, new AbortController().signal))
      .toMatchObject({ ok: false, kind: 'unavailable', detail: 'needs_download' });
    const controller = new AbortController();
    controller.abort();
    expect(await recover(failure, original, request, 6, sites, null, controller.signal)).toMatchObject({ ok: false, kind: 'aborted' });
    expect(await recover(failure, original, request, 6, sites,
      { start_utc: request.start_utc, end_utc: '2027-01-02T00:00:00Z' }, new AbortController().signal))
      .toMatchObject({ ok: false, kind: 'range' });
  });

  it('does not present a candidate whose independent re-evaluation fails the criterion', async () => {
    let count = 0;
    const client = { evaluate: async (q: EvaluateIn) => {
      count++;
      return { ok: true as const, data: evaluation(q, () => count === 3 ? false : true) };
    } };
    const outcome = await recover(client, original, request, 6, [], null, new AbortController().signal);
    expect(outcome).toMatchObject({ ok: false, kind: 'response' });
  });

  it('applies the selected scenario without losing the comparison site or the second date', () => {
    const option: RecoveryOption = { kind: 'site', evaluation: original, distanceKm: 3, request: { ...request, site_id: 'near', start_utc: '2027-01-03T06:00:00Z' } };
    const input = { mode: 'sites' as const, siteA: original.site.id, siteB: 'near', start: '2027-01-01T00:00',
      startB: '2027-02-01T00:00', days: 1, stepMin: 360 };
    expect(recoveryInput(input, option, original.site.id)).toEqual({ ...input, siteA: 'near', siteB: original.site.id, start: '2027-01-03T06:00' });
    expect(recoveryInput({ ...input, mode: 'dates' }, option, original.site.id))
      .toEqual({ ...input, mode: 'dates', siteA: 'near', start: '2027-01-03T06:00' });
    expect(input.siteA).toBe(original.site.id);
  });

  it.each([
    ['en', 'Evaluate delay and alternatives', 'Preview', 'Preview — plan not yet changed', 'Apply and recalculate'],
    ['it', 'Valuta ritardo e alternative', 'Anteprima', 'Anteprima — piano non ancora modificato', 'Applica e ricalcola'],
  ] as const)('shows a preview before applying in %s', async (language, search, preview, title, apply) => {
    useCatalog(language, language === 'it' ? itCatalog : enPages, enPages);
    vi.spyOn(raven, 'evaluate').mockImplementation(async (q) => ({
      ok: true, data: evaluation(q, (time) => time >= start + 12 * 3600000),
    }));
    const onapply = vi.fn();
    render(MissionRecovery, { baseline: original, request, sites: [], range: null, onapply });
    await fireEvent.click(screen.getByRole('button', { name: search }));
    const previewButton = await screen.findByRole('button', { name: preview });
    expect(onapply).not.toHaveBeenCalled();
    await fireEvent.click(previewButton);
    expect(screen.getByText(title)).toBeTruthy();
    expect(onapply).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: apply }));
    expect(onapply).toHaveBeenCalledOnce();
    expect(onapply.mock.calls[0]![0].request.start_utc).toBe('2027-01-01T12:00:00Z');
  });

  it.skipIf(!process.env.RAVEN_RECOVERY_LIVE_URL)('uses the real RAVEN API for delay and alternative evaluations', async () => {
    const url = process.env.RAVEN_RECOVERY_LIVE_URL!;
    const client = createRavenClient({
      fetch: (input, init) => fetch(new URL(String(input), url), init),
      confirmDownload: async () => false,
    });
    const catalog = await client.sites();
    expect(catalog.ok).toBe(true);
    if (!catalog.ok) return;
    const baseline = await client.evaluate(request);
    expect(baseline.ok).toBe(true);
    if (!baseline.ok) return;
    const candidateSites = catalog.data.sites.filter((s) => s.id === 'haworth');
    expect(candidateSites).toHaveLength(1);
    const outcome = await recover(client, baseline.data, request, 6, candidateSites,
      catalog.data.ephemeris.supported_range ?? null, new AbortController().signal);
    expect(outcome).toMatchObject({ ok: true, data: { sitesChecked: 1, searchHours: 168 } });
  }, 120000);
});
