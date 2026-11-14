// SPDX-License-Identifier: Apache-2.0
// Tempo simulato del visualizzatore: solo UTC, millisecondi dall'epoca Unix. Funzioni pure (testate).

/** Intervallo supportato dal motore (docs/ephemeris.md): 1972-01-01 .. 2150-01-20 UTC (margine di un giorno sul massimo). */
export const MIN_MS = Date.UTC(1972, 0, 1, 0, 0, 0);
export const MAX_MS = Date.UTC(2150, 0, 20, 23, 58, 50);

export const SPEEDS = [
  { id: 'min', label: '1 minuto al secondo', short: '×1 min/s', msPerS: 60_000 },
  { id: 'hour', label: '1 ora al secondo', short: '×1 h/s', msPerS: 3_600_000 },
  { id: 'day', label: '1 giorno al secondo', short: '×1 giorno/s', msPerS: 86_400_000 },
] as const;
export type SpeedId = (typeof SPEEDS)[number]['id'];

export const STEPS = {
  dayBack: -86_400_000,
  dayFwd: 86_400_000,
  hourBack: -3_600_000,
  hourFwd: 3_600_000,
} as const;

export function inRange(ms: number): boolean {
  return Number.isFinite(ms) && ms >= MIN_MS && ms <= MAX_MS;
}

export function clampMs(ms: number): number {
  if (!Number.isFinite(ms)) return MIN_MS;
  return Math.min(MAX_MS, Math.max(MIN_MS, ms));
}

/** Somma `delta` e limita all'intervallo; `clamped` dice se il limite e' stato raggiunto. */
export function stepMs(ms: number, delta: number): { ms: number; clamped: boolean } {
  const next = ms + delta;
  const c = clampMs(next);
  return { ms: c, clamped: c !== next };
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0');

/** "AAAA-MM-GG" per <input type="date"> (UTC). */
export function dateValue(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCFullYear(), 4)}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** "hh:mm:ss" per <input type="time" step="1"> (UTC). */
export function timeValue(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** ISO UTC senza millisecondi, con "Z", come richiede l'API. */
export function isoUtc(ms: number): string {
  return `${dateValue(ms)}T${timeValue(ms)}Z`;
}

/** Legge data e ora (UTC) dai campi; `null` se non valide (anche 30 febbraio). */
export function parseDateTime(date: string, time: string): number | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const tm = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(time || '00:00:00');
  if (!dm || !tm) return null;
  const [y, mo, d] = [Number(dm[1]), Number(dm[2]), Number(dm[3])];
  const [h, mi, s] = [Number(tm[1]), Number(tm[2]), Number(tm[3] ?? 0)];
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null;
  const ms = Date.UTC(y, mo - 1, d, h, mi, s);
  const back = new Date(ms);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) return null;
  return ms;
}

/** Testo dell'intervallo per i messaggi. */
export const RANGE_TEXT = 'dal 1972-01-01 al 2150-01-20 UTC';

/** Istante dopo `elapsedMs` di tempo reale a velocita' `msPerS`; si ferma ai limiti. */
export function advance(ms: number, elapsedMs: number, msPerS: number): { ms: number; atLimit: boolean } {
  const r = stepMs(ms, (elapsedMs / 1000) * msPerS);
  return { ms: r.ms, atLimit: r.clamped };
}
