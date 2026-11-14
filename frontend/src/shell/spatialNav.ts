// SPDX-License-Identifier: Apache-2.0
// Modalità TV (10 piedi) e navigazione spaziale con le frecce, senza dipendenze.
// Attiva per schermi >= 1920px senza puntatore fine, oppure con ?tv=1 (ricordato; ?tv=0 la spegne).
// Frecce: il focus passa all'elemento focalizzabile più vicino nella direzione; i controlli che usano
// già un asse (cursori, campi di testo, tablist orizzontali, toolbar verticali) tengono quell'asse.
// Back/Escape chiude il menu o il foglio aperto; Invio e Spazio restano quelli nativi.
// Chunk lazy: main.ts lo carica solo in modalità TV (il rilevamento sta in tv.ts, nel bundle iniziale).
import { isTvMode } from './tv';
export { detectTv, isTvMode } from './tv';

export type Dir = 'left' | 'right' | 'up' | 'down';
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

const KEYS: Record<string, Dir> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
const BACK_KEYS = new Set(['GoBack', 'BrowserBack', 'Escape']);
const BACK_CODES = new Set([461, 10009]); // LG webOS, Samsung Tizen

/** Punteggio del candidato: distanza lungo la direzione + 2x lo scarto laterale; null se non è in quella direzione. */
export function score(from: Box, to: Box, dir: Dir): number | null {
  const fc = { x: from.x + from.w / 2, y: from.y + from.h / 2 };
  const tc = { x: to.x + to.w / 2, y: to.y + to.h / 2 };
  let main: number;
  let side: number;
  if (dir === 'right') {
    main = to.x - (from.x + from.w);
    if (tc.x <= fc.x + 1) return null;
    side = Math.max(0, Math.abs(tc.y - fc.y) - (from.h + to.h) / 4);
  } else if (dir === 'left') {
    main = from.x - (to.x + to.w);
    if (tc.x >= fc.x - 1) return null;
    side = Math.max(0, Math.abs(tc.y - fc.y) - (from.h + to.h) / 4);
  } else if (dir === 'down') {
    main = to.y - (from.y + from.h);
    if (tc.y <= fc.y + 1) return null;
    side = Math.max(0, Math.abs(tc.x - fc.x) - (from.w + to.w) / 4);
  } else {
    main = from.y - (to.y + to.h);
    if (tc.y >= fc.y - 1) return null;
    side = Math.max(0, Math.abs(tc.x - fc.x) - (from.w + to.w) / 4);
  }
  return Math.max(0, main) + 2 * side;
}

/**
 * Indice del miglior candidato (o -1). `last[i]` = elemento fluttuante (es. "Spiega questa pagina", fisso in basso a
 * destra): scelto solo se in quella direzione non c'è nient'altro, così non ruba il focus al contenuto della pagina.
 */
export function pick(from: Box, candidates: Box[], dir: Dir, last?: readonly boolean[]): number {
  let best = -1;
  let bestScore = Infinity;
  candidates.forEach((c, i) => {
    let s = score(from, c, dir);
    if (s !== null && last?.[i]) s += 1e9; // dopo qualunque candidato normale (i punteggi sono pixel)
    if (s !== null && s < bestScore) {
      bestScore = s;
      best = i;
    }
  });
  return best;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root: Document): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => {
    if (el.closest('[inert], [hidden]')) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  });
}

/** Il controllo con il focus usa già quest'asse? */
export function ownsAxis(el: Element | null, dir: Dir): boolean {
  if (!el) return false;
  const horizontal = dir === 'left' || dir === 'right';
  const tag = el.tagName;
  if (tag === 'TEXTAREA') return true;
  if (tag === 'SELECT') return !horizontal;
  if (tag === 'INPUT') {
    const t = (el as HTMLInputElement).type;
    if (t === 'range') return horizontal;
    if (t === 'checkbox' || t === 'radio' || t === 'button' || t === 'submit') return false;
    return horizontal; // testo: il cursore si muove a sinistra/destra
  }
  const group = el.closest('[role="tablist"], [role="toolbar"], [role="radiogroup"], [role="listbox"]');
  if (group) {
    // listbox (selettore della lingua): verticale salvo aria-orientation="horizontal"
    const vertical =
      group.getAttribute('aria-orientation') === 'vertical' ||
      (group.getAttribute('role') === 'listbox' && group.getAttribute('aria-orientation') !== 'horizontal');
    // l'asse del gruppo resta al gruppo (scorre tra le voci); l'altro asse esce dal gruppo
    return vertical ? !horizontal : horizontal;
  }
  return false;
}

/** Installa i gestori (navigazione spaziale, Back, cursore che si nasconde). Ritorna la funzione di rimozione. */
export function installSpatialNav(doc: Document = document): () => void {
  let idle: ReturnType<typeof setTimeout> | undefined;
  const html = doc.documentElement;

  const onKey = (e: KeyboardEvent) => {
    if (!isTvMode()) return;
    const active = doc.activeElement as HTMLElement | null;
    if (BACK_KEYS.has(e.key) || BACK_CODES.has(e.keyCode)) {
      if (e.key === 'Escape') return; // i componenti gestiscono già Esc (menu, foglio)
      e.preventDefault();
      active?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return;
    }
    const dir = KEYS[e.key];
    if (!dir || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (ownsAxis(active, dir)) return;
    const all = focusables(doc);
    const from = active && active !== doc.body ? active.getBoundingClientRect() : { x: 0, y: -1, width: innerWidth, height: 1 };
    const fromBox = { x: from.x, y: from.y, w: from.width, h: from.height };
    const fromMain = !!active?.closest('main');
    const others = all.filter((el) =>
      el !== active && !(fromMain && dir !== 'up' && !el.closest('main') && el.closest('header')),
    );
    const i = pick(fromBox, others.map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    }), dir, others.map((el) => el.hasAttribute('data-nav-last')));
    if (i < 0) return;
    e.preventDefault();
    e.stopPropagation(); // la freccia non arriva al controllo di partenza (es. scena che ruoterebbe)
    let next = others[i]!;
    // dalla barra verso il basso: il primo controllo della pagina (ordine del DOM, es. la CTA), non il più vicino in pixel
    if (dir === 'down' && active?.closest('header') && !next.closest('header')) next = all.find((el) => el.closest('main')) ?? next;
    next.focus({ preventScroll: true });
    next.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
  };

  // cursore nascosto dopo 3 s di inattività (solo TV)
  const wake = () => {
    html.classList.remove('tv-idle');
    clearTimeout(idle);
    if (isTvMode()) idle = setTimeout(() => html.classList.add('tv-idle'), 3000);
  };

  doc.addEventListener('keydown', onKey, true);
  doc.addEventListener('pointermove', wake, { passive: true });
  wake();
  return () => {
    doc.removeEventListener('keydown', onKey, true);
    doc.removeEventListener('pointermove', wake);
    clearTimeout(idle);
  };
}
