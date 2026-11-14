// SPDX-License-Identifier: Apache-2.0
// Geometria pura della superficie 3D dell'onda, condivisa da WebGL e Canvas 2D: colormap viridis (sicura per i
// daltonici), da griglia a mesh (buffer riusati, riempiti sul posto), camera orbitale con limiti, proiezione
// prospettica senza allocazioni. Mondo: x = distanza (lunghezza WX), y = intensità (altezza WH), z = quota sulla
// linea di vista (profondità WZ). Nessun accesso al DOM.
import { rowAt } from './wave';

export const BG = '#0b0f17';
export const WX = 2;
export const WY = 0.7;
export const WZ = 1.2;

/* ------------------------------------------ colormap ------------------------------------------ */

const VIRIDIS: readonly (readonly [number, number, number])[] = [
  [68, 1, 84],
  [71, 45, 123],
  [59, 82, 139],
  [44, 114, 142],
  [33, 145, 140],
  [40, 174, 128],
  [94, 201, 98],
  [173, 220, 48],
  [253, 231, 37],
];
export const LUT_SIZE = 256;
/** Tabella RGB (0..255) a 256 livelli, interpolata linearmente tra i nodi di viridis. */
export const LUT: Uint8Array = (() => {
  const t = new Uint8Array(LUT_SIZE * 3);
  for (let i = 0; i < LUT_SIZE; i++) {
    const f = (i / (LUT_SIZE - 1)) * (VIRIDIS.length - 1);
    const a = Math.min(VIRIDIS.length - 2, Math.floor(f));
    const u = f - a;
    for (let c = 0; c < 3; c++) t[i * 3 + c] = Math.round(VIRIDIS[a]![c]! * (1 - u) + VIRIDIS[a + 1]![c]! * u);
  }
  return t;
})();
/** Indice 0..255 per un valore in [0, vmax] (fuori scala: saturato; NaN: 0). */
export function colorIndex(v: number, vmax: number): number {
  if (!(v > 0) || !(vmax > 0)) return 0;
  return v >= vmax ? LUT_SIZE - 1 : Math.round((v / vmax) * (LUT_SIZE - 1));
}
export const rgbCss = (i: number): string => `rgb(${LUT[i * 3]},${LUT[i * 3 + 1]},${LUT[i * 3 + 2]})`;
/** Nodi del gradiente CSS della legenda (stessi colori della superficie). */
export function legendGradient(): string {
  const stops = VIRIDIS.map((c, i) => `rgb(${c[0]},${c[1]},${c[2]}) ${Math.round((i / (VIRIDIS.length - 1)) * 100)}%`);
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}

/* ------------------------------------------- illuminazione ------------------------------------------- */

/** Luce direzionale fissa nel mondo (normalizzata) e livelli di ombreggiatura. */
const LIGHT = (() => {
  const v = [-0.45, 0.8, 0.4];
  const n = Math.hypot(v[0]!, v[1]!, v[2]!);
  return [v[0]! / n, v[1]! / n, v[2]! / n] as const;
})();
export const AMBIENT = 0.5;
export const SHADE_LEVELS = 8;
/** Fattore di luce (AMBIENT..1) per una normale (nx, ny, nz) normalizzata. */
export function lightFactor(nx: number, ny: number, nz: number): number {
  const d = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2];
  return AMBIENT + (1 - AMBIENT) * (d > 0 ? d : 0);
}

/* ---------------------------------------------- mesh ---------------------------------------------- */

