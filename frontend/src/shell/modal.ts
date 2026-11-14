// SPDX-License-Identifier: Apache-2.0
// Azione Svelte per finestre modali (pannello fonte, foglio "Spiega questa pagina"):
// sposta il nodo in <body>, rende inert il resto della pagina (tranne la regione degli annunci),
// intrappola il focus (Tab/Maiusc+Tab), chiude con Esc e restituisce il focus all'elemento di partenza.
// In modalità TV il tasto Indietro arriva qui come Esc (vedi spatialNav).

export interface ModalOptions {
  onClose: () => void;
  /** Elemento che ha aperto la finestra: riceve il focus alla chiusura (default: l'elemento attivo all'apertura). */
  returnTo?: HTMLElement | null;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

export function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest('[inert], [hidden]') && el.getAttribute('aria-hidden') !== 'true');
}

/** Ciclo del focus: ritorna l'elemento a cui spostarsi, o null se il comportamento nativo va bene. */
export function nextTrapTarget(items: HTMLElement[], active: Element | null, shift: boolean, container: HTMLElement): HTMLElement | null {
  if (items.length === 0) return container;
  const first = items[0]!;
  const last = items[items.length - 1]!;
  if (active === null || !container.contains(active) || active === container) return shift ? last : first;
  if (shift && active === first) return last;
  if (!shift && active === last) return first;
  return null;
}

const stack: HTMLElement[] = []; // finestre modali aperte (anche annidate): gestisce i tasti solo la più recente

export function modal(node: HTMLElement, opts: ModalOptions) {
  let options = opts;
  const opener = (opts.returnTo ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null)) as HTMLElement | null;
  const doc = node.ownerDocument;
  doc.body.appendChild(node);

  // body > #app > (nav, main, footer, #announcer): si isolano i figli di #app (tranne gli annunci) e gli altri figli di body
  const made: Element[] = [];
  const candidates: Element[] = [];
  for (const el of Array.from(doc.body.children)) {
    if (el.id === 'app') candidates.push(...Array.from(el.children));
    else candidates.push(el);
  }
  for (const el of candidates) {
    if (el === node || el.id === 'announcer' || el.tagName === 'SCRIPT' || el.hasAttribute('inert')) continue;
    el.setAttribute('inert', '');
    made.push(el);
  }
  stack.push(node);
  doc.documentElement.classList.add('modal-open');

  if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '-1');
  const start = focusables(node).find((el) => el.hasAttribute('data-autofocus')) ?? focusables(node)[0] ?? node;
  start.focus({ preventScroll: true });

  // il listener sta sul documento: se il focus finisce sul body (es. il pulsante premuto è stato rimosso) Esc e Tab funzionano ancora
  function onKey(e: KeyboardEvent) {
    if (stack[stack.length - 1] !== node) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      options.onClose();
      return;
    }
    if (e.key !== 'Tab') return;
    const target = nextTrapTarget(focusables(node), doc.activeElement, e.shiftKey, node);
    if (target) {
      e.preventDefault();
      target.focus({ preventScroll: true });
    }
  }
  doc.addEventListener('keydown', onKey);

  return {
    update(o: ModalOptions) {
      options = o;
    },
    destroy() {
      doc.removeEventListener('keydown', onKey);
      const at = stack.indexOf(node);
      if (at >= 0) stack.splice(at, 1);
      for (const el of made) el.removeAttribute('inert');
      if (stack.length === 0) doc.documentElement.classList.remove('modal-open');
      if (opener && opener.isConnected) opener.focus({ preventScroll: true });
      node.remove();
    },
  };
}
