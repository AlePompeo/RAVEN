// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Canvas2DUnavailableError, WEBGL_FALLBACK_MESSAGE, WebGLUnavailableError } from './errors';
import type { ViewportFactory, ViewportPort } from './port';
import { probeWebGL, selectViewportFactory, type ViewportMode } from './select';

function fakePort(tag: string, failMount?: unknown): ViewportPort & { log: string[] } {
  const log: string[] = [];
  return {
    log,
    mount: () => {
      log.push('mount');
      if (failMount) throw failMount;
    },
    update: (s) => void log.push(`update:${JSON.stringify(s)}`),
    dispose: () => void log.push(`dispose:${tag}`),
  };
}
const ok = (p: ViewportPort): ViewportFactory => async () => p;
const fail = (e: unknown): ViewportFactory => async () => {
  throw e;
};

function run(opts: Parameters<typeof selectViewportFactory>[0]) {
  const modes: ViewportMode[] = [];
  const f = selectViewportFactory({ ...opts, onMode: (m) => modes.push(m) });
  return { modes, f };
}

afterEach(() => vi.restoreAllMocks());

describe('selectViewportFactory', () => {
  it('uses three when WebGL is available', async () => {
    const t = fakePort('three');
    const c = fakePort('c2d');
    const canvas2d = vi.fn(ok(c));
    const { f, modes } = run({ webglAvailable: () => true, three: ok(t), canvas2d });
    const p = await f();
    const el = document.createElement('div');
    p.mount(el);
    p.update({ a: 1 });
    expect(t.log).toEqual(['mount', 'update:{"a":1}']);
    expect(canvas2d).not.toHaveBeenCalled();
    expect(modes).toEqual(['webgl']);
  });

  it('uses canvas2d without even loading three when WebGL is unavailable', async () => {
    const three = vi.fn(ok(fakePort('three')));
    const c = fakePort('c2d');
    const { f, modes } = run({ webglAvailable: () => false, three, canvas2d: ok(c) });
    const p = await f();
    p.mount(document.createElement('div'));
    expect(three).not.toHaveBeenCalled();
    expect(c.log).toEqual(['mount']);
    expect(modes).toEqual(['canvas2d']);
  });

  it('falls back to canvas2d when the three factory rejects (renderer creation throws)', async () => {
    const c = fakePort('c2d');
    const { f, modes } = run({ webglAvailable: () => true, three: fail(new WebGLUnavailableError()), canvas2d: ok(c) });
    const p = await f();
    p.mount(document.createElement('div'));
    expect(c.log).toEqual(['mount']);
    expect(modes).toEqual(['canvas2d']);
  });

  it('falls back transparently when three mount throws at runtime, replaying the state', async () => {
    const t = fakePort('three', new WebGLUnavailableError());
    const c = fakePort('c2d');
    const { f, modes } = run({ webglAvailable: () => true, three: ok(t), canvas2d: ok(c) });
    const p = await f();
    const el = document.createElement('div');
    p.mount(el);
    p.update({ yaw: 1 });
    await vi.waitFor(() => expect(c.log).toContain('mount'));
    expect(t.log).toContain('dispose:three');
    expect(c.log).toEqual(['mount', 'update:{"yaw":1}']);
    expect(modes).toEqual(['webgl', 'canvas2d']);
    p.update({ yaw: 2 });
    expect(c.log.at(-1)).toBe('update:{"yaw":2}');
    p.dispose();
    expect(c.log.at(-1)).toBe('dispose:c2d');
  });

  it('disposing before the late fallback resolves disposes the fallback and never mounts it', async () => {
    const t = fakePort('three', new WebGLUnavailableError());
    const c = fakePort('c2d');
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const { f } = run({
      webglAvailable: () => true,
      three: ok(t),
      canvas2d: async () => {
        await gate;
        return c;
      },
    });
    const p = await f();
    p.mount(document.createElement('div'));
    p.dispose();
    release();
    await vi.waitFor(() => expect(c.log).toContain('dispose:c2d'));
    expect(c.log).not.toContain('mount');
  });

  it('shows the text fallback only when canvas2d is unavailable too', async () => {
    const { f, modes } = run({
      webglAvailable: () => false,
      canvas2d: fail(new Canvas2DUnavailableError()),
    });
    const p = await f();
    const el = document.createElement('div');
    p.mount(el);
    expect(el.querySelector('[role=alert]')!.textContent).toBe(WEBGL_FALLBACK_MESSAGE);
    expect(modes).toEqual(['none']);
    p.update({});
    p.dispose();
    p.dispose();
    expect(el.querySelector('[role=alert]')).toBeNull();
  });

  it('both failing after a WebGL probe success also ends in the text fallback', async () => {
    const { f, modes } = run({
      webglAvailable: () => true,
      three: fail(new WebGLUnavailableError()),
      canvas2d: fail(new Canvas2DUnavailableError()),
    });
    const p = await f();
    const el = document.createElement('div');
    p.mount(el);
    expect(el.querySelector('[role=alert]')).not.toBeNull();
    expect(modes).toEqual(['none']);
  });
});

describe('probeWebGL', () => {
  const stub = (impl: (id: string) => unknown) =>
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(impl as never);

  it('is false when no context type works, and tries webgl2, webgl, experimental-webgl in order', () => {
    const seen: string[] = [];
    stub((id) => {
      seen.push(id);
      return null;
    });
    expect(probeWebGL()).toBe(false);
    expect(seen).toEqual(['webgl2', 'webgl', 'experimental-webgl']);
  });

  it('is false when getContext throws', () => {
    stub(() => {
      throw new Error('boom');
    });
    expect(probeWebGL()).toBe(false);
  });

  it('is true on a working context and releases it via WEBGL_lose_context', () => {
    const lose = vi.fn();
    stub((id) => (id === 'webgl' ? { getExtension: () => ({ loseContext: lose }) } : null));
    expect(probeWebGL()).toBe(true);
    expect(lose).toHaveBeenCalledOnce();
  });
});
