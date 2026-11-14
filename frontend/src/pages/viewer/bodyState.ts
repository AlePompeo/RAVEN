// SPDX-License-Identifier: Apache-2.0
// Corpo scelto nel visualizzatore: dal link (?body=mars) prima, poi dall'ultima scelta salvata, poi la Luna.
// localStorage può mancare o lanciare (modalità privata, criteri): ogni accesso è protetto.
import type { BodyId } from '../../viewports/scene';

/** Corpi del selettore su questo ramo (GrazingLink): Luna e Terra. Il ramo base conserva anche Sole e Marte. */
export const VIEWER_BODIES: readonly BodyId[] = ['moon', 'earth'];
const isBodyId = (v: unknown): v is BodyId => typeof v === 'string' && (VIEWER_BODIES as readonly string[]).includes(v);

export const STORAGE_KEY = 'hb.viewer.body';

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function storage(): StorageLike | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

export function readBody(search: string, store: StorageLike | null = storage()): BodyId {
  const q = new URLSearchParams(search).get('body');
  if (isBodyId(q)) return q;
  try {
    const saved = store?.getItem(STORAGE_KEY);
    if (isBodyId(saved)) return saved;
  } catch {
    /* archiviazione non disponibile */
  }
  return 'moon';
}

/** Ricorda la scelta e aggiorna il link (replaceState: nessuna voce nuova nella cronologia). */
export function writeBody(id: BodyId, loc: Pick<Location, 'pathname' | 'search' | 'hash'> = location, h: Pick<History, 'replaceState'> | null = typeof history !== 'undefined' ? history : null, store: StorageLike | null = storage()): string {
  try {
    store?.setItem(STORAGE_KEY, id);
  } catch {
    /* archiviazione non disponibile: resta il link */
  }
  const params = new URLSearchParams(loc.search);
  if (id === 'moon') params.delete('body');
  else params.set('body', id);
  const qs = params.toString();
  const url = `${loc.pathname}${qs ? `?${qs}` : ''}${loc.hash}`;
  try {
    h?.replaceState(h === history ? history.state : null, '', url);
  } catch {
    /* ambiente senza History API */
  }
  return url;
}
