// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import Home from './Home.svelte';
import { modeStore } from '../../shell/mode';
import { setLang } from '../../i18n/i18n.svelte';

const setMode = (m: 'learning' | 'avanzato') => modeStore().set(m);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function mount() {
  // jsdom non ha Canvas 2D: il palco passa al ripiego (Luna nascosta), la pagina resta completa
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  // niente IntersectionObserver: il mini-simulatore si carica subito (qui non serve aspettarlo)
  vi.stubGlobal('IntersectionObserver', undefined);
  return render(Home);
}

describe('Home (Il problema)', () => {
  it('palco: un h1, la domanda, UNA azione principale "Prova tu" verso /simula e l’ancora "Come funziona"', () => {
    const { container } = mount();
    expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['RAVEN']);
    const hero = screen.getByRole('region', { name: 'RAVEN' });
    expect(hero.querySelector('h1 img')?.getAttribute('src')).toContain('raven-logo');
    expect(hero.querySelector('h1 img')?.getAttribute('alt')).toBe('');
    expect(hero.textContent).toMatch(/polo Sud della Luna la Terra sta a circa un grado/);
    const links = [...hero.querySelectorAll('a')];
    expect(links.map((a) => a.textContent?.trim())).toEqual(['Prova tu', 'Come funziona', 'Inizia il Mission Planner', 'Demo guidata']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/simula', '#come-funziona', '/mission-planner', '/demo']);
    expect(container.querySelectorAll('.hero .btn--primary')).toHaveLength(1);
    // la CTA viene prima dell'interruttore di modalità nell'ordine del focus
    const order = [...hero.querySelectorAll('a, button')].map((e) => e.textContent?.trim());
    expect(order.indexOf('Prova tu')).toBe(0);
    expect(container.querySelector('#come-funziona')).not.toBeNull();
    expect(container.querySelector('[data-testid="moon-stage"]')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('la storia in quattro passi e la foto con alt e credito, senza il blocco finale rimosso', () => {
    const { container } = mount();
    for (const name of ['La Terra resta quasi sull’orizzonte', 'Perché un crinale conta', 'Cosa calcola RAVEN', 'Cosa significa per una missione']) {
      expect(screen.getByRole('region', { name })).toBeTruthy();
    }
    expect(screen.getByRole('img', { name: /La Terra, illuminata a metà/ })).toBeTruthy();
    expect(container.querySelector('.earth-credit')?.textContent).toMatch(/NASA, pubblico dominio/);
    expect(screen.queryByTestId('honesty')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Chi siamo' })).toBeNull();
    expect(screen.getByTestId('strip-summary').textContent).toMatch(/\d+ ore di contatto/);
  });

  it('Learning: solo testo semplice; Avanzato: una riga tecnica per passo e lo stack', () => {
    setMode('learning');
    const a = mount();
    expect(screen.getByTestId('learn-line')).toBeTruthy();
    expect(screen.queryAllByTestId('tech-line')).toHaveLength(0);
    expect(screen.queryByTestId('stack')).toBeNull();
    a.unmount();
    setMode('avanzato');
    mount();
    expect(screen.queryByTestId('learn-line')).toBeNull();
    expect(screen.getAllByTestId('tech-line')).toHaveLength(4);
    expect(screen.getByTestId('stack').textContent).toMatch(/Skyfield/);
    setMode('learning');
  });

  it('traduce la CTA del planner e al cambio lingua', async () => {
    mount();
    try {
      await setLang('en', { persist: false, url: false });
      await tick();
      const link = screen.getByRole('link', { name: 'Start the Mission Planner' });
      expect(link.getAttribute('href')).toBe('/mission-planner');
      expect(link.querySelector('span')?.getAttribute('lang')).toBe('en');
    } finally {
      await setLang('it', { persist: false, url: false });
    }
  });

  it('traduce tutta la storia e il mini-simulatore, compresi stati, validità e testo accessibile, senza perdere i valori', async () => {
    setMode('avanzato');
    mount();
    try {
      await setLang('en', { persist: false, url: false });
      await tick();
      await screen.findByTestId('mini-sim', {}, { timeout: 15_000 }); // a lazy chunk: slow under the load of the full suite
      for (const name of [
        'The Earth stays close to the horizon', 'Why a ridge matters',
        'What RAVEN calculates', 'What this means for a mission', 'The research stack',
      ]) expect(screen.getByRole('heading', { name })).toBeTruthy();
      expect(screen.getByRole('img', { name: /The half-lit Earth/ })).toBeTruthy();
      expect(screen.getByTestId('strip-summary').textContent).toMatch(/28 days.*hours of contact/);
      expect(screen.getByRole('link', { name: 'Open in the full simulator' })).toBeTruthy();
      expect(screen.getByRole('meter', { name: 'Link margin' })).toBeTruthy();
      await fireEvent.input(screen.getByTestId('mini-el-num'), { target: { value: '0' } });
      expect(screen.getByTestId('sentence').textContent).toContain('The Earth is below the horizon');
      expect(screen.getByTestId('validity').textContent).toContain('Model validity: Outside model');
      expect(screen.getByTestId('validity-reasons').textContent).toContain('the model is not valid');
      expect(screen.getByTestId('mini-stage').getAttribute('aria-label')).toContain('Side view:');
      expect(screen.getByTestId('mini-tech').textContent).toContain('diffraction loss');
      const margin = screen.getByTestId('gauge').getAttribute('data-margin');
      await setLang('it', { persist: false, url: false });
      await tick();
      expect(screen.getByRole('heading', { name: 'Come funziona, in quattro passi' })).toBeTruthy();
      expect(screen.getByTestId('sentence').textContent).toContain('La Terra è sotto');
      expect((screen.getByTestId('mini-el-num') as HTMLInputElement).value).toBe('0');
      expect(screen.getByTestId('gauge').getAttribute('data-margin')).toBe(margin);
    } finally {
      await setLang('it', { persist: false, url: false });
      setMode('learning');
    }
  });
});
