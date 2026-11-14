// SPDX-License-Identifier: Apache-2.0
// Pagine "contenitore" con schede (Simula, Siti): ospitano le pagine esistenti come schede, scelte con ?tab=.
// La scheda attiva e il titolo arrivano alla SubNav della pagina ospitata via contesto: un solo h1 per pagina.
import type { Component } from 'svelte';

export interface HubTab {
  /** Chiave stabile, valore di ?tab= */
  id: string;
  label: string;
  /** Titolo della pagina ospitata (resta nel nome accessibile dell’h1: "Simula – Scena lander"). */
  title: string;
  /** La pagina ospitata non ha una SubNav propria: la disegna il contenitore (es. il visualizzatore). */
  header?: boolean;
  /** Frase "Cosa stai guardando" per la SubNav disegnata dal contenitore. */
  learn?: string;
  load: () => Promise<{ default: Component<any> }>;
}

export interface HubCtx {
  title: string;
  label: string;
  tabs: readonly HubTab[];
  readonly active: string;
  select(id: string): void;
}

export const HUB_KEY = Symbol('hub');
export const TAB_PARAM = 'tab';

/** Scheda da ?tab= se valida (confronto esatto con gli id), altrimenti la prima. */
export function pickTab(search: string, tabs: readonly Pick<HubTab, 'id'>[]): string {
  let t: string | null = null;
  try {
    t = new URLSearchParams(search).get(TAB_PARAM);
  } catch {
    /* query non valida */
  }
  return tabs.find((x) => x.id === t)?.id ?? tabs[0]?.id ?? '';
}

/** Query con ?tab= impostato, gli altri parametri (scenario, mode) intatti. */
export function searchWithTab(search: string, id: string): string {
  const p = new URLSearchParams(search);
  p.set(TAB_PARAM, id);
  return `?${p.toString()}`;
}
