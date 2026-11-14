// SPDX-License-Identifier: Apache-2.0
// Client of the automatic site search: parse a prompt into a brief (rules), start a search job, poll it. Plain fetch, abortable, no retries
// that could start a second job.
import type { RavenOverlay } from '../ravenApi';

export interface Brief {
  start_utc: string | null; days: number | null; priority: 'sun' | 'earth' | 'radio' | 'balanced' | null;
  min_sun_percent: number | null; min_rf_percent: number | null; rate_bps: number | null;
  mission_class: string | null; mass_kg: number | null; k: number | null;
  lat_max_deg: number | null; lat_min_deg: number | null; max_slope_deg: number | null;
  min_distance_km: number | null; reference_site: string | null;
}
export interface Parsed {
  brief: Brief; found: string[]; unsupported: string[]; unresolved: string[]; rejected: string[]; level: string;
  model: string | null; filled_by_model: string[]; model_error: string | null; model_available: boolean | null;
}
export interface Proposal {
  rank: number; lat_deg: number; lon_deg_east: number; terrain: string; meets_objectives: boolean | null; name?: string | null; on_front?: boolean;
  core: { useful_fraction: number; sun_fraction: number; rf_fraction: number; useful_hours?: number; min_soc?: number };
  surrogate: Record<string, { mean: number | null; half_width: number | null }>;
  uncertainty: { samples: number; p_meet: number | null; p_low: number | null; p_high: number | null; drivers: { parameter: string; correlation: number }[] } | null;
}
export interface FinderResult {
  proposals: Proposal[]; evaluated: number; not_comparable: number; rounds: number; stop: string; interval: string;
  suitability: RavenOverlay | null; limits: string[]; tag: string; region?: 'polar' | 'catalogue'; order?: string[];
  pareto?: { name: string | null; lat_deg: number; lon_deg_east: number; core: Proposal['core']; meets_objectives: boolean | null }[];
  uncertainty_note: string | null; parameter_spreads: { group: string; name: string; kind: string; width: number; why: string }[];
}
export interface JobState { job_id: string; state: 'running' | 'done' | 'failed'; evaluated: number; budget: number; elapsed_s: number; result?: FinderResult; error?: string }
export interface Summary {
  facts: { best: { label: string } } | null; text: string | null; text_source: 'template' | 'model' | 'none'; model: string | null; model_note: string | null;
}
export interface LlmStatus { installed: boolean; running: boolean; model: string | null; free_mb: number | null; min_free_mb: number; enough_memory: boolean }
export type Fail = { ok: false; status: number; error: string };

async function call<T>(url: string, init: RequestInit): Promise<{ ok: true; data: T } | Fail> {
  try {
    const r = await fetch(url, init);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) return { ok: false, status: r.status, error: String((body as { error?: string }).error ?? r.status) };
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, status: 0, error: 'network' };
  }
}
const post = (body: unknown, signal?: AbortSignal) =>
  ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), ...(signal ? { signal } : {}) });

export const finder = {
  parse: (text: string, signal?: AbortSignal, opts: { use_model?: boolean; allow_external?: boolean } = {}) => call<Parsed>('/api/raven/brief/parse', post({ text, ...opts }, signal)),
  start: (brief: Partial<Brief>, budget: number, signal?: AbortSignal, opts: { region?: 'polar' | 'catalogue'; order?: string[] } = {}) => call<{ job_id: string }>('/api/raven/discover', post({ brief, budget, ...opts }, signal)),
  summary: (id: string, opts: { use_model: boolean; allow_external: boolean; lang: 'en' | 'it' }, signal?: AbortSignal) => call<Summary>(`/api/raven/discover/${encodeURIComponent(id)}/summary`, post(opts, signal)),
  llmStatus: (signal?: AbortSignal) => call<LlmStatus>('/api/raven/llm/status', signal ? { signal } : {}),
  poll: (id: string, signal?: AbortSignal) => call<JobState>(`/api/raven/discover/${encodeURIComponent(id)}`, signal ? { signal } : {}),
};
