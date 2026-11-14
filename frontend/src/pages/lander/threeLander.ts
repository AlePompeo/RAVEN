// SPDX-License-Identifier: Apache-2.0
// Renderer WebGL (three.js, stesso chunk pigro del visualizzatore e di /wave) della Scena lander: terreno LOLA con luce
// radente gia' applicata nei vertici, rover illustrativo e antenna in X-band, cielo NASA SVS, cono del
// fascio con l'HPBW vero, tubo della prima zona di Fresnel colorato dallo stato del link, Terra al diametro angolare vero.
import type * as ThreeNS from 'three';
import { WebGLUnavailableError } from '../../viewports/errors';
import type { ViewportFactory, ViewportPort } from '../../viewports/port';
import { ASSETS } from '../../viewports/bodies/assets';
import { starsAsset } from '../../viewports/bodies/registry';
import { detectQuality } from '../../viewports/quality';
import { beamDirection, pointing, STATE_INFO } from './model';
import { beamLength, coneRing, DEG, EARTH_DISTANCE_M, eyeOf, fresnelRings, terrainHeightAt, tubeIndices, type LanderViewState } from './view';

type Three = typeof ThreeNS;
const DPR_CAP = { hi: 2, lo: 1.5 } as const;
const BG = 0x05070b;

export function skyWorldFromTexture(T: Three, m: [number[], number[], number[]]): ThreeNS.Matrix4 {
  // NASA's celestial map is centred on RA=0 and RA increases left.
  // Texture direction (x,y,z) is (ICRF x, ICRF z, -ICRF y).
  return new T.Matrix4().set(
    m[0]![0]!, m[0]![2]!, -m[0]![1]!, 0,
    m[1]![0]!, m[1]![2]!, -m[1]![1]!, 0,
    m[2]![0]!, m[2]![2]!, -m[2]![1]!, 0,
    0, 0, 0, 1,
  );
}

class ThreeLander implements ViewportPort {
  private el: HTMLElement | null = null;
  private renderer: ThreeNS.WebGLRenderer | null = null;
  private scene: ThreeNS.Scene | null = null;
  private camera: ThreeNS.PerspectiveCamera | null = null;
  private dyn: ThreeNS.Group | null = null; // contenuto che dipende dalla scena API (ricostruito)
  private overlays: ThreeNS.Group | null = null;
  private terrainObj: ThreeNS.Mesh | null = null;
  private sunLight: ThreeNS.DirectionalLight | null = null;
  private beacon: ThreeNS.Mesh | null = null;
  private ridgeMark: ThreeNS.Mesh | null = null;
  private skyTexture: ThreeNS.Texture | null = null;
  private regolithTexture: ThreeNS.CanvasTexture | null = null;
  private ro: ResizeObserver | null = null;
  private raf = 0;
  private disposed = false;
  private state: LanderViewState | null = null;
  private seenScene = -1;
  private seenTerrain = -1;
  private seenKey = '';
  private frames = 0;
  private w = 0;
  private h = 0;

