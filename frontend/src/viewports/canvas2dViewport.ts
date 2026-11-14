// SPDX-License-Identifier: Apache-2.0
// Renderer senza WebGL: stessa SceneState di threeViewport, disegnata solo con Canvas 2D a partire dalle
// mappe NASA reali (colore + rilievo). L'ombreggiatura per pixel (shading.ts) gira in un Worker quando
// possibile: durante il movimento a mezza risoluzione, poi rifinita a piena risoluzione da ferma; i dischi
// già calcolati restano in una piccola cache per posizione. Senza Worker si calcola sul thread principale
// con qualità adattiva. Il cielo è la mappa stellare SVS ritagliata secondo la vista, più due strati di
// stelle in parallasse (assenti con reduced motion o qualità bassa).
import { Canvas2DUnavailableError } from './errors';
import type { ViewportFactory, ViewportPort } from './port';
import { ASSETS } from './bodies/assets';
import { BODIES, starsAsset } from './bodies/registry';
import { detectQuality, type Quality } from './quality';
import { azElToVector, defaultFrame, DEFAULT_SCENE, isSceneState, objToView, rotationRows, type BodyId, type DiskFrame, type SceneState } from './scene';
import { buildRelief, shadeDisk, type Relief, type ShadeParams, type Tex } from './shading';
import { loadImage, loadTex, releaseImage } from './textures';

export { rotationRows };

const REDUCED = '(prefers-reduced-motion: reduce)';
const SPIN_DEG_PER_S = 18; // = 0,3° a 60 fps, come threeViewport
const DEFAULT_LIGHT: [number, number, number] = [0.45, 0.3, 0.84];
const FADE_MS = 480;
const IDLE_MS = 160;
const CACHE_MAX = 16;
/** Campo visivo orizzontale del cielo (gradi). */
const SKY_FOV = 70;

export interface Canvas2dOptions {
  /** 'full' (visualizzatore: cielo nero pieno) oppure 'hero' (palco della home: fondo trasparente). */
  decor?: 'full' | 'hero';
  /** Raggio della sfera come frazione del lato minore del canvas (senza `place` né `frame`). Default 0.36. */
  radius?: number;
  /** Velocità della rotazione automatica in gradi al secondo. Default 18. */
  spinDegPerS?: number;
  /** Tetto ai fotogrammi al secondo (risparmio su macchine deboli). Default 60. */
  maxFps?: number;
  /** Lato massimo (px) del disco ombreggiato. Default 720. */
  maxSample?: number;
  /** Posizione e raggio della sfera (px CSS) in funzione delle dimensioni del canvas. */
  place?: (w: number, h: number) => DiskFrame;
  /** Carica le mappe NASA (default true; i test unitari lo disattivano). */
  textures?: boolean;
  /** Usa il Worker se disponibile (default true). */
  worker?: boolean;
  /** Livello di qualità (default: dal dispositivo). */
  quality?: Quality;
  /** @deprecated superficie procedurale rimossa nella v2; ignorati. */
  textureWidth?: number;
  seed?: number;
}

interface Surface {
  color: Tex | null;
  relief: Relief | null;
}

