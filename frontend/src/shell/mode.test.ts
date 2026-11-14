// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { DEFAULT_MODE, MODE_KEY, ModeStore, modeFromSearch, parseMode, resolveMode, searchWithMode } from './mode';

function mem(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m };
}
const blocked = {
  getItem: () => {
    throw new Error('SecurityError');
  },
  setItem: () => {
    throw new Error('QuotaExceeded');
  },
};

describe('parseMode', () => {
  it('accetta solo i due nomi esatti', () => {
    expect(parseMode('learning')).toBe('learning');
    expect(parseMode('avanzato')).toBe('avanzato');
    for (const bad of ['Avanzato', ' learning', 'learning ', 'ricercatore', '', '<script>', 'avanzato\u0000', null, undefined, 1, {}, ['avanzato']]) {
      expect(parseMode(bad)).toBeNull();
    }
  });
});

describe('modeFromSearch', () => {
  it('legge ?mode= e ignora valori malevoli o assenti', () => {
    expect(modeFromSearch('?mode=avanzato&site=x')).toBe('avanzato');
    expect(modeFromSearch('?site=x')).toBeNull();
    expect(modeFromSearch('?mode=%3Cimg%20src%3Dx%3E')).toBeNull();
    expect(modeFromSearch('?mode=javascript:alert(1)')).toBeNull();
    expect(modeFromSearch('?mode=' + 'a'.repeat(5000))).toBeNull();
    expect(modeFromSearch('?mode=AVANZATO')).toBeNull();
  });
});

describe('resolveMode: precedenza URL > archiviazione > predefinito', () => {
  it('predefinito Learning', () => {
    expect(DEFAULT_MODE).toBe('learning');
    expect(resolveMode('', null)).toBe('learning');
    expect(resolveMode('', mem())).toBe('learning');
  });
  it("l'archiviazione vale senza URL; l'URL vince", () => {
    expect(resolveMode('', mem({ [MODE_KEY]: 'avanzato' }))).toBe('avanzato');
    expect(resolveMode('?mode=learning', mem({ [MODE_KEY]: 'avanzato' }))).toBe('learning');
  });
  it('valori non validi in URL o archiviazione sono ignorati', () => {
    expect(resolveMode('?mode=hack', mem({ [MODE_KEY]: 'avanzato' }))).toBe('avanzato');
    expect(resolveMode('', mem({ [MODE_KEY]: '{"x":1}' }))).toBe('learning');
  });
  it('archiviazione bloccata: nessun errore, predefinito', () => {
    expect(resolveMode('', blocked)).toBe('learning');
  });
});

describe('searchWithMode', () => {
  it('conserva gli altri parametri', () => {
    const q = new URLSearchParams(searchWithMode('?site=shackleton&t=2027-01-01T00:00:00Z&mode=learning', 'avanzato'));
    expect(q.get('site')).toBe('shackleton');
    expect(q.get('t')).toBe('2027-01-01T00:00:00Z');
    expect(q.getAll('mode')).toEqual(['avanzato']);
  });
});

describe('ModeStore', () => {
  const loc = (search = '') => ({ pathname: '/analizza', search, hash: '#x' });
  it("set scrive archiviazione e URL senza perdere parametri, e avvisa chi ascolta", () => {
    const store = mem();
    const hist = { state: null, replaceState: vi.fn() };
    const s = new ModeStore({ loc: loc('?site=a'), hist, store });
    const seen: string[] = [];
    s.subscribe((m) => seen.push(m));
    s.set('avanzato');
    expect(s.get()).toBe('avanzato');
    expect(store.m.get(MODE_KEY)).toBe('avanzato');
    expect(hist.replaceState).toHaveBeenCalledWith(null, '', '/analizza?site=a&mode=avanzato#x');
    expect(seen).toEqual(['learning', 'avanzato']);
  });
  it('ignora valori non validi passati a set', () => {
    const s = new ModeStore({ loc: loc(), hist: null, store: null });
    s.set('x' as never);
    expect(s.get()).toBe('learning');
  });
  it('archiviazione bloccata: il cambio resta in memoria', () => {
    const s = new ModeStore({ loc: loc(), hist: null, store: blocked });
    expect(() => s.set('avanzato')).not.toThrow();
    expect(s.get()).toBe('avanzato');
  });
  it("sync adotta un ?mode= valido arrivato con la navigazione", () => {
    const l = loc();
    const s = new ModeStore({ loc: l, hist: null, store: null });
    l.search = '?mode=avanzato';
    expect(s.sync()).toBe('avanzato');
    l.search = '?mode=bad';
    expect(s.sync()).toBe('avanzato');
  });
  it("il caricamento non scrive nell'archiviazione (nessuna scrittura senza una scelta)", () => {
    const store = mem();
    new ModeStore({ loc: loc('?mode=avanzato'), hist: null, store });
    expect(store.m.size).toBe(0);
  });
});

describe('ModeSwitch', () => {
  it('gruppo "Modalità" con aria-pressed, frecce e annuncio', async () => {
    vi.useFakeTimers();
    const live = Object.assign(document.createElement('div'), { id: 'announcer' });
    live.setAttribute('aria-live', 'polite');
    document.body.append(live);
    const { default: ModeSwitch } = await import('./ModeSwitch.svelte');
    render(ModeSwitch);
    const group = screen.getByRole('group', { name: 'Modalità' });
    const learning = screen.getByRole('button', { name: 'Learning' });
    const adv = screen.getByRole('button', { name: 'Avanzato' });
    expect(group.contains(adv)).toBe(true);
    expect(learning.getAttribute('aria-pressed')).toBe('true');
    await fireEvent.click(adv);
    expect(adv.getAttribute('aria-pressed')).toBe('true');
    expect(learning.getAttribute('aria-pressed')).toBe('false');
    vi.advanceTimersByTime(100);
    expect(live.textContent).toBe('Modalità Avanzato attiva');
    await fireEvent.keyDown(adv, { key: 'ArrowLeft' });
    expect(learning.getAttribute('aria-pressed')).toBe('true');
    expect(document.activeElement).toBe(learning);
    vi.useRealTimers();
    live.remove();
  });
});
