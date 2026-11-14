// SPDX-License-Identifier: Apache-2.0
// Setup condiviso di vitest: i test devono essere ermetici, cioe' non dipendere dalla macchina che li
// esegue (core, memoria, Save-Data, DPR). Il livello di qualita' (viewports/quality.ts) legge questi valori:
// su un runner CI da 2 core darebbe il livello "lo" e cambierebbe DPR massimo e parallasse.
// I test che vogliono un altro valore lo ridefiniscono (vi.stubGlobal o Object.defineProperty).
const fixed: Record<string, unknown> = {
  hardwareConcurrency: 8,
  deviceMemory: 8,
  connection: undefined,
};
for (const [k, value] of Object.entries(fixed)) {
  Object.defineProperty(navigator, k, { value, configurable: true, writable: true });
}
Object.defineProperty(window, 'devicePixelRatio', { value: 1, configurable: true, writable: true });

// Lingua dei test esistenti: italiano (come gli e2e con hb.lang=it); i test i18n cambiano lingua e la ripristinano.
import { useCatalog } from './i18n/i18n.svelte';
import itCatalog from './i18n/it.json';
import enPagesCatalog from './i18n/en.pages.json';
useCatalog('it', itCatalog, enPagesCatalog);
