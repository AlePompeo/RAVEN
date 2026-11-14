// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  checkBounds, createRavenClient, evaluateIn, queryString, ravenSteps,
  type RavenComparison, type RavenEvaluation, type RavenHorizon, type RavenParameters, type RavenSnapshot, type RavenSteps,
} from './ravenApi';

const here = dirname(fileURLToPath(import.meta.url));
const fx = <T>(n: string): T => JSON.parse(readFileSync(resolve(here, `fixtures/raven/${n}.json`), 'utf8')) as T;
const START = '2027-01-01T00:00:00Z';

const reply = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
function stub(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const f = ((url: string, init?: RequestInit) => { calls.push({ url, ...(init ? { init } : {}) }); return Promise.resolve(handler(url, init)); }) as typeof fetch;
  return { f, calls };
}

describe('limiti D9', () => {
  it('i passi seguono la regola del backend e il default e 7 giorni a 10 minuti', () => {
    expect(ravenSteps(7, 10)).toBe(1008);
    const d = evaluateIn('x', START);
    expect([d.days, d.step_min]).toEqual([7, 10]);
    expect(checkBounds(d)).toBeNull();
  });
  it('1500 passi per sito, 6000 in totale, nessun finestra lunare da 29,53 giorni a 10 minuti', () => {
    expect(checkBounds({ start_utc: START, days: 10, step_min: 10 })).toBeNull(); // 1440
    expect(checkBounds({ start_utc: START, days: 29.53, step_min: 10 })).toBe('size'); // 4252
    expect(checkBounds({ start_utc: START, days: 10, step_min: 10 }, 5)).toBe('size'); // 7200 > 6000
    expect(checkBounds({ start_utc: START, days: 5, step_min: 10 }, 8)).toBeNull(); // 8 x 720 = 5760
  });
  it('rifiuta data, durata, passo e numero di siti non validi', () => {
    expect(checkBounds({ start_utc: '2027-01-01', days: 1, step_min: 10 })).toBe('start');
    expect(checkBounds({ start_utc: START, days: 0, step_min: 10 })).toBe('days');
    expect(checkBounds({ start_utc: START, days: 367, step_min: 1440 })).toBe('days');
    expect(checkBounds({ start_utc: START, days: 1, step_min: 0.5 })).toBe('step');
    expect(checkBounds({ start_utc: START, days: 1, step_min: 60 }, 17)).toBe('sites');
  });
});

describe('forma delle risposte reali (fixture catturate dall API)', () => {
  const ev = fx<RavenEvaluation>('evaluate');
  it('evaluate: versione, metriche, passi paralleli, finestre', () => {
    expect(ev.model_version).toMatch(/^raven-core-\d+/);
    expect(ev.registry_sha256).toMatch(/^[0-9a-f]{64}$/);
    for (const k of ['site', 'window', 'metrics', 'inputs_state', 'heights', 'rules', 'declared_limits', 'steps', 'windows'] as const) expect(ev[k]).toBeDefined();
    const s = ev.steps as RavenSteps;
    const cols = ['time_unix', 'sun_el_deg', 'earth_el_deg', 'sun_horizon_deg', 'earth_horizon_deg', 'terrain_reason', 'disc_fraction', 'lit', 'margin_db', 'rf_state', 'rf_closes', 'dsn_visible', 'gen_w', 'soc', 'state', 'link_usable', 'useful', 'limiting'] as const;
    for (const c of cols) expect(s[c]).toHaveLength(ev.window.n_steps);
    expect(Object.keys(ev.windows ?? {}).sort()).toEqual(['link_usable', 'lit', 'useful']);
    expect(ev.windows?.useful[0]).toMatchObject({ start_unix: expect.any(Number), open_start: expect.any(Boolean), tolerance_s: 1 });
    expect(ev.metrics.state_hours).toHaveProperty('operational');
  });
  it('compare: classifica senza punteggio, componenti, siti non confrontabili', () => {
    const c = fx<RavenComparison>('compare');
    expect(c.ranking.score).toBeNull();
    expect(c.ranking.order.length).toBeGreaterThan(0);
    expect(c.ranking.ranking[0]).toMatchObject({ site_id: expect.any(String), rank: 1 });
    expect(Array.isArray(c.ranking.not_comparable)).toBe(true);
    expect(c.sites.map((s) => s.site.id).sort()).toEqual(c.ranking.ranking.map((r) => r.site_id).sort());
    expect(c.model_version).toBe(ev.model_version);
  });
  it('snapshot, horizon e parameters', () => {
    const sn = fx<RavenSnapshot>('snapshot');
    expect(sn.sites[0]).toMatchObject({ id: expect.any(String), earth_el_deg: expect.any(Number), state: expect.any(String) });
    const h = fx<RavenHorizon>('horizon');
    expect(h.elevation_deg.length).toBe(h.distance_m.length);
    expect(h.azimuth_step_deg).toBe(0.25);
    const p = fx<RavenParameters>('parameters');
    expect(p.defaults.window).toMatchObject({ days: 7, step_min: 10, n_steps: 1008, max_steps_per_site: 1500, max_steps_total: 6000 });
    expect(p.defaults.rf).toMatchObject({ frequency_ghz: 8.425, station_gain_dbi: 68.29, tsys_k: 26.2, ebn0_db: 9.6 });
    expect(p.parameters[0]).toMatchObject({ key: expect.any(String), tag: expect.stringMatching(/^[VDI]$/) });
  });
});

