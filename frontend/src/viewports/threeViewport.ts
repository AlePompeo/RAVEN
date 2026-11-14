// SPDX-License-Identifier: Apache-2.0
// Renderer WebGL (three.js, chunk pigro). Camera ortografica in pixel CSS: il disco del corpo coincide con la
// geometria usata dai marcatori DOM e dal renderer Canvas 2D. Shader del corpo = stessa formula di shading.ts
// (luce in spazio lineare, rilievo dalle pendenze dell'altimetria LOLA, modello lunare a bordo piatto, bordo
// atmosferico per Terra e Marte). Cielo: mappa stellare SVS campionata per direzione di vista. Sole emissivo
// (immagine SDO + alone additivo), mai illuminato.
import type * as ThreeNS from 'three';
import type { ViewportFactory, ViewportPort } from './port';
import { WEBGL_FALLBACK_MESSAGE, WebGLUnavailableError } from './errors';
import { ASSETS } from './bodies/assets';
import { BODIES, starsAsset } from './bodies/registry';
import { detectQuality, type Quality } from './quality';
import { azElToVector, defaultFrame, DEFAULT_SCENE, isSceneState, rotationRows, type BodyId, type DiskFrame, type OverlayRaster, type SceneState } from './scene';
import { AMBIENT, RELIEF_EXAGGERATION } from './shading';
import { loadImage, releaseImage } from './textures';

type Three = typeof ThreeNS;

const REDUCED = '(prefers-reduced-motion: reduce)';
const FADE_MS = 480;
const SKY_FOV = 70;

export { WEBGL_FALLBACK_MESSAGE, WebGLUnavailableError };

function createRenderer(T: Three): ThreeNS.WebGLRenderer {
  try {
    return new T.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
  } catch (e) {
    throw new WebGLUnavailableError(undefined, { cause: e });
  }
}

const BODY_VS = /* glsl */ `
varying vec3 vObj;
void main() {
  vObj = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const BODY_FS = /* glsl */ `
