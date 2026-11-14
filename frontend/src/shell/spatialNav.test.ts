// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detectTv, ownsAxis, pick, score, type Box } from './spatialNav';

const box = (x: number, y: number, w = 100, h = 40): Box => ({ x, y, w, h });

afterEach(() => {
  delete document.documentElement.dataset.tv;
  vi.unstubAllGlobals();
});

describe('navigazione spaziale', () => {
  it('sceglie il vicino nella direzione, preferendo l’allineamento', () => {
    const from = box(100, 100);
    const cands = [box(300, 100), box(220, 400), box(100, 300), box(-200, 100), box(260, 160)];
    expect(pick(from, cands, 'right')).toBe(0); // stessa riga, anche se (260,160) è più vicino in x
    expect(pick(from, cands, 'down')).toBe(2);
    expect(pick(from, cands, 'left')).toBe(3);
    expect(pick(from, cands, 'up')).toBe(-1);
  });
  it('un elemento fluttuante (data-nav-last) vince solo se non c’è altro in quella direzione', () => {
    const from = box(100, 0);
    const cands = [box(300, 120), box(100, 900)]; // pulsante fisso più vicino in verticale, CTA più in basso
    expect(pick(from, cands, 'down', [true, false])).toBe(1);
    expect(pick(box(100, 950), cands, 'right', [true, false])).toBe(0); // nient'altro a destra: il fluttuante
    expect(pick(from, cands, 'down')).toBe(0); // senza marcatura vincerebbe il fluttuante
  });
  it('ignora ciò che sta dalla parte opposta', () => {
    expect(score(box(100, 100), box(0, 100), 'right')).toBeNull();
    expect(score(box(100, 100), box(100, 0), 'down')).toBeNull();
  });
  it('i controlli che usano un asse lo tengono', () => {
    const range = Object.assign(document.createElement('input'), { type: 'range' });
    expect(ownsAxis(range, 'left')).toBe(true);
    expect(ownsAxis(range, 'down')).toBe(false);
    const select = document.createElement('select');
    expect(ownsAxis(select, 'down')).toBe(true);
    expect(ownsAxis(select, 'right')).toBe(false);
    const list = document.createElement('div');
    list.setAttribute('role', 'tablist');
    const tab = document.createElement('button');
    list.appendChild(tab);
    expect(ownsAxis(tab, 'right')).toBe(true);
    expect(ownsAxis(tab, 'up')).toBe(false);
    const bar = document.createElement('div');
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-orientation', 'vertical');
    const b = document.createElement('button');
    bar.appendChild(b);
    expect(ownsAxis(b, 'down')).toBe(true);
    expect(ownsAxis(b, 'left')).toBe(false);
    expect(ownsAxis(document.createElement('a'), 'left')).toBe(false);
  });
});

describe('modalità TV', () => {
  const mem = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
  };
  it('?tv=1 la accende e la ricorda, ?tv=0 la spegne', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const s = mem();
    expect(detectTv('?tv=1', s)).toBe(true);
    expect(document.documentElement.dataset.tv).toBe('1');
    expect(detectTv('', s)).toBe(true);
    expect(detectTv('?tv=0', s)).toBe(false);
    expect(document.documentElement.dataset.tv).toBeUndefined();
    expect(detectTv('', s)).toBe(false);
  });
  it('schermo grande senza puntatore fine: accesa', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    expect(detectTv('', null)).toBe(true);
  });
});
