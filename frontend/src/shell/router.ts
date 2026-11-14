// SPDX-License-Identifier: Apache-2.0
import type { Component } from 'svelte';
import type { MessageKey } from '../i18n/i18n.svelte';

/** Una pagina registrata: percorso, titolo e caricamento lazy del componente. */
export interface PageModule {
  path: string;
  /** Titolo letterale (ripiego quando manca titleKey; usato dai test e da pagine senza catalogo). */
  title?: string;
  /** Chiave del titolo nel catalogo (docs/i18n.md); se presente vince su `title` (ripiego). */
  titleKey?: MessageKey;
  /** Chiave dell'etichetta di navigazione nel catalogo; se presente vince su `navLabel`. */
  navKey?: MessageKey;
  /** Mostrata nella navigazione principale se presente (valore = etichetta). */
  navLabel?: string;
  /** Gruppo di navigazione: 'main' (barra globale, predefinito) o 'legal' (piè di pagina). */
  navGroup?: 'main' | 'legal';
  /** Ordine nella navigazione (crescente); a parità o se assente, per percorso. */
  order?: number;
  /**
   * Vecchie rotte che portano qui: percorso -> parametri aggiunti (es. { '/wave': 'tab=onda' }). La shell sostituisce
   * l'URL con quello nuovo, query e hash conservati (redirectTo).
   */
  aliases?: Record<string, string>;
  /** Solo nelle voci di alias create dal router: URL di destinazione. */
  redirect?: string;
  /** Voce della barra da evidenziare per una pagina fuori barra (es. /telemetry -> /laboratorio). */
  section?: string;
  load: () => Promise<{ default: Component<any> }>;
}

/**
 * URL di destinazione di un alias: percorso del bersaglio, parametri della query originale (scenario, ?mode=) più
 * quelli del bersaglio (es. tab=onda, che vince), hash originale.
 */
export function redirectTo(target: string, search: string, hash = ''): string {
  const [p, q] = target.split('?');
  const s = new URLSearchParams(search);
  new URLSearchParams(q).forEach((v, k) => s.set(k, v));
  const qs = s.toString();
  return p + (qs ? '?' + qs : '') + hash;
}

export interface Router {
  resolve(url: string): PageModule | undefined;
  pages(): PageModule[];
}

function cleanBase(base: string): string {
  let b = base.startsWith('/') ? base : '/' + base;
  if (!b.endsWith('/')) b += '/';
  return b;
}

/** Rimuove query, hash, base e slash finale; garantisce lo slash iniziale. */
export function normalizePath(url: string, base = '/'): string {
  let p = url.split('#', 1)[0] ?? '';
  p = p.split('?', 1)[0] ?? '';
  if (!p.startsWith('/')) p = '/' + p;
  const b = cleanBase(base);
  if (b !== '/') {
    if (p === b.slice(0, -1) || p === b) p = '/';
    else if (p.startsWith(b)) p = p.slice(b.length - 1);
  }
  if (p.length > 1) p = p.replace(/\/+$/, '');
  return p === '' ? '/' : p;
}

/** Antepone la base a un percorso interno (per href e pushState). */
export function withBase(path: string, base = '/'): string {
  const b = cleanBase(base);
  const p = path.startsWith('/') ? path : '/' + path;
  return b === '/' ? p : b.slice(0, -1) + p;
}

export function createRouter(pages: PageModule[], notFound?: PageModule, base = '/'): Router {
  const map = new Map<string, PageModule>();
  for (const p of pages) {
    const key = normalizePath(p.path);
    if (map.has(key) && import.meta.env?.DEV) {
      console.warn(`[router] percorso duplicato: ${key}; vince l'ultimo registrato`);
    }
    map.set(key, p);
  }
  const sorted = [...map.values()].sort(
    (a, b) =>
      (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER) || a.path.localeCompare(b.path),
  );
  // alias dopo le pagine vere: un percorso registrato non viene mai coperto da un alias
  for (const p of sorted)
    for (const [from, q] of Object.entries(p.aliases ?? {}))
      if (!map.has(from)) map.set(from, { ...p, path: from, redirect: p.path + (q ? '?' + q : '') });
  return {
    resolve: (url) => map.get(normalizePath(url, base)) ?? notFound,
    pages: () => sorted,
  };
}

/** Pagine con etichetta di navigazione del gruppo richiesto (assente = 'main'), nell'ordine del router. */
export function navPages(pages: readonly PageModule[], group: 'main' | 'legal'): PageModule[] {
  return pages.filter((p) => (p.navKey || p.navLabel) && (p.navGroup ?? 'main') === group);
}

/** Costruisce il router dai moduli `pages/*\/index.ts` (export default PageModule). */
export function routerFromModules(mods: Record<string, { default: PageModule }>, base = '/'): Router {
  const all = Object.values(mods).map((m) => m.default);
  const notFound = all.find((p) => p.path === '/404');
  return createRouter(
    all.filter((p) => p.path !== '/404'),
    notFound,
    base,
  );
}
