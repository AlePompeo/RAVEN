// SPDX-License-Identifier: Apache-2.0
// Geometria della Scena lander, senza three.js e senza DOM (testabile): camera orbitale con preset, mesh del terreno
// con luce radente e ombre portate dal campo di quote, anello della zona di Fresnel, proiezione della sezione laterale.
// Riferimento del mondo (metri): x = e (avanti, verso la direzione della Terra), y = u (in alto), z = -n (a destra).
import { fresnelAt, type LanderScene, type SunLocal } from './model';

export const DEG = Math.PI / 180;
export const EARTH_DISTANCE_M = 40_000; // la Terra e' disegnata a una distanza finita ma con il diametro angolare vero

/* ------------------------------------------------------ camera ------------------------------------------------------ */

export type Preset = 'lander' | 'side' | 'top' | 'terrain';
export const PRESETS: readonly { id: Preset; label: string }[] = [
  { id: 'lander', label: 'Dal lander' },
  { id: 'side', label: 'Laterale' },
  { id: 'top', label: "Dall'alto" },
  { id: 'terrain', label: 'Terreno obliquo' },
];

export interface Cam {
  yaw: number; // 0 = guarda verso +x (la Terra); positivo verso +z (destra)
  pitch: number; // > 0 guarda in alto
  dist: number;
  target: [number, number, number];
  fovDeg: number;
}

export const MIN_DIST = 4;
export const MAX_DIST = 30_000;
export const PITCH_LIMIT = 89 * DEG;

export function presetCamera(preset: Preset, s: LanderScene | null, vExag = 1): Cam {
  const h = (s?.antenna.mastM ?? 2) * vExag;
  const reach = s ? Math.max(500, Math.min(10_000, s.ridge.d1M * 1.3)) : 3000;
  if (preset === 'lander') {
    return { yaw: 0.18, pitch: -0.32, dist: Math.max(9, h * 1.8), target: [-0.8, (h + 0.8) / 2, 0], fovDeg: 62 };
  }
  if (preset === 'side') return { yaw: -90 * DEG, pitch: -8 * DEG, dist: reach * 1.5, target: [reach * 0.4, h + reach * 0.03 * vExag, 0], fovDeg: 45 };
  if (preset === 'terrain') return { yaw: -50 * DEG, pitch: -38 * DEG, dist: Math.max(100, Math.min(10_000, (s?.terrain.patch?.sizeM ?? reach) * 1.05)), target: [0, h, 0], fovDeg: 50 };
  return { yaw: 0, pitch: -PITCH_LIMIT, dist: reach * 1.4, target: [reach * 0.35, 0, 0], fovDeg: 45 };
}

