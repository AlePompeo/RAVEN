// SPDX-License-Identifier: Apache-2.0
import type { AzEl } from '../contracts/telemetry';

export type BodyId = 'moon' | 'earth' | 'sun' | 'mars';
export const BODY_IDS: readonly BodyId[] = ['moon', 'earth', 'sun', 'mars'];

/** Disco del corpo in px CSS dentro il contenitore del renderer (stessa geometria per WebGL, 2D e marcatori). */
export interface DiskFrame {
  cx: number;
  cy: number;
  r: number;
}

/** Sovramappa RGBA: disco polare sud (quadrata, `limit` = latitudine a raggio 1) o tutta la Luna (equirettangolare, width x height). */
export interface OverlayRaster {
  pixels: Uint8ClampedArray;
  size: number;
  limit: number;
  width?: number;
  height?: number;
  projection?: 'disc' | 'equirectangular';
}

/** Stato della scena 3D (unità nel nome dei campi). */
export interface SceneState {
  yaw_deg: number;
  pitch_deg: number;
  autoRotate: boolean;
  /** Direzione della luce (azimut/elevazione nel riferimento della vista). */
  sun?: AzEl | undefined;
  /**
   * Direzione corpo -> Sole nello spazio-oggetto del corpo (assi del viewer, da /api/raven/sky/subsolar). Ha la
   * precedenza su `sun`: la stessa terna alimenta WebGL e Canvas 2D.
   */
  sunObj?: [number, number, number] | undefined;
  earth?: AzEl | undefined;
  /** Corpo mostrato (default: Luna). */
  body?: BodyId | undefined;
  /** Fattore di ingrandimento del disco (1 = predefinito). */
  zoom?: number | undefined;
  /** Sovramappa RGBA del disco polare sud (polo al centro, longitudine oraria dall'alto, raggio 1 a `limit` gradi), solo Luna. */
  overlay?: OverlayRaster | null | undefined;
  /** Disco imposto dalla pagina (marcatori DOM allineati); senza, il renderer centra il corpo. */
  frame?: DiskFrame | undefined;
}

export const DEFAULT_SCENE: SceneState = { yaw_deg: 0, pitch_deg: 15, autoRotate: false };
export const ZOOM_MIN = 0.6;
export const ZOOM_MAX = 2.4;

export function clampPitch(p: number): number {
  return Math.max(-80, Math.min(80, p));
}

export function clampZoom(z: number): number {
  return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
}

export function wrapYaw(y: number): number {
  return ((((y + 180) % 360) + 360) % 360) - 180;
}

export function isBodyId(v: unknown): v is BodyId {
  return typeof v === 'string' && (BODY_IDS as readonly string[]).includes(v);
}

/** Direzione unitaria (x=est, y=su, z=sud) da azimut (0=nord, orario) ed elevazione. */
export function azElToVector(a: AzEl): [number, number, number] {
  const az = (a.az_deg * Math.PI) / 180;
  const el = (a.el_deg * Math.PI) / 180;
  return [Math.cos(el) * Math.sin(az), Math.sin(el), -Math.cos(el) * Math.cos(az)];
}

/** Normalizza un vettore; `null` se non finito o nullo. */
export function normalizeVec(v: readonly number[]): [number, number, number] | null {
  if (v.length !== 3 || !v.every((c) => Number.isFinite(c))) return null;
  const n = Math.hypot(v[0]!, v[1]!, v[2]!);
  return n > 1e-9 ? [v[0]! / n, v[1]! / n, v[2]! / n] : null;
}

/** Versore corpo -> Sole del punto subsolare (lat, lon Est) nello spazio-oggetto: stessa mappa di `latLonToBody`. */
export function subsolarToLightObj(latDeg: number, lonDeg: number): [number, number, number] {
  return latLonToBody(latDeg, lonDeg);
}

/** Luce nel riferimento della vista: R · v (R = righe di `rotationRows`). */
export function objToView(rows: readonly number[], v: readonly number[]): [number, number, number] {
  const r = rows as number[];
  return [
    r[0]! * v[0]! + r[1]! * v[1]! + r[2]! * v[2]!,
    r[3]! * v[0]! + r[4]! * v[1]! + r[5]! * v[2]!,
    r[6]! * v[0]! + r[7]! * v[1]! + r[8]! * v[2]!,
  ];
}

