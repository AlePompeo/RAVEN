// SPDX-License-Identifier: Apache-2.0
// Logica pura dei messaggi: segnaposto con nome ({name}), plurali con Intl.PluralRules, numeri/date/unità con Intl.
// Non lancia mai: un messaggio mancante ripiega sull'inglese; una chiave assente anche in inglese diventa ⟦chiave⟧ solo
// in sviluppo, stringa vuota in produzione.
import { LANG_META, type Lang } from './locales';

/** Valore di catalogo: testo, oppure forme plurali CLDR (zero/one/two/few/many/other; 'other' obbligatoria). */
export type PluralForms = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };
export type Message = string | PluralForms;
export type Catalog = Readonly<Record<string, Message>>;
export type Params = Readonly<Record<string, string | number>>;


/** Tag Intl della lingua. */
export function intlTag(lang: Lang): string {
  return LANG_META[lang].tag;
}

const cache = new Map<string, Intl.NumberFormat | Intl.PluralRules | Intl.DateTimeFormat>();
function memo<T extends Intl.NumberFormat | Intl.PluralRules | Intl.DateTimeFormat>(key: string, make: () => T): T {
  let v = cache.get(key) as T | undefined;
  if (!v) {
    v = make();
    if (cache.size > 200) cache.clear();
    cache.set(key, v);
  }
  return v;
}


export function formatNumber(lang: Lang, n: number, opts: Intl.NumberFormatOptions = {}): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '–';
  try {
    return memo(`n|${lang}|${JSON.stringify(opts)}`, () => new Intl.NumberFormat(intlTag(lang), opts)).format(n);
  } catch {
    return String(n);
  }
}

export function formatDate(lang: Lang, d: Date | number, opts: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }): string {
  const date = d instanceof Date ? d : new Date(d);
  if (Number.isNaN(date.getTime())) return '–';
  try {
    return memo(`d|${lang}|${JSON.stringify(opts)}`, () => new Intl.DateTimeFormat(intlTag(lang), opts)).format(date);
  } catch {
    return date.toISOString();
  }
}

/** Unità di Intl (meter, kilometer, degree, hour, ...) dove esiste; altrimenti numero + spazio fine + simbolo (dB, Mbps). */
export function formatUnit(lang: Lang, n: number, unit: string, opts: Intl.NumberFormatOptions = {}): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '–';
  try {
    return memo(`u|${lang}|${unit}|${JSON.stringify(opts)}`, () => new Intl.NumberFormat(intlTag(lang), { ...opts, style: 'unit', unit })).format(n);
  } catch {
    let num: string;
    try {
      num = memo(`n|${lang}|${JSON.stringify(opts)}`, () => new Intl.NumberFormat(intlTag(lang), opts)).format(n);
    } catch {
      num = String(n);
    }
    return `${num} ${unit}`;
  }
}

export function pluralCategory(lang: Lang, n: number): Intl.LDMLPluralRule {
  try {
    return memo(`p|${lang}`, () => new Intl.PluralRules(intlTag(lang))).select(n);
  } catch {
    return 'other';
  }
}

function pickForm(lang: Lang, m: Message, params: Params | undefined): string | undefined {
  if (typeof m === 'string') return m;
  if (!m || typeof m !== 'object') return undefined;
  const n = Number(params?.count);
  const cat = Number.isFinite(n) ? pluralCategory(lang, n) : 'other';
  // forme esatte "=0" non servono: le categorie plurali vengono da Intl.PluralRules
  return m[cat] ?? m.other;
}

/** Sostituisce {nome} con il parametro; i numeri passano da formatNumber; segnaposto senza valore resta com'è. */
export function interpolate(lang: Lang, s: string, params?: Params): string {
  if (!params) return s;
  return s.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (all, name: string) => {
    if (!Object.prototype.hasOwnProperty.call(params, name)) return all;
    const v = params[name];
    return typeof v === 'number' ? formatNumber(lang, v) : String(v);
  });
}

export interface Translator {
  lang: Lang;
  messages: Catalog | null;
  fallback: Catalog;
  dev: boolean;
}

export function translate(tr: Translator, key: string, params?: Params): string {
  try {
    const own = tr.messages ? pickForm(tr.lang, tr.messages[key] as Message, params) : undefined;
    if (own) return interpolate(tr.lang, own, params);
    const en = pickForm('en', tr.fallback[key] as Message, params);
    if (en) return interpolate(tr.lang, en, params);
  } catch {
    /* mai un'eccezione verso l'interfaccia */
  }
  return tr.dev ? `⟦${key}⟧` : '';
}

/** Segnaposto di un messaggio (tutte le forme plurali), ordinati: per il controllo di parità dei cataloghi. */
export function placeholders(m: Message): string[] {
  const texts = typeof m === 'string' ? [m] : Object.values(m ?? {});
  const out = new Set<string>();
  for (const t of texts) for (const x of String(t).matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)) out.add(x[1]!);
  return [...out].sort();
}