export function clampCam(c: Cam): void {
  c.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, c.pitch));
  c.dist = Math.max(MIN_DIST, Math.min(MAX_DIST, c.dist));
  c.yaw = ((((c.yaw + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
}
export function orbit(c: Cam, dYaw: number, dPitch: number): void {
  c.yaw += dYaw;
  c.pitch += dPitch;
  clampCam(c);
}
export function zoomBy(c: Cam, factor: number): void {
  if (factor > 0 && Number.isFinite(factor)) c.dist /= factor;
  clampCam(c);
}
/** Direzione dello sguardo (versore). */
export function viewDir(c: Cam): [number, number, number] {
  const cp = Math.cos(c.pitch);
  return [cp * Math.cos(c.yaw), Math.sin(c.pitch), cp * Math.sin(c.yaw)];
}
export function eyeOf(c: Cam): [number, number, number] {
  const d = viewDir(c);
  return [c.target[0] - d[0] * c.dist, c.target[1] - d[1] * c.dist, c.target[2] - d[2] * c.dist];
}

/* ------------------------------------------------ terreno e luce ------------------------------------------------ */

export interface TerrainMesh {
  n: number;
  positions: Float32Array; // n*n*3, mondo con esagerazione verticale
  colors: Float32Array; // n*n*3, luce gia' applicata
  indices: Uint32Array;
  shadowFraction: number;
  sunUp: boolean;
}

export const AMBIENT = 0.16;
const REGOLITH: [number, number, number] = [0.66, 0.63, 0.58];

export function terrainIndices(n: number): Uint32Array {
  const idx = new Uint32Array((n - 1) * (n - 1) * 6);
  let k = 0;
  for (let j = 0; j < n - 1; j++) {
    for (let i = 0; i < n - 1; i++) {
      const a = j * n + i;
      const b = a + 1;
      const c = a + n;
      const d = c + 1;
      // vista dall'alto con e avanti (x) e z a destra: la faccia guarda in alto
      idx[k++] = a;
      idx[k++] = b;
      idx[k++] = c;
      idx[k++] = b;
      idx[k++] = d;
      idx[k++] = c;
    }
  }
  return idx;
}

/** Illuminazione di Lambert con ombre portate (marcia dei raggi sul campo di quote). `sun.dir` in (e, n, u). */
export function shadeTerrain(heights: Float32Array, n: number, spacing: number, sun: SunLocal): { light: Float32Array; shadowFraction: number; sunUp: boolean } {
  const light = new Float32Array(n * n);
  const [le, ln, lu] = sun.dir;
  const sunUp = lu > 0.0005;
  if (!sunUp) {
    light.fill(0);
    return { light, shadowFraction: 1, sunUp };
  }
  const hz = Math.hypot(le, ln);
  const te = hz > 1e-9 ? le / hz : 0; // direzione orizzontale verso il Sole in celle (colonne = e, righe = n)
  const tn = hz > 1e-9 ? ln / hz : 0;
  const slope = lu / Math.max(hz, 1e-9); // quota del raggio per metro orizzontale
  // colonna i = e, riga j = n (da destra a sinistra, n crescente con j)
  const z = (i: number, j: number) => heights[j * n + i]!;
  let shadowed = 0;
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const z0 = z(i, j);
      const ie = i === 0 ? 0 : i === n - 1 ? n - 1 : i;
      const dzde = (z(Math.min(n - 1, ie + 1), j) - z(Math.max(0, ie - 1), j)) / (spacing * (Math.min(n - 1, ie + 1) - Math.max(0, ie - 1)));
      const dzdn = (z(i, Math.min(n - 1, j + 1)) - z(i, Math.max(0, j - 1))) / (spacing * (Math.min(n - 1, j + 1) - Math.max(0, j - 1)));
      const inv = 1 / Math.sqrt(dzde * dzde + dzdn * dzdn + 1);
      const diff = Math.max(0, (-dzde * le - dzdn * ln + lu) * inv);
      let lit = 1;
      if (hz > 1e-9) {
        for (let s = 1; s < n; s++) {
          const fi = i + te * s;
          const fj = j + tn * s;
          if (fi < 0 || fj < 0 || fi > n - 1 || fj > n - 1) break;
          const ray = z0 + slope * s * spacing;
          const i0 = Math.min(n - 2, Math.floor(fi));
          const j0 = Math.min(n - 2, Math.floor(fj));
          const a = fi - i0;
          const b = fj - j0;
          const zt = z(i0, j0) * (1 - a) * (1 - b) + z(i0 + 1, j0) * a * (1 - b) + z(i0, j0 + 1) * (1 - a) * b + z(i0 + 1, j0 + 1) * a * b;
          if (zt > ray) {
            lit = 0;
            break;
          }
        }
      }
      if (lit === 0) shadowed++;
      light[j * n + i] = diff * lit;
    }
  }
  return { light, shadowFraction: shadowed / (n * n), sunUp };
}

/** Mesh del terreno: posizioni (con esagerazione verticale) e colori (luce applicata). */
export function buildTerrain(s: LanderScene, vExag: number, sun: SunLocal): TerrainMesh | null {
  const p = s.terrain.patch;
  if (!p) return null;
  const originalN = p.n;
  const half = p.sizeM / 2;
  // Insert a small illustrative landing pad at the known origin; the DEM grid is too coarse for rover wheels.
  const pad = Math.min(3, p.spacingM * 0.2);
  const axes = Array.from({ length: originalN }, (_, i) => -half + i * p.spacingM);
  for (const x of [-pad, pad]) {
    if (!axes.some((a) => Math.abs(a - x) < 1e-8)) axes.push(x);
  }
  axes.sort((a, b) => a - b);
  const n = axes.length;
  const positions = new Float32Array(n * n * 3);
  const { light, shadowFraction, sunUp } = shadeTerrain(p.heights, originalN, p.spacingM, sun);
  const colors = new Float32Array(n * n * 3);
  const sample = (values: Float32Array, e: number, north: number): number => {
    const x = Math.max(0, Math.min(originalN - 1, (e + half) / p.spacingM));
    const y = Math.max(0, Math.min(originalN - 1, (north + half) / p.spacingM));
    const i = Math.min(originalN - 2, Math.floor(x));
    const j = Math.min(originalN - 2, Math.floor(y));
    const a = x - i;
    const b = y - j;
    const v00 = values[j * originalN + i]!;
    const v10 = values[j * originalN + i + 1]!;
    const v01 = values[(j + 1) * originalN + i]!;
    const v11 = values[(j + 1) * originalN + i + 1]!;
    return a + b <= 1
      ? v00 + a * (v10 - v00) + b * (v01 - v00)
      : v11 + (1 - a) * (v01 - v11) + (1 - b) * (v10 - v11);
  };
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const k = j * n + i;
      const e = axes[i]!;
      const north = axes[j]!;
      positions[k * 3] = e;
      positions[k * 3 + 1] = Math.abs(e) <= pad && Math.abs(north) <= pad ? 0 : sample(p.heights, e, north) * vExag;
      positions[k * 3 + 2] = -north; // z = -n
      const l = AMBIENT + (1 - AMBIENT) * sample(light, e, north);
      const base = sunUp ? l : AMBIENT * 0.5;
      colors[k * 3] = REGOLITH[0] * base;
      colors[k * 3 + 1] = REGOLITH[1] * base;
      colors[k * 3 + 2] = REGOLITH[2] * base;
    }
  }
  return { n, positions, colors, indices: terrainIndices(n), shadowFraction, sunUp };
}

