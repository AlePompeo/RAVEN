// SPDX-License-Identifier: Apache-2.0
// Remote-sensing style colouring of the map overlays. A cell with no data is NEVER coloured as a value: outside the disc it is
// transparent, inside the disc it is hatched (the "unknown" texture). Scales: sequential (a quantity), categorical (classes).
import type { RavenOverlay } from '../../shell/ravenApi';

export type Rgb = readonly [number, number, number];

/** Viridis-like sequential stops (dark purple to yellow), readable in grey and by colour-blind viewers. */
export const SEQUENTIAL: readonly Rgb[] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
export const CATEGORICAL: readonly Rgb[] = [[31, 119, 180], [255, 127, 14], [44, 160, 44], [214, 39, 40]];

export function sequentialColor(t: number): Rgb {
  const x = Math.min(1, Math.max(0, t)) * (SEQUENTIAL.length - 1);
  const i = Math.min(SEQUENTIAL.length - 2, Math.floor(x));
  const f = x - i;
  const a = SEQUENTIAL[i]!, b = SEQUENTIAL[i + 1]!;
  return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f), Math.round(a[2] + (b[2] - a[2]) * f)];
}

/** CSS gradient of the sequential scale, for the legend bar. */
export const sequentialGradient = (): string => `linear-gradient(90deg, ${SEQUENTIAL.map((c, i) => `rgb(${c.join(',')}) ${Math.round((i / (SEQUENTIAL.length - 1)) * 100)}%`).join(', ')})`;

type Shape = Pick<RavenOverlay, 'size'> & Partial<Pick<RavenOverlay, 'projection' | 'width' | 'height'>>;

/** Width, height and kind of a raster: the south-polar disc is square (`size`), the whole Moon is `width` x `height`. */
export function rasterDims(o: Shape): { w: number; h: number; rect: boolean } {
  const rect = o.projection === 'equirectangular';
  return { w: rect ? o.width ?? o.size : o.size, h: rect ? o.height ?? o.size : o.size, rect };
}

export function decodeOverlay(o: Pick<RavenOverlay, 'data_b64'> & Shape): Uint8Array | null {
  try {
    const bin = atob(o.data_b64);
    const { w, h } = rasterDims(o);
    if (bin.length !== w * h) return null;
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

/** Is cell (x, y) of an n x n raster inside the map disc? */
export const insideDisc = (x: number, y: number, n: number): boolean => Math.hypot((x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1) <= 1;

const hatch = (out: Uint8ClampedArray, p: number, x: number, y: number, a: number): void => {
  if ((x + y) % 6 < 2) { out[p] = 200; out[p + 1] = 200; out[p + 2] = 200; out[p + 3] = Math.round(a / 2); }
};

/**
 * RGBA pixels of an overlay: the value colour at `opacity`, transparent outside the disc (a whole-Moon raster has no outside), and
 * a diagonal hatch (grey, half the opacity) for the cells that carry no data. Returns null when the raster is malformed.
 */
export function overlayPixels(o: Pick<RavenOverlay, 'data_b64' | 'kind' | 'nodata'> & Shape, opacity = 0.75): Uint8ClampedArray | null {
  const values = decodeOverlay(o);
  if (!values) return null;
  const { w, h, rect } = rasterDims(o);
  const out = new Uint8ClampedArray(w * h * 4);
  const a = Math.round(Math.min(1, Math.max(0, opacity)) * 255);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, p = i * 4, v = values[i]!;
      if (!rect && !insideDisc(x, y, w)) continue; // transparent
      if (v === o.nodata) { hatch(out, p, x, y, a); continue; }
      const rgb = o.kind === 'categorical' ? CATEGORICAL[(v - 1) % CATEGORICAL.length]! : sequentialColor((v - 1) / 254);
      out[p] = rgb[0]; out[p + 1] = rgb[1]; out[p + 2] = rgb[2]; out[p + 3] = a;
    }
  }
  return out;
}

type Layer = Pick<RavenOverlay, 'data_b64' | 'nodata'> & Shape;

/**
 * False-colour composite (as done with processed SAR products): red = Sun share, green = Earth share, blue = regional slope, each
 * stretched 0..1 from its own 8-bit raster. A cell with no data in ANY of the three is hatched, never mixed with a zero.
 */
export function compositePixels(sun: Layer, earth: Layer, slope: Layer, opacity = 0.75): Uint8ClampedArray | null {
  const [r, g, b] = [decodeOverlay(sun), decodeOverlay(earth), decodeOverlay(slope)];
  const d = rasterDims(sun), de = rasterDims(earth), ds = rasterDims(slope);
  if (!r || !g || !b || d.w !== de.w || d.h !== de.h || d.w !== ds.w || d.h !== ds.h || d.rect !== de.rect || d.rect !== ds.rect) return null;
  const { w, h, rect } = d;
  const out = new Uint8ClampedArray(w * h * 4);
  const a = Math.round(Math.min(1, Math.max(0, opacity)) * 255);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, p = i * 4;
      if (!rect && !insideDisc(x, y, w)) continue;
      if (r[i] === sun.nodata || g[i] === earth.nodata || b[i] === slope.nodata) { hatch(out, p, x, y, a); continue; }
      out[p] = Math.round(((r[i]! - 1) / 254) * 255); out[p + 1] = Math.round(((g[i]! - 1) / 254) * 255); out[p + 2] = Math.round(((b[i]! - 1) / 254) * 255);
      out[p + 3] = a;
    }
  }
  return out;
}
