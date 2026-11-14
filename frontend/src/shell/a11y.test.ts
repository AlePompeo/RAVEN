// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setTitle, focusMainHeading, announce, prefersReducedMotion, scrollBehavior } from './a11y';

beforeEach(() => {
  document.body.innerHTML = '';
  document.title = '';
});

describe('a11y', () => {
  it('aggiorna il titolo con il nome del sito', () => {
    setTitle('Telemetria');
    expect(document.title).toBe('Telemetria | RAVEN');
  });
  it("sposta il focus sull'h1", () => {
    document.body.innerHTML = '<main><h1>Titolo</h1></main>';
    expect(focusMainHeading(document.body)).toBe(true);
    const h1 = document.querySelector('h1')!;
    expect(document.activeElement).toBe(h1);
    expect(h1.getAttribute('tabindex')).toBe('-1');
  });
  it('senza h1 non fa nulla', () => {
    expect(focusMainHeading(document.body)).toBe(false);
  });
  it('annuncia nella regione live (svuota e riscrive)', () => {
    document.body.innerHTML = '<div id="a" aria-live="polite"></div>';
    const el = document.getElementById('a')!;
    vi.useFakeTimers();
    announce('Pagina caricata', el);
    expect(el.textContent).toBe('');
    vi.runAllTimers();
    expect(el.textContent).toBe('Pagina caricata');
    vi.useRealTimers();
  });
  it("annunci ravvicinati: vale solo l'ultimo", () => {
    document.body.innerHTML = '<div id="a"></div>';
    const el = document.getElementById('a')!;
    vi.useFakeTimers();
    announce('uno', el);
    announce('due', el);
    vi.runAllTimers();
    expect(el.textContent).toBe('due');
    vi.useRealTimers();
  });
  it('rispetta prefers-reduced-motion', () => {
    const mm = (matches: boolean) =>
      vi.stubGlobal('matchMedia', (q: string) => ({ matches, media: q }) as MediaQueryList);
    mm(true);
    expect(prefersReducedMotion()).toBe(true);
    expect(scrollBehavior()).toBe('auto');
    mm(false);
    expect(prefersReducedMotion()).toBe(false);
    expect(scrollBehavior()).toBe('smooth');
    vi.unstubAllGlobals();
  });
});
