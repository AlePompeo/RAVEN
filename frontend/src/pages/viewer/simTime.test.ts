// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { advance, clampMs, dateValue, inRange, isoUtc, MAX_MS, MIN_MS, parseDateTime, SPEEDS, stepMs, STEPS, timeValue } from './simTime';

const T = Date.UTC(2026, 9, 20, 12, 30, 15);

describe('simTime', () => {
  it('formatta e rilegge in UTC', () => {
    expect(dateValue(T)).toBe('2026-10-20');
    expect(timeValue(T)).toBe('12:30:15');
    expect(isoUtc(T)).toBe('2026-10-20T12:30:15Z');
    expect(parseDateTime('2026-10-20', '12:30:15')).toBe(T);
    expect(parseDateTime('2026-10-20', '12:30')).toBe(T - 15_000);
  });
  it('rifiuta date e ore non valide', () => {
    expect(parseDateTime('2026-02-30', '00:00:00')).toBeNull();
    expect(parseDateTime('', '00:00:00')).toBeNull();
    expect(parseDateTime('2026-13-01', '00:00:00')).toBeNull();
    expect(parseDateTime('2026-01-01', '24:00:00')).toBeNull();
    expect(parseDateTime('abc', 'x')).toBeNull();
  });
  it('passi di giorno e ora', () => {
    expect(stepMs(T, STEPS.dayFwd).ms).toBe(T + 86_400_000);
    expect(stepMs(T, STEPS.hourBack).ms).toBe(T - 3_600_000);
    expect(stepMs(T, STEPS.dayFwd).clamped).toBe(false);
  });
  it('limita all intervallo supportato', () => {
    expect(clampMs(MIN_MS - 1)).toBe(MIN_MS);
    expect(clampMs(MAX_MS + 1)).toBe(MAX_MS);
    expect(clampMs(Number.NaN)).toBe(MIN_MS);
    expect(stepMs(MAX_MS - 1000, STEPS.dayFwd)).toEqual({ ms: MAX_MS, clamped: true });
    expect(stepMs(MIN_MS + 1000, STEPS.dayBack)).toEqual({ ms: MIN_MS, clamped: true });
    expect(inRange(T)).toBe(true);
    expect(inRange(Date.UTC(1971, 11, 31))).toBe(false);
    expect(inRange(Date.UTC(2151, 0, 1))).toBe(false);
  });
  it('la riproduzione avanza per velocita e si ferma al limite', () => {
    const hour = SPEEDS.find((s) => s.id === 'hour')!;
    expect(advance(T, 500, hour.msPerS).ms).toBe(T + 1_800_000);
    const day = SPEEDS.find((s) => s.id === 'day')!;
    expect(advance(MAX_MS - 1000, 1000, day.msPerS)).toEqual({ ms: MAX_MS, atLimit: true });
  });
});
