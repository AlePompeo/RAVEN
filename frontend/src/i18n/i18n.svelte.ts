// SPDX-License-Identifier: Apache-2.0
// Lingua corrente come rune (`lang.current`) e `t()` reattiva: un componente che chiama t() nel markup si aggiorna al cambio
// di lingua senza ricaricare. Rune e non `$store`: il runtime degli store resterebbe fuori dal bundle iniziale.
// Inglese = sorgente, in due file: en.json (solo le stringhe del primo rendering: barra, piè di pagina, interruttori,
// titoli, hero della home; nel bundle iniziale) ed en.pages.json (tutto il resto: chunk lazy, caricato insieme al
// chunk della pagina, vedi ensurePages). Le altre lingue: un file con tutte le chiavi, un chunk a testa, a richiesta.
import en from './en.json';
import type enPages from './en.pages.json';
import * as core from './core';
import type { Catalog, Params } from './core';
import { LANG_KEY, LANG_META, localStore, parseLang, resolveLang, searchWithLang, langFromSearch, type Lang } from './locales';

/** Chiavi dei messaggi: unione generata dai cataloghi inglesi (una chiave assente fa fallire svelte-check). */
export type MessageKey = keyof typeof en | keyof typeof enPages;
export type { Lang } from './locales';

const EN = en as Catalog;
/** Ripiego inglese: en.json, poi anche en.pages.json quando è arrivato. */
let fb = $state.raw<Catalog>(EN);
let pagesP: Promise<void> | null = null;

/**
 * Carica en.pages.json (una volta). La shell lo attende insieme al chunk della pagina, quindi il contenuto di una
 * pagina non viene mai mostrato senza le sue stringhe inglesi (né in inglese né come ripiego delle altre lingue).
 */
export function ensurePages(): Promise<void> {
  pagesP ??= import('./en.pages.json')
    .then((m) => {
      fb = { ...EN, ...(m.default as Catalog) };
      loaded.set('en', fb);
      if (cur === 'en') msgs = fb;
    })
    .catch(() => {
      pagesP = null; // ritenta alla prossima pagina; intanto il ripiego resta en.json
    });
  return pagesP;
}
const loaders: Record<Exclude<Lang, 'en'>, () => Promise<{ default: unknown }>> = {
  it: () => import('./it.json'),
};
const loaded = new Map<Lang, Catalog>([['en', EN]]);

let cur = $state<Lang>('en');
let msgs = $state.raw<Catalog>(EN);
const dev = !!import.meta.env?.DEV;

export const lang = {
  get current(): Lang {
    return cur;
  },
  get dir(): 'ltr' {
    return LANG_META[cur].dir;
  },
  get tag(): string {
    return LANG_META[cur].tag;
  },
};

export function t(key: MessageKey, params?: Params): string {
  return core.translate({ lang: cur, messages: msgs, fallback: fb, dev }, key, params);
}
/** English text and numbers regardless of the site language: for the report, which is English only. */
export const tEn = (key: MessageKey, params?: Params): string => core.translate({ lang: 'en', messages: fb, fallback: fb, dev }, key, params);
export const formatNumberEn = (n: number, o?: Intl.NumberFormatOptions) => core.formatNumber('en', n, o);
export const formatNumber = (n: number, o?: Intl.NumberFormatOptions) => core.formatNumber(cur, n, o);
export const formatDate = (d: Date | number, o?: Intl.DateTimeFormatOptions) => core.formatDate(cur, d, o);
export const formatUnit = (n: number, unit: string, o?: Intl.NumberFormatOptions) => core.formatUnit(cur, n, unit, o);

/** Catalogo di una lingua (cache); null se il chunk non si carica o non è un oggetto. */
export async function loadCatalog(l: Lang): Promise<Catalog | null> {
  const have = loaded.get(l);
  if (have) return have;
  try {
    const m = await loaders[l as Exclude<Lang, 'en'>]();
    const c = m.default;
    if (!c || typeof c !== 'object' || Array.isArray(c)) return null;
    loaded.set(l, c as Catalog);
    return c as Catalog;
  } catch {
    return null;
  }
}

function applyDocument(l: Lang): void {
  try {
    const html = document.documentElement;
    html.lang = LANG_META[l].tag;
    html.dir = LANG_META[l].dir;
  } catch {
    /* nessun DOM (test) */
  }
}

function apply(l: Lang, c: Catalog): void {
  cur = l;
  msgs = c;
  applyDocument(l);
}

/** Solo per i test e la configurazione iniziale: imposta lingua e catalogo in modo sincrono. */
export function useCatalog(l: Lang, c: Catalog, enPagesCatalog?: Catalog): void {
  if (enPagesCatalog) {
    fb = { ...EN, ...enPagesCatalog };
    loaded.set('en', fb);
    pagesP = Promise.resolve();
  }
  if (l === 'en') c = fb;
  loaded.set(l, c);
  apply(l, c);
}

/** All'avvio: lingua risolta (URL > archivio > browser > en) e catalogo caricato prima del primo rendering. */
export async function initI18n(search = typeof location !== 'undefined' ? location.search : '', timeoutMs = 4000): Promise<Lang> {
  const l = resolveLang(search, localStore());
  if (l === 'en') {
    apply('en', fb);
    return 'en';
  }
  const c = await Promise.race([loadCatalog(l), new Promise<null>((r) => setTimeout(() => r(null), timeoutMs))]);
  if (c) apply(l, c);
  else apply('en', fb);
  return lang.current;
}

/** Dopo una navigazione interna: un ?lang= valido nell'URL vince sulla scelta in memoria. */
export async function syncLangFromUrl(search = location.search): Promise<void> {
  const l = langFromSearch(search);
  if (l && l !== cur) await setLang(l, { persist: false, url: false });
}

/**
 * Scelta dell'utente: carica il catalogo, poi aggiorna interfaccia, <html lang dir>, archivio (se disponibile) e URL
 * (replaceState, altri parametri intatti). Ritorna false se il catalogo non si carica (resta la lingua di prima).
 */
export async function setLang(next: Lang, o: { persist?: boolean; url?: boolean } = {}): Promise<boolean> {
  const l = parseLang(next);
  if (!l) return false;
  const c = await loadCatalog(l);
  if (!c) return false;
  if (o.persist !== false) {
    try {
      localStore()?.setItem(LANG_KEY, l);
    } catch {
      /* archiviazione bloccata: resta in memoria e nell'URL */
    }
  }
  if (o.url !== false) {
    try {
      const { pathname, search, hash } = location;
      history.replaceState(history.state, '', `${pathname}${searchWithLang(search, l)}${hash}`);
    } catch {
      /* ambiente senza History API */
    }
  }
  apply(l, c);
  return true;
}
