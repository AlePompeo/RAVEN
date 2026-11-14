// SPDX-License-Identifier: Apache-2.0
// Disposizione dei marcatori sul disco: i siti polari si addensano (dal lembo i poli sono compressi) e i
// pulsanti si coprirebbero a vicenda. Si tiene il primo di ogni gruppo vicino (il selezionato ha la
// precedenza); gli altri restano raggiungibili dall'elenco dei luoghi, che è l'alternativa completa.

export interface Positioned {
  id: string;
  x: number;
  y: number;
}

/** Distanza minima tra i centri (px): sotto questa soglia i pulsanti si coprono e non rispettano la dimensione minima del bersaglio. */
export const MIN_MARKER_DISTANCE = 44; // the touch target (--target): two markers never overlap each other

export function thinMarkers<T extends Positioned>(items: T[], selectedId: string | null, minDist = MIN_MARKER_DISTANCE): T[] {
  const order = [...items].sort((a, b) => (a.id === selectedId ? -1 : b.id === selectedId ? 1 : 0));
  const kept: T[] = [];
  for (const m of order) {
    if (kept.every((k) => Math.hypot(k.x - m.x, k.y - m.y) >= minDist)) kept.push(m);
  }
  // ordine originale (stabile per il DOM e per la tabulazione)
  return items.filter((m) => kept.includes(m));
}
