// SPDX-License-Identifier: Apache-2.0
// Ripiego Canvas 2D della superficie d'onda (nessun WebGL): quadrilateri pieni disegnati dal fondo verso il primo
// piano (algoritmo del pittore, ordine ricavato dalla posizione dell'occhio, senza ordinamenti), con la stessa camera
// orbitale, gli stessi colori e la stessa luce del renderer WebGL. Buffer riusati e stringhe di colore in cache:
// nessuna allocazione per fotogramma.
import { Canvas2DUnavailableError } from '../../viewports/errors';
import type { ViewportPort } from '../../viewports/port';
import {
  AMBIENT,
  BG,
  createMesh,
  DEFAULT_CAMERA,
  FRAME_COUNT,
  FRAME_SEGMENTS,
  fillMesh,
  fillSliceLine,
  fillSlicePlane,
  hasSurface,
  LUT,
  Projector,
  SHADE_LEVELS,
  worldX,
  type MeshBuffers,
  type WaveScene,
} from './surface';


const DPR_CAP = { hi: 2, lo: 1.5 } as const;

class CanvasWave implements ViewportPort {
  private el: HTMLElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private ro: ResizeObserver | null = null;
  private raf = 0;
  private disposed = false;
  private scene: WaveScene | null = null;
  private mesh: MeshBuffers | null = null;
  private seenGeom = -1;
  private seenZ = -1;
  private screen = new Float32Array(0);
  private slice = new Float32Array(0);
  private plane = new Float32Array(12);
  private sp = new Float32Array(12);
  private sliceScreen = new Float32Array(0);
  private frameScreen = new Float32Array(FRAME_COUNT * 6);
  private readonly proj = new Projector();
  private readonly styles: string[] = [];
  private w = 0;
  private h = 0;
  private frames = 0;

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Canvas2DUnavailableError();
    this.el = el;
    this.canvas = canvas;
    this.ctx = ctx;
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'display:block;width:100%;height:100%';
    el.appendChild(canvas);
    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(el);
    }
    this.resize();
    this.schedule();
  }

  update(state: unknown): void {
    if (this.disposed) return;
    this.scene = state as WaveScene;
    this.schedule();
  }

  private resize(): void {
    if (this.disposed || !this.el || !this.canvas || !this.ctx) return;
    this.w = Math.max(1, this.el.clientWidth);
    this.h = Math.max(1, this.el.clientHeight);
    const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP[this.scene?.tier ?? 'hi']);
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.schedule();
  }

  private schedule(): void {
    if (this.disposed || this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.draw();
    });
  }

  private style(shade: number, ci: number): string {
    const k = shade * 256 + ci;
    let s = this.styles[k];
    if (s === undefined) {
      const f = AMBIENT + ((1 - AMBIENT) * shade) / (SHADE_LEVELS - 1);
      s = `rgb(${Math.round(LUT[ci * 3]! * f)},${Math.round(LUT[ci * 3 + 1]! * f)},${Math.round(LUT[ci * 3 + 2]! * f)})`;
      this.styles[k] = s;
    }
    return s;
  }

  private rebuild(sc: WaveScene): void {
    if (!this.mesh || this.mesh.nx !== sc.nx || this.mesh.ny !== sc.ny) {
      this.mesh = createMesh(sc.nx, sc.ny);
      this.screen = new Float32Array(sc.nx * sc.ny * 3);
      this.slice = new Float32Array(sc.ny * 3);
      this.sliceScreen = new Float32Array(sc.ny * 3);
    }
    fillMesh(this.mesh, sc.grid, sc.xs, sc.zTop);
    this.seenGeom = sc.geom;
    this.seenZ = sc.zTop;
  }

  private draw(): void {
    const ctx = this.ctx;
    const sc = this.scene;
    if (this.disposed || !ctx || !this.canvas) return;
    const { w, h } = this;
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, w, h);
    this.proj.setup(sc?.camera ?? DEFAULT_CAMERA, w, h);
    const P = this.proj;

    // cornice
    const fs = this.frameScreen;
    for (let k = 0; k < FRAME_COUNT * 2; k++) P.project(FRAME_SEGMENTS[k * 3]!, FRAME_SEGMENTS[k * 3 + 1]!, FRAME_SEGMENTS[k * 3 + 2]!, fs, k * 3);
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(160,172,190,0.75)';
    ctx.beginPath();
    for (let k = 0; k < FRAME_COUNT; k++) {
      ctx.moveTo(fs[k * 6]!, fs[k * 6 + 1]!);
      ctx.lineTo(fs[k * 6 + 3]!, fs[k * 6 + 4]!);
    }
    ctx.stroke();

    if (sc && hasSurface(sc)) {
      if (this.seenGeom !== sc.geom || this.seenZ !== sc.zTop || !this.mesh) this.rebuild(sc);
      const m = this.mesh!;
      this.drawSurface(ctx, m, sc);
      this.drawSlice(ctx, m, sc);
    }
    this.frames++;
    this.canvas.dataset.frames = String(this.frames);
  }

  private drawSurface(ctx: CanvasRenderingContext2D, m: MeshBuffers, sc: WaveScene): void {
    const { nx, ny, positions: p, cidx, shade } = m;
    const P = this.proj;
    const s = this.screen;
    const n = nx * ny;
    for (let v = 0; v < n; v++) P.project(p[v * 3]!, p[v * 3 + 1]!, p[v * 3 + 2]!, s, v * 3);
    const stride = sc.tier === 'lo' ? 2 : 1;
    // lati lontani per primi: la x del mondo cresce con i, la z con j
    const iAsc = P.eyeX > 0;
    const jAsc = P.eyeZ > 0;
    const ni = Math.floor((nx - 1) / stride);
    const nj = Math.floor((ny - 1) / stride);
    ctx.lineWidth = 1;
    ctx.lineJoin = 'round';
    for (let ii = 0; ii < ni; ii++) {
      const i = (iAsc ? ii : ni - 1 - ii) * stride;
      for (let jj = 0; jj < nj; jj++) {
        const j = (jAsc ? jj : nj - 1 - jj) * stride;
        const a = (i * ny + j) | 0;
        const b = a + stride;
        const c = a + stride * ny;
        const d = c + stride;
        const ci = (cidx[a]! + cidx[b]! + cidx[c]! + cidx[d]!) >> 2;
        const sh = (shade[a]! + shade[b]! + shade[c]! + shade[d]!) >> 2;
        const st = this.style(sh, ci);
        ctx.fillStyle = st;
        ctx.strokeStyle = st;
        ctx.beginPath();
        ctx.moveTo(s[a * 3]!, s[a * 3 + 1]!);
        ctx.lineTo(s[b * 3]!, s[b * 3 + 1]!);
        ctx.lineTo(s[d * 3]!, s[d * 3 + 1]!);
        ctx.lineTo(s[c * 3]!, s[c * 3 + 1]!);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }
  }

  private drawSlice(ctx: CanvasRenderingContext2D, m: MeshBuffers, sc: WaveScene): void {
    const P = this.proj;
    const wx = worldX(sc.cursor, sc.xs[0]!, sc.xs[sc.nx - 1]!);
    fillSlicePlane(this.plane, wx);
    for (let k = 0; k < 4; k++) P.project(this.plane[k * 3]!, this.plane[k * 3 + 1]!, this.plane[k * 3 + 2]!, this.sp, k * 3);
    ctx.beginPath();
    ctx.moveTo(this.sp[0]!, this.sp[1]!);
    for (let k = 1; k < 4; k++) ctx.lineTo(this.sp[k * 3]!, this.sp[k * 3 + 1]!);
    ctx.closePath();
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 1;
    ctx.stroke();

    fillSliceLine(this.slice, sc.grid, m.nx, m.ny, sc.xs, sc.cursor, sc.zTop);
    const ls = this.sliceScreen;
    for (let j = 0; j < m.ny; j++) P.project(this.slice[j * 3]!, this.slice[j * 3 + 1]!, this.slice[j * 3 + 2]!, ls, j * 3);
    ctx.beginPath();
    ctx.moveTo(ls[0]!, ls[1]!);
    for (let j = 1; j < m.ny; j++) ctx.lineTo(ls[j * 3]!, ls[j * 3 + 1]!);
    ctx.lineJoin = 'round';
    ctx.strokeStyle = BG;
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    this.canvas?.remove();
    this.canvas = null;
    this.ctx = null;
    this.el = null;
    this.scene = null;
    this.mesh = null;
  }
}

export const createCanvasWave = (): ViewportPort => new CanvasWave();