precision highp float;
#define PI 3.141592653589793
uniform sampler2D colorMap;
uniform sampler2D heightMap;
uniform float hasColor;
uniform float hasHeight;
uniform vec2 heightSize;
uniform float kmRange;
uniform float radiusKm;
uniform vec3 lightObj;
uniform vec3 viewObj;
uniform float albedo;
uniform float lunar;
uniform vec3 atm;
uniform float hasAtm;
uniform float opacity;
uniform float ambient;
uniform float exaggeration;
uniform sampler2D overlayMap;
uniform float hasOverlay;
uniform float overlayLimit;
uniform float overlayMode;
varying vec3 vObj;
vec3 toLin(vec3 c) { return pow(c, vec3(2.2)); }
float hAt(vec2 uv) { return texture2D(heightMap, uv).r * kmRange * exaggeration; }
void main() {
  vec3 m = normalize(vObj);
  float u = atan(m.x, m.z) / (2.0 * PI) + 0.5;
  float v = 0.5 - asin(clamp(m.y, -1.0, 1.0)) / PI;
  vec3 n = m;
  float cl = max(length(m.xz), 1e-4);
  float sl = m.x / cl;
  float cL = m.z / cl;
  if (hasHeight > 0.5) {
    vec2 du = vec2(1.0 / heightSize.x, 0.0);
    vec2 dv = vec2(0.0, 1.0 / heightSize.y);
    vec2 uv = vec2(u, v);
    float dLon = 2.0 * PI * radiusKm / heightSize.x * max(0.05, cl);
    float dLat = PI * radiusKm / heightSize.y;
    float se = (hAt(uv + du) - hAt(uv - du)) / (2.0 * dLon);
    float sn = (hAt(uv - dv) - hAt(uv + dv)) / (2.0 * dLat);
    se = clamp(se, -0.6, 0.6);
    sn = clamp(sn, -0.6, 0.6);
    n = normalize(vec3(m.x - se * cL + sn * m.y * sl, m.y - sn * cl, m.z + se * sl + sn * m.y * cL));
  }
  float mu0g = dot(m, lightObj);
  float mu0 = mu0g < -0.05 ? 0.0 : max(0.0, dot(n, lightObj));
  float b = mu0;
  if (lunar > 0.5) {
    float mu = max(0.02, dot(n, viewObj));
    b = mu0 > 0.0 ? 0.62 * (2.0 * mu0 / (mu0 + mu)) * 0.5 + 0.38 * mu0 : 0.0;
  }
  b = albedo * b + ambient;
  vec3 base = hasColor > 0.5 ? toLin(texture2D(colorMap, vec2(u, v)).rgb) : vec3(0.18);
  // the overlay is DATA, not sunlight: it stays readable on the night side (a floor of 55 % brightness) and keeps the relief shading
  vec3 ovCol = vec3(0.0);
  float ovA = 0.0;
  if (hasOverlay > 0.5 && overlayMode > 0.5) {
    vec4 ovg = texture2D(overlayMap, vec2(u, v));
    ovCol = toLin(ovg.rgb);
    ovA = ovg.a;
  } else if (hasOverlay > 0.5) {
    float latd = degrees(asin(clamp(m.y, -1.0, 1.0)));
    if (latd <= overlayLimit) {
      float rho = (90.0 + latd) / (90.0 + overlayLimit);
      float lon = atan(m.x, m.z);
      vec4 ov = texture2D(overlayMap, vec2(0.5 + 0.5 * rho * sin(lon), 0.5 - 0.5 * rho * cos(lon)));
      ovCol = toLin(ov.rgb);
      ovA = ov.a;
    }
  }
  vec3 col = base * b;
  col = mix(col, ovCol * (0.55 + 0.45 * clamp(b, 0.0, 1.0)), ovA);
  if (hasAtm > 0.5) {
    float f = 1.0 - max(0.0, dot(m, viewObj));
    col += atm * f * f * f * clamp(mu0g + 0.35, 0.0, 1.0) * 0.55;
  }
  gl_FragColor = vec4(pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2)), opacity);
}`;

const SKY_VS = /* glsl */ `
varying vec2 vNdc;
void main() {
  vNdc = position.xy;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;

const SKY_FS = /* glsl */ `
precision highp float;
#define PI 3.141592653589793
uniform sampler2D stars;
uniform float hasStars;
uniform mat3 invRot;
uniform vec2 halfTan;
uniform float strength;
varying vec2 vNdc;
void main() {
  if (hasStars < 0.5) { gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }
  vec3 d = normalize(invRot * vec3(vNdc.x * halfTan.x, vNdc.y * halfTan.y, -1.0));
  float u = 0.5 + atan(d.x, -d.z) / (2.0 * PI);
  float v = 0.5 - asin(clamp(d.y, -1.0, 1.0)) / PI;
  gl_FragColor = vec4(texture2D(stars, vec2(u, v)).rgb * strength, 1.0);
}`;

const SUN_FS = /* glsl */ `
precision highp float;
uniform sampler2D map;
uniform float hasMap;
uniform float opacity;
varying vec2 vUv;
void main() {
  // il piano copre 2,4 raggi solari per lato; il ritaglio SDO copre 1,25 raggi
  vec2 p = vUv * 2.0 - 1.0;
  float rr = length(p) * 2.4;
  vec2 tuv = 0.5 + p * (2.4 / 1.25) * 0.5;
  bool inTex = all(greaterThanEqual(tuv, vec2(0.0))) && all(lessThanEqual(tuv, vec2(1.0)));
  vec3 disk = vec3(0.0);
  if (inTex) disk = hasMap > 0.5 ? texture2D(map, vec2(tuv.x, 1.0 - tuv.y)).rgb : vec3(0.76, 0.25, 0.05) * step(rr, 1.0);
  // alone: luce che decresce fuori dal disco (nessuna struttura inventata)
  float g = rr > 1.0 ? 0.42 * exp(-(rr - 1.0) * 1.8) * smoothstep(2.4, 1.6, rr) : 0.0;
  // alfa 1 dentro il disco (copre le stelle), 0 fuori (l'alone si somma al cielo): premoltiplicato
  float inside = 1.0 - smoothstep(0.995, 1.01, rr);
  gl_FragColor = vec4((disk + vec3(1.0, 0.55, 0.22) * g) * opacity, inside * opacity);
}`;

const PLANE_VS = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

class ThreeViewport implements ViewportPort {
  private el: HTMLElement | null = null;
  private renderer: ThreeNS.WebGLRenderer | null = null;
  private scene: ThreeNS.Scene | null = null;
  private camera: ThreeNS.OrthographicCamera | null = null;
  private body: ThreeNS.Mesh | null = null;
  private bodyMat: ThreeNS.ShaderMaterial | null = null;
  private sun: ThreeNS.Mesh | null = null;
  private sunMat: ThreeNS.ShaderMaterial | null = null;
  private skyMat: ThreeNS.ShaderMaterial | null = null;
  private textures = new Map<string, ThreeNS.Texture>();
  private ro: ResizeObserver | null = null;
  private mql: MediaQueryList | null = null;
  private raf = 0;
  private reduced = false;
  private disposed = false;
  private state: SceneState = { ...DEFAULT_SCENE };
  private bodyId: BodyId = 'moon';
  private w = 1;
  private h = 1;
  private fadeStart = -Infinity;
  private readonly q: Quality;
  /** Diagnostica (test di memoria): texture vive e frame disegnati. */
  stats = { textures: 0, frames: 0 };

  constructor(
    private readonly T: Three,
    private readonly preRenderer: ThreeNS.WebGLRenderer | null = null,
  ) {
    this.q = detectQuality();
  }

  private readonly onMotionChange = (): void => {
    this.reduced = this.mql?.matches ?? false;
    this.schedule();
  };

  mount(el: HTMLElement): void {
    if (this.disposed || this.el) return;
    this.el = el;
    const T = this.T;
    try {
      this.renderer = this.preRenderer ?? createRenderer(T);
    } catch (e) {
      // segnalato allo strato di selezione (select.ts), che passa a Canvas 2D
      this.el = null;
      this.renderer = null;
      throw e instanceof WebGLUnavailableError ? e : new WebGLUnavailableError(undefined, { cause: e });
    }
    const r = this.renderer;
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.q.dprCap));
    if ('outputColorSpace' in r) (r as { outputColorSpace: string }).outputColorSpace = T.LinearSRGBColorSpace;
    r.domElement.setAttribute('aria-hidden', 'true');
    r.domElement.style.display = 'block';
    r.domElement.style.width = '100%';
    r.domElement.style.height = '100%';
    el.appendChild(r.domElement);

    this.scene = new T.Scene();
    this.camera = new T.OrthographicCamera(-1, 1, 1, -1, -10000, 10000);
    this.camera.position.set(0, 0, 1000);

    // cielo: triangolo/rettangolo a schermo intero disegnato per primo
    this.skyMat = new T.ShaderMaterial({
      vertexShader: SKY_VS,
      fragmentShader: SKY_FS,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        stars: { value: null },
        hasStars: { value: 0 },
        invRot: { value: new T.Matrix3() },
        halfTan: { value: new T.Vector2(1, 1) },
        strength: { value: 0.9 },
      },
    });
    const sky = new T.Mesh(new T.PlaneGeometry(2, 2), this.skyMat);
    sky.frustumCulled = false;
    sky.renderOrder = -1;
    this.scene.add(sky);

    this.mql = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED) : null;
    this.reduced = this.mql?.matches ?? false;
    this.mql?.addEventListener('change', this.onMotionChange);

    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(el);
    }
    void this.texture(ASSETS[starsAsset(this.q.tier)].url).then((t) => {
      if (!t || !this.skyMat) return;
      this.skyMat.uniforms.stars!.value = t;
      this.skyMat.uniforms.hasStars!.value = 1;
      this.schedule();
    });
    this.buildBody(this.bodyId, false);
    this.resize();
    this.applyState();
    this.schedule();
  }

  private hostYaw = Number.NaN;

  update(state: unknown): void {
    if (this.disposed || !isSceneState(state)) return;
    const next = state.body ?? 'moon';
    // la rotazione automatica fa avanzare l'angolo qui dentro: se chi chiama non lo ha cambiato (nuovo campione di
    // telemetria, ridimensionamento, stop della rotazione) la scena non deve tornare indietro all'angolo vecchio
    const keepYaw = state.yaw_deg === this.hostYaw;
    this.hostYaw = state.yaw_deg;
    this.state = keepYaw ? { ...state, yaw_deg: this.state.yaw_deg } : { ...state };
    if (next !== this.bodyId) this.switchBody(next);
    this.applyState();
    this.schedule();
  }

  /* ----------------------------------- mappe ----------------------------------- */

  private async texture(url: string): Promise<ThreeNS.Texture | null> {
    const hit = this.textures.get(url);
    if (hit) return hit;
    try {
      const img = await loadImage(url);
      if (this.disposed) return null;
      const t = new this.T.Texture(img as unknown as HTMLImageElement);
      t.flipY = false;
      t.colorSpace = this.T.NoColorSpace;
      t.generateMipmaps = false;
      t.minFilter = this.T.LinearFilter;
      t.magFilter = this.T.LinearFilter;
      t.wrapS = this.T.RepeatWrapping;
      t.wrapT = this.T.ClampToEdgeWrapping;
      t.needsUpdate = true;
      this.textures.set(url, t);
      this.stats.textures = this.textures.size;
      return t;
    } catch {
      return null;
    }
  }

  private dropTexture(url: string): void {
    const t = this.textures.get(url);
    if (t) t.dispose();
    this.textures.delete(url);
    releaseImage(url);
    this.stats.textures = this.textures.size;
  }

  private buildBody(id: BodyId, fade: boolean): void {
    const T = this.T;
    if (!this.scene) return;
    const def = BODIES[id];
    const tier = this.q.tier;
    if (def.emissive) {
      this.sunMat = new T.ShaderMaterial({
        vertexShader: PLANE_VS,
        fragmentShader: SUN_FS,
        transparent: true,
        blending: T.CustomBlending,
        blendSrc: T.OneFactor,
        blendDst: T.OneMinusSrcAlphaFactor,
        depthWrite: false,
        uniforms: { map: { value: null }, hasMap: { value: 0 }, opacity: { value: fade ? 0 : 1 } },
      });
      this.sun = new T.Mesh(new T.PlaneGeometry(2, 2), this.sunMat);
      this.scene.add(this.sun);
      void this.texture(ASSETS[def.color[tier]].url).then((t) => {
        if (!t || this.bodyId !== id || !this.sunMat) return;
        this.sunMat.uniforms.map!.value = t;
        this.sunMat.uniforms.hasMap!.value = 1;
        this.schedule();
      });
    } else {
      this.bodyMat = new T.ShaderMaterial({
        vertexShader: BODY_VS,
        fragmentShader: BODY_FS,
        transparent: true,
        uniforms: {
          colorMap: { value: null },
          heightMap: { value: null },
          hasColor: { value: 0 },
          hasHeight: { value: 0 },
          heightSize: { value: new T.Vector2(1, 1) },
          kmRange: { value: def.height ? def.height.kmMax - def.height.kmMin : 0 },
          radiusKm: { value: def.height?.radiusKm ?? 1 },
          lightObj: { value: new T.Vector3(0, 0, 1) },
          viewObj: { value: new T.Vector3(0, 0, 1) },
          albedo: { value: def.albedo },
          lunar: { value: id === 'moon' ? 1 : 0 },
          atm: { value: new T.Vector3(...(def.atmosphere ?? [0, 0, 0])) },
          hasAtm: { value: def.atmosphere ? 1 : 0 },
          opacity: { value: fade ? 0 : 1 },
          ambient: { value: AMBIENT },
          exaggeration: { value: RELIEF_EXAGGERATION },
          overlayMap: { value: null },
          hasOverlay: { value: 0 },
          overlayLimit: { value: -75 },
          overlayMode: { value: 0 },
        },
      });
      this.body = new T.Mesh(new T.SphereGeometry(1, 128, 64), this.bodyMat);
      this.scene.add(this.body);
      void this.texture(ASSETS[def.color[tier]].url).then((t) => {
        if (!t || this.bodyId !== id || !this.bodyMat) return;
        this.bodyMat.uniforms.colorMap!.value = t;
        this.bodyMat.uniforms.hasColor!.value = 1;
        this.schedule();
      });
      if (def.height) {
        const ha = ASSETS[def.height[tier]];
        void this.texture(ha.url).then((t) => {
          if (!t || this.bodyId !== id || !this.bodyMat) return;
          this.bodyMat.uniforms.heightMap!.value = t;
          this.bodyMat.uniforms.heightSize!.value.set(ha.width, ha.height);
          this.bodyMat.uniforms.hasHeight!.value = 1;
          this.schedule();
        });
      }
    }
    this.fadeStart = fade ? performance.now() : -Infinity;
  }

  private disposeBody(): void {
    for (const m of [this.body, this.sun]) {
      if (!m) continue;
      this.scene?.remove(m);
      m.geometry.dispose();
      (m.material as ThreeNS.Material).dispose();
    }
    this.body = this.sun = null;
    this.bodyMat = this.sunMat = null;
    this.overlayTex?.dispose();
    this.overlayTex = null;
    this.overlaySrc = null;
  }

  private switchBody(next: BodyId): void {
    const prev = BODIES[this.bodyId];
    this.disposeBody();
    for (const t of ['hi', 'lo'] as const) {
      this.dropTexture(ASSETS[prev.color[t]].url);
      if (prev.height) this.dropTexture(ASSETS[prev.height[t]].url);
    }
    this.bodyId = next;
    this.buildBody(next, !this.reduced);
  }

  /* ----------------------------------- vista ----------------------------------- */

  private resize(): void {
    if (this.disposed || !this.el || !this.renderer || !this.camera) return;
    const w = Math.max(1, this.el.clientWidth);
    const h = Math.max(1, this.el.clientHeight || Math.round(w * 0.6));
    if (w === this.w && h === this.h) return;
    this.w = w;
    this.h = h;
    this.renderer.setSize(w, h, false);
    this.camera.left = -w / 2;
    this.camera.right = w / 2;
    this.camera.top = h / 2;
    this.camera.bottom = -h / 2;
    this.camera.updateProjectionMatrix();
    const fx = Math.tan(((SKY_FOV / 2) * Math.PI) / 180);
    this.skyMat?.uniforms.halfTan!.value.set(fx, (fx * h) / w);
    this.applyState();
    this.draw();
  }

  private frame(): DiskFrame {
    return this.state.frame ?? defaultFrame(this.w, this.h, this.state.zoom ?? 1);
  }

  private applyState(): void {
    const T = this.T;
    const rows = rotationRows(this.state.yaw_deg, this.state.pitch_deg);
    const R = new T.Matrix3().set(...(rows as [number, number, number, number, number, number, number, number, number]));
    const Rt = R.clone().transpose();
    this.skyMat?.uniforms.invRot!.value.copy(Rt);
    const now = typeof performance !== 'undefined' ? performance.now() : 0;
    const t = Math.min(1, Math.max(0, (now - this.fadeStart) / FADE_MS));
    const e = 1 - (1 - t) ** 3;
    const f = this.frame();
    const r = f.r * (t < 1 ? 0.94 + 0.06 * e : 1);
    const x = f.cx - this.w / 2;
    const y = this.h / 2 - f.cy;
    if (this.bodyMat) this.applyOverlay(this.bodyId === 'moon' ? this.state.overlay ?? null : null);
    if (this.body && this.bodyMat) {
      this.body.position.set(x, y, 0);
      this.body.scale.setScalar(r);
      this.body.setRotationFromMatrix(new T.Matrix4().setFromMatrix3(R));
      const so = this.state.sunObj;
      const sunV = this.state.sun ? azElToVector(this.state.sun) : [0.45, 0.3, 0.84];
      // sunObj e' gia' nello spazio-oggetto (assi del viewer): nessuna rotazione di vista
      const L = so
        ? new T.Vector3(so[0], so[1], so[2]).normalize()
        : new T.Vector3(sunV[0], sunV[1], sunV[2]).normalize().applyMatrix3(Rt);
      this.bodyMat.uniforms.lightObj!.value.copy(L);
      this.bodyMat.uniforms.viewObj!.value.set(0, 0, 1).applyMatrix3(Rt);
      this.bodyMat.uniforms.opacity!.value = t < 1 ? e : 1;
    }
    if (this.sun && this.sunMat) {
      this.sun.position.set(x, y, 0);
      this.sun.scale.setScalar(r * 2.4);
      this.sunMat.uniforms.opacity!.value = t < 1 ? e : 1;
    }
  }

  private overlaySrc: unknown = null;
  private overlayTex: ThreeNS.DataTexture | null = null;

  /** Carica (o toglie) la sovramappa: texture a celle nette (nearest), niente interpolazione fra dati e vuoti. */
  private applyOverlay(o: OverlayRaster | null): void {
    if (!this.bodyMat || o === this.overlaySrc) return;
    this.overlaySrc = o;
    const u = this.bodyMat.uniforms;
    this.overlayTex?.dispose();
    this.overlayTex = null;
    if (!o) { u.hasOverlay!.value = 0; u.overlayMap!.value = null; return; }
    const T = this.T;
    const tex = new T.DataTexture(new Uint8Array(o.pixels.buffer, o.pixels.byteOffset, o.pixels.byteLength), o.width ?? o.size, o.height ?? o.size, T.RGBAFormat);
    tex.magFilter = T.NearestFilter;
    tex.minFilter = T.NearestFilter;
    tex.generateMipmaps = false;
    tex.needsUpdate = true;
    this.overlayTex = tex;
    u.overlayMap!.value = tex;
    u.overlayLimit!.value = o.limit;
    u.overlayMode!.value = o.projection === 'equirectangular' ? 1 : 0;
    u.hasOverlay!.value = 1;
  }

  /** Un solo frame in coda; il ciclo continuo solo con rotazione automatica o dissolvenza in corso. */
  private schedule(): void {
    if (this.disposed || this.raf || !this.renderer) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.draw();
    });
  }

  private draw(): void {
    if (this.disposed || !this.renderer || !this.scene || !this.camera) return;
    const animate = this.state.autoRotate && !this.reduced;
    if (animate) this.state = { ...this.state, yaw_deg: this.state.yaw_deg + 0.3 };
    const fading = typeof performance !== 'undefined' && performance.now() - this.fadeStart < FADE_MS;
    this.applyState();
    this.renderer.render(this.scene, this.camera);
    this.stats.frames++;
    // stato leggibile da test e screenshot: mappe e cielo caricati, nessuna dissolvenza
    const u = this.bodyMat?.uniforms;
    const loaded = u ? u.hasColor!.value === 1 && (!BODIES[this.bodyId].height || u.hasHeight!.value === 1) : this.sunMat?.uniforms.hasMap!.value === 1;
    const ready = loaded && this.skyMat?.uniforms.hasStars!.value === 1 && !fading;
    if (this.el) {
      this.el.dataset.textures = String(this.textures.size);
      if (ready) this.el.dataset.ready = '1';
      else delete this.el.dataset.ready;
    }
    if (animate || fading) this.schedule();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.ro?.disconnect();
    this.ro = null;
    this.mql?.removeEventListener('change', this.onMotionChange);
    this.mql = null;
    this.disposeBody();
    this.overlayTex?.dispose();
    this.textures.forEach((t) => t.dispose());
    this.textures.clear();
    if (this.scene) {
      this.scene.traverse((o) => {
        const m = o as ThreeNS.Mesh;
        m.geometry?.dispose();
        const mat = m.material as ThreeNS.Material | ThreeNS.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else mat?.dispose();
      });
      this.scene.clear();
    }
    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.domElement.remove();
    }
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.skyMat = null;
    this.el = null;
  }
}

/** Esposto per i test: permette di iniettare un modulo three con renderer finto. */
export function createThreeViewport(T: Three): ViewportPort {
  return new ThreeViewport(T);
}

/** Three.js viene importato qui dentro: finisce in un chunk separato dal bundle iniziale. */
export const threeViewportFactory: ViewportFactory = async () => {
  const T = await import('three');
  // il renderer si crea qui: se WebGL manca la factory fallisce (WebGLUnavailableError) e
  // lo strato di selezione passa a Canvas 2D invece di mostrare solo testo.
  return new ThreeViewport(T, createRenderer(T));
};
