// SPDX-License-Identifier: Apache-2.0
import { createHash, webcrypto } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { reportLayout, simulatedCertificate } from './reportPresentation';

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('freezes page estimates during printing so carbon and certificate data are not invalidated', async () => {
  vi.useFakeTimers();
  const media = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal('matchMedia', () => media);
  let resize = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect = disconnect;
  });
  const fonts = Object.getOwnPropertyDescriptor(document, 'fonts');
  Object.defineProperty(document, 'fonts', { configurable: true, value: { ready: Promise.resolve() } });
  const node = document.createElement('article');
  const onpages = vi.fn();
  const action = reportLayout(node, { ready: true, onpages });
  try {
    await Promise.resolve();
    media.matches = true;
    media.dispatchEvent(new Event('change'));
    vi.advanceTimersByTime(250);
    resize();
    action.update({ ready: true, onpages });
    vi.advanceTimersByTime(250);
    expect(onpages).not.toHaveBeenCalled();

    media.matches = false;
    media.dispatchEvent(new Event('change'));
    vi.advanceTimersByTime(250);
    expect(onpages).toHaveBeenCalledExactlyOnceWith({ compact: 1, reference: 1 });
  } finally {
    action.destroy();
    if (fonts) Object.defineProperty(document, 'fonts', fonts);
    else Reflect.deleteProperty(document, 'fonts');
  }
  expect(disconnect).toHaveBeenCalledOnce();
});

it('binds a deterministic demo record to the content without claiming a signature or blockchain broadcast', async () => {
  vi.stubGlobal('crypto', webcrypto);
  const first = await simulatedCertificate({ b: 2, a: { x: 1 } });
  const reordered = await simulatedCertificate({ a: { x: 1 }, b: 2 });
  const changed = await simulatedCertificate({ a: { x: 2 }, b: 2 });
  expect(first).toEqual(reordered);
  expect(first.payload_sha256).toBe(createHash('sha256').update('{"a":{"x":1},"b":2}').digest('hex'));
  expect(changed.payload_sha256).not.toBe(first.payload_sha256);
  expect(first.simulated_transaction_id).toMatch(/^DEMO-[0-9a-f]{64}$/);
  expect(first).toMatchObject({
    status: 'simulation_only_not_broadcast', network: null, broadcast: false, cryptographic_signature: null,
  });
});