export interface MeshBuffers {
  nx: number;
  ny: number;
  positions: Float32Array;
  /** colore con la luce già applicata (0..1) */
  colors: Float32Array;
  /** indice di colore 0..255 e livello di luce 0..SHADE_LEVELS-1 per vertice (per il Canvas 2D) */
  cidx: Uint8Array;
  shade: Uint8Array;
  /** due triangoli per cella */
  indices: Uint16Array | Uint32Array;
}
export function createMesh(nx: number, ny: number): MeshBuffers {
  const n = nx * ny;
  const cells = Math.max(0, nx - 1) * Math.max(0, ny - 1);
  const indices = n > 65535 ? new Uint32Array(cells * 6) : new Uint16Array(cells * 6);
  let k = 0;
  for (let i = 0; i < nx - 1; i++) {
    for (let j = 0; j < ny - 1; j++) {
      const a = i * ny + j;
      const b = a + 1;
      const c = a + ny;
      const d = c + 1;
      indices[k++] = a;
      indices[k++] = c;
      indices[k++] = b;
      indices[k++] = b;
      indices[k++] = c;
      indices[k++] = d;
    }
  }
  return { nx, ny, positions: new Float32Array(n * 3), colors: new Float32Array(n * 3), cidx: new Uint8Array(n), shade: new Uint8Array(n), indices };
}

/** Posizione x nel mondo di una distanza (m) dato l'intervallo coperto dalla griglia. */
export const worldX = (x: number, x0: number, x1: number): number => ((x - x0) / (x1 > x0 ? x1 - x0 : 1) - 0.5) * WX;
export const worldZ = (j: number, ny: number): number => (j / (ny - 1) - 0.5) * WZ;

/**
 * Riempie posizioni, normali implicite (luce), colori e livelli dai valori `grid` (nx*ny, riga = distanza).
 * Scrive solo nei buffer già allocati.
 */
export function fillMesh(m: MeshBuffers, grid: Float32Array, xs: ArrayLike<number>, zTop: number): void {
  const { nx, ny, positions: p, colors: c, cidx, shade } = m;
  const x0 = xs[0]!;
  const x1 = xs[nx - 1]!;
  const sy = WY / zTop;
  for (let i = 0; i < nx; i++) {
    const wx = worldX(xs[i]!, x0, x1);
    for (let j = 0; j < ny; j++) {
      const v = grid[i * ny + j]!;
      const o = (i * ny + j) * 3;
      p[o] = wx;
      p[o + 1] = Math.min(v, zTop) * sy;
      p[o + 2] = worldZ(j, ny);
    }
  }
  for (let i = 0; i < nx; i++) {
    const i0 = i > 0 ? i - 1 : i;
    const i1 = i < nx - 1 ? i + 1 : i;
    const dx = p[(i1 * ny) * 3]! - p[(i0 * ny) * 3]!;
    for (let j = 0; j < ny; j++) {
      const j0 = j > 0 ? j - 1 : j;
      const j1 = j < ny - 1 ? j + 1 : j;
      const dz = p[(i * ny + j1) * 3 + 2]! - p[(i * ny + j0) * 3 + 2]!;
      const hx = (p[(i1 * ny + j) * 3 + 1]! - p[(i0 * ny + j) * 3 + 1]!) / (dx || 1);
      const hz = (p[(i * ny + j1) * 3 + 1]! - p[(i * ny + j0) * 3 + 1]!) / (dz || 1);
      const inv = 1 / Math.hypot(hx, 1, hz);
      const f = lightFactor(-hx * inv, inv, -hz * inv);
      const v = i * ny + j;
      const ci = colorIndex(grid[v]!, zTop);
      cidx[v] = ci;
      shade[v] = Math.min(SHADE_LEVELS - 1, Math.round(((f - AMBIENT) / (1 - AMBIENT)) * (SHADE_LEVELS - 1)));
      c[v * 3] = (LUT[ci * 3]! / 255) * f;
      c[v * 3 + 1] = (LUT[ci * 3 + 1]! / 255) * f;
      c[v * 3 + 2] = (LUT[ci * 3 + 2]! / 255) * f;
    }
  }
}

