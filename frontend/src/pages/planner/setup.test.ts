// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { defaultSetup, identifyRadioPreset, RADIO_PRESETS, readSetup } from './setup';

describe('mission setup', () => {
  it('restores valid metadata without accepting arbitrary saved types or excessive names', () => {
    const setup = { name: 'Studio lunare', kind: 'fixed-lander', path: 'advanced' };
    expect(readSetup(setup)).toEqual(setup);
    expect(readSetup({ ...setup, kind: 'unknown' })).toBeNull();
    expect(readSetup({ ...setup, name: 'x'.repeat(81) })).toBeNull();
    expect(readSetup(defaultSetup())).toEqual(defaultSetup());
  });

  it('marks a preset custom if any radio parameter is changed', () => {
    expect(identifyRadioPreset(RADIO_PRESETS.baseline)).toBe('baseline');
    expect(identifyRadioPreset({ ...RADIO_PRESETS.baseline, mast: 4 })).toBe('custom');
    expect(identifyRadioPreset({ ...RADIO_PRESETS.lowRate, gain: null })).toBe('custom');
  });
});
