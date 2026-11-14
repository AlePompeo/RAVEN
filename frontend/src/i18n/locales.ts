// SPDX-License-Identifier: Apache-2.0
// Lingue del sito (docs/design/grazinglink-ux.md, "Lingue"; docs/i18n.md). Predefinita: inglese.
// Scelta: ?lang= > localStorage hb.lang (try/catch, mai cookie) > lingua del browser se supportata > en.
// Ogni valore letto da URL, archiviazione o navigator è non fidato: vale solo se è esattamente uno dei codici sotto.

export type Lang = 'en' | 'it';
/** Ordine del selettore (deciso dall'utente). */
export const LANGS: readonly Lang[] = ['en', 'it'];
export const DEFAULT_LANG: Lang = 'en';
export const LANG_PARAM = 'lang';
export const LANG_KEY = 'hb.lang';

export interface LangMeta {
  /** Nome nella propria scrittura (mostrato nel selettore). */
  native: string;
  /** Valore di <html lang>. */
  tag: string;
  dir: 'ltr';
}

export const LANG_META: Readonly<Record<Lang, LangMeta>> = {
  en: { native: 'English', tag: 'en', dir: 'ltr' },
  it: { native: 'Italiano', tag: 'it', dir: 'ltr' },
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

/** Codice valido (confronto esatto) oppure null. */
export function parseLang(raw: unknown): Lang | null {
  return typeof raw === 'string' && (LANGS as readonly string[]).includes(raw) ? (raw as Lang) : null;
}

export function langFromSearch(search: string): Lang | null {
  if (typeof search !== 'string' || search.length > 4000) return null;
  try {
    return parseLang(new URLSearchParams(search).get(LANG_PARAM));
  } catch {
    return null;
  }
}

export function langFromStore(store: StorageLike | null): Lang | null {
  try {
    return parseLang(store?.getItem(LANG_KEY));
  } catch {
    return null;
  }
}

/** Prima lingua del browser supportata (sottotag primario). */
export function langFromNavigator(list: readonly unknown[] | null | undefined): Lang | null {
  if (!Array.isArray(list)) return null;
  for (const raw of list.slice(0, 20)) {
    if (typeof raw !== 'string' || raw.length > 35) continue;
    const tag = raw.toLowerCase();
    const primary = tag.split(/[-_]/, 1)[0] ?? '';
    const l = parseLang(primary);
    if (l) return l;
  }
  return null;
}

export function navigatorLangs(): readonly string[] {
  try {
    if (typeof navigator === 'undefined') return [];
    return navigator.languages?.length ? navigator.languages : navigator.language ? [navigator.language] : [];
  } catch {
    return [];
  }
}

export function resolveLang(search: string, store: StorageLike | null, nav: readonly unknown[] = navigatorLangs()): Lang {
  return langFromSearch(search) ?? langFromStore(store) ?? langFromNavigator(nav) ?? DEFAULT_LANG;
}

/** Query string con ?lang= impostato, gli altri parametri intatti. */
export function searchWithLang(search: string, l: Lang): string {
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(search);
  } catch {
    p = new URLSearchParams();
  }
  p.set(LANG_PARAM, l);
  return `?${p.toString()}`;
}

export function localStore(): StorageLike | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}