/** Curva della sezione sulla superficie alla distanza `x` (m): ny punti (x,y,z) del mondo, interpolando due righe. */
export function fillSliceLine(out: Float32Array, grid: Float32Array, nx: number, ny: number, xs: ArrayLike<number>, x: number, zTop: number): void {
  const { k, t } = rowAt(xs, x);
  const wx = worldX(x, xs[0]!, xs[nx - 1]!);
  const sy = WY / zTop;
  for (let j = 0; j < ny; j++) {
    const a = grid[k * ny + j]!;
    const b = grid[(k + 1) * ny + j]!;
    out[j * 3] = wx;
    out[j * 3 + 1] = Math.min(a + (b - a) * t, zTop) * sy + 0.004;
    out[j * 3 + 2] = worldZ(j, ny);
  }
}

/** Cornice (base e spigoli) e piano della sezione come coppie di estremi (6 float per segmento). */
export const FRAME_SEGMENTS: readonly number[] = (() => {
  const x = WX / 2;
  const z = WZ / 2;
  const s: number[] = [];
  const seg = (a: number[], b: number[]) => s.push(...a, ...b);
  seg([-x, 0, -z], [x, 0, -z]);
  seg([x, 0, -z], [x, 0, z]);
  seg([x, 0, z], [-x, 0, z]);
  seg([-x, 0, z], [-x, 0, -z]);
  seg([-x, 0, 0], [x, 0, 0]); // y = 0: la linea di vista (la cima del crinale è a x = 0, a sinistra)
  seg([-x, 0, -z], [-x, WY, -z]);
  seg([x, 0, -z], [x, WY, -z]);
  seg([-x, WY, -z], [x, WY, -z]);
  return s;
})();
export const FRAME_COUNT = FRAME_SEGMENTS.length / 6;

/** Piano della sezione: 4 angoli (x,y,z) a distanza `wx`. */
export function fillSlicePlane(out: Float32Array, wx: number): void {
  const z = WZ / 2;
  out.set([wx, 0, -z, wx, WY, -z, wx, WY, z, wx, 0, z]);
}

/* ------------------------------------------------ camera ------------------------------------------------ */

export interface Camera {
  yaw: number;
  pitch: number;
  zoom: number;
}
export const DEFAULT_CAMERA: Readonly<Camera> = { yaw: -0.62, pitch: 0.5, zoom: 1 };
export const PITCH_MIN = 0.06;
export const PITCH_MAX = 1.5;
export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 3;
export const FOV_DEG = 35;
export const BASE_DISTANCE = 3.4;
export const TARGET_Y = 0.2;

const TWO_PI = Math.PI * 2;
export function wrapYaw(a: number): number {
  const r = ((((a + Math.PI) % TWO_PI) + TWO_PI) % TWO_PI) - Math.PI;
  return Number.isFinite(r) ? r : 0;
}
/** Porta la camera nei limiti, sul posto. */
export function clampCamera(c: Camera): Camera {
  c.yaw = wrapYaw(c.yaw);
  c.pitch = Number.isFinite(c.pitch) ? Math.min(PITCH_MAX, Math.max(PITCH_MIN, c.pitch)) : DEFAULT_CAMERA.pitch;
  c.zoom = Number.isFinite(c.zoom) ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, c.zoom)) : 1;
  return c;
}
export function orbit(c: Camera, dyaw: number, dpitch: number): Camera {
  c.yaw += dyaw;
  c.pitch += dpitch;
  return clampCamera(c);
}
export function zoomBy(c: Camera, f: number): Camera {
  c.zoom *= f;
  return clampCamera(c);
}
export function resetCamera(c: Camera): Camera {
  c.yaw = DEFAULT_CAMERA.yaw;
  c.pitch = DEFAULT_CAMERA.pitch;
  c.zoom = DEFAULT_CAMERA.zoom;
  return c;
}
/** Posizione dell'occhio nel mondo (scrive in `out[0..2]`). */
export function eyePosition(c: Camera, out: number[] | Float32Array): void {
  const d = BASE_DISTANCE / c.zoom;
  const cp = Math.cos(c.pitch);
  out[0] = d * Math.sin(c.yaw) * cp;
  out[1] = TARGET_Y + d * Math.sin(c.pitch);
  out[2] = d * Math.cos(c.yaw) * cp;
}

