// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import enShell from './en.json';
import enPages from './en.pages.json';
import itCat from './it.json';
import { formatNumber, formatUnit, interpolate, placeholders, translate, type Catalog } from './core';
import { LANGS, LANG_META, langFromNavigator, langFromSearch, parseLang, resolveLang, searchWithLang, type Lang } from './locales';
import { initI18n, lang, setLang, t, useCatalog } from './i18n.svelte';

// sorgente inglese = en.json (primo rendering, bundle iniziale) + en.pages.json (lazy), chiavi disgiunte
const en: Catalog = { ...enShell, ...enPages };

describe('parità dei cataloghi (CI)', () => {
  const keys = Object.keys(en).sort();
  it('en.json ed en.pages.json non condividono chiavi', () => {
    expect(Object.keys(enShell).filter((k) => k in enPages)).toEqual([]);
  });
  it('lingue supportate: solo inglese e italiano', () => {
    expect([...LANGS]).toEqual(['en', 'it']);
  });
  it('it: stesse chiavi dell’inglese, stessi segnaposto, nessun valore vuoto', () => {
    const c = itCat as Catalog;
    expect(Object.keys(c).sort()).toEqual(keys);
    for (const k of Object.keys(c)) {
      const v = c[k]!;
      const src = en[k]!;
      expect(placeholders(v), `it ${k}`).toEqual(placeholders(src));
      if (typeof v === 'string') expect(v.trim(), `it ${k}`).not.toBe('');
      else {
        expect(typeof src, `it ${k}: plurale anche in en`).toBe('object');
        expect(v.other?.trim(), `it ${k}.other`).toBeTruthy();
        for (const f of Object.values(v)) expect(String(f).trim()).not.toBe('');
      }
    }
  });
  it('en: nessun valore vuoto', () => {
    for (const [k, v] of Object.entries(en)) {
      if (typeof v === 'string') expect(v.trim(), `en ${k}`).not.toBe('');
      else expect(v.other?.trim(), `en ${k}.other`).toBeTruthy();
    }
  });
});

describe('t() puro', () => {
  const tr = (l: Lang, messages: Catalog | null, dev = false) => ({ lang: l, messages, fallback: en, dev });
  it('segnaposto con nome; numeri formattati nella lingua', () => {
    expect(translate(tr('it', itCat as Catalog), 'shell.pageAnnounce', { title: 'Siti' })).toBe('Pagina Siti');
    expect(interpolate('it', '{a} e {b}', { a: 12345.5, b: 'x' })).toBe('12.345,5 e x');
    expect(interpolate('en', '{a}', { a: 1234.5 })).toBe('1,234.5');
    expect(interpolate('en', '{missing}', {})).toBe('{missing}');
  });
  it('plurali in inglese e italiano', () => {
    const h = (l: Lang, n: number) => translate(tr(l, l === 'it' ? (itCat as Catalog) : en), 'unit.hours', { count: n });
    expect([h('en', 1), h('en', 2)]).toEqual(['1 hour', '2 hours']);
    expect([h('it', 1), h('it', 5)]).toEqual(['1 ora', '5 ore']);
  });
  it('fallback all’inglese, chiave mancante mai mostrata in produzione, mai eccezioni', () => {
    expect(translate(tr('it', {}), 'home.try')).toBe('Try it');
    expect(translate(tr('it', null), 'home.try')).toBe('Try it');
    expect(translate(tr('it', { 'home.try': '' }), 'home.try')).toBe('Try it');
    expect(translate(tr('it', itCat as Catalog), 'nope.nope')).toBe('');
    expect(translate(tr('it', itCat as Catalog, true), 'nope.nope')).toBe('⟦nope.nope⟧');
    expect(translate(tr('it', { x: 42 as never }), 'x')).toBe('');
  });
  it('formattazione di numeri e unità', () => {
    expect(formatNumber('en', 12.5)).toBe('12.5');
    expect(formatUnit('it', 3, 'dB').replace(/\u202f/g, ' ')).toBe('3 dB');
    expect(formatUnit('en', 2, 'kilometer')).toBe('2 km');
    expect(formatNumber('en', NaN)).toBe('–');
  });
});

