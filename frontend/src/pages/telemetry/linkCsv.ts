// SPDX-License-Identifier: Apache-2.0
export const MAX_LINK_CSV_BYTES = 1_000_000;
export const MAX_LINK_SAMPLES = 2000;

export interface LinkSample {
  t_utc: string;
  margin_db: number;
  elevation_deg: number;
  rate_bps: number;
}

export type LinkCsvResult =
  | { ok: true; samples: LinkSample[] }
  | { ok: false; reason: 'header' | 'row' | 'order' | 'empty' | 'size'; line?: number };

function cells(line: string): string[] | null {
  const out: string[] = [];
  let value = '';
  let quoted = false;
  let closed = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i]!;
    if (quoted) {
      if (c === '"') {
        if (line[i + 1] === '"') {
          value += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else value += c;
    } else if (c === ',') {
      out.push(value.trim());
      value = '';
      closed = false;
    } else if (c === '"' && value.trim() === '' && !closed) {
      value = '';
      quoted = true;
    } else if (closed && !/\s/.test(c)) return null;
    else if (!closed) value += c;
  }
  if (quoted) return null;
  out.push(value.trim());
  return out;
}

const REQUIRED = ['t_utc', 'link_margin_db', 'earth_el_deg', 'rate_bps'];
const NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

export function parseLinkCsv(text: string): LinkCsvResult {
  if (new TextEncoder().encode(text).length > MAX_LINK_CSV_BYTES) return { ok: false, reason: 'size' };
  const lines = text.replace(/^\uFEFF/, '').split(/\r\n|\n|\r/);
  const header = cells(lines[0] ?? '');
  if (!header || new Set(header).size !== header.length || REQUIRED.some((name) => !header.includes(name))) {
    return { ok: false, reason: 'header' };
  }
  const indexes = REQUIRED.map((name) => header.indexOf(name));
  const samples: LinkSample[] = [];
  let previous = -Infinity;
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]!.trim()) continue;
    const row = cells(lines[i]!);
    if (!row || row.length !== header.length) return { ok: false, reason: 'row', line: i + 1 };
    const [time, margin, elevation, rate] = indexes.map((index) => row[index] ?? '');
    if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(time ?? '')) {
      return { ok: false, reason: 'row', line: i + 1 };
    }
    const ms = Date.parse(time!);
    const date = new Date(ms);
    if (!Number.isFinite(ms) || date.toISOString().slice(0, 19) !== time!.slice(0, 19)) {
      return { ok: false, reason: 'row', line: i + 1 };
    }
    const numbers = [margin, elevation, rate];
    if (numbers.some((v) => !v || !NUMBER.test(v) || !Number.isFinite(Number(v)))) {
      return { ok: false, reason: 'row', line: i + 1 };
    }
    const [m, e, r] = numbers.map(Number) as [number, number, number];
    if (Math.abs(m) > 10_000 || e < -90 || e > 90 || r <= 0 || r > 1e12) {
      return { ok: false, reason: 'row', line: i + 1 };
    }
    if (ms <= previous) return { ok: false, reason: 'order', line: i + 1 };
    if (samples.length >= MAX_LINK_SAMPLES) return { ok: false, reason: 'size' };
    samples.push({ t_utc: time!, margin_db: m, elevation_deg: e, rate_bps: r });
    previous = ms;
  }
  return samples.length ? { ok: true, samples } : { ok: false, reason: 'empty' };
}
