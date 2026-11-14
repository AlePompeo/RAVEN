// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import Button from './Button.svelte';
import Tile from './Tile.svelte';
import Chapter from './Chapter.svelte';
import Hero from './Hero.svelte';
import MediaFrame from './MediaFrame.svelte';
import Callout from './Callout.svelte';
import SubNav from './SubNav.svelte';
import { progressFor, scrollFx, THRESHOLDS } from './scrollFx';

const text = (t: string) => createRawSnippet(() => ({ render: () => `<span>${t}</span>` }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Button', () => {
  it('con href è un link a pillola, primario per default', () => {
    render(Button, { href: '/telemetry', children: text('Apri') });
    const a = screen.getByRole('link', { name: 'Apri' });
    expect(a.getAttribute('href')).toBe('/telemetry');
    expect(a.className).toContain('btn--primary');
  });
  it('senza href è un <button type="button">; ghost e aria-pressed', () => {
    render(Button, { variant: 'ghost', pressed: true, children: text('Ruota') });
    const b = screen.getByRole('button', { name: 'Ruota' });
    expect(b.getAttribute('type')).toBe('button');
    expect(b.className).toContain('btn--ghost');
    expect(b.getAttribute('aria-pressed')).toBe('true');
  });
  it('disabled usa aria-disabled, resta focalizzabile e non esegue onclick', async () => {
    const onclick = vi.fn();
    render(Button, { disabled: true, onclick, children: text('Invia') });
    const b = screen.getByRole('button', { name: 'Invia' }) as HTMLButtonElement;
    expect(b.disabled).toBe(false);
    expect(b.getAttribute('aria-disabled')).toBe('true');
    await fireEvent.click(b);
    expect(onclick).not.toHaveBeenCalled();
  });
});

describe('Tile', () => {
  it('con un nome è una regione; tone dark applica i token scuri', () => {
    const { container } = render(Tile, { tone: 'dark', label: 'Prova', children: text('x') });
    const s = screen.getByRole('region', { name: 'Prova' });
    expect(s.classList.contains('tone-dark')).toBe(true);
    expect(container.querySelector('.container')).not.toBeNull();
  });
  it('senza nome è un <div>; width full non aggiunge il contenitore; alt usa la superficie alternata', () => {
    const { container } = render(Tile, { tone: 'alt', width: 'full', children: text('x') });
    const d = container.querySelector('.tile')!;
    expect(d.tagName).toBe('DIV');
    expect(d.classList.contains('tile--alt')).toBe(true);
    expect(container.querySelector('.container')).toBeNull();
  });
});

describe('Chapter', () => {
  it('regione etichettata dal proprio titolo, con lead e slot media', () => {
    render(Chapter, { id: 'cap', title: 'Telemetria dal vivo', lead: 'Dati veri.', children: text('corpo'), media: text('foto') });
    const r = screen.getByRole('region', { name: 'Telemetria dal vivo' });
    expect(r.querySelector('h2#cap-h')).not.toBeNull();
    expect(screen.getByText('Dati veri.')).toBeTruthy();
    expect(r.querySelector('.chapter-media')?.textContent).toBe('foto');
  });
  it('headingLevel 3 produce un h3', () => {
    render(Chapter, { id: 'c3', title: 'Sotto', headingLevel: 3 });
    expect(screen.getByRole('heading', { level: 3, name: 'Sotto' })).toBeTruthy();
  });
});

describe('Hero', () => {
  it('palco sempre scuro, etichettato, con media e contenuto separati (il testo non sta sul media)', () => {
    const { container } = render(Hero, { labelledby: 't', media: text('luna'), children: createRawSnippet(() => ({ render: () => '<h1 id="t">Titolo</h1>' })) });
    const s = screen.getByRole('region', { name: 'Titolo' });
    expect(s.classList.contains('tone-dark')).toBe(true);
    const media = container.querySelector('.hero-media')!;
    const content = container.querySelector('.hero-content')!;
    expect(media.contains(content)).toBe(false);
    // overlay predefinito: scrim tra media e testo, effetto di scroll 'drift'
    expect(container.querySelector('.hero-scrim')?.getAttribute('aria-hidden')).toBe('true');
    expect(media.querySelector('.fx-drift')).not.toBeNull();
    expect(s.dataset.layout).toBe('overlay');
  });
  it('layout split senza scrim sovrapposto e con effetto recede', () => {
    const { container } = render(Hero, { labelledby: 't', layout: 'split', fx: 'recede', media: text('luna'), children: createRawSnippet(() => ({ render: () => '<h1 id="t">T</h1>' })) });
    expect(container.querySelector('.hero-scrim')).toBeNull();
    expect(container.querySelector('.fx-recede')).not.toBeNull();
  });
});

