// SPDX-License-Identifier: Apache-2.0
/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { Telemetry } from '../../contracts/telemetry';
import { createTelemetryClient, parseSample, statusText, type ConnectionStatus, type SourceLike } from './client';
import { buildTable, pushSample, toChartData } from './table';

class FakeSource implements SourceLike {
  static all: FakeSource[] = [];
  onopen: SourceLike['onopen'] = null;
  onmessage: SourceLike['onmessage'] = null;
  onerror: SourceLike['onerror'] = null;
  closed = false;
  constructor(public url: string) {
    FakeSource.all.push(this);
  }
  close(): void {
    this.closed = true;
  }
}

const sample = (i: number, extra: Partial<Telemetry> = {}): Telemetry => ({
  schema_version: '1.0.0',
  t_utc: new Date(Date.UTC(2026, 0, 1, 0, 0, i)).toISOString(),
  site_id: 'shackleton',
  power_w: 100 + i,
  ...extra,
});

function setup(random: () => number = () => 1) {
  FakeSource.all = [];
  const timers: { fn: () => void; ms: number; id: number; live: boolean }[] = [];
  const samples: Telemetry[] = [];
  const statuses: ConnectionStatus[] = [];
  const client = createTelemetryClient({
    onSample: (s) => samples.push(s),
    onStatus: (s) => statuses.push(s),
    createSource: (u) => new FakeSource(u),
    random,
    setTimer: (fn, ms) => {
      const t = { fn, ms, id: timers.length, live: true };
      timers.push(t);
      return t.id;
    },
    clearTimer: (h) => {
      const t = timers[h as number];
      if (t) t.live = false;
    },
  });
  return { client, timers, samples, statuses };
}

describe('telemetry client', () => {
  it('connects to the stream url and delivers valid samples only', () => {
    const { client, samples, statuses } = setup();
    client.start();
    const s = FakeSource.all[0]!;
    expect(s.url).toBe('/api/telemetry/stream');
    s.onopen?.({});
    s.onmessage?.({ data: JSON.stringify(sample(1)) });
    s.onmessage?.({ data: 'not json' });
    s.onmessage?.({ data: JSON.stringify({ t_utc: 'x', power_w: 1 }) });
    s.onmessage?.({ data: JSON.stringify({ ...sample(2), power_w: 'NaN' }) });
    expect(samples).toHaveLength(1);
    expect(statuses.at(-1)).toEqual({ kind: 'open' });
  });

  it('reconnects with exponential backoff, resets after open, and closes failed sources', () => {
    const { client, timers, statuses } = setup();
    client.start();
    FakeSource.all[0]!.onerror?.({});
    expect(FakeSource.all[0]!.closed).toBe(true);
    expect(timers[0]!.ms).toBe(1000);
    expect(statuses.at(-1)).toEqual({ kind: 'reconnecting', attempt: 1, delayMs: 1000 });
    timers[0]!.fn();
    expect(FakeSource.all).toHaveLength(2);
    FakeSource.all[1]!.onerror?.({});
    expect(timers[1]!.ms).toBe(2000);
    timers[1]!.fn();
    FakeSource.all[2]!.onopen?.({});
    FakeSource.all[2]!.onerror?.({});
    expect(timers[2]!.ms).toBe(1000); // backoff azzerato dopo open
  });

  it('caps the backoff delay', () => {
    const { client, timers } = setup();
    client.start();
    for (let i = 0; i < 10; i++) {
      FakeSource.all.at(-1)!.onerror?.({});
      timers.at(-1)!.fn();
    }
    FakeSource.all.at(-1)!.onerror?.({});
    expect(timers.at(-1)!.ms).toBe(30000);
  });

  it('stop closes the source, cancels the retry, ignores late events, and is idempotent', () => {
    const { client, timers, samples, statuses } = setup();
    client.start();
    const s = FakeSource.all[0]!;
    s.onerror?.({});
    client.stop();
    client.stop();
    expect(timers[0]!.live).toBe(false);
    expect(statuses.some((x) => x.kind === 'closed')).toBe(false); // nessuno stato dopo la distruzione
    const n = statuses.length;
    client.stop();
    expect(statuses).toHaveLength(n);
    timers[0]!.fn(); // un timer già in volo non deve riconnettere
    expect(FakeSource.all).toHaveLength(1);

    client.start();
    const s2 = FakeSource.all[1]!;
    client.stop();
    expect(s2.closed).toBe(true);
    expect(s2.onmessage).toBeNull();
    expect(samples).toHaveLength(0);
  });

  it('parseSample validates; statusText is textual', () => {
    expect(parseSample(JSON.stringify(sample(0)))).not.toBeNull();
    expect(parseSample(42)).toBeNull();
    expect(parseSample('null')).toBeNull();
    expect(statusText({ kind: 'open' })).toMatch(/Connesso/);
    expect(statusText({ kind: 'reconnecting', attempt: 2, delayMs: 2000 })).toBe(
      statusText({ kind: 'reconnecting', attempt: 3, delayMs: 4000 }),
    );
  });
});

describe('backoff jitter', () => {
  it('applies injectable jitter between half and full delay', () => {
    const lo = setup(() => 0);
    lo.client.start();
    FakeSource.all[0]!.onerror?.({});
    expect(lo.timers[0]!.ms).toBe(500);
    const hi = setup(() => 1);
    hi.client.start();
    FakeSource.all[0]!.onerror?.({});
    expect(hi.timers[0]!.ms).toBe(1000);
  });
});

