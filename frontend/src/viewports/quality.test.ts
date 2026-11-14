// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { detectQuality } from './quality';

describe('detectQuality (ingressi espliciti, indipendente dall\'host)', () => {
  it('macchina forte: livello hi', () => {
    expect(detectQuality({ hardwareConcurrency: 8, deviceMemory: 8 }, false)).toEqual({ tier: 'hi', dprCap: 2, parallax: true });
  });
  it('2 core, poca memoria, Save-Data o reduced-data: livello lo', () => {
    expect(detectQuality({ hardwareConcurrency: 2, deviceMemory: 8 }, false).tier).toBe('lo');
    expect(detectQuality({ hardwareConcurrency: 8, deviceMemory: 2 }, false).tier).toBe('lo');
    expect(detectQuality({ hardwareConcurrency: 8, connection: { saveData: true } }, false).tier).toBe('lo');
    expect(detectQuality({ hardwareConcurrency: 8 }, true)).toEqual({ tier: 'lo', dprCap: 1.5, parallax: false });
  });
  it('il setup condiviso fissa un host forte', () => {
    expect(detectQuality(undefined, false).tier).toBe('hi');
  });
});
