// SPDX-License-Identifier: Apache-2.0
// Passo 4 della home ("cosa significa per una missione"): un mese ILLUSTRATIVO in cui la Terra sale e scende con la
// librazione davanti a un crinale fisso. Per ogni ora: la geometria dice "visibile" solo se la Terra sta sopra la cima;
// il modello del browser (computeLink, lo stesso di Simula) dice se il link chiude davvero. La differenza sono le ore
// guadagnate nella zona di transizione. Elevazione sintetica, non effemeridi: è dichiarato nella pagina.
import { computeLink, type CompTable, type LinkInput } from '../simula/linkModel';

export const STRIP_DAYS = 28;
/** Scenario dell'esempio: crinale di 40 m a 2 km, 1 Mbps (gli altri parametri sono quelli predefiniti di Simula). */
export const STRIP_INPUT: Readonly<Partial<LinkInput>> = { ridgeHeightM: 40, rateBps: 1e6 };
/** Elevazione sintetica (gradi): 0,95° ± 0,55° con il periodo della librazione (27,3 giorni). */
export const stripElevation = (hour: number): number => 0.95 + 0.55 * Math.sin((2 * Math.PI * hour) / (27.32 * 24));

export interface Strip {
  /** Per ogni ora: 0 = bloccato, 1 = solo il link reale chiude (transizione), 2 = visibile anche per la geometria. */
  cells: Uint8Array;
  geometricHours: number;
  realHours: number;
}

export function missionStrip(input: Partial<LinkInput> = {}, table: CompTable | null = null, days = STRIP_DAYS): Strip {
  const n = days * 24;
  const cells = new Uint8Array(n);
  let geo = 0;
  let real = 0;
  for (let h = 0; h < n; h++) {
    const o = computeLink({ ...input, earthElDeg: stripElevation(h) }, table);
    const g = !o.blocksLos;
    const r = o.marginDb >= 0;
    if (g) geo++;
    if (r) real++;
    cells[h] = g && r ? 2 : r ? 1 : 0;
  }
  return { cells, geometricHours: geo, realHours: real };
}

/** Intervalli consecutivi dello stesso valore, per disegnare la striscia con pochi rettangoli. */
export function runs(cells: Uint8Array): { start: number; len: number; v: number }[] {
  const out: { start: number; len: number; v: number }[] = [];
  for (let i = 0; i < cells.length; i++) {
    const last = out[out.length - 1];
    if (last && last.v === cells[i]) last.len++;
    else out.push({ start: i, len: 1, v: cells[i]! });
  }
  return out;
}