/** R = Rx(pitch)·Ry(yaw) (righe), come la rotazione Euler XYZ del corpo in threeViewport. */
export function rotationRows(yawDeg: number, pitchDeg: number): number[] {
  const y = (yawDeg * Math.PI) / 180;
  const p = (pitchDeg * Math.PI) / 180;
  const cy = Math.cos(y);
  const sy = Math.sin(y);
  const cp = Math.cos(p);
  const sp = Math.sin(p);
  return [cy, 0, sy, sp * sy, cp, -sp * cy, -cp * sy, sp, cp * cy];
}

/** Punto della superficie (gradi, longitudine Est positiva) nel riferimento del corpo; lon 0 verso +z. */
export function latLonToBody(latDeg: number, lonDeg: number): [number, number, number] {
  const la = (latDeg * Math.PI) / 180;
  const lo = (lonDeg * Math.PI) / 180;
  return [Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)];
}

/** Proiezione ortografica di un punto della superficie; `visible` falso se è sull'emisfero nascosto. */
export function projectLatLon(
  latDeg: number,
  lonDeg: number,
  s: Pick<SceneState, 'yaw_deg' | 'pitch_deg'>,
  f: DiskFrame,
): { x: number; y: number; z: number; visible: boolean } {
  const m = rotationRows(s.yaw_deg, s.pitch_deg);
  const [bx, by, bz] = latLonToBody(latDeg, lonDeg);
  const x = m[0]! * bx + m[1]! * by + m[2]! * bz;
  const y = m[3]! * bx + m[4]! * by + m[5]! * bz;
  const z = m[6]! * bx + m[7]! * by + m[8]! * bz;
  return { x: f.cx + x * f.r, y: f.cy - y * f.r, z, visible: z > 0.08 };
}

/** Rotazione (yaw, pitch) che porta il punto lat/lon al centro del disco. */
export function centerOn(latDeg: number, lonDeg: number): { yaw_deg: number; pitch_deg: number } {
  return { yaw_deg: wrapYaw(-lonDeg), pitch_deg: clampPitch(latDeg) };
}

/** Geometria predefinita del disco: centrato, raggio 36% del lato minore per lo zoom. */
export function defaultFrame(w: number, h: number, zoom = 1): DiskFrame {
  return { cx: w / 2, cy: h / 2, r: Math.max(20, Math.min(w, h) * 0.36 * clampZoom(zoom)) };
}

export function isSceneState(s: unknown): s is SceneState {
  if (typeof s !== 'object' || s === null) return false;
  const o = s as Record<string, unknown>;
  return (
    typeof o.yaw_deg === 'number' &&
    Number.isFinite(o.yaw_deg) &&
    typeof o.pitch_deg === 'number' &&
    Number.isFinite(o.pitch_deg) &&
    typeof o.autoRotate === 'boolean' &&
    (o.body === undefined || isBodyId(o.body))
  );
}

function fmt(label: string, a: AzEl | undefined): string {
  return a
    ? `${label}: azimut ${a.az_deg.toFixed(0)}°, elevazione ${a.el_deg.toFixed(0)}°${a.el_deg < 0 ? ' (sotto l’orizzonte)' : ''}.`
    : `${label}: dato non disponibile.`;
}

const BODY_NAME: Record<BodyId, string> = { moon: 'Luna', earth: 'Terra', sun: 'Sole', mars: 'Marte' };

/** Descrizione testuale equivalente alla scena 3D. */
export function describeScene(s: SceneState, motionAllowed: boolean): string {
  const rot = s.autoRotate && motionAllowed ? 'Rotazione automatica attiva.' : 'Rotazione automatica ferma.';
  const body = s.body ?? 'moon';
  if (body === 'sun') {
    return [
      'Sole: immagine SDO AIA a 30,4 nanometri (ultravioletto estremo, falsi colori) del 1 ottobre 2026.',
      'È una sola osservazione: la rotazione sposta soltanto il cielo stellato.',
      rot,
    ].join(' ');
  }
  const parts = [
    `${BODY_NAME[body]} vista con rotazione orizzontale di ${s.yaw_deg.toFixed(0)}° e inclinazione di ${s.pitch_deg.toFixed(0)}°.`,
    fmt('Sole', s.sun),
  ];
  if (body === 'moon') parts.push(fmt('Terra', s.earth));
  parts.push(rot);
  return parts.join(' ');
}
