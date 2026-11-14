// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { defaultObjectives, evaluateObjectives, readObjectives } from './objectives';

describe('mission objectives', () => {
  it('restores valid objectives and rejects malformed thresholds', () => {
    expect(readObjectives({ priority: 'radio', minSunPercent: 0, minRfPercent: 100 })).toEqual({
      priority: 'radio', minSunPercent: 0, minRfPercent: 100,
    });
    expect(readObjectives({ ...defaultObjectives(), minSunPercent: 101 })).toBeNull();
    expect(readObjectives({ ...defaultObjectives(), minRfPercent: NaN })).toBeNull();
    expect(readObjectives({ ...defaultObjectives(), priority: 'other' })).toBeNull();
  });

  it('compares exact sample fractions without treating unavailable RF as a failure', () => {
    const objectives = { priority: 'balanced' as const, minSunPercent: 50, minRfPercent: 50 };
    expect(evaluateObjectives(objectives, 0.5, [true, false])).toEqual({ sun: 'met', rf: 'met' });
    expect(evaluateObjectives(objectives, 0.499, [false, false])).toEqual({ sun: 'not_met', rf: 'not_met' });
    expect(evaluateObjectives(objectives, 0.5, null)).toEqual({ sun: 'met', rf: 'unknown' });
    expect(evaluateObjectives({ ...objectives, minSunPercent: 29 }, 0.29, null).sun).toBe('met');
    expect(evaluateObjectives(defaultObjectives(), 0, null)).toEqual({ sun: 'not_set', rf: 'not_set' });
  });
});
