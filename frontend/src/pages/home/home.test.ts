// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import Home from './Home.svelte';
import { setLang } from '../../i18n/i18n.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Home', () => {
  it('keeps the requested hero links while restoring the story', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    const { container } = render(Home);
    const hero = screen.getByRole('region', { name: 'RAVEN' });
    const links = [...hero.querySelectorAll('a')];
    expect(links.map((a) => a.textContent?.trim())).toEqual(['Prova e impara', 'Inizia il Mission Planner', 'Demo guidata', 'About']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/simula', '/mission-planner', '/demo', '/about']);
    expect(hero.querySelectorAll('button')).toHaveLength(0);
    expect(container.querySelector('#come-funziona')).toBeTruthy();
    expect(screen.getByTestId('step-horizon')).toBeTruthy();
    expect(screen.getByTestId('step-ridge')).toBeTruthy();
    expect(screen.getByTestId('step-compute')).toBeTruthy();
    expect(screen.getByTestId('step-mission')).toBeTruthy();
    expect(hero.textContent).not.toContain('NASA Scientific Visualization Studio');
  });

  it('loads the interactive mini simulator and updates its scenario link', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(Home);
    const slider = (await screen.findByTestId('mini-el')).querySelector('input[type="range"]')!;
    const link = screen.getByRole('link', { name: /simulatore completo/i });
    const previous = link.getAttribute('href');
    await fireEvent.input(slider, { target: { value: '3' } });
    await waitFor(() => expect(link.getAttribute('href')).not.toBe(previous));
  });

  it('translates the primary action and planner link', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    render(Home);
    try {
      await setLang('en', { persist: false, url: false });
      await tick();
      expect(screen.getByRole('link', { name: 'Try and learn' }).getAttribute('href')).toBe('/simula');
      expect(screen.getByRole('link', { name: 'Start the Mission Planner' }).getAttribute('href')).toBe('/mission-planner');
      expect(screen.getByRole('link', { name: 'About' }).getAttribute('href')).toBe('/about');
    } finally {
      await setLang('it', { persist: false, url: false });
    }
  });
});
