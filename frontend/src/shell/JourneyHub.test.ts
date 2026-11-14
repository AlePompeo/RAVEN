// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { setLang } from '../i18n/i18n.svelte';
import JourneyHub from './JourneyHub.svelte';

afterEach(async () => {
  cleanup();
  await setLang('it', { persist: false, url: false });
});

describe('JourneyHub i18n', () => {
  it('aggiorna Explore in inglese', async () => {
    render(JourneyHub);
    expect(screen.getByRole('link', { name: 'Simula l’onda' }).getAttribute('href')).toContain('/simula?tab=onda');
    await setLang('en', { persist: false, url: false });
    await tick();
    const english = screen.getByRole('link', { name: 'Simulate the wave' });
    expect(english.getAttribute('href')).toContain('/simula?tab=onda');
    expect(english.getAttribute('lang')).toBe('en');
    expect(screen.getByText('Change the geometry and see how the link responds.').getAttribute('lang')).toBe('en');
  });

  it('keeps four Explore tools and moves the generic sites library to the Planner', async () => {
    const { container } = render(JourneyHub);
    await setLang('en', { persist: false, url: false });
    await tick();
    expect(container.querySelectorAll('.cards > li')).toHaveLength(4);
    expect(screen.getByRole('heading', { name: 'Transmission link 3D model' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Link budget' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '3D sites analysis' })).toBeTruthy();
    expect(container.querySelector('a[href*="/laboratorio"]')).toBeNull();
    expect(screen.getByText(/educational sites library is in the Mission Planner/)).toBeTruthy();
    expect(screen.queryByTestId('antenna-guide')).toBeNull();
    await setLang('it', { persist: false, url: false });
    await tick();
    expect(screen.getByRole('heading', { name: 'Analisi 3D dei siti' })).toBeTruthy();
  });
});
