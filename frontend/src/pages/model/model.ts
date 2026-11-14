// SPDX-License-Identifier: Apache-2.0
// Pagina "Modello e validazione": tipi delle risposte di /api/raven/{validation,model,parameters} e funzioni pure di
// mappatura (stato peggiore per stadio, filtri della tabella, esportazione JSON). Nessun numero è scritto qui.

export const STATUSES = ['verified', 'plausibility_only', 'not_validated', 'unknown'] as const;
export type Status = (typeof STATUSES)[number];
export const STAGES = ['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'] as const;
export type StageId = (typeof STAGES)[number];

export interface Entry {
  id: string;
  stage: string;
  status: Status;
  what: string;
  against: string;
  residual: string;
  not_validated: string;
  evidence: string[];
  phrase: string;
}
export interface ParamGroup {
  id: string;
  stage: string;
  group: string;
  tag: 'V' | 'D' | 'I';
  status: Status;
  meaning: string;
  n_parameters: number;
  phrase: string;
}
export interface Validation {
  model_version?: string;
  statuses: Status[];
  note: string;
  stages: Entry[];
  parameter_groups: ParamGroup[];
}
export interface ModelInfo {
  model_version: string;
  registry_sha256: string;
  stages: { stage: string; reads: string[] }[];
  limits: Record<string, number>;
  declared_limits: string[];
  validation: Validation;
}
export interface Param {
  key: string;
  stage: string;
  group: string;
  tag: 'V' | 'D' | 'I';
  default: number | string | boolean | null;
  unit: string;
  min: number | null;
  max: number | null;
  source: string;
  note: string;
}
export interface Parameters {
  model_version: string;
  registry_sha256: string;
  tags: Record<string, string>;
  parameters: Param[];
}

/** Segno testuale e icona per stato (colore, testo e icona: mai il solo colore). */
export const STATUS_ICON: Record<Status, string> = {
  verified: '✓',
  plausibility_only: '≈',
  not_validated: '✕',
  unknown: '?',
};
/** Semaforo del Learning: verde, giallo, rosso, grigio. */
export const STATUS_LIGHT: Record<Status, 'green' | 'amber' | 'red' | 'grey'> = {
  verified: 'green',
  plausibility_only: 'amber',
  not_validated: 'red',
  unknown: 'grey',
};

const RANK: Record<Status, number> = { unknown: 0, not_validated: 1, plausibility_only: 2, verified: 3 };

export function isStatus(s: unknown): s is Status {
  return typeof s === 'string' && (STATUSES as readonly string[]).includes(s);
}

/** Stato peggiore tra le voci (nessuna voce = ignoto). */
export function worstStatus(entries: readonly { status: unknown }[]): Status {
  let w: Status = 'verified';
  if (!entries.length) return 'unknown';
  for (const e of entries) {
    if (!isStatus(e.status)) return 'unknown';
    if (RANK[e.status] < RANK[w]) w = e.status;
  }
  return w;
}

export function entriesFor(v: Validation, stage: string): Entry[] {
  return v.stages.filter((e) => e.stage === stage);
}

/** Conteggio delle voci per stato (per il semaforo e per il test di parità con l'API). */
export function countByStatus(v: Validation): Record<Status, number> {
  const c: Record<Status, number> = { verified: 0, plausibility_only: 0, not_validated: 0, unknown: 0 };
  for (const e of v.stages) if (isStatus(e.status)) c[e.status]++;
  return c;
}

export interface ParamFilter {
  stage: string; // '' = tutti
  tag: string; // '' = tutti
  text: string;
}

export function filterParams(rows: readonly Param[], f: ParamFilter): Param[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter(
    (p) =>
      (!f.stage || p.stage === f.stage) &&
      (!f.tag || p.tag === f.tag) &&
      (!q || p.key.toLowerCase().includes(q) || p.source.toLowerCase().includes(q)),
  );
}

export function rangeText(p: Pick<Param, 'min' | 'max'>): string {
  if (p.min == null && p.max == null) return '—';
  return `${p.min ?? '…'} – ${p.max ?? '…'}`;
}

/** JSON della matrice di validazione esattamente come l'API la restituisce, con la versione del modello. */
export function exportMatrix(v: Validation, modelVersion: string): string {
  return JSON.stringify({ model_version: modelVersion, ...v }, null, 2);
}