describe('MediaFrame', () => {
  it('picture con sorgenti, img con dimensioni, lazy, alt e riga di credito', () => {
    const { container } = render(MediaFrame, {
      src: '/a.jpg',
      alt: 'La Terra sorge',
      width: 1280,
      height: 747,
      sources: [{ srcset: '/a.webp 1280w', type: 'image/webp' }],
      credit: 'Foto NASA',
      fade: 'bottom',
    });
    const img = screen.getByRole('img', { name: 'La Terra sorge' }) as HTMLImageElement;
    expect(img.getAttribute('loading')).toBe('lazy');
    expect(img.getAttribute('width')).toBe('1280');
    expect(container.querySelector('source')?.getAttribute('type')).toBe('image/webp');
    expect(container.querySelector('figcaption')?.textContent).toBe('Foto NASA');
    expect(container.querySelector('[data-fade="bottom"]')).not.toBeNull();
  });
});

describe('Callout', () => {
  it('rende titolo, contenuto e tipo', () => {
    const { container } = render(Callout, { kind: 'warning', title: 'Attenzione', id: 'n', children: text('Dati esterni') });
    const c = container.querySelector('#n')!;
    expect(c.getAttribute('data-kind')).toBe('warning');
    expect(c.textContent).toContain('Attenzione');
    expect(c.textContent).toContain('Dati esterni');
    expect(c.getAttribute('role')).toBeNull(); // non è una regione live
  });
});

describe('SubNav', () => {
  it('contiene l’h1 della pagina e lo slot laterale', () => {
    render(SubNav, { title: 'Telemetria', aside: text('Connesso') });
    expect(screen.getByRole('heading', { level: 1, name: 'Telemetria' })).toBeTruthy();
    expect(screen.getByText('Connesso')).toBeTruthy();
  });
});

describe('scrollFx', () => {
  it('progressFor: settle cresce entrando dal basso, recede cala uscendo dall’alto', () => {
    expect(progressFor('settle', 0.4, 300)).toBe(0.4);
    expect(progressFor('settle', 0.4, -10)).toBe(1);
    expect(progressFor('recede', 0.4, -200)).toBe(0.4);
    expect(progressFor('recede', 0.4, 50)).toBe(1);
    expect(progressFor('settle', 3, 10)).toBe(1);
    expect(THRESHOLDS).toHaveLength(21);
  });

  function stubIO() {
    const observers: { cb: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }[] = [];
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        disconnect = vi.fn();
        constructor(cb: IntersectionObserverCallback) {
          observers.push({ cb, disconnect: this.disconnect });
        }
        observe() {}
      },
    );
    return observers;
  }

  it('senza supporto CSS usa IntersectionObserver e scrive --fx-progress', () => {
    const observers = stubIO();
    const el = document.createElement('div');
    const a = scrollFx(el, { mode: 'settle', forceFallback: true });
    expect(el.dataset.fx).toBe('io');
    observers[0]!.cb(
      [{ intersectionRect: { height: 250 }, boundingClientRect: { height: 500, top: 400 }, rootBounds: { height: 800 } } as unknown as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
    expect(el.style.getPropertyValue('--fx-progress')).toBe('0.500');
    a.destroy();
    expect(el.dataset.fx).toBeUndefined();
    expect(observers[0]!.disconnect).toHaveBeenCalled();
  });

  it('con prefers-reduced-motion non fa nulla', () => {
    const observers = stubIO();
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener() {}, removeEventListener() {} }));
    const el = document.createElement('div');
    scrollFx(el, { mode: 'recede', forceFallback: true }).destroy();
    expect(observers).toHaveLength(0);
    expect(el.dataset.fx).toBeUndefined();
  });

  it('mode none non osserva', () => {
    const observers = stubIO();
    const el = document.createElement('div');
    scrollFx(el, { mode: 'none', forceFallback: true });
    expect(observers).toHaveLength(0);
  });
});
