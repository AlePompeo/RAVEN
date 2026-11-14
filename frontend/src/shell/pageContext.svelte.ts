// SPDX-License-Identifier: Apache-2.0
// Contesto della pagina corrente per "Spiega questa pagina": le pagine pubblicano qui che cosa l'utente sta
// guardando (simulazione scelta e valori, corpo celeste scelto). Solo in memoria; viene inviato all'assistente
// solo quando l'utente fa una domanda. Una pagina che esce chiama clear().

export type CtxScalar = string | number;

// $state.raw: oggetti sostituiti per intero, senza proxy (il chunk iniziale ha un budget in byte)
let current = $state.raw<{ simulation_id: string; params: Record<string, CtxScalar> }>({ simulation_id: '', params: {} });

export const pageCtx = {
  get simulation_id() {
    return current.simulation_id;
  },
  get params() {
    return current.params;
  },
};

export function setPageContext(c: { simulation_id?: string; params?: Record<string, CtxScalar> }): void {
  current = { simulation_id: c.simulation_id ?? '', params: c.params ?? {} };
}

export function clearPageContext(): void {
  current = { simulation_id: '', params: {} };
}

/** Nome della cartella in frontend/src/pages/ per un percorso (page_id del contratto dell'assistente). */
export function pageIdFor(path: string): string {
  const seg = path.replace(/^\/+/, '').split('/')[0] ?? '';
  return seg === '' ? 'home' : seg;
}

/** Preferenze del foglio (solo in memoria, valgono fino alla chiusura della scheda). */
let questionKey = $state.raw(false);
export const explainPrefs = {
  get questionKey() {
    return questionKey;
  },
  set questionKey(v: boolean) {
    questionKey = v;
  },
};
