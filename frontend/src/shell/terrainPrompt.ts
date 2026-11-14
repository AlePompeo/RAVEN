// SPDX-License-Identifier: Apache-2.0
// Finestra di conferma del download del terreno (chunk lazy: montata solo quando il server risponde 409 "needs download").
// Una sola finestra alla volta: le richieste che arrivano mentre e' aperta aspettano la stessa risposta; dopo un rifiuto
// le richieste identiche nei 15 secondi successivi non riaprono la finestra.
import { mount, unmount } from 'svelte';
import TerrainPrompt from './TerrainPrompt.svelte';
import type { TerrainEstimate } from './ravenApi';

let pending: Promise<boolean> | null = null;
let declinedAt = 0;
export const REPROMPT_MS = 15_000;

export function confirmTerrainDownload(estimate: TerrainEstimate): Promise<boolean> {
  if (pending) return pending;
  if (Date.now() - declinedAt < REPROMPT_MS) return Promise.resolve(false);
  pending = new Promise<boolean>((resolve) => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    let comp: ReturnType<typeof mount> | null = null;
    const done = (yes: boolean) => {
      if (comp) void unmount(comp);
      host.remove();
      if (!yes) declinedAt = Date.now();
      pending = null;
      resolve(yes);
    };
    comp = mount(TerrainPrompt, { target: host, props: { estimate, decide: done } });
  });
  return pending;
}

/** Per i test: azzera lo stato. */
export function resetTerrainPrompt(): void {
  pending = null;
  declinedAt = 0;
}
