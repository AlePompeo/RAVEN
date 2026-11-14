// SPDX-License-Identifier: Apache-2.0
// Renderer WebGL (three.js, chunk pigro condiviso con il visualizzatore) della superficie d'onda: una mesh con
// colori per vertice (viridis, luce già applicata come nel ripiego Canvas 2D), cornice, piano e curva della sezione.
// I buffer della mesh sono quelli di `surface.ts` e vengono riempiti sul posto: nessuna allocazione per fotogramma.
import type * as ThreeNS from 'three';
import { WebGLUnavailableError } from '../../viewports/errors';
import type { ViewportFactory, ViewportPort } from '../../viewports/port';
import {
  createMesh,
  eyePosition,
  fitOf,
  FOV_DEG,
  FRAME_SEGMENTS,
  fillMesh,
  fillSliceLine,
  fillSlicePlane,
  hasSurface,
  TARGET_Y,
  worldX,
  type MeshBuffers,
  type WaveScene,
} from './surface';


type Three = typeof ThreeNS;
const DPR_CAP = { hi: 2, lo: 1.5 } as const;

class ThreeWave implements ViewportPort {
  private el: HTMLElement | null = null;
  private renderer: ThreeNS.WebGLRenderer | null = null;
  private scene: ThreeNS.Scene | null = null;
  private camera: ThreeNS.PerspectiveCamera | null = null;
  private surface: ThreeNS.Mesh | null = null;
  private geo: ThreeNS.BufferGeometry | null = null;
  private mesh: MeshBuffers | null = null;
  private plane: ThreeNS.Mesh | null = null;
  private outline: ThreeNS.LineLoop | null = null;
  private curve: ThreeNS.Line | null = null;
  private planeAttr: ThreeNS.BufferAttribute | null = null;
  private curveAttr: ThreeNS.BufferAttribute | null = null;
  private owned: { dispose(): void }[] = [];
  private ro: ResizeObserver | null = null;
  private raf = 0;
  private disposed = false;
  private state: WaveScene | null = null;
  private seenGeom = -1;
  private seenZ = -1;
  private eye = new Float32Array(3);
  private frames = 0;
  private w = 0;
  private h = 0;

