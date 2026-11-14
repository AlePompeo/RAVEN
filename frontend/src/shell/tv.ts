// SPDX-License-Identifier: Apache-2.0
// Rilevamento della modalità TV (10 piedi): unica parte nel bundle iniziale. La navigazione spaziale (spatialNav.ts)
// è un chunk lazy, caricato da main.ts solo quando la modalità TV è attiva.
// Attiva per schermi >= 1920px senza puntatore fine, oppure con ?tv=1 (ricordato; ?tv=0 la spegne).

export const TV_KEY = 'hb.tv';

export function isTvMode(): boolean {
  return document.documentElement.dataset.tv === '1';
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

/** Decide e applica la modalità TV; ritorna lo stato. */
export function detectTv(search = location.search, store: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null = safeStorage()): boolean {
  const q = new URLSearchParams(search).get('tv');
  try {
    if (q === '1') store?.setItem(TV_KEY, '1');
    if (q === '0') store?.removeItem(TV_KEY);
  } catch {
    /* archiviazione non disponibile */
  }
  let saved = false;
  try {
    saved = store?.getItem(TV_KEY) === '1';
  } catch {
    saved = false;
  }
  const big = typeof matchMedia === 'function' && matchMedia('(min-width: 1920px) and (not (any-pointer: fine))').matches;
  const on = q === '1' || (q !== '0' && (saved || big));
  if (on) document.documentElement.dataset.tv = '1';
  else delete document.documentElement.dataset.tv;
  return on;
}
