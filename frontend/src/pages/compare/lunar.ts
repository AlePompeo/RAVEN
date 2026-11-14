// SPDX-License-Identifier: Apache-2.0
// Shared Planner input helpers and compatibility types; all calculations use RAVEN.

export type ParamStatus = 'V' | 'D' | 'I';

export interface LunarSite {
  id: string;
  name: string;
  lat_deg: number;
  lon_deg_east: number;
  kind: string;
  coordinate_basis: string;
  verified: boolean;
  source_url: string;
}

export interface ParamRow {
  key: string;
  group: 'link' | 'energy' | 'window';
  value: number | string;
  unit: string;
  min?: number;
  max?: number;
  allowed?: string[];
  status: ParamStatus;
  source: string;
  note: string;
}

export interface Defaults {
  parameters: ParamRow[];
  limits: {
    days_max: number; step_min_min: number; max_total_points: number; timeline_series_per_site?: number;
    terrain_solar_max_steps_per_site?: number;
  };
  disclaimer: string;
}

export interface SiteMetrics {
  useful_hours: number;
  useful_fraction: number;
  longest_gap_h: number;
  n_windows: number;
  mean_margin_db: number | null;
  min_margin_db: number | null;
  sun_fraction: number;
  earth_fraction: number;
  ground_station_fraction: number;
  link_fraction: number;
  power_available_fraction: number;
  energy: { min_soc: number; survived: boolean; harvested_wh: number | null; unmet_wh: number | null; longest_dark_h: number };
}

export interface AnalyzeRequest {
  site_ids: string[];
  custom_sites?: import('../../shell/customSites').CustomSiteDef[];
  start_utc: string;
  days: number;
  step_min: number;
  overrides: Record<string, number | string>;
}

export function paramError(row: ParamRow, v: number | string | null | undefined): string | null {
  if (row.allowed) return typeof v === 'string' && row.allowed.includes(v) ? null : 'Valore non ammesso.';
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'Inserisci un numero.';
  if (row.min !== undefined && v < row.min) return `Minimo ${row.min}.`;
  if (row.max !== undefined && v > row.max) return `Massimo ${row.max}.`;
  return null;
}

export function toStartUtc(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local);
  if (!m) return null;
  const [y, mo, d, h, mi] = [1, 2, 3, 4, 5].map((i) => Number(m[i]));
  const seconds = Number(m[6] ?? '0');
  const t = new Date(Date.UTC(y!, mo! - 1, d!, h!, mi!));
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo! - 1 || t.getUTCDate() !== d || h! > 23 || mi! > 59 || seconds > 59) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] ?? '00'}Z`;
}

export type ApiFailure = 'unavailable' | 'busy' | 'invalid' | 'server' | 'network';

export function downloadText(name: string, mime: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000); // a slow machine may still be saving the file after one second
}