  constructor(
    private readonly T: Three,
    private readonly preRenderer: ThreeNS.WebGLRenderer,
  ) {}

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    const T = this.T;
    this.el = el;
    const r = this.preRenderer;
    this.renderer = r;
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR_CAP[this.state?.tier ?? 'hi']));
    // i colori della mesh sono già sRGB e la luce è nei vertici: nessuna conversione in uscita
    if ('outputColorSpace' in r) (r as { outputColorSpace: string }).outputColorSpace = T.LinearSRGBColorSpace;
    r.setClearColor(new T.Color().setRGB(11 / 255, 15 / 255, 23 / 255, T.LinearSRGBColorSpace), 1);    r.domElement.setAttribute('aria-hidden', 'true');
    r.domElement.style.cssText = 'display:block;width:100%;height:100%';
    el.appendChild(r.domElement);

    this.scene = new T.Scene();
    this.camera = new T.PerspectiveCamera(FOV_DEG, 1.6, 0.05, 50);

    const frameGeo = new T.BufferGeometry();
    frameGeo.setAttribute('position', new T.BufferAttribute(new Float32Array(FRAME_SEGMENTS), 3));
    const frameMat = new T.LineBasicMaterial({ color: new T.Color().setRGB(0.63, 0.67, 0.75, T.LinearSRGBColorSpace) });
    const frame = new T.LineSegments(frameGeo, frameMat);
    frame.frustumCulled = false;
    this.scene.add(frame);

    this.planeAttr = new T.BufferAttribute(new Float32Array(12), 3);
    this.planeAttr.setUsage(T.DynamicDrawUsage);
    const planeGeo = new T.BufferGeometry();
    planeGeo.setAttribute('position', this.planeAttr);
    planeGeo.setIndex([0, 1, 2, 0, 2, 3]);
    const planeMat = new T.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.13, side: T.DoubleSide, depthWrite: false });
    this.plane = new T.Mesh(planeGeo, planeMat);
    this.plane.frustumCulled = false;
    this.plane.renderOrder = 2;
    const outGeo = new T.BufferGeometry();
    outGeo.setAttribute('position', this.planeAttr);
    const outMat = new T.LineBasicMaterial({ color: 0xffffff });
    this.outline = new T.LineLoop(outGeo, outMat);
    this.outline.frustumCulled = false;
    this.scene.add(this.plane, this.outline);
    this.owned.push(frameGeo, frameMat, planeGeo, planeMat, outGeo, outMat);

    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(el);
    }
    this.resize();
    this.schedule();
  }

  update(state: unknown): void {
    if (this.disposed) return;
    this.state = state as WaveScene;
    this.schedule();
  }

  private resize(): void {
    if (this.disposed || !this.el || !this.renderer || !this.camera) return;
    const w = Math.max(1, this.el.clientWidth);
    const h = Math.max(1, this.el.clientHeight);
    if (w === this.w && h === this.h) return;
    this.w = w;
    this.h = h;
    this.renderer.setSize(this.w, this.h, false);
    this.camera.aspect = this.w / this.h;
    this.camera.zoom = fitOf(this.w, this.h);
    this.camera.updateProjectionMatrix();
    this.render();
  }

  private schedule(): void {
    if (this.disposed || this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.render();
    });
  }

  /** Nuova mesh solo se cambiano le dimensioni della griglia; altrimenti si riempiono i buffer esistenti. */
  private rebuild(sc: WaveScene): void {
    const T = this.T;
    if (!this.mesh || this.mesh.nx !== sc.nx || this.mesh.ny !== sc.ny) {
      if (this.surface) {
        this.scene?.remove(this.surface);
        this.geo?.dispose();
        (this.surface.material as ThreeNS.Material).dispose();
      }
      if (this.curve) {
        this.scene?.remove(this.curve);
        this.curve.geometry.dispose();
        (this.curve.material as ThreeNS.Material).dispose();
      }
      const m = createMesh(sc.nx, sc.ny);
      this.mesh = m;
      const geo = new T.BufferGeometry();
      const pos = new T.BufferAttribute(m.positions, 3);
      const col = new T.BufferAttribute(m.colors, 3);
      pos.setUsage(T.DynamicDrawUsage);
      col.setUsage(T.DynamicDrawUsage);
      geo.setAttribute('position', pos);
      geo.setAttribute('color', col);
      geo.setIndex(new T.BufferAttribute(m.indices, 1));
      this.geo = geo;
      this.surface = new T.Mesh(geo, new T.MeshBasicMaterial({ vertexColors: true, side: T.DoubleSide }));
      this.surface.frustumCulled = false;
      this.scene?.add(this.surface);

      this.curveAttr = new T.BufferAttribute(new Float32Array(sc.ny * 3), 3);
      this.curveAttr.setUsage(T.DynamicDrawUsage);
      const cg = new T.BufferGeometry();
      cg.setAttribute('position', this.curveAttr);
      this.curve = new T.Line(cg, new T.LineBasicMaterial({ color: 0xffffff }));
      this.curve.frustumCulled = false;
      this.curve.renderOrder = 3;
      this.scene?.add(this.curve);
    }
    fillMesh(this.mesh, sc.grid, sc.xs, sc.zTop);
    (this.geo!.getAttribute('position') as ThreeNS.BufferAttribute).needsUpdate = true;
    (this.geo!.getAttribute('color') as ThreeNS.BufferAttribute).needsUpdate = true;
    this.seenGeom = sc.geom;
    this.seenZ = sc.zTop;
  }

  private render(): void {
    const sc = this.state;
    const r = this.renderer;
    const cam = this.camera;
    if (this.disposed || !r || !cam || !this.scene) return;
    const has = !!sc && hasSurface(sc);
    if (this.surface) this.surface.visible = has;
    if (this.curve) this.curve.visible = has;
    if (this.plane) this.plane.visible = has;
    if (this.outline) this.outline.visible = has;
    if (sc && has) {
      if (this.seenGeom !== sc.geom || this.seenZ !== sc.zTop || !this.mesh) this.rebuild(sc);
      fillSlicePlane(this.planeAttr!.array as Float32Array, worldX(sc.cursor, sc.xs[0]!, sc.xs[sc.nx - 1]!));
      this.planeAttr!.needsUpdate = true;
      fillSliceLine(this.curveAttr!.array as Float32Array, sc.grid, sc.nx, sc.ny, sc.xs, sc.cursor, sc.zTop);
      this.curveAttr!.needsUpdate = true;
    }
    if (sc) {
      eyePosition(sc.camera, this.eye);
      cam.position.set(this.eye[0]!, this.eye[1]!, this.eye[2]!);
    } else cam.position.set(2, 2, 3);
    cam.lookAt(0, TARGET_Y, 0);
    r.render(this.scene, cam);
    this.frames++;
    r.domElement.dataset.frames = String(this.frames);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    for (const o of this.owned) o.dispose();
    this.geo?.dispose();
    (this.surface?.material as ThreeNS.Material | undefined)?.dispose();
    this.curve?.geometry.dispose();
    (this.curve?.material as ThreeNS.Material | undefined)?.dispose();
    const r = this.renderer;
    if (r) {
      r.domElement.remove();
      r.dispose();
      try {
        r.forceContextLoss();
      } catch {
        /* contesto già perso */
      }
    }
    this.renderer = null;
    this.scene = null;
    this.state = null;
    this.mesh = null;
    this.el = null;
  }
}

/** Esposto per i test: modulo three e renderer iniettabili. */
export const createThreeWave = (T: Three, renderer: ThreeNS.WebGLRenderer): ViewportPort => new ThreeWave(T, renderer);

export const threeWaveFactory: ViewportFactory = async () => {
  const T = await import('three');
  let renderer: ThreeNS.WebGLRenderer;
  try {
    renderer = new T.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
  } catch (e) {
    throw new WebGLUnavailableError(undefined, { cause: e });
  }
  return new ThreeWave(T, renderer);
};
