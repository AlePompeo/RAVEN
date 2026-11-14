// SPDX-License-Identifier: Apache-2.0
// Worker dell'ombreggiatura software: decodifica le mappe (OffscreenCanvas) e calcola i dischi fuori dal
// thread principale. Protocollo: 'load' (corpo + URL) -> 'ready' | 'error'; 'frame' -> 'frame' (buffer trasferito).
import { buildRelief, shadeDisk, type Relief, type ShadeParams, type Tex } from './shading';

interface Surface {
  color: Tex;
  relief: Relief | null;
}

const surfaces = new Map<string, Surface>();

async function tex(url: string): Promise<Tex> {
  const bmp = await createImageBitmap(await (await fetch(url)).blob());
  const c = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('OffscreenCanvas 2D non disponibile');
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return { w: c.width, h: c.height, data: ctx.getImageData(0, 0, c.width, c.height).data };
}

type Msg =
  | { type: 'load'; key: string; color: string; height?: { url: string; kmMin: number; kmMax: number; radiusKm: number } }
  | { type: 'drop'; key: string }
  | { type: 'frame'; id: number; key: string; params: ShadeParams };

const ctx = self as unknown as { postMessage(m: unknown, t?: Transferable[]): void; onmessage: ((e: MessageEvent<Msg>) => void) | null };

ctx.onmessage = (e) => {
  const m = e.data;
  if (m.type === 'drop') {
    surfaces.delete(m.key);
    return;
  }
  if (m.type === 'load') {
    void (async () => {
      try {
        const color = await tex(m.color);
        const relief = m.height ? buildRelief(await tex(m.height.url), m.height.kmMin, m.height.kmMax, m.height.radiusKm) : null;
        surfaces.set(m.key, { color, relief });
        ctx.postMessage({ type: 'ready', key: m.key });
      } catch (err) {
        ctx.postMessage({ type: 'error', key: m.key, message: String(err) });
      }
    })();
    return;
  }
  const s = surfaces.get(m.key);
  const buf = new Uint8ClampedArray(m.params.S * m.params.S * 4);
  const t0 = performance.now();
  shadeDisk(buf, m.params, s?.color ?? null, s?.relief ?? null);
  ctx.postMessage({ type: 'frame', id: m.id, key: m.key, S: m.params.S, ms: performance.now() - t0, buf }, [buf.buffer]);
};