describe('client', () => {
  it('mappa 422 e 503 e gli errori di rete, senza metterli in cache', async () => {
    for (const [status, kind] of [[422, 'invalid'], [503, 'unavailable'], [500, 'server']] as const) {
      const { f } = stub(() => reply({}, status));
      expect(await createRavenClient({ fetch: f }).evaluate(evaluateIn('s', START))).toEqual({ ok: false, kind, status });
    }
    const net = createRavenClient({ fetch: (() => Promise.reject(new TypeError('x'))) as typeof fetch });
    expect(await net.evaluate(evaluateIn('s', START))).toEqual({ ok: false, kind: 'network' });
    const bad = createRavenClient({ fetch: (() => Promise.resolve(new Response('no'))) as typeof fetch });
    expect(await bad.evaluate(evaluateIn('s', START))).toEqual({ ok: false, kind: 'response' });
    expect(bad.cached).toBe(0);
  });
  it('le richieste identiche usano la cache (anche con chiavi in ordine diverso) e quelle in volo si fondono', async () => {
    const { f, calls } = stub(() => reply({ model_version: 'raven-core-1' }));
    const c = createRavenClient({ fetch: f });
    const [a, b] = await Promise.all([
      c.evaluate({ site_id: 's', start_utc: START, days: 1, step_min: 60 }),
      c.evaluate({ step_min: 60, days: 1, start_utc: START, site_id: 's' }),
    ]);
    expect(a.ok && b.ok).toBe(true);
    await c.evaluate({ site_id: 's', start_utc: START, days: 1, step_min: 60 });
    expect(calls).toHaveLength(1);
    await c.evaluate({ site_id: 's', start_utc: START, days: 2, step_min: 60 });
    expect(calls).toHaveLength(2);
    expect(calls[0]?.init?.method).toBe('POST');
  });
  it('GET: query ordinata e cache', async () => {
    expect(queryString({ t: START, a: 1, z: undefined })).toBe('a=1&t=2027-01-01T00%3A00%3A00Z');
    const { f, calls } = stub(() => reply({ sites: [] }));
    const c = createRavenClient({ fetch: f });
    await c.snapshot({ t: START, station: 'dsn18' });
    await c.snapshot({ station: 'dsn18', t: START });
    expect(calls.map((x) => x.url)).toEqual(['/api/raven/snapshot?station=dsn18&t=2027-01-01T00%3A00%3A00Z']);
  });
  it('annulla la richiesta superata di un canale', async () => {
    const seen: AbortSignal[] = [];
    const f = ((_u: string, init?: RequestInit) => new Promise<Response>((_res, rej) => {
      seen.push(init!.signal!);
      init!.signal!.addEventListener('abort', () => rej(new DOMException('a', 'AbortError')));
    })) as typeof fetch;
    const c = createRavenClient({ fetch: f });
    const first = c.evaluate(evaluateIn('s', START), { signal: c.latest('planner') });
    const second = c.evaluate(evaluateIn('s', START, { days: 1 }), { signal: c.latest('planner') });
    expect(await first).toEqual({ ok: false, kind: 'aborted' });
    expect(seen[0]?.aborted).toBe(true);
    expect(seen[1]?.aborted).toBe(false);
    void second;
  });
  it('un chiamante che annulla non interrompe un altro chiamante della stessa richiesta', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const f = (() => gate.then(() => reply({ ok: 1 }))) as typeof fetch;
    const c = createRavenClient({ fetch: f });
    const ac = new AbortController();
    const a = c.evaluate(evaluateIn('s', START), { signal: ac.signal });
    const b = c.evaluate(evaluateIn('s', START));
    ac.abort();
    release();
    expect(await a).toEqual({ ok: false, kind: 'aborted' });
    expect((await b).ok).toBe(true);
  });
});
