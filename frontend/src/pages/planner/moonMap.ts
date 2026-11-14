// SPDX-License-Identifier: Apache-2.0
// South-polar azimuthal equidistant map of the Moon: radius 1 at `limit` degrees S, the pole at the centre, longitude clockwise from the top.
// Shared by the report figure and the site picker.

/** Re-projects the equirectangular colour map `im` into a W x H disc on `ctx` (outside the disc stays transparent). */
export function renderPolarTexture(ctx: CanvasRenderingContext2D, im: HTMLImageElement, W: number, H: number, limit: number): void {
  const src = document.createElement('canvas'); src.width = im.naturalWidth; src.height = im.naturalHeight;
  const sc = src.getContext('2d');
  if (!sc) return;
  sc.drawImage(im, 0, 0);
  const sd = sc.getImageData(0, 0, src.width, src.height).data;
  const od = ctx.createImageData(W, H);
  const R = W / 2;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const dx = (x + 0.5 - R) / R, dy = (y + 0.5 - R) / R, rho = Math.hypot(dx, dy), o = (y * W + x) * 4;
    if (rho > 1) { od.data[o + 3] = 0; continue; }
    const lat = -90 + rho * (90 + limit), lon = (Math.atan2(dx, -dy) * 180) / Math.PI;
    const u = Math.min(src.width - 1, Math.floor(((lon + 180) / 360) * src.width));
    const v = Math.min(src.height - 1, Math.floor(((90 - lat) / 180) * src.height));
    const i = (v * src.width + u) * 4;
    od.data[o] = sd[i]!; od.data[o + 1] = sd[i + 1]!; od.data[o + 2] = sd[i + 2]!; od.data[o + 3] = 255;
  }
  ctx.putImageData(od, 0, 0);
}

/** Pixel of a point (latitude, longitude east) on a W x H polar map; null north of the limit. */
export function pixelFromPolar(lat: number, lon: number, W: number, H: number, limit: number): { x: number; y: number } | null {
  if (lat > limit) return null;
  const rho = (90 + lat) / (90 + limit), th = (lon * Math.PI) / 180;
  return { x: W / 2 + rho * (W / 2) * Math.sin(th), y: H / 2 - rho * (H / 2) * Math.cos(th) };
}

/** Latitude and longitude east (-180..180) under a pixel; null outside the disc. */
export function polarFromPixel(x: number, y: number, W: number, H: number, limit: number): { lat: number; lon: number } | null {
  const dx = (x - W / 2) / (W / 2), dy = (y - H / 2) / (H / 2), rho = Math.hypot(dx, dy);
  if (rho > 1) return null;
  const lon = (Math.atan2(dx, -dy) * 180) / Math.PI;
  return { lat: -90 + rho * (90 + limit), lon };
}
