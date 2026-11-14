// SPDX-License-Identifier: Apache-2.0
import type { MessageKey } from '../../i18n/i18n.svelte';
import type { ParamRow } from '../compare/lunar';
import { readRun, type JourneyRun } from './journey';

export const HISTORY_KEY = 'hb.planner-journey.history.v1';
export const HISTORY_LIMIT = 8;
export const HISTORY_MAX_CHARS = 2_000_000;
export interface HistoryEntry { id: string; name: string; savedAt: string; run: unknown }
type Read = { ok: true; entries: HistoryEntry[]; exists: boolean } | { ok: false; error: MessageKey };
type Write = { ok: true; entries: HistoryEntry[] } | { ok: false; error: MessageKey };
type HistoryStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function readHistory(storage: Pick<Storage, 'getItem'>): Read {
  try {
    const raw = storage.getItem(HISTORY_KEY);
    if (raw === null) return { ok: true, entries: [], exists: false };
    if (raw.length > HISTORY_MAX_CHARS) return { ok: false, error: 'history.readError' };
    const doc: unknown = JSON.parse(raw);
    if (!doc || typeof doc !== 'object' || !('version' in doc) || doc.version !== 1 ||
        !('entries' in doc) || !Array.isArray(doc.entries) || doc.entries.length > HISTORY_LIMIT) return { ok: false, error: 'history.readError' };
    const entries: HistoryEntry[] = [];
    for (const e of doc.entries) {
      if (!e || typeof e !== 'object' || typeof e.id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(e.id) ||
          typeof e.name !== 'string' || e.name.length > 80 || typeof e.savedAt !== 'string' || !Number.isFinite(Date.parse(e.savedAt)) ||
          !e.run || typeof e.run !== 'object' || entries.some((p) => p.id === e.id)) return { ok: false, error: 'history.readError' };
      entries.push({ id: e.id, name: e.name, savedAt: e.savedAt, run: e.run });
    }
    return { ok: true, entries, exists: true };
  } catch { return { ok: false, error: 'history.readError' }; }
}

export function writeHistory(storage: Pick<Storage, 'setItem'>, entries: readonly HistoryEntry[]): Write {
  if (entries.length > HISTORY_LIMIT) return { ok: false, error: 'history.full' };
  const raw = JSON.stringify({ version: 1, entries });
  if (raw.length > HISTORY_MAX_CHARS) return { ok: false, error: 'history.tooLarge' };
  try {
    storage.setItem(HISTORY_KEY, raw);
    return { ok: true, entries: [...entries] };
  } catch { return { ok: false, error: 'history.writeError' }; }
}

export function archiveRun(storage: HistoryStorage, run: JourneyRun, rows: readonly ParamRow[], ids: readonly string[], registry: string, version: string): Write {
  const raw = JSON.stringify(run);
  if (!readRun(raw, rows, ids, registry, version)) return { ok: false, error: 'history.invalid' };
  const existing = readHistory(storage);
  if (!existing.ok) return existing;
  if (existing.entries.some((e) => JSON.stringify(e.run) === raw)) return { ok: true, entries: existing.entries };
  if (existing.entries.length >= HISTORY_LIMIT) return { ok: false, error: 'history.full' };
  return writeHistory(storage, [{ id: crypto.randomUUID(), name: run.config.name, savedAt: run.createdAt, run }, ...existing.entries]);
}
