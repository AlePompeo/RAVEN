// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest';
import { createRouter, navPages, normalizePath, redirectTo, withBase, type PageModule } from './router';
import { router as appRouter } from '../registry';
import { t } from '../i18n/i18n.svelte';

// etichette dal catalogo (i test girano in italiano, test-setup.ts)
const label = (p: PageModule) => (p.navKey ? t(p.navKey) : p.navLabel);

describe('base path', () => {
  it('normalizePath rimuove la base', () => {
    expect(normalizePath('/app/telemetry/?x=1', '/app/')).toBe('/telemetry');
    expect(normalizePath('/app/', '/app/')).toBe('/');
    expect(normalizePath('/app', '/app/')).toBe('/');
    expect(normalizePath('/telemetry', '/')).toBe('/telemetry');
  });
  it('withBase antepone la base', () => {
    expect(withBase('/telemetry', '/app/')).toBe('/app/telemetry');
    expect(withBase('/', '/app/')).toBe('/app/');
    expect(withBase('/telemetry', '/')).toBe('/telemetry');
  });
  it('resolve usa la base del router', () => {
    const r = createRouter([page('/telemetry')], undefined, '/app/');
    expect(r.resolve('/app/telemetry')?.path).toBe('/telemetry');
  });
});

describe('ordine e duplicati', () => {
  it('ordina per order poi per percorso', () => {
    const p = (path: string, order?: number): PageModule => ({ ...page(path), ...(order === undefined ? {} : { order }) });
    const r = createRouter([p('/b'), p('/a'), p('/z', 1)]);
    expect(r.pages().map((x) => x.path)).toEqual(['/z', '/a', '/b']);
  });
  it('avvisa in dev sui percorsi duplicati', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    createRouter([page('/a'), page('/a/')]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});

const page = (path: string): PageModule => ({ path, title: path, load: async () => ({ default: {} as never }) });

describe('router', () => {
  it('risolve un percorso registrato', () => {
    const r = createRouter([page('/'), page('/telemetry')]);
    expect(r.resolve('/telemetry')?.path).toBe('/telemetry');
  });
  it('usa la pagina 404 per percorsi sconosciuti', () => {
    const r = createRouter([page('/')], page('/404'));
    expect(r.resolve('/boh')?.path).toBe('/404');
  });
  it('normalizza slash finale e query', () => {
    const r = createRouter([page('/telemetry')]);
    expect(r.resolve('/telemetry/?x=1')?.path).toBe('/telemetry');
  });
  it('senza fallback restituisce undefined', () => {
    expect(createRouter([page('/')]).resolve('/x')).toBeUndefined();
  });
  it('normalizePath gestisce hash, radice e slash mancante', () => {
    expect(normalizePath('/a/#frag')).toBe('/a');
    expect(normalizePath('?q=1')).toBe('/');
    expect(normalizePath('a')).toBe('/a');
    expect(normalizePath('/')).toBe('/');
  });
});

describe('gruppi di navigazione', () => {
  it('navPages separa barra principale e piè di pagina; senza etichetta la pagina è esclusa', () => {
    const p = (path: string, extra: Partial<PageModule>): PageModule => ({ ...page(path), ...extra });
    const r = createRouter([
      p('/', { navLabel: 'Home', order: 0 }),
      p('/telemetry', { navLabel: 'Telemetria', order: 20 }),
      p('/privacy', { navLabel: 'Privacy', navGroup: 'legal', order: 91 }),
      p('/hidden', {}),
    ]);
    expect(navPages(r.pages(), 'main').map((x) => x.path)).toEqual(['/', '/telemetry']);
    expect(navPages(r.pages(), 'legal').map((x) => x.path)).toEqual(['/privacy']);
  });
});

describe('alias delle vecchie rotte', () => {
  it('redirectTo conserva query e hash e aggiunge i parametri del bersaglio (che vincono)', () => {
    expect(redirectTo('/simula?tab=onda', '?site=shackleton&mode=avanzato', '#x')).toBe('/simula?site=shackleton&mode=avanzato&tab=onda#x');
    expect(redirectTo('/analizza', '?site=a&t=2027-01-01T00%3A00%3A00Z')).toBe('/analizza?site=a&t=2027-01-01T00%3A00%3A00Z');
    expect(redirectTo('/siti?tab=globo', '?tab=boh')).toBe('/siti?tab=globo');
    expect(redirectTo('/analizza', '')).toBe('/analizza');
  });
  it('il router risolve gli alias verso la nuova pagina; un percorso vero non è mai coperto', () => {
    const p = { ...page('/simula'), aliases: { '/wave': 'tab=onda', '/real': '' } };
    const r = createRouter([p, page('/real')]);
    expect(r.resolve('/wave/?x=1')?.redirect).toBe('/simula?tab=onda');
    expect(r.resolve('/real')?.redirect).toBeUndefined();
    expect(r.pages().map((x) => x.path)).toEqual(['/real', '/simula']);
  });
  it("registro dell'app: le vecchie rotte portano ai nuovi posti", () => {
    const want: Record<string, string> = {
      '/lander': '/simula?tab=sito',
      '/wave': '/simula?tab=onda',
      '/grazinglink': '/analizza',
      '/viewer': '/siti?tab=globo',
      '/compare': '/siti?tab=classifica',
    };
    for (const [from, to] of Object.entries(want)) expect(appRouter.resolve(from)?.redirect, from).toBe(to);
    for (const p of ['/telemetry', '/sims', '/contacts', '/chat']) expect(appRouter.resolve(p)?.redirect, p).toBeUndefined();
  });
});

describe('registro della navigazione', () => {
  it('barra principale con Contatti e piè di pagina con le pagine legali', () => {
    expect(navPages(appRouter.pages(), 'main').map((p) => [p.path, label(p)])).toEqual([
      ['/', 'Home'],
      ['/mission-planner', 'Mission Planner'],
      ['/dashboard', 'Dashboard'],
      ['/learn', 'Learn'],
      ['/pricing', 'Piani'],
      ['/contacts', 'Contatti'],
    ]);
    expect(navPages(appRouter.pages(), 'legal').map(label)).toEqual(['About', 'Explore', 'Licenze', 'Privacy', 'Cookie', "Condizioni d'uso"]);
    expect(appRouter.resolve('/model')?.path).toBe('/model');
    expect(appRouter.resolve('/roadmap')?.path).toBe('/404');
  });
  it('gli strumenti restano rotte vere sotto Explore, la chat sotto Learn', () => {
    for (const p of ['/simula', '/analizza', '/siti', '/laboratorio', '/telemetry', '/sims']) {
      expect(appRouter.resolve(p)?.section).toBe('/explore');
    }
    expect(appRouter.resolve('/chat')?.section).toBe('/learn');
  });
});
