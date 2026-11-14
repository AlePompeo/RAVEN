// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createCanvasWave } from './canvasWave';
import { EMPTY_SCENE, type WaveScene } from './surface';

function stubContext() {
  const calls = { fill: 0, stroke: 0, fillStyles: new Set<string>() };
  const ctx = {
    fillStyle: '' as string,
    strokeStyle: '',
    lineWidth: 1,
    lineJoin: '',
    setTransform() {},
    fillRect() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    closePath() {},
    fill() {
      calls.fill++;
      calls.fillStyles.add(String(this.fillStyle));
    },
    stroke() {
      calls.stroke++;
    },
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  return calls;
}

function scene(nx: number, ny: number, tier: 'hi' | 'lo' = 'hi'): WaveScene {
  const xs = Array.from({ length: nx }, (_, i) => 10 + i * 20);
  const grid = new Float32Array(nx * ny).map((_, k) => 0.2 + 1.1 * Math.abs(Math.sin(k / 7)));
  return { ...EMPTY_SCENE(), nx, ny, xs, grid, geom: 1, zTop: 1.4, cursor: xs[3]!, tier };
}

let rafs: FrameRequestCallback[] = [];
beforeEach(() => {
  rafs = [];
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => rafs.push(cb));
  vi.stubGlobal('cancelAnimationFrame', () => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const flush = () => rafs.splice(0).forEach((cb) => cb(0));

describe('ripiego Canvas 2D', () => {
  it('disegna una cella per quadrilatero con colori diversi e aggiorna il contatore dei fotogrammi', () => {
    const calls = stubContext();
    const host = document.createElement('div');
    const p = createCanvasWave();
    p.mount(host);
    p.update(scene(12, 20));
    flush();
    // 11 x 19 celle, più il piano della sezione
    expect(calls.fill).toBe(11 * 19 + 1);
    expect(calls.fillStyles.size).toBeGreaterThan(5);
    expect(host.querySelector('canvas')!.dataset.frames).toBeDefined();
    p.dispose();
    expect(host.querySelector('canvas')).toBeNull();
  });
  it('il livello basso disegna una cella ogni due', () => {
    const calls = stubContext();
    const p = createCanvasWave();
    p.mount(document.createElement('div'));
    p.update(scene(13, 21, 'lo'));
    flush();
    expect(calls.fill).toBe(6 * 10 + 1);
    p.dispose();
  });
  it('senza superficie non disegna celle; dispose è idempotente', () => {
    const calls = stubContext();
    const p = createCanvasWave();
    p.mount(document.createElement('div'));
    p.update(EMPTY_SCENE());
    flush();
    expect(calls.fill).toBe(0);
    p.dispose();
    p.dispose();
    p.update(scene(4, 4));
    expect(rafs).toHaveLength(0);
  });
  it('senza contesto 2D il mount fallisce (la selezione passa al messaggio testuale)', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    expect(() => createCanvasWave().mount(document.createElement('div'))).toThrow();
  });
});
