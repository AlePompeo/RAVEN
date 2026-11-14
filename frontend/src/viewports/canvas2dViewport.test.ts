// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canvas2dViewportFactory, createCanvas2dViewport } from './canvas2dViewport';
import { Canvas2DUnavailableError } from './errors';

interface Call {
  name: string;
  args: unknown[];
  alpha: number;
}

/** Contesto 2D finto che registra le chiamate (jsdom non ha Canvas 2D). */
function makeCtx(calls: Call[]): CanvasRenderingContext2D {
  const props: Record<string, unknown> = { globalAlpha: 1 };
  const grad = { addColorStop() {} };
  return new Proxy({} as Record<string, unknown>, {
    get(_t, k: string) {
      if (k in props) return props[k];
      return (...args: unknown[]) => {
        calls.push({ name: k, args, alpha: props.globalAlpha as number });
        if (k === 'createImageData') {
          const [w, h] = args as [number, number];
          return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
        }
        if (k.startsWith('create') && k.endsWith('Gradient')) return grad;
        if (k === 'measureText') return { width: 10 };
        return undefined;
      };
    },
    set(_t, k: string, v) {
      props[k] = v;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
}

class FakeMql {
  matches = false;
  listeners = new Set<() => void>();
  addEventListener(_t: string, fn: () => void): void {
    this.listeners.add(fn);
  }
  removeEventListener(_t: string, fn: () => void): void {
    this.listeners.delete(fn);
  }
  set(matches: boolean): void {
    this.matches = matches;
    [...this.listeners].forEach((fn) => fn());
  }
}

let calls: Call[];
let mql: FakeMql;
let queue: Map<number, FrameRequestCallback>;
let nextId: number;
let roCallbacks: Set<() => void>;
let size: { w: number; h: number };

function step(ts?: number): void {
  const cbs = [...queue.values()];
  queue.clear();
  cbs.forEach((cb) => cb(ts as number));
}
const count = (n: string) => calls.filter((c) => c.name === n).length;
const base = { yaw_deg: 0, pitch_deg: 15, autoRotate: false };
const opts = { textures: false };

function host(): HTMLElement {
  const el = document.createElement('div');
  Object.defineProperty(el, 'clientWidth', { get: () => size.w });
  Object.defineProperty(el, 'clientHeight', { get: () => size.h });
  return el;
}

beforeEach(() => {
  calls = [];
  size = { w: 400, h: 300 };
  mql = new FakeMql();
  queue = new Map();
  nextId = 1;
  roCallbacks = new Set();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((id: string) =>
    id === '2d' ? makeCtx(calls) : null) as never);
  vi.stubGlobal('matchMedia', () => mql);
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    queue.set(nextId, cb);
    return nextId++;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => queue.delete(id));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      private cb: () => void;
      constructor(cb: () => void) {
        this.cb = cb;
      }
      observe(): void {
        roCallbacks.add(this.cb);
      }
      disconnect(): void {
        roCallbacks.delete(this.cb);
      }
    },
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('canvas2dViewport', () => {
  it('draws the scene: real-map sphere (shaded per pixel), sky, no canvas text', () => {
    const v = createCanvas2dViewport(opts);
    const el = host();
    v.mount(el);
    v.update({ ...base, sun: { az_deg: 120, el_deg: 35 }, earth: { az_deg: 10, el_deg: 25 } });
    step();
    expect(el.querySelector('canvas')).not.toBeNull();
    expect(el.querySelector('canvas')!.getAttribute('aria-hidden')).toBe('true');
    expect(count('putImageData')).toBe(1);
    expect(count('drawImage')).toBeGreaterThanOrEqual(1); // disco
    expect(count('fillRect')).toBeGreaterThanOrEqual(1); // cielo nero
    expect(count('clip')).toBe(1);
    // etichette e marcatori sono pulsanti DOM nella pagina, non testo nel canvas
    expect(count('fillText')).toBe(0);
    v.dispose();
  });

  it('draws the Sun as an emissive image with a glow: no per-pixel shading, no terminator', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    v.update({ ...base, body: 'sun' });
    step();
    expect(count('putImageData')).toBe(0);
    expect(count('createRadialGradient')).toBe(1);
    expect(count('fillText')).toBe(0);
    v.dispose();
  });

  it('switching body redraws and ignores unknown bodies', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    v.update({ ...base, body: 'mars' });
    step();
    expect(count('putImageData')).toBe(1);
    queue.clear(); // salta la dissolvenza
    v.update({ ...base, body: 'pluto' }); // non valido: ignorato
    expect(queue.size).toBe(0);
    v.dispose();
  });

  it('redraws on state change, only once per frame, and idles otherwise', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    step();
    const n = count('putImageData');
    v.update({ ...base, yaw_deg: 40 });
    v.update({ ...base, yaw_deg: 50 });
    expect(queue.size).toBe(1);
    step();
    expect(count('putImageData')).toBe(n + 1);
    expect(queue.size).toBe(0); // niente ciclo continuo senza autoRotate
    v.update('not a scene'); // ignorato
    expect(queue.size).toBe(0);
    v.dispose();
  });

  it('does not draw after dispose; update/dispose are safe and idempotent', () => {
    const v = createCanvas2dViewport(opts);
    const el = host();
    v.mount(el);
    v.update({ ...base, autoRotate: true });
    expect(queue.size).toBe(1);
    v.dispose();
    v.dispose();
    expect(queue.size).toBe(0);
    const n = calls.length;
    v.update({ ...base, yaw_deg: 90 });
    step();
    expect(calls.length).toBe(n);
    expect(el.querySelector('canvas')).toBeNull();
  });

  it('animates only with autoRotate and reacts to prefers-reduced-motion changes', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    v.update({ ...base, autoRotate: true });
    step(1000);
    step(1020);
    expect(queue.size).toBe(1); // ciclo continuo
    mql.set(true);
    step(1040); // ultimo frame statico
    expect(queue.size).toBe(0);
    const frozen = count('putImageData');
    step(1060);
    expect(count('putImageData')).toBe(frozen);
    mql.set(false);
    expect(queue.size).toBe(1);
    v.dispose();
  });

  it('does not loop when reduced motion is already on at mount', () => {
    mql.matches = true;
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    v.update({ ...base, autoRotate: true });
    step();
    expect(queue.size).toBe(0);
    v.dispose();
  });

  it('caps the frame rate at 60 fps (skips early frames)', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    v.update({ ...base, autoRotate: true });
    step(1000);
    const n = count('putImageData');
    step(1005); // troppo presto
    expect(count('putImageData')).toBe(n);
    expect(queue.size).toBe(1);
    step(1017);
    expect(count('putImageData')).toBe(n + 1);
    v.dispose();
  });

  it('handles resize with DPR and redraws', () => {
    vi.stubGlobal('devicePixelRatio', 2);
    const v = createCanvas2dViewport(opts);
    const el = host();
    v.mount(el);
    step();
    const canvas = el.querySelector('canvas')!;
    expect(canvas.width).toBe(800);
    expect(canvas.height).toBe(600);
    size = { w: 200, h: 100 };
    roCallbacks.forEach((cb) => cb());
    expect(queue.size).toBe(1);
    step();
    expect(canvas.width).toBe(400);
    expect(canvas.height).toBe(200);
    v.dispose();
    expect(roCallbacks.size).toBe(0);
  });

  it('removes every listener on dispose', () => {
    const v = createCanvas2dViewport(opts);
    v.mount(host());
    expect(mql.listeners.size).toBe(1);
    expect(roCallbacks.size).toBe(1);
    v.dispose();
    expect(mql.listeners.size).toBe(0);
    expect(roCallbacks.size).toBe(0);
    mql.set(true); // evento tardivo: nessun effetto
    expect(queue.size).toBe(0);
  });

  it('is deterministic: same state gives the same pixel buffer', () => {
    const grab = (): number[] => {
      calls = [];
      const v = createCanvas2dViewport({ textures: false });
      v.mount(host());
      v.update({ ...base, yaw_deg: 33, sun: { az_deg: 90, el_deg: 20 } });
      step();
      const data = (calls.find((c) => c.name === 'putImageData')!.args[0] as ImageData).data;
      v.dispose();
      return Array.from(data);
    };
    const a = grab();
    const b = grab();
    expect(a).toEqual(b);
    expect(new Set(a).size).toBeGreaterThan(30); // ombreggiatura, non un colore piatto
  });

  it('factory rejects with Canvas2DUnavailableError when no 2d context exists', async () => {
    (HTMLCanvasElement.prototype.getContext as unknown as { mockImplementation: (f: () => null) => void }).mockImplementation(
      () => null,
    );
    await expect(canvas2dViewportFactory()).rejects.toBeInstanceOf(Canvas2DUnavailableError);
  });
});

