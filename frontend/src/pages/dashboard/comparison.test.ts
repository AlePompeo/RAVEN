// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { knownHours } from './comparison';

describe('knownHours', () => {
  it('counts true samples using their duration', () => {
    expect(knownHours([true, false, true], 30)).toBe(1);
    expect(knownHours([false, false], 60)).toBe(0);
  });
  it('does not turn missing samples into a complete total', () => {
    expect(knownHours([true, null, false], 60)).toBeNull();
    expect(knownHours([], 60)).toBeNull();
  });
});