/** Riduzione dell'ingrandimento sugli schermi stretti (verticali) perché la scatola resti intera. */
export const fitOf = (w: number, h: number): number => Math.min(1, w / (h || 1) / 1.35);

/** Proiezione prospettica con gli stessi parametri della PerspectiveCamera di three.js; nessuna allocazione dopo la creazione. */
export class Projector {
  private readonly eye = new Float32Array(3);
  private ex = 0;
  private ey = 0;
  private ez = 0;
  private rx = 0;
  private rz = 0;
  private ux = 0;
  private uy = 0;
  private uz = 0;
  private fx = 0;
  private fy = 0;
  private fz = 0;
  private focal = 1;
  private cx = 0;
  private cy = 0;
  /** posizione dell'occhio, per l'ordine di disegno */
  get eyeX(): number {
    return this.ex;
  }
  get eyeZ(): number {
    return this.ez;
  }
  setup(c: Camera, w: number, h: number): void {
    const eye = this.eye;
    eyePosition(c, eye);
    this.ex = eye[0]!;
    this.ey = eye[1]!;
    this.ez = eye[2]!;
    let fx = -this.ex;
    let fy = TARGET_Y - this.ey;
    let fz = -this.ez;
    const fl = Math.hypot(fx, fy, fz);
    fx /= fl;
    fy /= fl;
    fz /= fl;
    // destra = f x su(0,1,0), poi su = destra x f
    let rx = -fz;
    let rz = fx;
    const rl = Math.hypot(rx, rz) || 1;
    rx /= rl;
    rz /= rl;
    this.rx = rx;
    this.rz = rz;
    this.ux = -fy * rz;
    this.uy = rz * fx - rx * fz;
    this.uz = fy * rx;
    this.fx = fx;
    this.fy = fy;
    this.fz = fz;
    this.focal = (h / 2 / Math.tan((FOV_DEG * Math.PI) / 360)) * fitOf(w, h);
    this.cx = w / 2;
    this.cy = h / 2;
  }
  /** Scrive (sx, sy, profondità) in out[o..o+2]; la y dello schermo cresce verso il basso. */
  project(x: number, y: number, z: number, out: Float32Array, o: number): void {
    const dx = x - this.ex;
    const dy = y - this.ey;
    const dz = z - this.ez;
    const depth = dx * this.fx + dy * this.fy + dz * this.fz;
    const s = this.focal / (depth > 1e-3 ? depth : 1e-3);
    out[o] = this.cx + (dx * this.rx + dz * this.rz) * s;
    out[o + 1] = this.cy - (dx * this.ux + dy * this.uy + dz * this.uz) * s;
    out[o + 2] = depth;
  }
}

/** Stato condiviso con i due renderer (oggetto mutabile: `geom` cambia quando arriva una nuova griglia). */
export interface WaveScene {
  geom: number;
  grid: Float32Array;
  nx: number;
  ny: number;
  xs: ArrayLike<number>;
  zTop: number;
  /** distanza del cursore in metri */
  cursor: number;
  camera: Camera;
  /** 'lo': meno celle disegnate e DPR minore */
  tier: 'hi' | 'lo';
}
export const EMPTY_SCENE = (): WaveScene => ({ geom: 0, grid: new Float32Array(0), nx: 0, ny: 0, xs: [], zTop: 1.2, cursor: 0, camera: { ...DEFAULT_CAMERA }, tier: 'hi' });
export const hasSurface = (s: WaveScene): boolean => s.nx >= 2 && s.ny >= 2 && s.grid.length === s.nx * s.ny && s.xs.length >= s.nx;