type Img = ImageBitmap | HTMLImageElement;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function lightVector(sun: SceneState['sun'], view?: [number, number, number]): [number, number, number] {
  const v = view ?? (sun ? azElToVector(sun) : DEFAULT_LIGHT);
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

const ease = (t: number) => 1 - (1 - t) ** 3;

class Canvas2dViewport implements ViewportPort {
  private el: HTMLElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private sphere: HTMLCanvasElement | null = null;
  private sphereCtx: CanvasRenderingContext2D | null = null;
  private sphereImg: ImageData | null = null;
  private sphereN = 0;
  private ro: ResizeObserver | null = null;
  private io: IntersectionObserver | null = null;
  private mql: MediaQueryList | null = null;
  private raf = 0;
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  private lastFrame = -Infinity;
  private lastChange = -Infinity;
  private reduced = false;
  private visible = true;
  private pageVisible = true;
  private disposed = false;
  private frames = 0;
  private state: SceneState = { ...DEFAULT_SCENE };
  private body: BodyId = 'moon';
  private w = 0;
  private h = 0;
  private dpr = 1;
  private adapt = 1;
  private readonly q: Quality;
  // superfici: sul thread principale (senza Worker) o solo "pronta" nel Worker
  private surfaces = new Map<BodyId, Surface>();
  private workerReady = new Set<BodyId>();
  private worker: Worker | null = null;
  private inFlight: string | null = null;
  private wantKey = '';
  private wantParams: ShadeParams | null = null;
  private reqId = 0;
  private cache = new Map<string, HTMLCanvasElement>();
  private shown: { key: string; body: BodyId; canvas: HTMLCanvasElement } | null = null;
  private stars: Img | null = null;
  private sunImg: Img | null = null;
  private layers: Float32Array[] = [];
  private fadeFrom: HTMLCanvasElement | null = null;
  private fadeStart = 0;
  /** Il frame appena disegnato è definitivo (mappe caricate, piena risoluzione). */
  private complete = false;
  /** Diagnostica per i test di prestazione: ms dell'ultima ombreggiatura e dischi presentati. */
  stats = { shadeMs: 0, disks: 0, worker: false };

  constructor(private readonly opts: Canvas2dOptions) {
    this.q = opts.quality ?? detectQuality();
  }

  private readonly onMotionChange = (): void => {
    this.reduced = this.mql?.matches ?? false;
    this.schedule();
  };

  private readonly onVisibility = (): void => {
    this.pageVisible = document.visibilityState !== 'hidden';
    if (this.pageVisible) this.schedule();
  };

  private get minFrameMs(): number {
    return 1000 / Math.max(1, Math.min(60, this.opts.maxFps ?? 60));
  }

  /** Fotogrammi disegnati finora (diagnostica e test). */
  get frameCount(): number {
    return this.frames;
  }

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Canvas2DUnavailableError();
    this.el = el;
    this.canvas = canvas;
    this.ctx = ctx;
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    el.appendChild(canvas);

    this.mql = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED) : null;
    this.reduced = this.mql?.matches ?? false;
    this.mql?.addEventListener('change', this.onMotionChange);
    if (typeof document.addEventListener === 'function') {
      this.pageVisible = document.visibilityState !== 'hidden';
      document.addEventListener('visibilitychange', this.onVisibility);
    }
    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(el);
    }
    if (typeof IntersectionObserver !== 'undefined') {
      this.io = new IntersectionObserver((entries) => {
        const last = entries[entries.length - 1];
        if (!last) return;
        this.visible = last.isIntersecting;
        if (this.visible) this.schedule();
      });
      this.io.observe(el);
    }
    this.startWorker();
    if (this.opts.textures !== false) {
      void loadImage(ASSETS[starsAsset(this.q.tier === 'hi' && this.opts.decor !== 'hero' ? 'hi' : 'lo')].url).then(
        (img) => {
          if (this.disposed) return;
          this.stars = img;
          this.schedule();
        },
        () => {},
      );
    }
    this.loadBody(this.body);
    this.resize();
  }

  private hostYaw = Number.NaN;

  /** Firma dei soli campi dello stato che influenzano il disegno di questo renderer. */
  private drawSig(): string {
    const { earth: _earth, ...visible } = this.state as typeof this.state & { earth?: unknown };
    return JSON.stringify(visible);
  }

  update(state: unknown): void {
    if (this.disposed || !isSceneState(state)) return;
    const next = state.body ?? 'moon';
    if (next !== this.body) this.switchBody(next);
    // la rotazione automatica fa avanzare l'angolo qui dentro: se chi chiama non lo ha cambiato (nuovo campione di
    // telemetria, ridimensionamento, stop della rotazione) la scena non deve tornare indietro all'angolo vecchio
    const keepYaw = state.yaw_deg === this.hostYaw;
    this.hostYaw = state.yaw_deg;
    const before = this.drawSig();
    this.state = keepYaw ? { ...state, yaw_deg: this.state.yaw_deg } : { ...state };
    // un campione di telemetria che cambia solo ciò che questo renderer non disegna (la posizione della Terra nel
    // cielo) non sposta nulla: niente passaggio a bassa risoluzione (la scena sfarfallava una volta al secondo,
    // anche con riduzione del movimento)
    if (this.drawSig() === before) return;
    this.lastChange = typeof performance !== 'undefined' ? performance.now() : 0;
    this.schedule();
  }

  /* ------------------------------ corpi e mappe ------------------------------ */

  private startWorker(): void {
    if (this.opts.worker === false || this.opts.textures === false || typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') return;
    try {
      const w = new Worker(new URL('./shadeWorker.ts', import.meta.url), { type: 'module' });
      w.onmessage = (e: MessageEvent) => this.onWorker(e.data as { type: string; key: string; [k: string]: unknown });
      w.onerror = () => this.stopWorker();
      this.worker = w;
      this.stats.worker = true;
    } catch {
      this.worker = null;
    }
  }

  private stopWorker(): void {
    this.worker?.terminate();
    this.worker = null;
    this.stats.worker = false;
    this.inFlight = null;
    this.workerReady.clear();
    this.loadBody(this.body); // ripiego sul thread principale
    this.schedule();
  }

  private loadBody(id: BodyId): void {
    if (this.opts.textures === false) return;
    const b = BODIES[id];
    const tier = this.q.tier;
    if (b.emissive) {
      void loadImage(ASSETS[b.color[tier]].url).then(
        (img) => {
          if (this.disposed || this.body !== id) return;
          this.sunImg = img;
          this.schedule();
        },
        () => {},
      );
      return;
    }
    const height = b.height ? { url: ASSETS[b.height[tier]].url, kmMin: b.height.kmMin, kmMax: b.height.kmMax, radiusKm: b.height.radiusKm } : undefined;
    if (this.worker) {
      this.worker.postMessage({ type: 'load', key: id, color: ASSETS[b.color[tier]].url, height });
      return;
    }
    if (this.surfaces.get(id)?.color) return;
    void (async () => {
      try {
        const color = await loadTex(ASSETS[b.color[tier]].url);
        const relief = height ? buildRelief(await loadTex(height.url), height.kmMin, height.kmMax, height.radiusKm) : null;
        if (this.disposed || this.body !== id) return;
        this.surfaces.set(id, { color, relief });
        this.schedule();
      } catch {
        /* resta l'anteprima grigia: la descrizione testuale è comunque nella pagina */
      }
    })();
  }

  private switchBody(next: BodyId): void {
    const prev = this.body;
    if (!this.reduced && this.canvas && this.canvas.width > 1 && typeof document !== 'undefined') {
      const snap = document.createElement('canvas');
      snap.width = this.canvas.width;
      snap.height = this.canvas.height;
      const sctx = snap.getContext('2d');
      if (sctx) {
        sctx.drawImage(this.canvas, 0, 0);
        this.fadeFrom = snap;
        this.fadeStart = typeof performance !== 'undefined' ? performance.now() : 0;
      }
    }
    // rilascio della memoria del corpo precedente (pixel, bitmap, dischi in cache)
    this.surfaces.delete(prev);
    this.workerReady.delete(prev);
    this.worker?.postMessage({ type: 'drop', key: prev });
    const pb = BODIES[prev];
    for (const t of ['hi', 'lo'] as const) {
      releaseImage(ASSETS[pb.color[t]].url);
      if (pb.height) releaseImage(ASSETS[pb.height[t]].url);
    }
    this.cache.clear();
    this.shown = null;
    this.sunImg = null;
    this.body = next;
    this.loadBody(next);
  }

  private onWorker(m: { type: string; key: string; [k: string]: unknown }): void {
    if (this.disposed) return;
    if (m.type === 'ready') {
      this.workerReady.add(m.key as BodyId);
      this.cache.clear();
      this.schedule();
      return;
    }
    if (m.type === 'error') return;
    if (m.type !== 'frame') return;
    const key = m.key as string;
    const frameKey = this.inFlight;
    this.inFlight = null;
    const S = m.S as number;
    this.stats.shadeMs = m.ms as number;
    if (frameKey && frameKey.startsWith(`${this.body}|`)) {
      const c = document.createElement('canvas');
      c.width = c.height = S;
      const cctx = c.getContext('2d');
      if (cctx) {
        cctx.putImageData(new ImageData(m.buf as Uint8ClampedArray<ArrayBuffer>, S, S), 0, 0);
        this.cache.set(frameKey, c);
        if (this.cache.size > CACHE_MAX) this.cache.delete(this.cache.keys().next().value as string);
        this.shown = { key: frameKey, body: this.body, canvas: c };
        this.stats.disks++;
      }
    }
    void key;
    // la vista è cambiata nel frattempo: chiedi il disco più recente
    if (this.wantParams && this.wantKey !== frameKey) this.request(this.wantKey, this.wantParams);
    this.schedule();
  }

  private request(key: string, params: ShadeParams): void {
    if (!this.worker) return;
    this.wantKey = key;
    this.wantParams = params;
    if (this.inFlight) return;
    this.inFlight = key;
    this.worker.postMessage({ type: 'frame', id: ++this.reqId, key: this.body, params });
  }

  /* --------------------------------- ciclo --------------------------------- */

  private resize(): void {
    if (this.disposed || !this.el || !this.canvas) return;
    const w = Math.max(1, this.el.clientWidth);
    const h = Math.max(1, this.el.clientHeight || Math.round(w * 0.6));
    this.dpr = Math.min(window.devicePixelRatio || 1, this.q.dprCap);
    this.w = w;
    this.h = h;
    this.canvas.width = Math.round(w * this.dpr);
    this.canvas.height = Math.round(h * this.dpr);
    this.layers = [];
    this.schedule();
  }

  /** Un solo frame in coda; il ciclo continuo solo con rotazione automatica ammessa e vista visibile. */
  private schedule(): void {
    if (this.disposed || this.raf || !this.ctx) return;
    this.raf = requestAnimationFrame((ts?: number) => {
      this.raf = 0;
      this.frame(typeof ts === 'number' ? ts : Number.isFinite(this.lastFrame) ? this.lastFrame + this.minFrameMs + 0.1 : 0);
    });
  }

  private frame(now: number): void {
    if (this.disposed || !this.ctx) return;
    const animate = this.state.autoRotate && !this.reduced && this.visible && this.pageVisible;
    const minMs = this.minFrameMs;
    if (now - this.lastFrame < minMs - 1) {
      this.schedule();
      return;
    }
    const dt = Number.isFinite(this.lastFrame) ? Math.min(100, now - this.lastFrame) : minMs;
    this.lastFrame = now;
    if (animate) {
      const spin = this.opts.spinDegPerS ?? SPIN_DEG_PER_S;
      this.state = { ...this.state, yaw_deg: this.state.yaw_deg + (spin * dt) / 1000 };
    }
    const t0 = typeof performance !== 'undefined' ? performance.now() : 0;
    const fading = this.draw(animate);
    this.frames++;
    const spent = (typeof performance !== 'undefined' ? performance.now() : 0) - t0;
    if (!this.worker) {
      // qualità adattiva sul thread principale: macchina lenta -> disco più piccolo
      if (spent > 14) this.adapt = Math.max(0.3, this.adapt * 0.8);
      else if (spent < 5 && this.adapt < 1) this.adapt = Math.min(1, this.adapt * 1.1);
    }
    if (animate || fading) this.schedule();
  }

  /* --------------------------------- disegno --------------------------------- */

  private diskFrame(): DiskFrame {
    const { w, h } = this;
    if (this.state.frame) return this.state.frame;
    const placed = this.opts.place?.(w, h);
    if (placed) return placed;
    const f = defaultFrame(w, h, this.state.zoom ?? 1);
    if (this.opts.radius !== undefined && this.state.zoom === undefined) f.r = Math.max(20, Math.min(w, h) * this.opts.radius);
    return f;
  }

  /** Ritorna true se una dissolvenza è in corso (serve un altro frame). */
  private draw(animate: boolean): boolean {
    const ctx = this.ctx;
    if (!ctx || this.w < 1) return false;
    const { w, h, dpr } = this;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
    const rows = rotationRows(this.state.yaw_deg, this.state.pitch_deg);
    this.drawSky(ctx, rows);

    const now = typeof performance !== 'undefined' ? performance.now() : 0;
    const t = this.fadeFrom ? Math.min(1, (now - this.fadeStart) / FADE_MS) : 1;
    const f = this.diskFrame();
    const dolly = this.fadeFrom ? 0.94 + 0.06 * ease(t) : 1;
    const frame = { cx: f.cx, cy: f.cy, r: f.r * dolly };
    this.complete = false;
    if (BODIES[this.body].emissive) this.drawSun(ctx, frame);
    else this.drawBody(ctx, frame, rows, animate);
    let fading = false;
    if (this.fadeFrom) {
      if (t >= 1) this.fadeFrom = null;
      else {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.globalAlpha = 1 - ease(t);
        ctx.drawImage(this.fadeFrom, 0, 0);
        ctx.globalAlpha = 1;
        fading = true;
      }
    }
    // stato leggibile da test e screenshot: scena caricata e stabile
    const ready = this.complete && (this.stars !== null || this.opts.textures === false) && !this.fadeFrom;
    if (this.el) {
      this.el.dataset.disks = String(this.stats.disks);
      this.el.dataset.shadeMs = this.stats.shadeMs.toFixed(1);
      this.el.dataset.textures = String(this.surfaces.size + this.workerReady.size + this.cache.size + (this.sunImg ? 1 : 0));
      if (ready) this.el.dataset.ready = '1';
      else delete this.el.dataset.ready;
    }

    return fading;
  }

  private drawSky(ctx: CanvasRenderingContext2D, m: number[]): void {
    const { w, h } = this;
    if (this.opts.decor === 'hero') ctx.clearRect(0, 0, w, h);
    else {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
    }
    // centro della vista nel cielo: R^T · (0,0,-1)
    const dx = -m[6]!;
    const dy = -m[7]!;
    const dz = -m[8]!;
    const uc = 0.5 + Math.atan2(dx, -dz) / (2 * Math.PI);
    const vc = 0.5 - Math.asin(Math.max(-1, Math.min(1, dy))) / Math.PI;
    const img = this.stars;
    if (img) {
      const W = img.width;
      const H = img.height;
      const cw = (W * SKY_FOV) / 360;
      const ch = Math.min(H, (cw * h) / w);
      const sy = Math.max(0, Math.min(H - ch, vc * H - ch / 2));
      let sx = (((uc * W - cw / 2) % W) + W) % W;
      ctx.globalAlpha = this.opts.decor === 'hero' ? 0.75 : 0.9;
      const first = Math.min(cw, W - sx);
      ctx.drawImage(img, sx, sy, first, ch, 0, 0, (first / cw) * w, h);
      if (first < cw) {
        sx = 0;
        ctx.drawImage(img, 0, sy, cw - first, ch, (first / cw) * w, 0, ((cw - first) / cw) * w, h);
      }
      ctx.globalAlpha = 1;
    }
    // strati in parallasse: più vicini, scorrono più veloci del cielo; mai con reduced motion
    if (!this.q.parallax || this.reduced) return;
    if (!this.layers.length) {
      const rnd = mulberry32(4720);
      for (const n of [Math.round((w * h) / 9000), Math.round((w * h) / 16000)]) {
        const a = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
          a[i * 3] = rnd();
          a[i * 3 + 1] = rnd();
          a[i * 3 + 2] = 0.15 + rnd() * 0.3;
        }
        this.layers.push(a);
      }
    }
    const pxPerTurn = (w * 360) / SKY_FOV;
    this.layers.forEach((a, li) => {
      const k = li === 0 ? 1.25 : 1.6;
      const ox = uc * pxPerTurn * k;
      const oy = (vc - 0.5) * h * 2 * k;
      ctx.fillStyle = '#dfe6f0';
      for (let i = 0; i < a.length; i += 3) {
        const x = (((a[i]! * w - ox) % w) + w) % w;
        const y = (((a[i + 1]! * h - oy) % h) + h) % h;
        ctx.globalAlpha = a[i + 2]!;
        const s = li === 0 ? 0.8 : 1.1;
        ctx.fillRect(x, y, s, s);
      }
    });
    ctx.globalAlpha = 1;
  }

  private drawSun(ctx: CanvasRenderingContext2D, f: DiskFrame): void {
    const { cx, cy, r } = f;
    // corona morbida: solo un alone di luce, nessuna struttura inventata
    const g = ctx.createRadialGradient(cx, cy, r, cx, cy, r * 2.4);
    g.addColorStop(0, 'rgba(255,150,60,0.42)');
    g.addColorStop(0.35, 'rgba(255,120,40,0.12)');
    g.addColorStop(1, 'rgba(255,100,30,0)');
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = g;
    ctx.fillRect(cx - r * 2.4, cy - r * 2.4, r * 4.8, r * 4.8);
    // il disco copre le stelle dietro di sé (l'immagine viene sommata in modo additivo)
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.arc(cx, cy, r * 1.01, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = 'lighter';
    const img = this.sunImg;
    this.complete = img !== null;
    if (img) {
      const s = r / 0.8; // il disco occupa l'80% del ritaglio
      ctx.drawImage(img, cx - s, cy - s, 2 * s, 2 * s);
    } else {
      ctx.fillStyle = '#c2410c';
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  private shadeParams(S: number, rows: number[]): ShadeParams {
    const b = BODIES[this.body];
    return {
      S,
      rows,
      light: this.state.sunObj ? lightVector(undefined, objToView(rows, this.state.sunObj)) : lightVector(this.state.sun),
      albedo: b.albedo,
      lunar: this.body === 'moon',
      atmosphere: b.atmosphere ?? null,
    };
  }

  private drawBody(ctx: CanvasRenderingContext2D, f: DiskFrame, rows: number[], animate: boolean): void {
    const { cx, cy, r } = f;
    const full = Math.max(48, Math.min(this.opts.maxSample ?? 720, Math.round(2 * r * Math.min(this.dpr, 1.5))));
    let disk: HTMLCanvasElement | null = null;

    if (this.worker) {
      const now = typeof performance !== 'undefined' ? performance.now() : 0;
      const moving = animate || now - this.lastChange < IDLE_MS;
      const S = moving ? Math.max(48, Math.round(full * 0.5)) : full;
      const L = this.state.sunObj
        ? `o${this.state.sunObj.map((c) => c.toFixed(3)).join(',')}`
        : this.state.sun ? `${this.state.sun.az_deg.toFixed(1)},${this.state.sun.el_deg.toFixed(1)}` : '-';
      const key = `${this.body}|${this.workerReady.has(this.body) ? 1 : 0}|${this.state.yaw_deg.toFixed(2)}|${this.state.pitch_deg.toFixed(2)}|${L}|${S}`;
      const hit = this.cache.get(key);
      if (hit) {
        this.shown = { key, body: this.body, canvas: hit };
        this.wantKey = key;
      } else this.request(key, this.shadeParams(S, rows));
      if (this.shown?.body === this.body) disk = this.shown.canvas;
      this.complete = !moving && this.workerReady.has(this.body) && this.shown?.key === key;
      // rifinitura a piena risoluzione quando la vista si ferma
      if (moving && !animate) {
        if (this.idleTimer) clearTimeout(this.idleTimer);
        this.idleTimer = setTimeout(() => {
          this.idleTimer = null;
          this.schedule();
        }, IDLE_MS + 10);
      }
    } else {
      const S = Math.max(48, Math.round(full * this.adapt));
      if (!this.sphere || this.sphereN !== S) {
        this.sphere = document.createElement('canvas');
        this.sphere.width = S;
        this.sphere.height = S;
        this.sphereCtx = this.sphere.getContext('2d');
        this.sphereImg = this.sphereCtx ? this.sphereCtx.createImageData(S, S) : null;
        this.sphereN = S;
      }
      const sctx = this.sphereCtx;
      const img = this.sphereImg;
      if (sctx && img) {
        const surf = this.surfaces.get(this.body);
        const t0 = typeof performance !== 'undefined' ? performance.now() : 0;
        shadeDisk(img.data, this.shadeParams(S, rows), surf?.color ?? null, surf?.relief ?? null);
        this.stats.shadeMs = (typeof performance !== 'undefined' ? performance.now() : 0) - t0;
        sctx.putImageData(img, 0, 0);
        this.stats.disks++;
        disk = this.sphere;
        this.complete = !!surf?.color;
      }
    }
    if (!disk) return;
    ctx.imageSmoothingEnabled = true;
    // ritaglio circolare anti-alias: il bordo del disco ricampionato non mostra la scalettatura
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(disk, cx - r - 1, cy - r - 1, 2 * r + 2, 2 * r + 2);
    ctx.restore();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = null;
    this.ro?.disconnect();
    this.ro = null;
    this.io?.disconnect();
    this.io = null;
    this.mql?.removeEventListener('change', this.onMotionChange);
    this.mql = null;
    if (typeof document.removeEventListener === 'function') document.removeEventListener('visibilitychange', this.onVisibility);
    this.worker?.terminate();
    this.worker = null;
    this.canvas?.remove();
    this.canvas = this.sphere = this.fadeFrom = null;
    this.ctx = this.sphereCtx = null;
    this.sphereImg = null;
    this.surfaces.clear();
    this.cache.clear();
    this.shown = null;
    this.stars = this.sunImg = null;
    this.el = null;
  }
}

export function createCanvas2dViewport(opts: Canvas2dOptions = {}): ViewportPort & { stats: Canvas2dViewport['stats'] } {
  return new Canvas2dViewport(opts);
}

/** Factory con opzioni (es. palco della home); fallisce con Canvas2DUnavailableError senza contesto 2D. */
export function canvas2dViewportFactoryWith(opts: Canvas2dOptions): ViewportFactory {
  return async () => {
    const probe = document.createElement('canvas');
    if (!probe.getContext('2d')) throw new Canvas2DUnavailableError();
    return new Canvas2dViewport(opts);
  };
}

/** Fallisce con Canvas2DUnavailableError se non c'è nemmeno un contesto 2D. */
export const canvas2dViewportFactory: ViewportFactory = canvas2dViewportFactoryWith({});
