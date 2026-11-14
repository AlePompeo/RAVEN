// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createThreeViewport } from './threeViewport';
import { WebGLUnavailableError } from './errors';

let renders = 0;
let resizes = 0;
let renderer: { disposed: boolean } | null = null;

class FakeRenderer {
  domElement = document.createElement('canvas');
  disposed = false;
  constructor() {
    renderer = this;
  }
  setPixelRatio(): void {}
  setSize(): void { resizes++; }
  render(): void {
    renders++;
  }
  dispose(): void {
    this.disposed = true;
  }
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

let mql: FakeMql;
let queue: Map<number, () => void>;
let nextId: number;

/** Esegue i frame attualmente in coda (quelli nuovi finiscono nel frame successivo). */
function step(): void {
  const cbs = [...queue.values()];
  queue.clear();
  cbs.forEach((cb) => cb());
}

const T = { ...THREE, WebGLRenderer: FakeRenderer } as unknown as typeof THREE;
const spin = { yaw_deg: 0, pitch_deg: 0, autoRotate: true };

beforeEach(() => {
  renders = 0;
  resizes = 0;
  renderer = null;
  mql = new FakeMql();
  queue = new Map();
  nextId = 1;
  vi.stubGlobal('matchMedia', () => mql);
  vi.stubGlobal('requestAnimationFrame', (cb: () => void) => {
    queue.set(nextId, cb);
    return nextId++;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => queue.delete(id));
});
afterEach(() => vi.unstubAllGlobals());

describe('threeViewport reduced motion', () => {
  it('repaints a resized drawing buffer synchronously and does not clear an unchanged size', () => {
    let notifyResize = () => {};
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { notifyResize = callback; }
      observe(): void {}
      disconnect(): void {}
    });
    const el = document.createElement('div');
    let width = 400;
    Object.defineProperty(el, 'clientWidth', { get: () => width });
    Object.defineProperty(el, 'clientHeight', { value: 200 });
    const v = createThreeViewport(T);
    v.mount(el);
    step();
    const previous = renders;
    notifyResize();
    expect(resizes).toBe(1);
    expect(renders).toBe(previous);
    width = 600;
    notifyResize();
    expect(resizes).toBe(2);
    expect(renders).toBe(previous + 1); // no animation frame needed before the browser paints
    v.dispose();
  });

  it('stops and restarts auto-rotation when the OS setting changes after mount', () => {
    const v = createThreeViewport(T);
    v.mount(document.createElement('div'));
    v.update(spin);
    step();
    step();
    expect(queue.size).toBe(1); // ciclo continuo attivo

    mql.set(true); // l'utente attiva "riduci movimento"
    step(); // ultimo frame statico
    expect(queue.size).toBe(0);
    const frozen = renders;
    step();
    expect(renders).toBe(frozen);

    mql.set(false);
    expect(queue.size).toBe(1);
    step();
    expect(queue.size).toBe(1);
    v.dispose();
  });

  it('does not loop at all when reduced motion is already on at mount', () => {
    mql.matches = true;
    const v = createThreeViewport(T);
    v.mount(document.createElement('div'));
    v.update(spin);
    step();
    expect(queue.size).toBe(0);
    v.dispose();
  });

  it('dispose removes the matchMedia listener, cancels the frame and releases the renderer', () => {
    const v = createThreeViewport(T);
    const el = document.createElement('div');
    v.mount(el);
    v.update(spin);
    expect(mql.listeners.size).toBe(1);
    expect(queue.size).toBe(1);
    v.dispose();
    v.dispose();
    expect(mql.listeners.size).toBe(0);
    expect(queue.size).toBe(0);
    expect(renderer!.disposed).toBe(true);
    expect(el.querySelector('canvas')).toBeNull();
    mql.set(true); // evento tardivo: nessun effetto
    v.update(spin);
    expect(queue.size).toBe(0);
  });
});

describe('threeViewport renderer failure', () => {
  it('mount throws WebGLUnavailableError (no text in the DOM) when the renderer cannot be created', () => {
    class Broken {
      constructor() {
        throw new Error('no webgl');
      }
    }
    const v = createThreeViewport({ ...THREE, WebGLRenderer: Broken } as unknown as typeof THREE);
    const el = document.createElement('div');
    expect(() => v.mount(el)).toThrow(WebGLUnavailableError);
    expect(el.childNodes.length).toBe(0);
    v.dispose();
  });
});
