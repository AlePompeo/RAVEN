// SPDX-License-Identifier: Apache-2.0
/** Registro del consenso per categorie non essenziali. Default: nessuna categoria attiva. */
export const CATEGORIES = ['analytics', 'media'] as const;
export type Category = (typeof CATEGORIES)[number];
export const STORAGE_KEY = 'consent.v1';
const ATTR = 'data-consent-category';
const SRC_ATTR = 'data-consent-src';

interface Entry {
  granted: boolean;
  at: string;
}
type Store = Partial<Record<Category, Entry>>;

function read(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return {};
    const out: Store = {};
    for (const c of CATEGORIES) {
      const e = (parsed as Record<string, unknown>)[c];
      if (typeof e === 'object' && e !== null) {
        const { granted, at } = e as Record<string, unknown>;
        if (typeof granted === 'boolean' && typeof at === 'string') out[c] = { granted, at };
      }
    }
    return out;
  } catch {
    return {};
  }
}

/** true se la scelta e stata salvata; ogni errore di storage vale come "nessun consenso". */
function write(category: Category, granted: boolean): boolean {
  try {
    const store = read();
    store[category] = { granted, at: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    return true;
  } catch {
    return false;
  }
}

/** Categorie revocate in questa sessione anche se la revoca non e stata salvata (fail safe). */
const sessionRevoked = new Set<Category>();

/** Valore effettivamente salvato nello storage (puo restare true se la revoca non e stata persistita). */
export function isStoredGranted(category: Category): boolean {
  return read()[category]?.granted === true;
}

export function isGranted(category: Category): boolean {
  return !sessionRevoked.has(category) && isStoredGranted(category);
}

/** Restituisce false se la scelta non ha potuto essere salvata (consenso non attivo). */
export function grant(category: Category): boolean {
  const saved = write(category, true);
  if (saved) sessionRevoked.delete(category);
  return saved;
}

/**
 * Revoca e rimuove i tag script iniettati. Il codice gia eseguito resta in memoria fino al
 * ricaricamento della pagina. Restituisce false se la revoca non ha potuto essere salvata.
 */
export function revoke(category: Category): boolean {
  // Fail safe: anche se la persistenza fallisce, in questa sessione non si caricano piu script.
  sessionRevoked.add(category);
  const saved = write(category, false);
  if (saved) sessionRevoked.delete(category);
  document.querySelectorAll(`script[${ATTR}="${category}"]`).forEach((s) => s.remove());
  return saved;
}

export interface LoadScriptOptions {
  /** Host (con eventuale porta) ammessi per gli script di terze parti; se assente, qualsiasi host https. */
  allowedHosts?: readonly string[];
  /** Valore SRI, es. "sha384-...". */
  integrity?: string;
}

/**
 * Inietta uno script solo se la categoria e concessa; null altrimenti.
 * Ammessi solo URL https: oppure della stessa origine della pagina. Lo script e caricato con
 * crossorigin="anonymous" e referrerpolicy="no-referrer".
 * NB: la Content-Security-Policy del server (script-src) deve consentire esplicitamente ogni host
 * usato qui, altrimenti il browser bloccherà lo script anche con consenso.
 */
export function loadScript(category: Category, src: string, opts: LoadScriptOptions = {}): HTMLScriptElement | null {
  if (!isGranted(category)) return null;
  let url: URL;
  try {
    url = new URL(src, document.baseURI);
  } catch {
    return null;
  }
  const sameOrigin = url.origin === location.origin;
  if (!sameOrigin && url.protocol !== 'https:') return null;
  if (sameOrigin && url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  if (opts.allowedHosts && !sameOrigin && !opts.allowedHosts.includes(url.host)) return null;
  for (const s of document.querySelectorAll<HTMLScriptElement>(`script[${ATTR}="${category}"]`)) {
    if (s.getAttribute(SRC_ATTR) === url.href) return s;
  }
  const el = document.createElement('script');
  el.src = url.href;
  el.async = true;
  el.setAttribute('crossorigin', 'anonymous');
  el.setAttribute('referrerpolicy', 'no-referrer');
  if (opts.integrity) el.integrity = opts.integrity;
  el.setAttribute(ATTR, category);
  el.setAttribute(SRC_ATTR, url.href);
  document.head.appendChild(el);
  return el;
}
