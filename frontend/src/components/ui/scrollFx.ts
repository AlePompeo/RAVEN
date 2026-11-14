// SPDX-License-Identifier: Apache-2.0
// Effetti legati allo scroll: CSS `animation-timeline: view()` dove supportato (nessun JS a runtime);
// altrimenti un IntersectionObserver a soglie scrive `--fx-progress` (0..1) sull'elemento osservato e
// `data-fx="io"` attiva le regole CSS equivalenti (app.css). Con prefers-reduced-motion: niente.

export type ScrollFxMode = 'settle' | 'recede';

const REDUCED = '(prefers-reduced-motion: reduce)';

export function supportsScrollTimeline(): boolean {
  return (
    typeof CSS !== 'undefined' &&
    typeof CSS.supports === 'function' &&
    CSS.supports('animation-timeline: view()') &&
    CSS.supports('animation-timeline: scroll()')
  );
}

/** Soglie ogni 5%: abbastanza fluido per transform/opacity, pochi callback. */
export const THRESHOLDS = Array.from({ length: 21 }, (_, i) => i / 20);

/**
 * Avanzamento dell'effetto da una voce IO.
 * settle: cresce mentre l'elemento entra dal basso (resta 1 dopo).
 * recede: cala mentre l'elemento esce dall'alto (1 finché è sotto il bordo superiore).
 */
export function progressFor(mode: ScrollFxMode, ratio: number, top: number): number {
  const r = Math.max(0, Math.min(1, ratio));
  if (mode === 'settle') return top > 0 ? r : 1;
  return top < 0 ? r : 1;
}

export interface ScrollFxOptions {
  /** 'none': nessun effetto (comodo per usare l'azione in modo condizionale). */
  mode: ScrollFxMode | 'none';
  /** Per i test: forza l'assenza del supporto CSS. */
  forceFallback?: boolean;
}

/** Azione Svelte: `<div use:scrollFx={{ mode: 'settle' }}>`. */
export function scrollFx(node: HTMLElement, opts: ScrollFxOptions) {
  let mode = opts.mode;
  let io: IntersectionObserver | null = null;
  const mql = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED) : null;

  const stop = () => {
    io?.disconnect();
    io = null;
    delete node.dataset.fx;
    node.style.removeProperty('--fx-progress');
  };
  const start = () => {
    stop();
    if (mode === 'none' || mql?.matches) return;
    if (!opts.forceFallback && supportsScrollTimeline()) return;
    if (typeof IntersectionObserver === 'undefined') return;
    node.dataset.fx = 'io';
    io = new IntersectionObserver(
      (entries) => {
        const e = entries[entries.length - 1];
        if (!e) return;
        // rispetto alla parte che PUÒ stare nella finestra: un elemento più alto del viewport arriva comunque a 1
        const h = e.boundingClientRect.height;
        const full = Math.min(h, e.rootBounds?.height ?? h) || 1;
        if (mode === 'none') return;
        const p = progressFor(mode, e.intersectionRect.height / full, e.boundingClientRect.top);
        node.style.setProperty('--fx-progress', p.toFixed(3));
      },
      { threshold: THRESHOLDS },
    );
    io.observe(node);
  };

  mql?.addEventListener('change', start);
  start();

  return {
    update(next: ScrollFxOptions) {
      const was = mode;
      mode = next.mode;
      if ((was === 'none') !== (mode === 'none')) start();
    },
    destroy() {
      mql?.removeEventListener('change', start);
      stop();
    },
  };
}
