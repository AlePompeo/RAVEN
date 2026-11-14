// SPDX-License-Identifier: Apache-2.0
// Istante predefinito della Scena lander: quando lo scenario non ha un istante esplicito si cerca, nel mese lunare
// successivo, il primo istante in cui il Sole vero (JPL DE440, GET /api/raven/sky/series) sta tra 1 e 3 gradi sull'orizzonte
// del sito (luce radente: il rilievo si vede). Nessuna luce inventata: se non c'e' un istante cosi', resta quello dato.
import { isoUtc } from '../viewer/simTime';
import { sunLocal } from './model';

export const GRAZING_MIN_DEG = 1;
export const GRAZING_MAX_DEG = 3;
export const SEARCH_DAYS = 29.53;
export const SEARCH_STEP_S = 3600;

export interface SunSeries {
  ms: number[];
  dirs: [number, number, number][];
}

export type DefaultInstant =
  | { kind: 'grazing'; ms: number; elDeg: number }
  | { kind: 'none'; ms: number; elDeg: number | null };

/** Quota del Sole (gradi) al sito, per ogni punto della serie. */
export const sunElevations = (s: SunSeries, latDeg: number, lonDeg: number): number[] => s.dirs.map((d) => sunLocal(latDeg, lonDeg, d, 0).elDeg);

/**
 * Primo istante (il piu' vicino a `startMs`, dal basso verso l'alto nel tempo) con quota del Sole in [lo, hi].
 * Se non c'e', `none` con l'istante dato e la quota del Sole a quell'istante (primo punto della serie).
 */
export function pickGrazingInstant(startMs: number, s: SunSeries, latDeg: number, lonDeg: number, lo = GRAZING_MIN_DEG, hi = GRAZING_MAX_DEG): DefaultInstant {
  const el = sunElevations(s, latDeg, lonDeg);
  for (let i = 0; i < el.length; i++) {
    const e = el[i]!;
    if (s.ms[i]! >= startMs && e >= lo && e <= hi) return { kind: 'grazing', ms: s.ms[i]!, elDeg: e };
  }
  return { kind: 'none', ms: startMs, elDeg: el[0] ?? null };
}

export function parseSeries(json: unknown): SunSeries | null {
  const o = json as { t_utc?: unknown; sun_direction_body_fixed?: unknown } | null;
  const t = o?.t_utc;
  const d = o?.sun_direction_body_fixed;
  if (!Array.isArray(t) || !Array.isArray(d) || t.length !== d.length || t.length === 0) return null;
  const ms = t.map((x) => (typeof x === 'string' ? Date.parse(x) : NaN));
  if (ms.some((x) => !Number.isFinite(x))) return null;
  const dirs: [number, number, number][] = [];
  for (const v of d) {
    if (!Array.isArray(v) || v.length !== 3 || v.some((c) => typeof c !== 'number' || !Number.isFinite(c))) return null;
    const n = Math.hypot(v[0] as number, v[1] as number, v[2] as number);
    if (n === 0) return null;
    dirs.push([(v[0] as number) / n, (v[1] as number) / n, (v[2] as number) / n]);
  }
  return { ms, dirs };
}

export function seriesUrl(startMs: number): string {
  const end = startMs + SEARCH_DAYS * 86_400_000;
  return `/api/raven/sky/series?body=moon&t0=${encodeURIComponent(isoUtc(startMs))}&t1=${encodeURIComponent(isoUtc(end))}&step_s=${SEARCH_STEP_S}`;
}

/** Cerca l'istante predefinito; null se il servizio non risponde (si resta sull'istante dato, senza nota). */
export async function chooseDefaultInstant(startMs: number, latDeg: number, lonDeg: number, f: typeof fetch = fetch, signal?: AbortSignal): Promise<DefaultInstant | null> {
  try {
    const res = await f(seriesUrl(startMs), signal ? { signal } : {});
    if (!res.ok) return null;
    const s = parseSeries(await res.json());
    return s ? pickGrazingInstant(startMs, s, latDeg, lonDeg) : null;
  } catch {
    return null;
  }
}
