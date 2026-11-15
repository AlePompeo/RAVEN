// SPDX-License-Identifier: Apache-2.0
import type { MessageKey } from '../../i18n/i18n.svelte';
import type { Params } from '../../i18n/core';

export interface UiError {
  key: MessageKey;
  params?: Params;
}

export interface InputRow {
  name: string;
  value: string;
}

export interface FieldError {
  index: number;
  field: 'name' | 'value';
  message: UiError;
}
export type BuildResult =
  | { ok: true; inputs: Record<string, number> }
  | { ok: false; error: UiError; errors: FieldError[] };
export type RunResult = { ok: true; outputs: Record<string, number> } | { ok: false; error: UiError };

/** Nomi che alterano il prototipo: rifiutati esplicitamente. Gli altri (es. "toString") sono ammessi. */
const RESERVED = new Set(['__proto__']);

/** Converte le righe del form in input numerici finiti; i nomi devono essere unici e non vuoti. */
export function buildInputs(rows: InputRow[]): BuildResult {
  if (rows.length === 0) return { ok: false, error: { key: 'sims.errorNoInputs' }, errors: [] };
  const inputs: Record<string, number> = {};
  const errors: FieldError[] = [];
  const seen = new Set<string>();
  rows.forEach((r, index) => {
    const name = r.name.trim();
    if (!name) errors.push({ index, field: 'name', message: { key: 'sims.errorNameRequired' } });
    else if (RESERVED.has(name)) errors.push({ index, field: 'name', message: { key: 'sims.errorNameReserved', params: { name } } });
    else if (seen.has(name)) errors.push({ index, field: 'name', message: { key: 'sims.errorNameDuplicate', params: { name } } });
    else seen.add(name);
    const text = r.value.trim();
    const n = text === '' ? NaN : Number(text);
    if (!Number.isFinite(n)) errors.push({ index, field: 'value', message: { key: 'sims.errorNumber' } });
    else if (name && !errors.some((e) => e.index === index)) Object.defineProperty(inputs, name, { value: n, enumerable: true, writable: true, configurable: true });
  });
  if (errors.length > 0) return { ok: false, error: { key: 'sims.errorFields' }, errors };
  return { ok: true, inputs };
}

export async function listSimulations(fetchFn: typeof fetch): Promise<string[]> {
  const res = await fetchFn('/api/plugins');
  if (!res.ok) throw new Error(`elenco non disponibile (${res.status})`);
  const data = (await res.json()) as { plugins?: { id: string; kind: string }[] };
  return (data.plugins ?? []).filter((p) => p.kind === 'simulation').map((p) => p.id);
}

const STATUS_TEXT: Record<number, MessageKey> = {
  404: 'sims.errorNotFound',
  422: 'sims.errorInvalidInputs',
  502: 'sims.errorFailed',
  504: 'sims.errorTimeout',
};

export async function runSimulation(
  fetchFn: typeof fetch,
  id: string,
  inputs: Record<string, number>,
  signal?: AbortSignal,
): Promise<RunResult> {
  try {
    const init: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inputs }),
    };
    if (signal) init.signal = signal;
    const res = await fetchFn(`/api/simulations/${encodeURIComponent(id)}/run`, init);
    if (!res.ok) return { ok: false, error: { key: STATUS_TEXT[res.status] ?? 'sims.errorServer', params: { status: res.status } } };
    const data = (await res.json()) as { outputs?: Record<string, unknown> };
    const outputs: Record<string, number> = {};
    for (const [k, v] of Object.entries(data.outputs ?? {})) {
      if (typeof v !== 'number' || !Number.isFinite(v)) return { ok: false, error: { key: 'sims.errorResponse' } };
      outputs[k] = v;
    }
    return { ok: true, outputs };
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return { ok: false, error: { key: 'sims.errorCancelled' } };
    return { ok: false, error: { key: 'sims.errorNetwork' } };
  }
}
