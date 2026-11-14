// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import evaluationFixture from '../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation } from '../../shell/ravenApi';
import type { ParamRow } from '../compare/lunar';
import { customSites } from '../../shell/customSites';
import { journeyRequests, newDraft, readRun, requestKey, type JourneyRun } from './journey';
import { archiveRun, readHistory, writeHistory, HISTORY_KEY, HISTORY_LIMIT, HISTORY_MAX_CHARS } from './history';

const evaluation = evaluationFixture as RavenEvaluation;
const rows: ParamRow[] = [
  { key: 'array_area_m2', value: 1, min: .01, max: 100 },
  { key: 'cell_efficiency', value: .295, min: .05, max: .5 },
  { key: 'orientation', value: 'horizontal', allowed: ['horizontal', 'tilted', 'tracking'] },
  { key: 'tilt_deg', value: 0, min: 0, max: 90 },
  { key: 'tilt_azimuth_deg', value: 0, min: 0, max: 360 },
].map((row) => ({ ...row, group: 'energy', unit: '-', status: 'I', source: 'illustrative', note: '' }));
const ids = [evaluation.site.id, 'haworth'];
function makeRun(): JourneyRun {
  const config = newDraft(rows, ids)!;
  config.name = 'Polar comparison';
  config.input.start = '2027-01-01T00:00';
  config.input.days = 1; config.input.stepMin = 360;
  const requests = journeyRequests(config, rows)!;
  return { config, requests, key: requestKey(requests), createdAt: '2026-11-08T00:00:00Z',
    evaluations: requests.map((q) => ({ ...structuredClone(evaluation), site: { ...evaluation.site, id: q.site_id } })) };
}
afterEach(() => { localStorage.clear(); customSites.set([]); });
const save = (run: JourneyRun) => archiveRun(localStorage, run, rows, ids, evaluation.registry_sha256, evaluation.model_version);

describe('local calculation history', () => {
  it('persists complete calculations, deduplicates the same snapshot and rejects invalid inputs', () => {
    const run = makeRun();
    expect(save(run).ok).toBe(true);
    expect(save(run).ok).toBe(true);
    const stored = readHistory(localStorage);
    expect(stored.ok && stored.entries).toHaveLength(1);
    if (!stored.ok) throw new Error('history unreadable');
    expect(readRun(JSON.stringify(stored.entries[0]!.run), rows, ids, evaluation.registry_sha256)).toEqual(run);
    run.evaluations[0]!.steps!.soc.pop();
    expect(save(run)).toEqual({ ok: false, error: 'history.invalid' });
    expect(readHistory(localStorage)).toEqual(stored);
  });

  it('never overwrites a corrupted archive and reports access or quota failures', () => {
    localStorage.setItem(HISTORY_KEY, '{broken');
    expect(save(makeRun())).toEqual({ ok: false, error: 'history.readError' });
    expect(localStorage.getItem(HISTORY_KEY)).toBe('{broken');
    const unavailable = { getItem: vi.fn(() => { throw new Error('blocked'); }) };
    expect(readHistory(unavailable)).toEqual({ ok: false, error: 'history.readError' });
    const full = { setItem: vi.fn(() => { throw new DOMException('full', 'QuotaExceededError'); }) };
    expect(writeHistory(full, [])).toEqual({ ok: false, error: 'history.writeError' });
  });

  it('refuses count and size overflow without evicting prior calculations', () => {
    const first = save(makeRun());
    if (!first.ok) throw new Error('archive failed');
    const entries = Array.from({ length: HISTORY_LIMIT }, (_, i) => ({ ...first.entries[0]!, id: `entry-${i}` }));
    expect(writeHistory(localStorage, entries).ok).toBe(true);
    const before = localStorage.getItem(HISTORY_KEY);
    const next = makeRun(); next.createdAt = '2026-11-08T01:00:00Z';
    expect(save(next)).toEqual({ ok: false, error: 'history.full' });
    expect(localStorage.getItem(HISTORY_KEY)).toBe(before);
    expect(writeHistory(localStorage, [{ ...entries[0]!, run: { padding: 'x'.repeat(HISTORY_MAX_CHARS) } }]))
      .toEqual({ ok: false, error: 'history.tooLarge' });
    expect(localStorage.getItem(HISTORY_KEY)).toBe(before);
  });

  it('keeps incompatible snapshots removable and leaves an explicit empty history after clearing', () => {
    const result = save(makeRun());
    if (!result.ok) throw new Error('archive failed');
    const entry = result.entries[0]!;
    expect(readRun(JSON.stringify(entry.run), rows, ids, 'another-registry')).toBeNull();
    expect(readHistory(localStorage).ok).toBe(true);
    expect(writeHistory(localStorage, []).ok).toBe(true);
    expect(readHistory(localStorage)).toEqual({ ok: true, exists: true, entries: [] });
  });
});