type WithFrames = ReturnType<typeof createCanvas2dViewport> & { frameCount: number };

describe('canvas2dViewport, variante palco (hero)', () => {
  it('solo Luna e stelle: niente testo, reticolo o bussola; fondo pulito e disco ritagliato', () => {
    const v = createCanvas2dViewport({ ...opts, decor: 'hero', radius: 0.4 });
    v.mount(host());
    v.update({ ...base, sun: { az_deg: 120, el_deg: 35 }, earth: { az_deg: 10, el_deg: 25 } });
    step();
    expect(count('putImageData')).toBe(1);
    expect(count('fillText')).toBe(0);
    expect(count('strokeText')).toBe(0);
    expect(count('clearRect')).toBe(1);
    expect(count('clip')).toBe(1);
    v.dispose();
  });

  it('maxFps limita i fotogrammi (20 su 1 s simulato a 60 Hz)', () => {
    const v = createCanvas2dViewport({ ...opts, decor: 'hero', maxFps: 20, spinDegPerS: 4 }) as WithFrames;
    v.mount(host());
    v.update({ ...base, autoRotate: true });
    for (let i = 0; i <= 60; i++) step(i * (1000 / 60));
    expect(v.frameCount).toBeGreaterThanOrEqual(18);
    expect(v.frameCount).toBeLessThanOrEqual(22);
    v.dispose();
  });

  it('a scheda nascosta (Page Visibility) la rotazione si ferma e riparte quando torna visibile', () => {
    let state: DocumentVisibilityState = 'visible';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => state);
    const v = createCanvas2dViewport({ ...opts, decor: 'hero' }) as WithFrames;
    v.mount(host());
    v.update({ ...base, autoRotate: true });
    step(0);
    step(20);
    state = 'hidden';
    document.dispatchEvent(new Event('visibilitychange'));
    step(40);
    const frozen = v.frameCount;
    step(60);
    expect(queue.size).toBe(0);
    expect(v.frameCount).toBe(frozen);
    state = 'visible';
    document.dispatchEvent(new Event('visibilitychange'));
    expect(queue.size).toBe(1);
    v.dispose();
  });
});
