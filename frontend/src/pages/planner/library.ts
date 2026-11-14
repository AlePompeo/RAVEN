// SPDX-License-Identifier: Apache-2.0
import { BITRATES } from '../../shell/scenario';
import { customSites } from '../../shell/customSites';
import { inRange } from '../viewer/simTime';
import type { ParamRow } from '../compare/lunar';
import { readObjectives } from './objectives';
import { readPanel } from './panel';
import { readSetup } from './setup';
import { readSavedPlanner, type SavedPlanner } from './timeline';

export const LIBRARY_KEY = 'hb.mission-planner.library.v1';
export const LIBRARY_LIMIT = 20;

export interface SavedRadio {
  station: 'dsn34' | 'dsn18';
  gain: number;
  rate: number;
  k: number;
  mast: number;
}
export interface LibraryEntry {
  id: string;
  name: string;
  savedAt: string;
  config: unknown;
}
export interface RestoredMission {
  planner: SavedPlanner;
  radio: SavedRadio;
  selectedTime: number | null;
}
export type LibraryRead = { ok: true; entries: LibraryEntry[] } | { ok: false };

export function readLibrary(storage: Pick<Storage, 'getItem'>): LibraryRead {
  try {
    const raw = storage.getItem(LIBRARY_KEY);
    if (raw === null) return { ok: true, entries: [] };
    if (raw.length > 200_000) return { ok: false };
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object') return { ok: false };
    const doc = value as Record<string, unknown>;
    if (doc.version !== 1 || !Array.isArray(doc.entries) || doc.entries.length > LIBRARY_LIMIT) return { ok: false };
    const entries: LibraryEntry[] = [];
    for (const item of doc.entries) {
      if (!item || typeof item !== 'object') return { ok: false };
      const e = item as Record<string, unknown>;
      if (typeof e.id !== 'string' || !/^\d{1,20}$/.test(e.id) ||
          typeof e.name !== 'string' || e.name.length > 80 ||
          typeof e.savedAt !== 'string' || !Number.isFinite(Date.parse(e.savedAt)) ||
          !e.config || typeof e.config !== 'object' || entries.some((existing) => existing.id === e.id)) return { ok: false };
      entries.push({ id: e.id, name: e.name, savedAt: e.savedAt, config: e.config });
    }
    return { ok: true, entries };
  } catch {
    return { ok: false };
  }
}

export function writeLibrary(storage: Pick<Storage, 'setItem'>, entries: readonly LibraryEntry[]): boolean {
  try {
    const raw = JSON.stringify({ version: 1, entries });
    if (raw.length > 200_000) return false;
    storage.setItem(LIBRARY_KEY, raw);
    return true;
  } catch {
    return false;
  }
}

export function restoreMission(config: unknown, validSites: readonly string[], parameters: readonly ParamRow[], definitions = customSites.get()): RestoredMission | null {
  if (!config || typeof config !== 'object') return null;
  const c = config as Record<string, unknown>;
  if (!c.planner || typeof c.planner !== 'object') return null;
  const planner = readSavedPlanner(JSON.stringify(c.planner), validSites, definitions);
  if (!planner || !readSetup(planner.setup) || !readPanel(planner.panel, parameters) || !readObjectives(planner.objectives)) return null;
  if (!c.radio || typeof c.radio !== 'object') return null;
  const r = c.radio as Record<string, unknown>;
  if ((r.station !== 'dsn34' && r.station !== 'dsn18') ||
      typeof r.gain !== 'number' || !Number.isFinite(r.gain) || r.gain < -10 || r.gain > 45 ||
      typeof r.rate !== 'number' || !BITRATES.includes(r.rate) ||
      typeof r.k !== 'number' || !Number.isFinite(r.k) || r.k < 0 || r.k > 6 ||
      typeof r.mast !== 'number' || !Number.isFinite(r.mast) || r.mast < 0.1 || r.mast > 100 ||
      r.mast !== planner.mast) return null;
  if (c.selectedTime !== null && (typeof c.selectedTime !== 'number' ||
      !Number.isFinite(c.selectedTime) || !inRange(c.selectedTime * 1000))) return null;
  return {
    planner,
    radio: { station: r.station, gain: r.gain, rate: r.rate, k: r.k, mast: r.mast },
    selectedTime: typeof c.selectedTime === 'number' ? c.selectedTime : null,
  };
}
