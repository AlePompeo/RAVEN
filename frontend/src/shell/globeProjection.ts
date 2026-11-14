// SPDX-License-Identifier: Apache-2.0
// Proiezione ortografica del globo lunare (vista da fuori): da punto dello schermo a latitudine/longitudine est e
// ritorno. Il globo e' disegnato dalla mappa equirettangolare (nord in alto, longitudine est a destra): non e' un DEM.

const D2R = Math.PI / 180;
const R2D = 180 / Math.PI;

export interface View { lat0: number; lon0: number }

/** (x, y) in [-1, 1] (x a destra, y in alto) -> lat/lon est del punto sul globo; null fuori dal disco. */
export function unproject(x: number, y: number, v: View): { lat: number; lon: number } | null {
  const rho = Math.hypot(x, y);
  if (!Number.isFinite(rho) || rho > 1) return null;
  const phi0 = v.lat0 * D2R;
  if (rho === 0) return { lat: v.lat0, lon: wrap(v.lon0) };
  const c = Math.asin(rho);
  const sinPhi = Math.cos(c) * Math.sin(phi0) + (y * Math.sin(c) * Math.cos(phi0)) / rho;
  const lat = Math.asin(Math.max(-1, Math.min(1, sinPhi))) * R2D;
  const lon = v.lon0 + Math.atan2(x * Math.sin(c), rho * Math.cos(phi0) * Math.cos(c) - y * Math.sin(phi0) * Math.sin(c)) * R2D;
  return { lat, lon: wrap(lon) };
}

/** lat/lon est -> (x, y) sul disco; null se il punto e' sull'emisfero nascosto. */
export function project(lat: number, lon: number, v: View): { x: number; y: number } | null {
  const phi = lat * D2R;
  const phi0 = v.lat0 * D2R;
  const dl = (lon - v.lon0) * D2R;
  const visible = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(dl);
  if (visible < 0) return null;
  return {
    x: Math.cos(phi) * Math.sin(dl),
    y: Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * Math.cos(phi) * Math.cos(dl),
  };
}

/** Longitudine in (-180, 180]. */
export function wrap(lon: number): number {
  const w = ((((lon + 180) % 360) + 360) % 360) - 180;
  return w === -180 ? 180 : w;
}

export const clampLat = (lat: number): number => Math.max(-90, Math.min(90, lat));
