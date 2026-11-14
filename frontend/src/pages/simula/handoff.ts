// SPDX-License-Identifier: Apache-2.0
// Passaggio di valori tra le schede di Simula (nessuna dipendenza): la scheda "Scena" pubblica frequenza, raggio e
// distanza del crinale, la scheda "L'onda" li usa come valori iniziali. Aperta da sola, l'onda non trova nulla e usa
// i suoi predefiniti. Solo in memoria (niente storage): ricaricando la pagina si riparte dal predefinito o dall'URL.
export interface WaveHandoff {
  frequencyGhz: number;
  radiusM: number;
  distanceM: number;
}

let current: WaveHandoff | null = null;

export function setWaveHandoff(h: WaveHandoff | null): void {
  current = h ? { ...h } : null;
}
export function getWaveHandoff(): WaveHandoff | null {
  return current ? { ...current } : null;
}
