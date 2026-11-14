// SPDX-License-Identifier: Apache-2.0
// Compatibility types consumed by the RAVEN Planner adapters; no legacy calculation or API client.
import type { ParamRow, Series } from '../grazinglink/grazing';

export const MAX_STEPS_PER_SITE = 1500;

export const MAX_TOTAL_SAMPLES = 6000;

export const UNCOVERED_STATE = 'non confrontabile con RAVEN (fuori copertura DEM)';

export interface SiteMeta {
  id: string;
  name: string;
  lat_deg: number;
  lon_deg_east: number;
}

export interface TerrainFlags {
  source: string;
  product_id: string | null;
  synthetic: boolean;
  radius_resolved: boolean;
  radius_resolved_fraction: number;
  correction_status: string;
  correction_label: string;
  multipath_status: string;
  blocked_fraction: number;
}

export interface AnalysedRow {
  site: SiteMeta;
  state: string;
  covered: true;
  rank: number | null;
  geometric_hours: number;
  real_hours: number;
  transition_hours: number;
  total_hours: number;
  margin_min_db: number | null;
  margin_median_db: number | null;
  rate_bps: { min: number | null; median: number | null; max: number | null; mean_declared: number; declared_fraction: number };
  compensator: { k: number; outage_pct: number; delivered_bits: number; scheduled_bits: number; relative_data: number | null; declared_steps: number };
  earth_el_min_deg: number | null;
  earth_el_max_deg: number | null;
  terrain: TerrainFlags;
  series: { time_unix: number[]; margin_db: Series; earth_el_deg: Series; chosen_rate_bps: Series; geometric_visible: Series; step_min: number };
  window_samples?: {
    time_unix: number[];
    geometric_visible: boolean[];
    link_ok: boolean[];
    margin_db: Series;
    chosen_rate_bps: number[];
  };
}

export interface UncoveredRow {
  site: SiteMeta;
  state: string;
  covered: false;
  rank: null;
}

export type SiteRow = AnalysedRow | UncoveredRow;

export interface CompareResult {
  model_version?: string;
  registry_sha256?: string;
  label: string;
  window: { start_utc: string; days: number; step_min: number; n_steps: number };
  sites: SiteRow[];
  ranking: string[];
  ranking_rule: string;
  ranking_columns: string[];
  uncovered_state: string;
  rate_bps: number;
  station: string;
  k: number;
  parameters: (ParamRow & { key: string })[];
  disclaimer: string;
}
