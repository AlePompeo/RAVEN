// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_SCENARIO,
  msToT,
  normalizeT,
  tToMs,
  parseScenario,
  ScenarioStore,
  scenarioQuery,
  STORAGE_KEY,
  URL_WRITE_MS,
  withScenario,
  writeScenarioParams,
} from './scenario';

afterEach(() => vi.useRealTimers());

describe('parseScenario', () => {
  it('parses a full valid query', () => {
    const s = parseScenario('?site=shackleton&t=2027-04-07T12:30:00Z&station=dsn18&gain=20.5&rate=100000&k=2.33&antenna_h=25');
    expect(s).toEqual({ site: 'shackleton', t: '2027-04-07T12:30:00Z', station: 'dsn18', gain: 20.5, bitrate: 100000, k: 2.33, mast: 25, customSites: [] });
  });

  it('defaults when empty', () => {
    expect(parseScenario('')).toEqual(DEFAULT_SCENARIO);
    expect(parseScenario('?body=earth&tv=1')).toEqual(DEFAULT_SCENARIO);
  });

  it('ignores malicious or out-of-domain values and never throws', () => {
    const bad = [
      'site=<script>alert(1)</script>',
      'site=../../etc/passwd',
      'site=a%00b',
      `site=${'a'.repeat(200)}`,
      'site=UPPER',
      "site=x';drop",
      't=2027-02-30T00:00:00Z',
      't=1960-01-01T00:00:00Z',
      't=2300-01-01T00:00:00Z',
      't=javascript:alert(1)',
      't=2027-04-07T25:00:00Z',
      'station=dsn99',
      'station=__proto__',
      'gain=NaN',
      'gain=1e999',
      'gain=999',
      'gain=-11',
      'rate=12345',
      'rate=Infinity',
      'rate=0x10',
      'k=-1',
      'k=7',
      'k=abc',
      'antenna_h=101',
    ].join('&');
    expect(parseScenario(`?${bad}`)).toEqual(DEFAULT_SCENARIO);
  });

  it('keeps valid fields when others are invalid', () => {
    const s = parseScenario('?site=haworth&t=nope&station=zz&rate=300000');
    expect(s.site).toBe('haworth');
    expect(s.t).toBeNull();
    expect(s.station).toBe('dsn34');
    expect(s.bitrate).toBe(300000);
  });

  it('converts between milliseconds and the scenario time', () => {
    expect(msToT(Date.UTC(2027, 3, 7, 12, 30, 15, 900))).toBe('2027-04-07T12:30:15Z');
    expect(tToMs('2027-04-07T12:30:15Z')).toBe(Date.UTC(2027, 3, 7, 12, 30, 15));
    expect(msToT(Number.NaN)).toBeNull();
    expect(msToT(Date.UTC(1960, 0, 1))).toBeNull();
  });

  it('normalizes the time and rejects out-of-range or odd formats', () => {
    expect(normalizeT('2027-04-07T12:30')).toBe('2027-04-07T12:30:00Z');
    expect(normalizeT('2027-04-07T12:30:15Z')).toBe('2027-04-07T12:30:15Z');
    expect(normalizeT('2027-04-07 12:30:15')).toBeNull();
    expect(normalizeT(42)).toBeNull();
    expect(normalizeT('2150-01-21T00:00:00Z')).toBeNull();
  });
});

