// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { MAX_LINK_SAMPLES, parseLinkCsv } from './linkCsv';

const header = 't_utc,link_margin_db,earth_el_deg,rate_bps';
const row = '2026-10-12T10:00:00Z,6.2,0.9,100000';

describe('link telemetry CSV', () => {
  it('parses quoted cells, reordered columns and optional columns', () => {
    const result = parseLinkCsv('\ufeffrate_bps,t_utc,earth_el_deg,link_margin_db,note\n1e5,"2026-10-12T10:00:00Z",0.9,6.2,"a,b"');
    expect(result).toEqual({ ok: true, samples: [{ t_utc: '2026-10-12T10:00:00Z', margin_db: 6.2, elevation_deg: 0.9, rate_bps: 100000 }] });
  });

  it('rejects missing headers, malformed numbers, dates and CSV', () => {
    expect(parseLinkCsv('t_utc,rate_bps\nx,1')).toEqual({ ok: false, reason: 'header' });
    for (const invalid of [
      '2026-02-30T10:00:00Z,1,1,100',
      '2026-10-12T10:00:00,1,1,100',
      '2026-10-12T10:00:00Z,,1,100',
      '2026-10-12T10:00:00Z,NaN,1,100',
      '2026-10-12T10:00:00Z,1,91,100',
      '2026-10-12T10:00:00Z,1,1,0',
      '2026-10-12T10:00:00Z,1e308,1,100',
      '2026-10-12T10:00:00Z,1,1,1e308',
      '2026-10-12T10:00:00Z,"1,1,100',
    ]) expect(parseLinkCsv(`${header}\n${invalid}`)).toEqual({ ok: false, reason: 'row', line: 2 });
  });

  it('rejects duplicate or out-of-order timestamps instead of silently reordering', () => {
    expect(parseLinkCsv(`${header}\n${row}\n${row}`)).toEqual({ ok: false, reason: 'order', line: 3 });
  });

  it('rejects an empty file and excessive samples', () => {
    expect(parseLinkCsv(`${header}\n`)).toEqual({ ok: false, reason: 'empty' });
    const rows = Array.from({ length: MAX_LINK_SAMPLES + 1 }, (_, i) =>
      `${new Date(Date.UTC(2026, 0, 1, 0, 0, i)).toISOString()},1,1,100`);
    expect(parseLinkCsv(`${header}\n${rows.join('\n')}`)).toEqual({ ok: false, reason: 'size' });
  });
});
