// SPDX-License-Identifier: Apache-2.0
// Modalità del sito (docs/design/grazinglink-ux.md, "Pubblico e livelli"): 'learning' (predefinita, per chi arriva la prima
// volta) o 'avanzato'. Una sola scelta per tutto il sito. Precedenza: ?mode= nell'URL (link condivisibile) > localStorage
// (in try/catch, mai cookie) > predefinito. Ogni valore letto da URL o archiviazione è non fidato: se non è esattamente
// uno dei due nomi viene ignorato. La modalità cambia solo cosa si vede: i numeri sono gli stessi.
// Non è nel bundle iniziale: lo importano solo ModeSwitch e le pagine (chunk lazy).

export type Mode = 'learning' | 'avanzato';
export const MODES: readonly Mode[] = ['learning', 'avanzato'];
export const DEFAULT_MODE: Mode = 'learning';
export const MODE_PARAM = 'mode';
export const MODE_KEY = 'hb.mode';

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;
type Loc = Pick<Location, 'pathname' | 'search' | 'hash'>;
type Hist = Pick<History, 'replaceState' | 'state'>;

/** Valore valido (confronto esatto, nessuna normalizzazione) oppure null. */
export function parseMode(raw: unknown): Mode | null {
  return typeof raw === 'string' && (MODES as readonly string[]).includes(raw) ? (raw as Mode) : null;
}

/** Modalità forzata dall'URL, se presente e valida. */
export function modeFromSearch(search: string): Mode | null {
  if (typeof search !== 'string' || search.length > 4000) return null;
  try {
    return parseMode(new URLSearchParams(search).get(MODE_PARAM));
  } catch {
    return null;
  }
}

function readStored(store: StorageLike | null): Mode | null {
  try {
    return parseMode(store?.getItem(MODE_KEY));
  } catch {
    return null;
  }
}

/** URL > archiviazione > predefinito. */
export function resolveMode(search: string, store: StorageLike | null): Mode {
  return modeFromSearch(search) ?? readStored(store) ?? DEFAULT_MODE;
}

/** Query string con ?mode= impostato, gli altri parametri intatti (vuota se non resta nulla). */
export function searchWithMode(search: string, m: Mode): string {
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(search);
  } catch {
    p = new URLSearchParams();
  }
  p.set(MODE_PARAM, m);
  return `?${p.toString()}`;
}

function localStore(): StorageLike | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

interface Env {
  loc: Loc;
  hist: Hist | null;
  store: StorageLike | null;
}

type Listener = (m: Mode) => void;

/** Store minimo (contratto degli store di Svelte: `$store` nei componenti). */
export class ModeStore {
  private m: Mode;
  private readonly subs = new Set<Listener>();
  private readonly env: Env;

  constructor(env?: Partial<Env>) {
    this.env = {
      loc: env?.loc ?? (typeof location !== 'undefined' ? location : { pathname: '/', search: '', hash: '' }),
      hist: env && 'hist' in env ? (env.hist ?? null) : typeof history !== 'undefined' ? history : null,
      store: env && 'store' in env ? (env.store ?? null) : localStore(),
    };
    this.m = resolveMode(this.env.loc.search, this.env.store);
  }

  get(): Mode {
    return this.m;
  }

  /** Dopo una navigazione: un ?mode= valido nell'URL vince, altrimenti resta la scelta in memoria. */
  sync(): Mode {
    const u = modeFromSearch(this.env.loc.search);
    if (u && u !== this.m) {
      this.m = u;
      this.emit();
    }
    return this.m;
  }

  /** Scelta dell'utente: aggiorna memoria, archiviazione (se disponibile) e URL (replaceState, altri parametri intatti). */
  set(next: Mode): void {
    const m = parseMode(next);
    if (!m) return;
    try {
      this.env.store?.setItem(MODE_KEY, m);
    } catch {
      /* archiviazione bloccata: resta in memoria e nell'URL */
    }
    try {
      const { pathname, search, hash } = this.env.loc;
      this.env.hist?.replaceState(this.env.hist.state, '', `${pathname}${searchWithMode(search, m)}${hash}`);
    } catch {
      /* ambiente senza History API */
    }
    if (m === this.m) return;
    this.m = m;
    this.emit();
  }

  subscribe(fn: Listener): () => void {
    this.subs.add(fn);
    fn(this.m);
    return () => void this.subs.delete(fn);
  }

  private emit(): void {
    for (const f of this.subs) f(this.m);
  }
}

let shared: ModeStore | null = null;
/** Store condiviso dell'applicazione (creato al primo uso). */
export function modeStore(): ModeStore {
  shared ??= new ModeStore();
  return shared;
}