/** Height on the rendered triangles, or null outside the patch. */
export function terrainHeightAt(mesh: TerrainMesh, e: number, z: number): number | null {
  const { n, positions } = mesh;
  const axis = (i: number, north: boolean) => north ? -positions[i * n * 3 + 2]! : positions[i * 3]!;
  const locate = (value: number, north: boolean): number => {
    if (value < axis(0, north) || value > axis(n - 1, north)) return -1;
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = Math.floor((lo + hi) / 2);
      if (axis(mid, north) <= value) lo = mid;
      else hi = mid;
    }
    return lo;
  };
  const north = -z;
  const i = locate(e, false);
  const j = locate(north, true);
  if (i < 0 || j < 0) return null;
  const x = (e - axis(i, false)) / (axis(i + 1, false) - axis(i, false));
  const y = (north - axis(j, true)) / (axis(j + 1, true) - axis(j, true));
  const at = (col: number, row: number) => positions[(row * n + col) * 3 + 1]!;
  const a = at(i, j), b = at(i + 1, j), c = at(i, j + 1), d = at(i + 1, j + 1);
  return x + y <= 1 ? a + x * (b - a) + y * (c - a) : d + (1 - x) * (c - d) + (1 - y) * (b - d);
}

/* ------------------------------------------------- zona di Fresnel ------------------------------------------------- */

export interface TubeRings {
  segments: number;
  sides: number;
  /** (segments + 1) * sides * 3 */
  positions: Float32Array;
  /** Distanze lungo la linea di vista, un valore per anello. */
  d: Float32Array;
  /** Raggi (m, veri, senza scala di disegno) per anello. */
  radius: Float32Array;
}

/**
 * Anelli della prima zona di Fresnel lungo la linea di vista (antenna -> oltre il crinale). Il raggio vero e' scalato di
 * `scale` solo nel disegno; l'asse segue l'esagerazione verticale `vExag` come il terreno.
 */
export function fresnelRings(s: LanderScene, scale: number, vExag: number, segments = 48, sides = 20): TubeRings {
  const positions = new Float32Array((segments + 1) * sides * 3);
  const dArr = new Float32Array(segments + 1);
  const rArr = new Float32Array(segments + 1);
  const el = s.earth.elDeg * DEG;
  const h = s.antenna.mastM;
  const dEnd = s.fresnel.dEndM;
  const ax = [Math.cos(el), Math.sin(el) * vExag];
  const axl = Math.hypot(ax[0]!, ax[1]!);
  const px = -ax[1]! / axl; // perpendicolare nel piano (e, u) del disegno
  const py = ax[0]! / axl;
  for (let k = 0; k <= segments; k++) {
    const d = (dEnd * k) / segments;
    const r = fresnelAt(s, d);
    dArr[k] = d;
    rArr[k] = r;
    const cx = d * Math.cos(el);
    const cy = (h + d * Math.sin(el)) * vExag;
    for (let a = 0; a < sides; a++) {
      const th = (a / sides) * 2 * Math.PI;
      const rr = r * scale;
      const o = (k * sides + a) * 3;
      positions[o] = cx + rr * Math.cos(th) * px;
      positions[o + 1] = cy + rr * Math.cos(th) * py;
      positions[o + 2] = rr * Math.sin(th);
    }
  }
  return { segments, sides, positions, d: dArr, radius: rArr };
}

export function tubeIndices(segments: number, sides: number): Uint32Array {
  const idx = new Uint32Array(segments * sides * 6);
  let q = 0;
  for (let k = 0; k < segments; k++) {
    for (let a = 0; a < sides; a++) {
      const a0 = k * sides + a;
      const a1 = k * sides + ((a + 1) % sides);
      const b0 = a0 + sides;
      const b1 = a1 + sides;
      idx[q++] = a0;
      idx[q++] = b0;
      idx[q++] = a1;
      idx[q++] = a1;
      idx[q++] = b0;
      idx[q++] = b1;
    }
  }
  return idx;
}

/* ------------------------------------------------ cono del fascio ------------------------------------------------ */