describe('serialisation', () => {
  it('writes only non-default fields and round-trips', () => {
    const s = { ...DEFAULT_SCENARIO, site: 'haworth', t: '2027-04-07T00:00:00Z', bitrate: 1e5, station: 'dsn18' as const };
    const q = scenarioQuery(s);
    expect(q).toBe('?site=haworth&t=2027-04-07T00%3A00%3A00Z&station=dsn18&rate=100000');
    expect(parseScenario(q)).toEqual(s);
    expect(scenarioQuery(DEFAULT_SCENARIO)).toBe('');
    expect(withScenario('/grazinglink', s).startsWith('/grazinglink?site=haworth')).toBe(true);
    const tab = new URLSearchParams(withScenario('/simula?tab=onda', s).split('?')[1]);
    expect(tab.get('tab')).toBe('onda');
    expect(tab.get('site')).toBe('haworth');
    expect(parseScenario(scenarioQuery({ ...s, mast: 3 })).mast).toBe(3);
    expect(parseScenario('?mast=3').mast).toBeNull();
  });

  it('preserves unrelated params and replaces scenario ones', () => {
    const p = writeScenarioParams({ ...DEFAULT_SCENARIO, site: 'haworth' }, new URLSearchParams('body=earth&site=old&k=3'));
    expect(p.get('body')).toBe('earth');
    expect(p.get('site')).toBe('haworth');
    expect(p.has('k')).toBe(false);
  });

  it('puts custom sites in the scenario: URL round trip, validation, no echo of invalid values', () => {
    const cs = [
      { id: 'c-pole', name: 'Pole A (test)', lat_deg: -88.12346, lon_deg_east: 1.5 },
      { id: 'c-eq', name: 'Eq', lat_deg: 0, lon_deg_east: -120, panel_height_m: 3, antenna_height_m: 2.5 },
    ];
    const scenario = { ...DEFAULT_SCENARIO, site: 'c-eq', customSites: cs };
    const q = scenarioQuery(scenario);
    expect(parseScenario(q)).toEqual(scenario);
    expect(new URLSearchParams(q).get('cs')!.length).toBeLessThan(200);
    // a custom id is valid only if the same scenario defines it
    expect(parseScenario('?site=c-eq').site).toBeNull();
    expect(parseScenario('?site=c-eq&cs=c-eq~1~2~Eq').site).toBe('c-eq');
    // malicious or out-of-range values are dropped silently
    for (const bad of ['c-x~91~0~X', 'c-x~0~361~X', 'c-x~0~0~<b>', 'C-X~0~0~X', 'c-x~NaN~0~X', 'c-x~1e5~0~X', 'c-x~0~0~' + 'a'.repeat(41), 'shackleton~0~0~X', 'c-x~0~0~X~0~2', 'c-x~0~0~X~2~101']) {
      expect(parseScenario('?cs=' + encodeURIComponent(bad)).customSites).toEqual([]);
    }
    expect(parseScenario('?cs=' + encodeURIComponent('c-x~0~0~' + 'a'.repeat(900))).customSites).toEqual([]); // oversize
    const nine = Array.from({ length: 9 }, (_, i) => `c-s${i}~${i}~${i}~S${i}`).join('!');
    expect(parseScenario('?cs=' + encodeURIComponent(nine)).customSites).toHaveLength(8);
    expect(parseScenario('?cs=c-a~1~1~A!c-a~2~2~B').customSites).toHaveLength(1); // duplicate id
    expect(parseScenario('?cs=c-a~10~350~A').customSites[0]!.lon_deg_east).toBe(-10); // 0..360 input
  });
});

function env(search = '', store: Record<string, string> | null = {}) {
  const calls: string[] = [];
  const loc = { pathname: '/viewer', search, hash: '' };
  const hist = { state: null, replaceState: (_s: unknown, _t: string, url: string) => void calls.push(url) };
  const st = store
    ? { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => void (store[k] = v) }
    : null;
  return { calls, loc, hist, st, store };
}

describe('ScenarioStore', () => {
  it('reads the URL first, then sessionStorage', () => {
    const a = env('?site=haworth', { [STORAGE_KEY]: '?site=shackleton' });
    expect(new ScenarioStore({ loc: a.loc, hist: a.hist, store: a.st }).get().site).toBe('haworth');
    const b = env('', { [STORAGE_KEY]: '?site=shackleton' });
    expect(new ScenarioStore({ loc: b.loc, hist: b.hist, store: b.st }).get().site).toBe('shackleton');
  });

  it('survives a throwing storage and a hostile stored value', () => {
    const e = env('');
    const throwing = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    };
    const s = new ScenarioStore({ loc: e.loc, hist: e.hist, store: throwing });
    expect(s.get()).toEqual(DEFAULT_SCENARIO);
    s.set({ site: 'haworth' });
    expect(() => s.flush()).not.toThrow();
    const h = env('', { [STORAGE_KEY]: '?site=<img onerror=1>&k=99' });
    expect(new ScenarioStore({ loc: h.loc, hist: h.hist, store: h.st }).get()).toEqual(DEFAULT_SCENARIO);
  });

  it('validates on set, notifies, and writes the URL at most once per interval', () => {
    vi.useFakeTimers();
    const e = env('?body=earth');
    const s = new ScenarioStore({ loc: e.loc, hist: e.hist, store: e.st });
    const seen: (string | null)[] = [];
    const off = s.subscribe((v) => seen.push(v.site));
    s.set({ site: 'haworth' });
    s.set({ site: '<bad>' });
    s.set({ site: 'haworth' }); // identical: no notification
    s.set({ k: 99 });
    expect(seen).toEqual([null, 'haworth']); // '<bad>' and k=99 are ignored, identical set is a no-op
    expect(s.get().k).toBeNull();
    expect(e.calls).toHaveLength(0);
    vi.advanceTimersByTime(URL_WRITE_MS);
    expect(e.calls).toHaveLength(1);
    expect(e.calls[0]).toBe('/viewer?body=earth&site=haworth');
    expect(e.store?.[STORAGE_KEY]).toBe('?site=haworth');
    off();
    s.set({ site: 'shackleton' });
    expect(seen.at(-1)).not.toBe('shackleton');
  });

  it('reload keeps the in-memory scenario unless the URL carries one', () => {
    const e = env('');
    const s = new ScenarioStore({ loc: e.loc, hist: e.hist, store: e.st });
    s.set({ site: 'haworth' });
    expect(s.reload().site).toBe('haworth');
    e.loc.search = '?site=nobile-rim';
    expect(s.reload().site).toBe('nobile-rim');
  });
});
