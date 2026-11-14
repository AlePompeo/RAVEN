// SPDX-License-Identifier: Apache-2.0
export type MissionKind = 'site-study' | 'fixed-lander' | 'communications';
export type PlannerPath = 'guided' | 'advanced';
export interface MissionSetup {
  name: string;
  kind: MissionKind;
  path: PlannerPath;
}

export const defaultSetup = (): MissionSetup => ({ name: '', kind: 'site-study', path: 'guided' });

export function readSetup(value: unknown): MissionSetup | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  if (typeof v.name !== 'string' || v.name.length > 80 ||
      (v.kind !== 'site-study' && v.kind !== 'fixed-lander' && v.kind !== 'communications') ||
      (v.path !== 'guided' && v.path !== 'advanced')) return null;
  return { name: v.name, kind: v.kind, path: v.path };
}

export interface RadioPreset {
  station: 'dsn34' | 'dsn18';
  gain: number;
  rate: number;
  k: number;
  mast: number;
}
export const RADIO_PRESETS = {
  baseline: { station: 'dsn34', gain: 15, rate: 100_000, k: 2.33, mast: 2 },
  lowRate: { station: 'dsn34', gain: 10, rate: 10_000, k: 2.33, mast: 2 },
  highRate: { station: 'dsn34', gain: 25, rate: 1_000_000, k: 2.33, mast: 2 },
} as const satisfies Record<string, RadioPreset>;
export type RadioPresetId = keyof typeof RADIO_PRESETS;

export function identifyRadioPreset(value: {
  station: string; gain: number | null; rate: number; k: number | null; mast: number | null;
}): RadioPresetId | 'custom' {
  for (const id of Object.keys(RADIO_PRESETS) as RadioPresetId[]) {
    const preset = RADIO_PRESETS[id];
    if (preset.station === value.station && preset.gain === value.gain && preset.rate === value.rate &&
        preset.k === value.k && preset.mast === value.mast) return id;
  }
  return 'custom';
}
