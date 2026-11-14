// SPDX-License-Identifier: Apache-2.0
// "RAVEN estimate": a value the engine derives from its own results for a report field the user did not fill.
// It is stored next to the dossier, never in place of a user value, and counts nowhere until the user accepts it.
export type EstimateTag = 'D' | 'I';
export type EstimateStatus = 'proposed' | 'accepted' | 'dismissed';
export const ESTIMATE_FIELDS = ['high_level_requirements', 'verification_plan', 'ait_plan',
  'schedule', 'mass_and_power_budgets', 'economic_feasibility', 'environmental_footprint', 'orbit_or_landing'] as const;
export type EstimateField = typeof ESTIMATE_FIELDS[number];

/** A catalog message with its parameters (rendered in the reader's language), a raw machine value or a number; null = unknown. */
export type Cell = string | number | null | { key: string; params?: Record<string, string | number> };
export interface EstimateItem { id: string; cells: Record<string, Cell> }
export interface EstimateRange { unit: string; min: number | null; typical: number | null; max: number | null }
export interface EstimateInput { name: string; value: string | number | boolean | null; tag?: string }

export interface EngineEstimate {
  id: string;
  field: EstimateField;
  method_id: string;
  source: string;
  tag: EstimateTag;
  range: EstimateRange | null;
  items: EstimateItem[];
  inputs_used: EstimateInput[];
  validity_limits: string[];
  produced_at: string;
  status: EstimateStatus;
  /** Digest of inputs and result: a regenerated estimate with the same digest keeps the user's decision. */
  digest: string;
}
export type Draft = Omit<EngineEstimate, 'produced_at' | 'status' | 'digest'>;

export interface Range3 { min: number; typical: number; max: number }
export interface MassDefaults {
  /** Mass is estimated only when the user applies the declared defaults (tag I, editable); otherwise it stays unknown. */
  applied: boolean;
  arrayKgPerM2: Range3; batteryWhPerKg: Range3; radioFraction: Range3; structureFraction: Range3;
}
export const MASS_DEFAULTS_KEYS = ['arrayKgPerM2', 'batteryWhPerKg', 'radioFraction', 'structureFraction'] as const;
/** Illustrative design values (tag I): not a datasheet, not a flight heritage claim. Always editable. */
export function defaultMassDefaults(): MassDefaults {
  return {
    applied: true,
    arrayKgPerM2: { min: 1.5, typical: 3, max: 6 },
    batteryWhPerKg: { min: 100, typical: 150, max: 200 },
    radioFraction: { min: 0.03, typical: 0.05, max: 0.08 },
    structureFraction: { min: 0.15, typical: 0.2, max: 0.3 },
  };
}

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const range3 = (v: unknown): v is Range3 => record(v) && num(v.min) && num(v.typical) && num(v.max);

/** True when the declared defaults cannot be used (unordered, non-positive densities, fractions that leave no mass). */
export function massDefaultsIssue(d: MassDefaults): boolean {
  const ordered = (r: Range3) => r.min <= r.typical && r.typical <= r.max;
  return !(ordered(d.arrayKgPerM2) && d.arrayKgPerM2.min > 0 && ordered(d.batteryWhPerKg) && d.batteryWhPerKg.min > 0 &&
    ordered(d.radioFraction) && d.radioFraction.min >= 0 && ordered(d.structureFraction) && d.structureFraction.min >= 0 &&
    d.radioFraction.max + d.structureFraction.max < 1);
}
export function readMassDefaults(v: unknown): MassDefaults | null {
  if (!record(v) || typeof v.applied !== 'boolean') return null;
  const out = defaultMassDefaults();
  out.applied = v.applied;
  for (const key of MASS_DEFAULTS_KEYS) {
    const r = v[key];
    if (!range3(r)) return null;
    out[key] = { min: r.min, typical: r.typical, max: r.max };
  }
  return out;
}

const isCell = (v: unknown): v is Cell => v === null || typeof v === 'string' || num(v) ||
  (record(v) && typeof v.key === 'string' && (v.params === undefined || record(v.params)));
/** Estimates are regenerable, so a stored list that does not parse is dropped, never trusted. */
export function readEstimates(v: unknown): EngineEstimate[] {
  if (!Array.isArray(v)) return [];
  const out: EngineEstimate[] = [];
  for (const e of v) {
    if (!record(e) || typeof e.id !== 'string' || !ESTIMATE_FIELDS.some((f) => f === e.field) ||
        typeof e.method_id !== 'string' || typeof e.source !== 'string' || (e.tag !== 'D' && e.tag !== 'I') ||
        !Array.isArray(e.items) || !Array.isArray(e.inputs_used) || !Array.isArray(e.validity_limits) ||
        typeof e.produced_at !== 'string' || typeof e.digest !== 'string' ||
        !['proposed', 'accepted', 'dismissed'].includes(String(e.status))) continue;
    const items = e.items.filter((i): i is EstimateItem => record(i) && typeof i.id === 'string' && record(i.cells) &&
      Object.values(i.cells).every(isCell));
    if (items.length !== e.items.length) continue;
    const r = e.range;
    out.push({ ...(e as unknown as EngineEstimate), items,
      range: record(r) && typeof r.unit === 'string' ? { unit: r.unit, min: num(r.min) ? r.min : null,
        typical: num(r.typical) ? r.typical : null, max: num(r.max) ? r.max : null } : null });
  }
  return out;
}

/** Small stable digest (FNV-1a, 32 bit) of a JSON-serialisable value. Not a security hash. */
export function digestOf(value: unknown): string {
  const text = JSON.stringify(value);
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, '0');
}

/** Estimates the report shows: everything the user has not dismissed (an estimate is automatic; the user's own value always wins). */
export const activeEstimates = (list: readonly EngineEstimate[] | undefined) => (list ?? []).filter((e) => e.status !== 'dismissed');
