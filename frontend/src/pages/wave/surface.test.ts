// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import {
  AMBIENT,
  clampCamera,
  colorIndex,
  createMesh,
  DEFAULT_CAMERA,
  eyePosition,
  fillMesh,
  fillSliceLine,
  hasSurface,
  EMPTY_SCENE,
  legendGradient,
  LUT,
  orbit,
  PITCH_MAX,
  PITCH_MIN,
  Projector,
  resetCamera,
  worldX,
  wrapYaw,
  WX,
  WY,
  WZ,
  ZOOM_MAX,
  ZOOM_MIN,
  zoomBy,
  type Camera,
} from './surface';

const cam = (): Camera => ({ ...DEFAULT_CAMERA });

describe('colormap viridis', () => {
  it('estremi viola e giallo, monotona in luminosità', () => {
    expect([LUT[0], LUT[1], LUT[2]]).toEqual([68, 1, 84]);
    expect([LUT[255 * 3], LUT[255 * 3 + 1], LUT[255 * 3 + 2]]).toEqual([253, 231, 37]);
    const lum = (i: number) => 0.2126 * LUT[i * 3]! + 0.7152 * LUT[i * 3 + 1]! + 0.0722 * LUT[i * 3 + 2]!;
    for (let i = 1; i < 256; i++) expect(lum(i)).toBeGreaterThanOrEqual(lum(i - 1) - 0.5);
  });
  it('indice: saturazione, zero e NaN', () => {
    expect(colorIndex(0, 1.2)).toBe(0);
    expect(colorIndex(-3, 1.2)).toBe(0);
    expect(colorIndex(Number.NaN, 1.2)).toBe(0);
    expect(colorIndex(0.6, 1.2)).toBe(Math.round(127.5));
    expect(colorIndex(5, 1.2)).toBe(255);
    expect(colorIndex(1, 0)).toBe(0);
  });
  it('gradiente della legenda con nove nodi', () => {
    expect(legendGradient().match(/rgb\(/g)).toHaveLength(9);
  });
});

describe('da griglia a mesh', () => {
  const nx = 4;
  const ny = 3;
  const xs = [0, 100, 200, 400];
  const grid = new Float32Array(nx * ny).map((_, k) => (k % ny === 1 ? 1.2 : 0.3));

  it('indici: due triangoli per cella, tutti validi', () => {
    const m = createMesh(nx, ny);
    expect(m.indices).toHaveLength((nx - 1) * (ny - 1) * 6);
    for (const v of m.indices) expect(v).toBeLessThan(nx * ny);
    expect(createMesh(300, 300).indices).toBeInstanceOf(Uint32Array);
    expect(createMesh(nx, ny).indices).toBeInstanceOf(Uint16Array);
  });
  it('posizioni: x dalla distanza vera, y dall’intensità, z dalla quota', () => {
    const m = createMesh(nx, ny);
    fillMesh(m, grid, xs, 1.2);
    const p = m.positions;
    expect(p[0]).toBeCloseTo(-WX / 2, 6);
    expect(p[(3 * ny) * 3]).toBeCloseTo(WX / 2, 6);
    expect(p[(2 * ny) * 3]).toBeCloseTo(0, 6); // x = 200 di 400: metà
    expect(p[1]).toBeCloseTo((0.3 / 1.2) * WY, 6);
    expect(p[4]).toBeCloseTo(WY, 6);
    expect(p[2]).toBeCloseTo(-WZ / 2, 6);
    expect(p[(ny - 1) * 3 + 2]).toBeCloseTo(WZ / 2, 6);
  });
  it('valori oltre la quota massima sono tagliati; colori nel range e luce >= ambiente', () => {
    const m = createMesh(nx, ny);
    fillMesh(m, new Float32Array(nx * ny).fill(5), xs, 1.2);
    expect(m.positions[1]).toBeCloseTo(WY, 6);
    for (const c of m.colors) {
      expect(c).toBeGreaterThanOrEqual(0);
      expect(c).toBeLessThanOrEqual(1);
    }
    expect(m.cidx.every((v) => v === 255)).toBe(true);
    const mm = createMesh(nx, ny);
    fillMesh(mm, grid, xs, 1.2);
    const f = mm.colors[(1 * ny + 1) * 3 + 1]! / (LUT[mm.cidx[1 * ny + 1]! * 3 + 1]! / 255);
    expect(f).toBeGreaterThanOrEqual(AMBIENT - 1e-6);
    expect(f).toBeLessThanOrEqual(1 + 1e-6);
  });
  it('riempie sul posto: stessi buffer dopo una nuova griglia, nessuna allocazione', () => {
    const m = createMesh(nx, ny);
    const refs = [m.positions, m.colors, m.cidx, m.shade];
    fillMesh(m, grid, xs, 1.2);
    const first = m.positions.slice();
    fillMesh(m, grid.map((v) => v / 2), xs, 1.2);
    expect([m.positions, m.colors, m.cidx, m.shade]).toEqual(refs);
    expect(m.positions[4]).toBeLessThan(first[4]!);
  });
  it('curva della sezione: interpola tra le righe alla distanza del cursore', () => {
    const out = new Float32Array(ny * 3);
    fillSliceLine(out, grid, nx, ny, xs, 150, 1.2);
    expect(out[0]).toBeCloseTo(worldX(150, 0, 400), 6);
    expect(out[3 + 1]).toBeCloseTo(WY + 0.004, 4);
    expect(out[1]).toBeCloseTo((0.3 / 1.2) * WY + 0.004, 4);
  });
  it('hasSurface richiede dimensioni coerenti', () => {
    expect(hasSurface(EMPTY_SCENE())).toBe(false);
    expect(hasSurface({ ...EMPTY_SCENE(), nx, ny, grid, xs })).toBe(true);
    expect(hasSurface({ ...EMPTY_SCENE(), nx, ny, grid: new Float32Array(5), xs })).toBe(false);
  });
});

describe('camera', () => {
  it('l’inclinazione è limitata e lo zoom pure', () => {
    const c = cam();
    orbit(c, 0, 10);
    expect(c.pitch).toBe(PITCH_MAX);
    orbit(c, 0, -10);
    expect(c.pitch).toBe(PITCH_MIN);
    zoomBy(c, 100);
    expect(c.zoom).toBe(ZOOM_MAX);
    zoomBy(c, 1e-6);
    expect(c.zoom).toBe(ZOOM_MIN);
  });
  it('l’imbardata si avvolge in (-pi, pi]', () => {
    expect(wrapYaw(Math.PI * 3)).toBeCloseTo(-Math.PI, 6);
    expect(wrapYaw(-0.5)).toBeCloseTo(-0.5, 9);
    const c = cam();
    orbit(c, 7, 0);
    expect(Math.abs(c.yaw)).toBeLessThanOrEqual(Math.PI + 1e-9);
  });
  it('valori non finiti tornano ai predefiniti; reset', () => {
    const c: Camera = { yaw: Number.NaN, pitch: Number.NaN, zoom: Number.POSITIVE_INFINITY };
    clampCamera(c);
    expect(c).toEqual({ yaw: 0, pitch: DEFAULT_CAMERA.pitch, zoom: 1 });
    orbit(c, 1, 0.3);
    zoomBy(c, 2);
    expect(resetCamera(c)).toEqual(DEFAULT_CAMERA);
  });
  it('l’occhio sta alla distanza voluta e sopra il piano', () => {
    const e = [0, 0, 0];
    eyePosition({ yaw: 0, pitch: 0.5, zoom: 1 }, e);
    expect(e[0]).toBeCloseTo(0, 9);
    expect(e[1]).toBeGreaterThan(0.2);
    expect(e[2]).toBeGreaterThan(0);
  });
});

describe('proiezione', () => {
  it('il bersaglio cade al centro dello schermo e la y del mondo sale', () => {
    const P = new Projector();
    P.setup(cam(), 800, 500);
    const o = new Float32Array(6);
    P.project(0, 0.2, 0, o, 0);
    expect(o[0]).toBeCloseTo(400, 3);
    expect(o[1]).toBeCloseTo(250, 3);
    expect(o[2]).toBeGreaterThan(0);
    P.project(0, 0.7, 0, o, 3);
    expect(o[4]).toBeLessThan(o[1]!);
  });
  it('destra del mondo a destra dello schermo guardando da +z', () => {
    const P = new Projector();
    P.setup({ yaw: 0, pitch: 0.3, zoom: 1 }, 800, 500);
    const o = new Float32Array(6);
    P.project(-0.5, 0, 0, o, 0);
    P.project(0.5, 0, 0, o, 3);
    expect(o[3]).toBeGreaterThan(o[0]!);
  });
  it('lo zoom ingrandisce', () => {
    const P = new Projector();
    const o = new Float32Array(6);
    P.setup({ yaw: 0, pitch: 0.3, zoom: 1 }, 800, 500);
    P.project(1, 0, 0, o, 0);
    P.setup({ yaw: 0, pitch: 0.3, zoom: 2 }, 800, 500);
    P.project(1, 0, 0, o, 3);
    expect(Math.abs(o[3]! - 400)).toBeGreaterThan(Math.abs(o[0]! - 400));
  });
});
