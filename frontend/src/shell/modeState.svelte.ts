// SPDX-License-Identifier: Apache-2.0
// Modalità come rune per i componenti: `modeNow.current`, `modeNow.advanced`. Legata allo store di mode.ts
// (unica fonte). Rune e non `$store`: il runtime degli store di Svelte finirebbe nel bundle iniziale.
import { modeStore, type Mode } from './mode';

let m = $state<Mode>(modeStore().get());
modeStore().subscribe((v) => (m = v));

export const modeNow = {
  get current(): Mode {
    return m;
  },
  /** true in Avanzato: le pagine mostrano parametri, tabelle e dettagli tecnici. */
  get advanced(): boolean {
    return m === 'avanzato';
  },
};
