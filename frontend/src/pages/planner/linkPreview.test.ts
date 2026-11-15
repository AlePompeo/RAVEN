// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import LinkPreview from './LinkPreview.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useCatalog('it', itCatalog, en);
});

it('shows both interactive charts before a mission run and explains the synthetic scenario', async () => {
  useCatalog('en', {}, en);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  render(LinkPreview, { radio: { station: 'dsn34', gain: 15, rate: 100000, mast: 2 } });
  expect(screen.getByText(/Educational scenario with a synthetic ridge/)).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Validity map' })).toBeTruthy();
  expect(screen.getByRole('meter', { name: 'Link margin' })).toBeTruthy();
  const gauge = screen.getByTestId('gauge');
  const before = gauge.getAttribute('data-margin');
  await fireEvent.keyDown(screen.getByTestId('validity-canvas'), { key: 'ArrowRight' });
  await tick();
  expect(gauge.getAttribute('data-margin')).not.toBe(before);
  expect(screen.getByTestId('vmap-summary').textContent).toContain('Current point: Earth at');
  expect((await screen.findAllByText(/Split-step table unavailable/)).length).toBeGreaterThan(0);
});

it('explicitly identifies default settings if planner radio inputs are incomplete', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  render(LinkPreview, { radio: { station: 'dsn34', gain: null, rate: null, mast: null } });
  expect(screen.getByText(/impostazioni radio sono incomplete/)).toBeTruthy();
});
