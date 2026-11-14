// SPDX-License-Identifier: Apache-2.0
// Caricamento delle mappe: immagini decodificate (per drawImage / WebGL) e pixel (per l'ombreggiatura
// software). Cache per URL con rilascio esplicito al cambio di corpo (memoria limitata).
import type { Tex } from './shading';

type Img = ImageBitmap | HTMLImageElement;

const images = new Map<string, Promise<Img>>();

function viaElement(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = 'async';
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`immagine non caricabile: ${url}`));
    img.src = url;
  });
}

/** Immagine decodificata (ImageBitmap se disponibile). */
export function loadImage(url: string): Promise<Img> {
  let p = images.get(url);
  if (!p) {
    p = (async () => {
      if (typeof createImageBitmap === 'function' && typeof fetch === 'function') {
        try {
          const blob = await (await fetch(url)).blob();
          return await createImageBitmap(blob);
        } catch {
          /* ripiego sull'elemento <img> */
        }
      }
      return viaElement(url);
    })();
    p.catch(() => images.delete(url));
    images.set(url, p);
  }
  return p;
}

/** Pixel RGBA dell'immagine (canvas temporaneo, poi rilasciato). */
export async function loadTex(url: string): Promise<Tex> {
  const img = await loadImage(url);
  const w = img.width;
  const h = img.height;
  const canvas: OffscreenCanvas | HTMLCanvasElement =
    typeof OffscreenCanvas === 'function' ? new OffscreenCanvas(w, h) : Object.assign(document.createElement('canvas'), { width: w, height: h });
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null;
  if (!ctx) throw new Error('Canvas 2D non disponibile');
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, w, h).data;
  canvas.width = canvas.height = 1;
  return { w, h, data };
}

/** Rilascia l'immagine dalla cache (e la memoria della bitmap). */
export function releaseImage(url: string): void {
  const p = images.get(url);
  if (!p) return;
  images.delete(url);
  void p.then((img) => {
    if ('close' in img && typeof img.close === 'function') img.close();
  }, () => {});
}

/** Precarica quando il browser è inattivo (non blocca nulla, errori ignorati). */
export function preloadIdle(urls: string[]): void {
  const run = () => urls.forEach((u) => void loadImage(u).catch(() => {}));
  const ric = (globalThis as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
  if (typeof ric === 'function') ric(run, { timeout: 4000 });
  else setTimeout(run, 1500);
}

/** Numero di immagini in cache (diagnostica e test di memoria). */
export function cachedImageCount(): number {
  return images.size;
}
