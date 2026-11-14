// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import GlobalNav from './GlobalNav.svelte';
import type { PageModule } from './router';

const page = (path: string, navLabel: string): PageModule => ({ path, title: navLabel, navLabel, load: async () => ({ default: {} as never }) });
const pages = [page('/', 'Home'), page('/telemetry', 'Telemetria'), page('/sims', 'Simulazioni')];

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove('menu-open');
});

describe('GlobalNav', () => {
  it('navigazione "Principale" con base applicata e aria-current sulla pagina attiva', () => {
    render(GlobalNav, { pages, path: '/telemetry', base: '/app/' });
    const nav = screen.getByRole('navigation', { name: 'Principale' });
    const links = [...nav.querySelectorAll('a')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/app/', '/app/telemetry', '/app/sims']);
    expect(links[1]!.getAttribute('aria-current')).toBe('page');
    expect(links[0]!.getAttribute('aria-current')).toBeNull();
  });

  it('pulsante Menu: aria-expanded/controls, focus sul primo link, Esc chiude e ridà il focus', async () => {
    render(GlobalNav, { pages, path: '/' });
    const toggle = screen.getByRole('button', { name: 'Menu' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).not.toBeNull();
    await fireEvent.click(toggle);
    await tick();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(document.documentElement.classList.contains('menu-open')).toBe(true);
    expect(document.activeElement?.textContent).toBe('Home');
    await fireEvent.keyDown(window, { key: 'Escape' });
    await tick();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(toggle);
    expect(document.documentElement.classList.contains('menu-open')).toBe(false);
  });

  it('il cambio di percorso chiude il menu senza spostare il focus sul pulsante', async () => {
    const r = render(GlobalNav, { pages, path: '/' });
    const toggle = screen.getByRole('button', { name: 'Menu' });
    await fireEvent.click(toggle);
    await tick();
    await r.rerender({ pages, path: '/sims' });
    await tick();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).not.toBe(toggle);
  });
});
