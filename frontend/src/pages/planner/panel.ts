// SPDX-License-Identifier: Apache-2.0
import { paramError, type ParamRow } from '../compare/lunar';

export interface PanelValues {
  array_area_m2: number | null;
  cell_efficiency: number | null;
  orientation: string;
  tilt_deg: number | null;
  tilt_azimuth_deg: number | null;
}

const keys = ['array_area_m2', 'cell_efficiency', 'orientation', 'tilt_deg', 'tilt_azimuth_deg'] as const;

export function panelDefaults(rows: readonly ParamRow[]): PanelValues | null {
  if (keys.some((key) => {
    const row = rows.find((item) => item.key === key && item.group === 'energy');
    return !row || (key === 'orientation' ? !row.allowed?.length : typeof row.min !== 'number' || typeof row.max !== 'number');
  })) return null;
  const values = Object.fromEntries(rows.filter((row) => row.group === 'energy').map((row) => [row.key, row.value]));
  return readPanel(values, rows);
}

/** Validate against the backend's current bounds, including persisted configurations. */
export function readPanel(value: unknown, rows: readonly ParamRow[]): PanelValues | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  if (typeof v.array_area_m2 !== 'number' || typeof v.cell_efficiency !== 'number' ||
      typeof v.orientation !== 'string' || typeof v.tilt_deg !== 'number' || typeof v.tilt_azimuth_deg !== 'number') return null;
  const panel: PanelValues = {
    array_area_m2: v.array_area_m2, cell_efficiency: v.cell_efficiency, orientation: v.orientation,
    tilt_deg: v.tilt_deg, tilt_azimuth_deg: v.tilt_azimuth_deg,
  };
  return panelOverrides(panel, rows) === null ? null : panel;
}

export function panelOverrides(panel: PanelValues, rows: readonly ParamRow[]): Record<string, number | string> | null {
  const overrides: Record<string, number | string> = {};
  for (const key of keys) {
    if (panel.orientation !== 'tilted' && (key === 'tilt_deg' || key === 'tilt_azimuth_deg')) continue;
    const row = rows.find((item) => item.key === key && item.group === 'energy');
    const value = panel[key];
    if (!row || paramError(row, value)) return null;
    if (value !== row.value && value !== null) overrides[key] = value;
  }
  return overrides;
}
