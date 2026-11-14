// SPDX-License-Identifier: Apache-2.0
/** Pure formatting and comparison helpers for the report. They never turn an unknown into a number. */

export const MINUS = '−';

/** Typographic minus for a number already formatted by Intl; ISO dates and hyphenated words are left alone. */
export function minusSign(text: string): string {
  return text.replace(/(^|[\s(])-(?=\d)/g, `$1${MINUS}`);
}

/** One UTC format for the whole report: `YYYY-MM-DD HH:mm UTC`, never seconds or milliseconds. Unparseable input is returned as is. */
export function utcMinute(value: string | number | Date): string {
  if (typeof value === 'string') {
    const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
    return m ? `${m[1]} ${m[2]} UTC` : value;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isFinite(date.getTime()) ? utcMinute(date.toISOString()) : String(value);
}

/** Bit rate with the largest exact unit (3000000 -> 3 Mbit/s); non-round rates keep every digit. `format` localises numbers. */
export function bitRate(value: number, format: (n: number) => string = String): string {
  if (!Number.isFinite(value)) return String(value);
  for (const [factor, unit] of [[1e6, 'Mbit/s'], [1e3, 'kbit/s']] as const) {
    if (Math.abs(value) >= factor && Number.isInteger(value / factor * 1000)) return `${format(value / factor)} ${unit}`;
  }
  return `${format(value)} bit/s`;
}

/** Strict element-wise equality; null (unknown) only equals null, so two unknowns are never confused with a number. */
export function sameSeries(a: readonly (number | null)[], b: readonly (number | null)[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** Rows of a two-scenario table: those where A and B differ, and the ones shared. */
export function splitShared<T>(a: Readonly<Record<string, T>>, b: Readonly<Record<string, T>>) {
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])];
  const differing: string[] = [];
  const shared: string[] = [];
  for (const key of keys) (key in a && key in b && Object.is(a[key], b[key]) ? shared : differing).push(key);
  return { differing, shared };
}

type ParameterSet = Readonly<Record<string, Readonly<Record<string, unknown>>>>;

/** Parameters of several scenarios, grouped: rows with the same value in every scenario once, the rest per scenario. */
export function sharedParameters(sets: readonly ParameterSet[]) {
  const shared: Record<string, Record<string, unknown>> = {};
  const differing: Record<string, Record<string, unknown>>[] = sets.map(() => ({}));
  const groups = [...new Set(sets.flatMap((set) => Object.keys(set)))];
  for (const group of groups) {
    const keys = [...new Set(sets.flatMap((set) => Object.keys(set[group] ?? {})))];
    for (const key of keys) {
      const same = sets.every((set) => group in set && key in set[group]! && Object.is(set[group]![key], sets[0]![group]?.[key]));
      if (same) (shared[group] ??= {})[key] = sets[0]![group]![key];
      else sets.forEach((set, i) => { if (group in set && key in set[group]!) (differing[i]![group] ??= {})[key] = set[group]![key]; });
    }
  }
  return { shared, differing };
}