  constructor(
    private readonly T: Three,
    private readonly renderer0: ThreeNS.WebGLRenderer,
  ) {}

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    const T = this.T;
    this.el = el;
    const r = this.renderer0;
    this.renderer = r;
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR_CAP[this.state?.tier ?? 'hi']));
    r.outputColorSpace = T.SRGBColorSpace;
    r.setClearColor(new T.Color(BG), 1);
    r.domElement.setAttribute('aria-hidden', 'true');
    r.domElement.style.cssText = 'display:block;width:100%;height:100%';
    el.appendChild(r.domElement);
    this.scene = new T.Scene();
    this.camera = new T.PerspectiveCamera(45, 1.6, 0.3, 120_000);
    this.scene.add(new T.AmbientLight(0xffffff, 0.35));
    this.sunLight = new T.DirectionalLight(0xfff4e0, 2.2);
    this.scene.add(this.sunLight);
    this.loadSky();
    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(el);
    }
    this.resize();
    this.schedule();
  }

  private loadSky(): void {
    const T = this.T;
    const canvas = this.renderer!.domElement;
    canvas.dataset.sky = 'loading';
    const url = ASSETS[starsAsset(detectQuality().tier)].url;
    this.skyTexture = new T.TextureLoader().load(url, (texture) => {
      if (this.disposed || !this.scene) {
        texture.dispose();
        return;
      }
      texture.mapping = T.EquirectangularReflectionMapping;
      texture.colorSpace = T.SRGBColorSpace;
      this.scene.background = texture;
      canvas.dataset.sky = 'nasa';
      this.schedule();
    }, undefined, (error) => {
      if (this.disposed) return;
      canvas.dataset.sky = 'unavailable';
      this.el?.dispatchEvent(new Event('lander-sky-error'));
      console.warn('NASA star map could not be loaded', error);
    });
  }

  update(state: unknown): void {
    if (this.disposed) return;
    this.state = state as LanderViewState;
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
    this.camera.updateProjectionMatrix();
    // ResizeObserver runs after animation frames: repaint before the cleared buffer can be composited.
    this.render();
  }

  private schedule(): void {
    if (this.disposed || this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.render();
    });
  }

  private disposeGroup(g: ThreeNS.Object3D): void {
    g.traverse((o) => {
      const m = o as ThreeNS.Mesh;
      m.geometry?.dispose();
      const mat = m.material as ThreeNS.Material | ThreeNS.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
      else mat?.dispose();
    });
  }

  private mat(color: number | string, opts: ThreeNS.MeshBasicMaterialParameters = {}): ThreeNS.MeshBasicMaterial {
    return new this.T.MeshBasicMaterial({ color: new this.T.Color(color), ...opts });
  }

  /** Rover e antenna X-band da primitive: telaio, ruote, palo e parabola orientata sull'asse del fascio. */
  private buildRover(st: LanderViewState): ThreeNS.Group {
    const T = this.T;
    const s = st.scene!;
    const g = new T.Group();
    const body = new T.MeshLambertMaterial({ color: 0xc9ccd2 });
    const dark = new T.MeshLambertMaterial({ color: 0x2b2f36 });
    const gold = new T.MeshLambertMaterial({ color: 0xd9a441 });
    const panelMaterial = new T.MeshLambertMaterial({ color: 0x19375f });
    const trim = new T.MeshLambertMaterial({ color: 0x738291 });
    const chassis = new T.Mesh(new T.BoxGeometry(1.5, 0.45, 1.0), body);
    chassis.position.set(-1.1, 0.62, 0);
    g.add(chassis);
    const lower = new T.Mesh(new T.BoxGeometry(1.3, 0.16, 0.9), gold);
    lower.position.set(-1.1, 0.37, 0);
    g.add(lower);
    const panel = new T.Mesh(new T.BoxGeometry(1.2, 0.04, 0.9), panelMaterial);
    panel.position.set(-1.1, 0.87, 0);
    g.add(panel);
    for (const x of [-1.4, -1.1, -0.8]) {
      const strip = new T.Mesh(new T.BoxGeometry(0.012, 0.008, 0.86), trim);
      strip.position.set(x, 0.894, 0);
      g.add(strip);
    }
    for (const z of [-0.22, 0.22]) {
      const strip = new T.Mesh(new T.BoxGeometry(1.15, 0.008, 0.012), trim);
      strip.position.set(-1.1, 0.895, z);
      g.add(strip);
    }
    for (const x of [-1.7, -0.5]) {
      for (const z of [-0.62, 0.62]) {
        const wheel = new T.Mesh(new T.CylinderGeometry(0.3, 0.3, 0.2, 18), dark);
        wheel.rotation.x = Math.PI / 2;
        wheel.position.set(x, 0.3, z);
        g.add(wheel);
        const hub = new T.Mesh(new T.CylinderGeometry(0.11, 0.11, 0.215, 12), trim);
        hub.rotation.x = Math.PI / 2;
        hub.position.copy(wheel.position);
        g.add(hub);
        const suspension = new T.Mesh(new T.BoxGeometry(0.08, 0.12, 0.3), trim);
        suspension.position.set(x, 0.48, z * 0.75);
        g.add(suspension);
      }
    }
    const instrument = new T.Mesh(new T.BoxGeometry(0.25, 0.18, 0.25), body);
    instrument.position.set(-1.55, 1.02, -0.24);
    g.add(instrument);
    const lens = new T.Mesh(new T.CylinderGeometry(0.045, 0.045, 0.025, 12), dark);
    lens.rotation.z = Math.PI / 2;
    lens.position.set(-1.41, 1.02, -0.24);
    g.add(lens);
    const mastH = s.antenna.mastM * st.vExag;
    const mast = new T.Mesh(new T.CylinderGeometry(0.035, 0.035, Math.max(0.1, mastH - 0.6), 8), dark);
    mast.position.set(-0.5, 0.6 + (mastH - 0.6) / 2, 0);
    g.add(mast);
    // parabola: calotta sferica con la parte concava verso l'asse del fascio
    const d = beamDirection(s.earth.elDeg, st.errorDeg);
    const axis = new T.Vector3(d[0], d[1] * st.vExag, 0).normalize();
    const dishR = Math.max(0.15, s.antenna.diameterM / 2);
    const dish = new T.Mesh(new T.SphereGeometry(dishR * 1.15, 24, 8, 0, Math.PI * 2, 0, Math.asin(1 / 1.15)), new T.MeshLambertMaterial({ color: 0xeeeeee, side: T.DoubleSide }));
    dish.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), axis.clone().negate());
    dish.position.set(0, mastH, 0);
    g.add(dish);
    const feed = new T.Mesh(new T.CylinderGeometry(0.012, 0.012, dishR * 0.9, 6), gold);
    feed.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), axis);
    feed.position.copy(axis.clone().multiplyScalar(dishR * 0.45)).add(new T.Vector3(0, mastH, 0));
    g.add(feed);
    const arm = new T.Mesh(new T.BoxGeometry(0.5, 0.03, 0.03), dark); // braccio dal palo al fuoco della parabola
    arm.position.set(-0.25, mastH, 0);
    g.add(arm);
    return g;
  }

  private line(points: number[], color: number | string, opacity = 1): ThreeNS.Line {
    const T = this.T;
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.BufferAttribute(new Float32Array(points), 3));
    const l = new T.Line(g, new T.LineBasicMaterial({ color: new T.Color(color), transparent: opacity < 1, opacity }));
    l.frustumCulled = false;
    return l;
  }

  /** Costruisce tutto cio' che dipende dalla scena dell'API e dalle scale di disegno. */
  private rebuild(st: LanderViewState): void {
    const T = this.T;
    if (this.dyn) {
      this.scene?.remove(this.dyn);
      this.disposeGroup(this.dyn);
    }
    const g = new T.Group();
    this.dyn = g;
    const overlay = new T.Group();
    this.overlays = overlay;
    g.add(overlay);
    this.beacon = null;
    this.ridgeMark = null;
    const s = st.scene;
    if (!s || !this.scene) return;
    const info = STATE_INFO[s.link.state];
    const ex = st.vExag;
    const el = s.earth.elDeg * DEG;
    const h = s.antenna.mastM * ex;
    const apex: [number, number, number] = [0, h, 0];

    // profilo lungo l'azimut della Terra (dove il motore ha cercato il crinale)
    const p = s.terrain.profile;
    const pl: number[] = [];
    for (let i = 0; i < p.e.length; i++) pl.push(p.e[i]!, p.u[i]! * ex + 0.4, 0);
    overlay.add(this.line(pl, 0x6ee7ff));

    // linea di vista geometrica fino alla Terra
    const dl = new T.Vector3(Math.cos(el), Math.sin(el) * ex, 0).normalize();
    overlay.add(this.line([0, h, 0, dl.x * EARTH_DISTANCE_M, h + dl.y * EARTH_DISTANCE_M, 0], 0xffffff, 0.9));

    // crinale: cima, segmento fino alla linea di vista, marcatore
    const tip: [number, number, number] = [s.ridge.e, s.ridge.u * ex, 0];
    const losAtRidge = h + (s.ridge.e * Math.tan(el)) * ex;
    overlay.add(this.line([tip[0], tip[1], 0, tip[0], losAtRidge, 0], 0xffb340));
    this.ridgeMark = new T.Mesh(new T.SphereGeometry(1, 14, 10), this.mat(0xffb340));
    this.ridgeMark.position.set(...tip);
    overlay.add(this.ridgeMark);

    // Terra: diametro angolare vero (la distanza e' simbolica)
    const er = EARTH_DISTANCE_M * Math.tan((s.earth.angularDiameterDeg / 2) * DEG);
    const earth = new T.Mesh(new T.SphereGeometry(er, 28, 18), this.mat(0x3b82f6));
    earth.position.set(dl.x * EARTH_DISTANCE_M, h + dl.y * EARTH_DISTANCE_M, 0);
    g.add(earth);
    const cap = new T.Mesh(new T.SphereGeometry(er * 1.003, 20, 10, 0, Math.PI * 2, 0, 0.5), this.mat(0xf1f5f9));
    cap.position.copy(earth.position);
    g.add(cap);

    // tubo di Fresnel
    const rings = fresnelRings(s, st.tubeScale, ex);
    const tg = new T.BufferGeometry();
    tg.setAttribute('position', new T.BufferAttribute(rings.positions, 3));
    tg.setIndex(new T.BufferAttribute(tubeIndices(rings.segments, rings.sides), 1));
    const tube = new T.Mesh(tg, new T.MeshBasicMaterial({ color: new T.Color(info.color), transparent: true, opacity: 0.22, side: T.DoubleSide, depthWrite: false }));
    tube.renderOrder = 2;
    tube.frustumCulled = false;
    overlay.add(tube);
    // anello al crinale
    let kr = 0;
    for (let k = 1; k <= rings.segments; k++) if (Math.abs(rings.d[k]! - s.ridge.d1M) < Math.abs(rings.d[kr]! - s.ridge.d1M)) kr = k;
    const ring: number[] = [];
    for (let a = 0; a <= rings.sides; a++) {
      const o = (kr * rings.sides + (a % rings.sides)) * 3;
      ring.push(rings.positions[o]!, rings.positions[o + 1]!, rings.positions[o + 2]!);
    }
    overlay.add(this.line(ring, info.color));

    // cono del fascio (HPBW vero) con asse puntato verso la Terra piu' l'errore di puntamento
    const pt = pointing(s, st.errorDeg);
    const L = beamLength(s);
    const dir = beamDirection(s.earth.elDeg, st.errorDeg);
    const base = coneRing(apex, dir, s.antenna.hpbwDeg / 2, L, ex);
    const sides = base.length / 3;
    const cpos = new Float32Array((sides + 1) * 3);
    cpos.set(apex, 0);
    cpos.set(base, 3);
    const cidx: number[] = [];
    for (let a = 0; a < sides; a++) cidx.push(0, 1 + a, 1 + ((a + 1) % sides));
    const cg = new T.BufferGeometry();
    cg.setAttribute('position', new T.BufferAttribute(cpos, 3));
    cg.setIndex(cidx);
    const coneColor = pt.beyond ? STATE_INFO.blocked.color : STATE_INFO.open.color;
    const cone = new T.Mesh(cg, new T.MeshBasicMaterial({ color: new T.Color(coneColor), transparent: true, opacity: 0.16, side: T.DoubleSide, depthWrite: false, wireframe: false }));
    cone.renderOrder = 3;
    cone.frustumCulled = false;
    overlay.add(cone);
    const edge: number[] = [];
    for (let a = 0; a <= sides; a++) {
      const o = (a % sides) * 3;
      edge.push(base[o]!, base[o + 1]!, base[o + 2]!);
    }
    overlay.add(this.line(edge, coneColor, 0.8));

    g.add(this.buildRover(st));
    // richiamo per le viste lontane: il modello (1,5 m) non si vedrebbe
    this.beacon = new T.Mesh(new T.SphereGeometry(1, 12, 8), this.mat(0xfff176));
    this.beacon.position.set(...apex);
    overlay.add(this.beacon);
    this.scene.add(g);
  }

  private render(): void {
    const st = this.state;
    const r = this.renderer;
    const cam = this.camera;
    if (this.disposed || !r || !cam || !this.scene) return;
    if (st) {
      const key = `${st.vExag}|${st.tubeScale}|${st.errorDeg}`;
      if (st.sceneGen !== this.seenScene || key !== this.seenKey) {
        this.rebuild(st);
        this.seenScene = st.sceneGen;
        this.seenKey = key;
      }
      if (st.terrainGen !== this.seenTerrain) {
        this.buildTerrain(st);
        this.seenTerrain = st.terrainGen;
      }
      if (this.overlays) this.overlays.visible = st.showOverlays;
      r.domElement.dataset.overlays = st.showOverlays ? 'visible' : 'hidden';
      const m = st.scene?.sky?.icrfToScene;
      if (m) {
        this.scene.backgroundRotation.setFromRotationMatrix(skyWorldFromTexture(this.T, m));
      } else {
        this.scene.backgroundRotation.set(0, 0, 0);
      }
      r.domElement.dataset.skyOrientation = m ? 'site-time' : 'illustrative';
      const d = st.sun.dir;
      this.sunLight?.position.set(d[0], d[2], -d[1]);
      cam.fov = st.cam.fovDeg;
      cam.updateProjectionMatrix();
      const e = eyeOf(st.cam);
      const ground = st.terrain ? terrainHeightAt(st.terrain, e[0], e[2]) : null;
      cam.position.set(e[0], ground === null ? e[1] : Math.max(e[1], ground + 1.5), e[2]);
      cam.lookAt(...st.cam.target);
      r.domElement.dataset.camera = JSON.stringify(st.cam);
      this.beacon?.scale.setScalar(Math.max(0.2, st.cam.dist / 160));
      this.ridgeMark?.scale.setScalar(Math.max(1.5, st.cam.dist / 90));
    }
    r.render(this.scene, cam);
    this.frames++;
    r.domElement.dataset.frames = String(this.frames);
  }

  private buildTerrain(st: LanderViewState): void {
    const T = this.T;
    if (this.terrainObj) {
      this.scene?.remove(this.terrainObj);
      this.terrainObj.geometry.dispose();
      (this.terrainObj.material as ThreeNS.Material).dispose();
      this.terrainObj = null;
    }
    const tm = st.terrain;
    if (!tm || !this.scene) return;
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(tm.positions, 3));
    geo.setAttribute('color', new T.BufferAttribute(tm.colors, 3));
    const uv = new Float32Array(tm.positions.length / 3 * 2);
    for (let i = 0; i < uv.length / 2; i++) {
      uv[i * 2] = tm.positions[i * 3]! / 16;
      uv[i * 2 + 1] = tm.positions[i * 3 + 2]! / 16;
    }
    geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
    geo.setIndex(new T.BufferAttribute(tm.indices, 1));
    if (!this.regolithTexture) {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 128;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Unable to create the regolith texture');
      const image = ctx.createImageData(canvas.width, canvas.height);
      let seed = 7241;
      for (let i = 0; i < image.data.length; i += 4) {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const shade = 198 + (seed >>> 27);
        image.data[i] = image.data[i + 1] = image.data[i + 2] = shade;
        image.data[i + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
      this.regolithTexture = new T.CanvasTexture(canvas);
      this.regolithTexture.wrapS = this.regolithTexture.wrapT = T.RepeatWrapping;
      this.regolithTexture.colorSpace = T.SRGBColorSpace;
      this.regolithTexture.anisotropy = Math.min(4, this.renderer?.capabilities.getMaxAnisotropy() ?? 1);
    }
    this.terrainObj = new T.Mesh(geo, new T.MeshBasicMaterial({ vertexColors: true, map: this.regolithTexture, side: T.DoubleSide }));
    this.terrainObj.frustumCulled = false;
    this.scene.add(this.terrainObj);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    if (this.dyn) this.disposeGroup(this.dyn);
    if (this.terrainObj) {
      this.terrainObj.geometry.dispose();
      (this.terrainObj.material as ThreeNS.Material).dispose();
    }
    this.skyTexture?.dispose();
    this.skyTexture = null;
    this.regolithTexture?.dispose();
    this.regolithTexture = null;
    const r = this.renderer;
    if (r) {
      r.domElement.remove();
      r.dispose();
      try {
        r.forceContextLoss();
      } catch {
        /* contesto gia' perso */
      }
    }
    this.renderer = null;
    this.scene = null;
    this.state = null;
    this.el = null;
  }
}

export const createThreeLander = (T: Three, renderer: ThreeNS.WebGLRenderer): ViewportPort => new ThreeLander(T, renderer);

export const threeLanderFactory: ViewportFactory = async () => {
  const T = await import('three');
  let renderer: ThreeNS.WebGLRenderer;
  try {
    renderer = new T.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
  } catch (e) {
    throw new WebGLUnavailableError(undefined, { cause: e });
  }
  return new ThreeLander(T, renderer);
};
