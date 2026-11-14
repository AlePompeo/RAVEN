// SPDX-License-Identifier: Apache-2.0
// Shared state of the remote-sensing style overlays (dashboard and /siti): which layer, opacity, the rasters fetched once, the
// RGBA raster for the 3D Moon / globe and the canvas for the polar map. A cell with no data stays hatched, never a value.
import { raven, type RavenOverlay } from '../ravenApi';
import { overlayPixels, compositePixels, rasterDims } from '../../pages/dashboard/overlayColors';

export type Layer = 'none' | 'elevation' | 'slope' | 'coverage' | 'sun' | 'earth' | 'both' | 'sun_gap' | 'earth_gap' | 'suitability' | 'composite' | 'useful';
export type Single = 'elevation' | 'slope' | 'coverage' | 'sun' | 'earth' | 'both' | 'sun_gap' | 'earth_gap';
/** RGBA pixels: the south-polar disc (square, `limit` = latitude at radius 1) or the whole Moon (equirectangular, width x height). */
export interface Raster { pixels: Uint8ClampedArray; size: number; width: number; height: number; limit: number; projection: 'disc' | 'equirectangular' }
export type Scope = 'polar' | 'global';
const LIMIT = -75;
const cache = new Map<string, RavenOverlay>();

export class OverlayController {
  layer = $state<Layer>('none');
  /** 'polar' = the south-polar disc (2 km cells, polar map); 'global' = the whole Moon (15 km cells, 3D Moon). */
  scope = $state<Scope>('polar');
  opacity = $state(0.7);
  busy = $state(false);
  failed = $state(false);
  data = $state.raw<RavenOverlay | null>(null);
  parts = $state.raw<Partial<Record<Single, RavenOverlay>>>({});
  canvas = $state.raw<HTMLCanvasElement | null>(null);
  raster = $state.raw<Raster | null>(null);
  /** The cloud of a site search (a polar raster computed by the server for one brief); shown as the layer 'suitability'. */
  suitability = $state.raw<RavenOverlay | null>(null);

  single = $derived<Single | null>(
    this.layer === 'elevation' || this.layer === 'slope' || this.layer === 'coverage' || this.layer === 'sun' || this.layer === 'earth' || this.layer === 'both' || this.layer === 'sun_gap' || this.layer === 'earth_gap' ? this.layer : null,
  );
  needs = $derived<Single[]>(this.layer === 'composite' ? ['sun', 'earth', 'slope'] : this.single ? [this.single] : []);

  /** Call inside a component's `$effect.root` or `$effect`: fetches what the layer needs and builds the raster. */
  fetchEffect(): (() => void) | void {
    const want = this.needs;
    if (this.layer === 'suitability') { this.parts = {}; this.data = this.suitability; this.failed = false; return; }
    if (!want.length) { this.data = null; this.parts = {}; this.canvas = null; this.raster = null; this.failed = false; return; }
    const ctl = new AbortController();
    this.failed = false;
    const scope = this.scope;
    const ck = (l: Single) => `${scope}:${l}`;
    const missing = want.filter((l) => !cache.has(ck(l)));
    const finish = () => {
      this.parts = Object.fromEntries(want.map((l) => [l, cache.get(ck(l))])) as Partial<Record<Single, RavenOverlay>>;
      this.data = this.layer === 'composite' ? null : cache.get(ck(want[0]!)) ?? null;
    };
    if (!missing.length) { finish(); return; }
    this.busy = true;
    void Promise.all(missing.map((l) => raven.overlay(l, { signal: ctl.signal }, scope).then((r) => ({ l, r })))).then((all) => {
      if (ctl.signal.aborted) return;
      this.busy = false;
      for (const { l, r } of all) if (r.ok) cache.set(ck(l), r.data);
      if (want.every((l) => cache.has(ck(l)))) finish(); else { this.data = null; this.parts = {}; this.failed = true; }
    });
    return () => ctl.abort();
  }

  buildEffect(): void {
    const o = this.data, p = this.parts, a = this.opacity, comp = this.layer === 'composite';
    const px = comp ? (p.sun && p.earth && p.slope ? compositePixels(p.sun, p.earth, p.slope, a) : null) : o ? overlayPixels(o, a) : null;
    const ref = comp ? p.sun : o;
    const { w, h, rect } = ref ? rasterDims(ref) : { w: 0, h: 0, rect: false };
    if (!px) { this.canvas = null; this.raster = null; if (comp ? !!(p.sun && p.earth && p.slope) : !!o) this.failed = true; return; }
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    if (!ctx) { this.canvas = null; this.failed = true; return; }
    ctx.putImageData(new ImageData(px as Uint8ClampedArray<ArrayBuffer>, w, h), 0, 0);
    if (rect) { this.canvas = null; } else {
      const big = document.createElement('canvas'); big.width = 840; big.height = 840;
      const bx = big.getContext('2d');
      if (bx) { bx.imageSmoothingEnabled = false; bx.drawImage(c, 0, 0, 840, 840); }
      this.canvas = bx ? big : c;
    }
    this.raster = { pixels: px as Uint8ClampedArray, size: w, width: w, height: h, limit: LIMIT, projection: rect ? 'equirectangular' : 'disc' };
  }
}