describe('scelta della lingua', () => {
  const store = (v: string | null) => ({ getItem: () => v, setItem: () => {} });
  const blocked = {
    getItem: () => {
      throw new Error('SecurityError');
    },
    setItem: () => {
      throw new Error('SecurityError');
    },
  };
  it('?lang= > archivio > browser > en', () => {
    expect(resolveLang('?lang=en', store('it'), ['it'])).toBe('en');
    expect(resolveLang('', store('it'), ['en'])).toBe('it');
    expect(resolveLang('', store(null), ['fr-FR', 'it-IT'])).toBe('it');
    expect(resolveLang('', store(null), ['fr-FR'])).toBe('en');
    expect(resolveLang('', blocked, ['de'])).toBe('en');
    expect(resolveLang('', null, [])).toBe('en');
  });
  it('valori malevoli, sconosciuti o di lingue rimosse ignorati', () => {
    for (const v of ['hi', 'zh', 'ar', 'ko', 'zh-Hans', 'AR', 'IT', 'it ', 'fr', '<script>', '__proto__', 'constructor', 'en;', '%00', 'x'.repeat(5000)])
      expect(langFromSearch(`?lang=${encodeURIComponent(v)}`)).toBeNull();
    expect(langFromSearch('?lang=ar&lang=it')).toBeNull();
    expect(langFromSearch('?lang=it&lang=ar')).toBe('it');
    expect(langFromSearch('?' + 'a'.repeat(5000))).toBeNull();
    expect(parseLang({ toString: () => 'it' })).toBeNull();
    expect(resolveLang('?lang=evil', store('<img>'), [42, null, 'zh-CN', 'ar-SA'])).toBe('en');
    expect(resolveLang('?lang=ar', store('ko'), ['hi'])).toBe('en');
    expect(langFromNavigator(['ko-KR'])).toBeNull();
    expect(langFromNavigator(null)).toBeNull();
  });
  it('searchWithLang conserva gli altri parametri', () => {
    expect(searchWithLang('?mode=avanzato&site=x', 'it')).toBe('?mode=avanzato&site=x&lang=it');
    expect(searchWithLang('?lang=it', 'en')).toBe('?lang=en');
  });
  it('codici di <html lang>: sempre ltr', () => {
    expect(LANGS.map((l) => LANG_META[l].tag)).toEqual(['en', 'it']);
    expect(LANGS.every((l) => LANG_META[l].dir === 'ltr')).toBe(true);
  });
});

describe('stato reattivo e documento', () => {
  afterEach(() => {
    localStorage.clear();
    useCatalog('it', itCat as Catalog); // predefinito dei test (test-setup.ts)
    history.replaceState(null, '', '/');
  });
  it('setLang aggiorna t(), <html lang dir>, archivio e URL con gli altri parametri', async () => {
    history.replaceState(null, '', '/simula?mode=avanzato#x');
    expect(await setLang('en')).toBe(true);
    expect(lang.current).toBe('en');
    expect(t('home.try')).toBe('Try it');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(localStorage.getItem('hb.lang')).toBe('en');
    expect(location.search).toBe('?mode=avanzato&lang=en');
    expect(location.hash).toBe('#x');
    await setLang('it');
    expect(document.documentElement.lang).toBe('it');
    expect(await setLang('ar' as Lang)).toBe(false);
    expect(lang.current).toBe('it');
  });
  it('archivio bloccato: la scelta resta in memoria, nessuna eccezione', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });
    expect(await setLang('en')).toBe(true);
    expect(t('nav.problem')).toBe('The problem');
    spy.mockRestore();
  });
  it('initI18n: predefinito inglese; ?lang= vince; codici rimossi ignorati', async () => {
    localStorage.clear();
    Object.defineProperty(navigator, 'languages', { value: ['en-US'], configurable: true });
    expect(await initI18n('')).toBe('en');
    expect(t('nav.problem')).toBe('The problem');
    expect(document.documentElement.lang).toBe('en');
    expect(await initI18n('?lang=it')).toBe('it');
    expect(t('nav.problem')).toBe('Il problema');
    localStorage.setItem('hb.lang', 'it');
    expect(await initI18n('?lang=<b>')).toBe('it');
    expect(await initI18n('?lang=ar')).toBe('it');
    localStorage.setItem('hb.lang', 'ko');
    expect(await initI18n('')).toBe('en');
  });
});
