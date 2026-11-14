// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { mountViewport, type ViewportFactory, type ViewportPort } from './port';
import { azElToVector, clampPitch, describeScene, wrapYaw } from './scene';

class FakeViewport implements ViewportPort {
  listeners = 0;
  updates: unknown[] = [];
  disposeCalls = 0;
  mounted = false;
  private disposed = false;
  private readonly handler = () => {};
  private el: HTMLElement | null = null;

  mount(el: HTMLElement): void {
    this.el = el;
    el.addEventListener('click', this.handler);
    this.listeners++;
    this.mounted = true;
  }
  update(state: unknown): void {
    if (this.disposed) return;
    this.updates.push(state);
  }
  dispose(): void {
    this.disposeCalls++;
    if (this.disposed) return;
    this.disposed = true;
    this.el?.removeEventListener('click', this.handler);
    if (this.mounted) this.listeners--;
  }
}

describe('mountViewport', () => {
  it('loads via factory, mounts, and forwards updates', async () => {
    const fake = new FakeViewport();
    const factory: ViewportFactory = async () => fake;
    const h = mountViewport(factory, document.createElement('div'));
    h.update({ a: 1 }); // prima del caricamento: tenuto in coda
    await h.ready;
    expect(fake.mounted).toBe(true);
    expect(fake.updates).toEqual([{ a: 1 }]);
    h.update({ a: 2 });
    expect(fake.updates).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it('dispose is idempotent and update after dispose is safe; listeners return to zero', async () => {
    const fake = new FakeViewport();
    const h = mountViewport(async () => fake, document.createElement('div'));
    await h.ready;
    expect(fake.listeners).toBe(1);
    h.dispose();
    h.dispose();
    expect(fake.listeners).toBe(0);
    expect(fake.disposeCalls).toBe(1);
    expect(() => h.update({ x: 1 })).not.toThrow();
    expect(() => fake.update({ x: 1 })).not.toThrow();
    expect(fake.updates).toEqual([]);
  });

  it('disposes a viewport that resolves after the handle was disposed, without mounting', async () => {
    const fake = new FakeViewport();
    const h = mountViewport(async () => fake, document.createElement('div'));
    h.dispose();
    await h.ready;
    expect(fake.mounted).toBe(false);
    expect(fake.disposeCalls).toBe(1);
    expect(fake.listeners).toBe(0);
  });

  it('reports factory errors without throwing', async () => {
    const errors: unknown[] = [];
    const h = mountViewport(
      () => Promise.reject(new Error('boom')),
      document.createElement('div'),
      (e) => errors.push(e),
    );
    await h.ready;
    expect(errors).toHaveLength(1);
    expect(() => h.dispose()).not.toThrow();
  });
});

describe('threeViewportFactory (jsdom, no WebGL)', () => {
  it('rejects with WebGLUnavailableError when WebGL is unavailable (selection layer falls back)', async () => {
    const { threeViewportFactory } = await import('./threeViewport');
    const { WebGLUnavailableError } = await import('./errors');
    const spy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    await expect(threeViewportFactory()).rejects.toBeInstanceOf(WebGLUnavailableError);
    spy.mockRestore();
  }, 20000);
});

describe('scene helpers', () => {
  it('clamps pitch and wraps yaw', () => {
    expect(clampPitch(120)).toBe(80);
    expect(clampPitch(-120)).toBe(-80);
    expect(wrapYaw(190)).toBe(-170);
    expect(wrapYaw(-190)).toBe(170);
  });
  it('converts az/el to a unit vector', () => {
    const [x, y, z] = azElToVector({ az_deg: 0, el_deg: 90 });
    expect(x).toBeCloseTo(0);
    expect(y).toBeCloseTo(1);
    expect(z).toBeCloseTo(0);
  });
  it('describes the scene, honouring reduced motion', () => {
    const s = { yaw_deg: 10, pitch_deg: 15, autoRotate: true, sun: { az_deg: 90, el_deg: -5 } };
    expect(describeScene(s, true)).toContain('Rotazione automatica attiva');
    expect(describeScene(s, false)).toContain('Rotazione automatica ferma');
    expect(describeScene(s, true)).toContain('sotto l’orizzonte');
    expect(describeScene(s, true)).toContain('Terra: dato non disponibile');
  });
});