describe('contract', () => {
  const fixture = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../contracts/examples/telemetry.sample.json'), 'utf8');

  it('parses the shared contract example with all fields', () => {
    const s = parseSample(fixture);
    expect(s).toEqual(JSON.parse(fixture));
    expect(s?.schema_version).toBe('1.0.0');
    expect(s?.sun).toEqual({ az_deg: 120.5, el_deg: 35.0 });
    expect(s?.earth?.el_deg).toBe(5.5);
    expect(s?.link_margin_db).toBe(6.2);
  });

  it('rejects missing required fields, bad semver, non-finite and malformed nested values', () => {
    const base = JSON.parse(fixture) as Record<string, unknown>;
    const bad = (o: Record<string, unknown>) => parseSample(JSON.stringify(o));
    for (const k of ['schema_version', 't_utc', 'site_id', 'power_w']) {
      const { [k]: _omit, ...rest } = base;
      expect(bad(rest), k).toBeNull();
    }
    expect(bad({ ...base, schema_version: '1' })).toBeNull();
    expect(bad({ ...base, power_w: null })).toBeNull();
    expect(bad({ ...base, link_margin_db: 'x' })).toBeNull();
    expect(bad({ ...base, sun: { az_deg: 1 } })).toBeNull();
    expect(bad({ ...base, earth: { az_deg: 1, el_deg: null } })).toBeNull();
    expect(parseSample('{"schema_version":"1.0.0","t_utc":"2026-10-12T12:00:00Z","site_id":"a","power_w":1e999}')).toBeNull();
    const { sun: _s, earth: _e, link_margin_db: _l, ...minimal } = base;
    expect(bad(minimal)).not.toBeNull();
  });
});

describe('schema-driven strictness', () => {
  const schema = JSON.parse(
    readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../contracts/telemetry.schema.json'), 'utf8'),
  ) as {
    required: string[];
    additionalProperties: boolean;
    properties: { schema_version: { pattern: string }; site_id: { minLength: number } };
    $defs: { AzEl: { additionalProperties: boolean; required: string[] } };
  };
  const example = JSON.parse(
    readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../contracts/examples/telemetry.sample.json'), 'utf8'),
  ) as Record<string, unknown>;
  const p = (o: unknown) => parseSample(JSON.stringify(o));

  it('schema still has the shape this test assumes', () => {
    expect(schema.additionalProperties).toBe(false);
    expect(schema.$defs.AzEl.additionalProperties).toBe(false);
    expect(schema.properties.site_id.minLength).toBe(1);
  });

  it('rejects every missing required field', () => {
    for (const k of schema.required) {
      const o = { ...example };
      delete o[k];
      expect(p(o), k).toBeNull();
    }
    for (const k of schema.$defs.AzEl.required) {
      const sun = { ...(example.sun as Record<string, unknown>) };
      delete sun[k];
      expect(p({ ...example, sun }), k).toBeNull();
    }
  });

  it('rejects unknown properties at top level and in sun/earth', () => {
    expect(p({ ...example, extra: 1 })).toBeNull();
    expect(p({ ...example, sun: { ...(example.sun as object), extra: 1 } })).toBeNull();
    expect(p({ ...example, earth: { ...(example.earth as object), alt_km: 1 } })).toBeNull();
  });

  it('rejects empty site_id and schema_version not matching the schema pattern', () => {
    expect(p({ ...example, site_id: '' })).toBeNull();
    const re = new RegExp(schema.properties.schema_version.pattern);
    for (const v of ['1', '1.0', '01.0.0', '1.0.0-beta', 'v1.0.0', '1.0.0 ', '1.0.0\n']) {
      expect(re.test(v) && v === v.trim(), v).toBe(false); // il caso deve violare lo schema
      expect(p({ ...example, schema_version: v }), v).toBeNull();
    }
    expect(p({ ...example, schema_version: '0.12.3' })).not.toBeNull();
  });

  it('requires RFC 3339 date-time with timezone', () => {
    for (const t of ['2026-10-12', '2026-10-12T12:00:00', '12 Oct 2026', '2026-13-01T00:00:00Z', '2026-02-30T00:00:00Z', '2026-10-12T25:00:00Z', 'x']) {
      expect(p({ ...example, t_utc: t }), t).toBeNull();
    }
    for (const t of ['2026-10-12T12:00:00Z', '2026-10-12T12:00:00.123+02:00', '2026-10-12t12:00:00z']) {
      expect(p({ ...example, t_utc: t }), t).not.toBeNull();
    }
  });
});

describe('table builder', () => {
  it('lists the latest N samples, newest first, with caption and placeholders', () => {
    const buf = Array.from({ length: 15 }, (_, i) => sample(i, i === 14 ? { link_margin_db: 3.14159 } : {}));
    const t = buildTable(buf, 5);
    expect(t.rows).toHaveLength(5);
    expect(t.caption).toContain('5');
    expect(t.rows[0]).toEqual([buf[14]!.t_utc, 'shackleton', '114.0', '3.1']);
    expect(t.rows[1]![3]).toBe('—');
    expect(t.headers).toHaveLength(4);
  });

  it('handles an empty buffer', () => {
    expect(buildTable([]).rows).toEqual([]);
  });

  it('pushSample bounds the buffer without mutating input', () => {
    const a = [sample(0), sample(1)];
    const b = pushSample(a, sample(2), 2);
    expect(a).toHaveLength(2);
    expect(b.map((s) => s.power_w)).toEqual([101, 102]);
  });

  it('toChartData yields Float64Arrays in epoch seconds with NaN gaps', () => {
    const d = toChartData([sample(0), sample(1, { link_margin_db: 2 })]);
    expect(d.time).toBeInstanceOf(Float64Array);
    expect(d.time[1]! - d.time[0]!).toBe(1);
    expect(Number.isNaN(d.link_margin_db[0]!)).toBe(true);
    expect(d.link_margin_db[1]).toBe(2);
  });
});