/** Anello di base del cono con apice `apex` e asse `dir` (e, u) nel piano verticale: punti mondo (x, y, z). */
export function coneRing(apex: [number, number, number], dir: [number, number], halfAngleDeg: number, length: number, vExag: number, sides = 36): Float32Array {
  const out = new Float32Array(sides * 3);
  const ax = dir[0];
  const ay = dir[1] * vExag;
  const al = Math.hypot(ax, ay);
  const ux = ax / al;
  const uy = ay / al;
  const px = -uy;
  const py = ux;
  const r = length * Math.tan(halfAngleDeg * DEG);
  for (let k = 0; k < sides; k++) {
    const th = (k / sides) * 2 * Math.PI;
    out[k * 3] = apex[0] + ux * length + r * Math.cos(th) * px;
    out[k * 3 + 1] = apex[1] + uy * length + r * Math.cos(th) * py;
    out[k * 3 + 2] = apex[2] + r * Math.sin(th);
  }
  return out;
}

/** Lunghezza del cono del fascio: fino al crinale e un po' oltre, tra 40 e 2500 m. */
export function beamLength(s: LanderScene): number {
  return Math.max(40, Math.min(2500, s.ridge.d1M * 1.15));
}

/** Stato condiviso dai due renderer (tutto cio' che serve per disegnare, nessun accesso alla rete). */
export interface LanderViewState {
  scene: LanderScene | null;
  sceneGen: number;
  terrain: TerrainMesh | null;
  terrainGen: number;
  cam: Cam;
  vExag: number;
  tubeScale: number;
  errorDeg: number;
  showOverlays: boolean;
  sun: SunLocal;
  tier: 'hi' | 'lo';
  /** Language of the text drawn in the 2D section; absent = Italian (the site pages), 'en' = the report. */
  language?: 'en';
}

/* ---------------------------------------------- sezione laterale 2D ---------------------------------------------- */

export interface SectionLayout {
  eMin: number;
  eMax: number;
  uMin: number;
  uMax: number;
  /** Rapporto tra scala verticale e orizzontale (>= 1: sezione esagerata in verticale). */
  exaggeration: number;
  toX(e: number): number;
  toY(u: number): number;
}

/** Riquadro della sezione: asse e dall'antenna oltre il crinale, asse u dal fondo del profilo sopra la cima. */
export function sectionLayout(s: LanderScene, w: number, h: number, pad = { l: 56, r: 24, t: 28, b: 40 }): SectionLayout {
  const pe = s.terrain.profile.e;
  const pu = s.terrain.profile.u;
  const eMin = -Math.max(40, (pe[pe.length - 1]! - pe[0]!) * 0.02);
  const eMax = Math.max(s.ridge.e * 1.35, s.ridge.e + 150);
  const el = Math.tan(s.earth.elDeg * DEG);
  const losEnd = s.antenna.mastM + eMax * el;
  const r1 = s.fresnel.r1AtRidgeM;
  let uLo = Infinity;
  let uHi = -Infinity;
  for (let i = 0; i < pe.length; i++) {
    if (pe[i]! > eMax) break;
    uLo = Math.min(uLo, pu[i]!);
    uHi = Math.max(uHi, pu[i]!);
  }
  if (!Number.isFinite(uLo)) {
    uLo = 0;
    uHi = 1;
  }
  uHi = Math.max(uHi, s.ridge.u, losEnd + r1, s.antenna.mastM * 2);
  uLo = Math.min(uLo, -1);
  const span = Math.max(uHi - uLo, 10);
  const uMin = uLo - span * 0.06;
  const uMax = uHi + span * 0.1;
  const pw = Math.max(10, w - pad.l - pad.r);
  const ph = Math.max(10, h - pad.t - pad.b);
  const sx = pw / (eMax - eMin);
  const sy = ph / (uMax - uMin);
  return { eMin, eMax, uMin, uMax, exaggeration: sy / sx, toX: (e) => pad.l + (e - eMin) * sx, toY: (u) => pad.t + ph - (u - uMin) * sy };
}

/** Bordi superiore e inferiore della prima zona di Fresnel nella sezione: [e, uAlto, uBasso] a n passi. */
export function fresnelBand(s: LanderScene, n = 60): { e: number; hi: number; lo: number; d: number; r: number }[] {
  const el = s.earth.elDeg * DEG;
  const out: { e: number; hi: number; lo: number; d: number; r: number }[] = [];
  for (let k = 0; k <= n; k++) {
    const d = (s.fresnel.dEndM * k) / n;
    const r = fresnelAt(s, d);
    const e = d * Math.cos(el);
    const u = s.antenna.mastM + d * Math.sin(el);
    const dv = r / Math.cos(el); // scarto verticale di un punto a distanza r in perpendicolare
    out.push({ e, hi: u + dv, lo: u - dv, d, r });
  }
  return out;
}
