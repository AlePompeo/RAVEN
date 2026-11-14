// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { CATEGORICAL, compositePixels, decodeOverlay, insideDisc, overlayPixels, rasterDims, sequentialColor } from './overlayColors';

const b64 = (bytes: number[]) => btoa(String.fromCharCode(...bytes));
const raster = (n: number, f: (x: number, y: number) => number) => b64(Array.from({ length: n * n }, (_, i) => f(i % n, Math.floor(i / n))));

describe('overlay colours', () => {
  it('sequential scale runs dark to light and clamps', () => {
    expect(sequentialColor(0)).toEqual([68, 1, 84]);
    expect(sequentialColor(1)).toEqual([253, 231, 37]);
    expect(sequentialColor(-5)).toEqual(sequentialColor(0));
    expect(sequentialColor(9)).toEqual(sequentialColor(1));
    const mid = sequentialColor(0.5);
    expect(mid[1]).toBeGreaterThan(sequentialColor(0)[1]);
  });
  it('decodes only a raster of the declared size', () => {
    expect(decodeOverlay({ data_b64: b64([1, 2, 3, 4]), size: 2 })).toEqual(new Uint8Array([1, 2, 3, 4]));
    expect(decodeOverlay({ data_b64: b64([1, 2, 3]), size: 2 })).toBeNull();
    expect(decodeOverlay({ data_b64: '###', size: 2 })).toBeNull();
  });
  it('no data is transparent outside the disc and hatched inside, never a value colour', () => {
    const n = 16;
    const px = overlayPixels({ data_b64: raster(n, () => 0), size: n, kind: 'sequential', nodata: 0 }, 1)!;
    const alphaAt = (x: number, y: number) => px[(y * n + x) * 4 + 3]!;
    expect(alphaAt(0, 0)).toBe(0); // corner: outside
    let hatched = 0, empty = 0;
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (insideDisc(x, y, n)) { if (alphaAt(x, y) > 0) hatched++; else empty++; }
    expect(hatched).toBeGreaterThan(0);
    expect(empty).toBeGreaterThan(0); // the hatch is a texture, not a fill
    for (let i = 0; i < px.length; i += 4) if (px[i + 3]! > 0) expect([px[i], px[i + 1], px[i + 2]]).toEqual([200, 200, 200]);
  });
  it('colours values and keeps categories distinct', () => {
    const n = 16;
    const seq = overlayPixels({ data_b64: raster(n, () => 255), size: n, kind: 'sequential', nodata: 0 }, 0.5)!;
    const c = (8 * n + 8) * 4;
    expect([seq[c], seq[c + 1], seq[c + 2]]).toEqual([253, 231, 37]);
    expect(seq[c + 3]).toBe(128);
    const cat = overlayPixels({ data_b64: raster(n, (x) => (x < 8 ? 1 : 2)), size: n, kind: 'categorical', nodata: 0 }, 1)!;
    const left = (8 * n + 6) * 4, right = (8 * n + 9) * 4;
    expect([cat[left], cat[left + 1], cat[left + 2]]).toEqual([...CATEGORICAL[0]!]);
    expect([cat[right], cat[right + 1], cat[right + 2]]).toEqual([...CATEGORICAL[1]!]);
  });
});

describe('false-colour composite', () => {
  const n = 16;
  const layer = (f: (x: number, y: number) => number) => ({ data_b64: raster(n, f), size: n, nodata: 0 });
  it('maps Sun to red, Earth to green and slope to blue', () => {
    const px = compositePixels(layer(() => 255), layer(() => 1), layer(() => 128), 1)!;
    const c = (8 * n + 8) * 4;
    expect(px[c]).toBe(255);
    expect(px[c + 1]).toBe(0);
    expect(px[c + 2]).toBe(Math.round((127 / 254) * 255));
    expect(px[c + 3]).toBe(255);
  });
  it('a cell with no data in any layer is hatched and never mixed with a zero', () => {
    const px = compositePixels(layer(() => 255), layer((x) => (x === 8 ? 0 : 200)), layer(() => 100), 1)!;
    for (let y = 0; y < n; y++) {
      const p = (y * n + 8) * 4;
      if (!insideDisc(8, y, n)) continue;
      if (px[p + 3]! > 0) expect([px[p], px[p + 1], px[p + 2]]).toEqual([200, 200, 200]); // the hatch grey, not a colour of the data
    }
  });
  it('refuses rasters of different sizes or malformed rasters', () => {
    expect(compositePixels(layer(() => 1), { data_b64: raster(8, () => 1), size: 8, nodata: 0 }, layer(() => 1))).toBeNull();
    expect(compositePixels(layer(() => 1), layer(() => 1), { data_b64: '###', size: n, nodata: 0 })).toBeNull();
  });
});

describe('whole-Moon (equirectangular) rasters', () => {
  const w = 8, h = 4;
  const rect = (f: (x: number, y: number) => number) => ({
    data_b64: b64(Array.from({ length: w * h }, (_, i) => f(i % w, Math.floor(i / w)))), size: w, width: w, height: h,
    projection: 'equirectangular' as const, nodata: 0, kind: 'sequential' as const,
  });
  it('takes its size from width and height, and refuses a wrong length', () => {
    expect(rasterDims(rect(() => 1))).toEqual({ w, h, rect: true });
    expect(decodeOverlay(rect(() => 1))?.length).toBe(w * h);
    expect(decodeOverlay({ ...rect(() => 1), height: 5 })).toBeNull();
  });
  it('has no outside: every corner is coloured, and only no-data cells are hatched', () => {
    const px = overlayPixels(rect((x) => (x === 3 ? 0 : 255)), 1)!;
    expect(px.length).toBe(w * h * 4);
    const alpha = (x: number, y: number) => px[(y * w + x) * 4 + 3]!;
    expect(alpha(0, 0)).toBe(255); // a corner of a disc would be transparent
    expect(alpha(7, 3)).toBe(255);
    for (let y = 0; y < h; y++) if (alpha(3, y) > 0) expect(px[(y * w + 3) * 4]).toBe(200); // the hatch grey, not a value colour
  });
  it('a composite of whole-Moon layers keeps the shape and refuses a disc mixed with a rectangle', () => {
    const l = (v: number) => rect(() => v);
    const px = compositePixels(l(255), l(1), l(128), 1)!;
    expect(px.length).toBe(w * h * 4);
    expect(px[0]).toBe(255);
    expect(compositePixels(l(1), l(1), { data_b64: b64(Array.from({ length: w * h }, () => 1)), size: w, nodata: 0 })).toBeNull();
  });
});
