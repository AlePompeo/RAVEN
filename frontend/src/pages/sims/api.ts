// SPDX-License-Identifier: Apache-2.0
export interface InputRow {
  name: string;
  value: string;
}

export interface FieldError {
  index: number;
  field: 'name' | 'value';
  message: string;
}
export type BuildResult =
  | { ok: true; inputs: Record<string, number> }
  | { ok: false; error: string; errors: FieldError[] };
export type RunResult = { ok: true; outputs: Record<string, number> } | { ok: false; error: string };

/** Nomi che alterano il prototipo: rifiutati esplicitamente. Gli altri (es. "toString") sono ammessi. */
const RESERVED = new Set(['__proto__']);

/** Converte le righe del form in input numerici finiti; i nomi devono essere unici e non vuoti. */
export function buildInputs(rows: InputRow[]): BuildResult {
  if (rows.length === 0) return { ok: false, error: 'Aggiungi almeno un ingresso.', errors: [] };
  const inputs: Record<string, number> = {};
  const errors: FieldError[] = [];
  const seen = new Set<string>();
  rows.forEach((r, index) => {
    const name = r.name.trim();
    if (!name) errors.push({ index, field: 'name', message: 'Il nome e obbligatorio.' });
    else if (RESERVED.has(name)) errors.push({ index, field: 'name', message: `Il nome «${name}» non e ammesso.` });
    else if (seen.has(name)) errors.push({ index, field: 'name', message: `Il nome «${name}» e ripetuto.` });
    else seen.add(name);
    const text = r.value.trim();
    const n = text === '' ? NaN : Number(text);
    if (!Number.isFinite(n)) errors.push({ index, field: 'value', message: 'Inserisci un numero finito.' });
    else if (name && !errors.some((e) => e.index === index)) Object.defineProperty(inputs, name, { value: n, enumerable: true, writable: true, configurable: true });
  });
  if (errors.length > 0) return { ok: false, error: 'Correggi i campi evidenziati.', errors };
  return { ok: true, inputs };
}

export async function listSimulations(fetchFn: typeof fetch): Promise<string[]> {
  const res = await fetchFn('/api/plugins');
  if (!res.ok) throw new Error(`elenco non disponibile (${res.status})`);
  const data = (await res.json()) as { plugins?: { id: string; kind: string }[] };
  return (data.plugins ?? []).filter((p) => p.kind === 'simulation').map((p) => p.id);
}

const STATUS_TEXT: Record<number, string> = {
  404: 'Simulazione non trovata.',
  422: 'Ingressi non validi.',
  502: 'Simulazione fallita.',
  504: 'Simulazione oltre il tempo massimo.',
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
    if (!res.ok) return { ok: false, error: STATUS_TEXT[res.status] ?? `Errore del server (${res.status}).` };
    const data = (await res.json()) as { outputs?: Record<string, unknown> };
    const outputs: Record<string, number> = {};
    for (const [k, v] of Object.entries(data.outputs ?? {})) {
      if (typeof v !== 'number' || !Number.isFinite(v)) return { ok: false, error: 'Risposta non valida dal server.' };
      outputs[k] = v;
    }
    return { ok: true, outputs };
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return { ok: false, error: 'Richiesta annullata.' };
    return { ok: false, error: 'Impossibile contattare il server.' };
  }
}
