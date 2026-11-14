// SPDX-License-Identifier: Apache-2.0
// Livello di qualità dal dispositivo: core, memoria, Save-Data, prefers-reduced-data. Le macchine deboli
// ricevono mappe da 1k, DPR massimo 1,5 e nessuno strato di stelle in parallasse.

export interface Quality {
  tier: 'hi' | 'lo';
  dprCap: number;
  parallax: boolean;
}

interface NavLike {
  hardwareConcurrency?: number;
  deviceMemory?: number;
  connection?: { saveData?: boolean };
}

export function detectQuality(nav: NavLike | undefined = typeof navigator !== 'undefined' ? (navigator as NavLike) : undefined, reducedData = matches('(prefers-reduced-data: reduce)')): Quality {
  const cores = nav?.hardwareConcurrency ?? 4;
  const mem = nav?.deviceMemory ?? 4;
  const save = nav?.connection?.saveData === true || reducedData;
  const weak = cores <= 2 || mem <= 2 || save;
  return weak ? { tier: 'lo', dprCap: 1.5, parallax: false } : { tier: 'hi', dprCap: 2, parallax: true };
}

function matches(q: string): boolean {
  try {
    return typeof matchMedia === 'function' && matchMedia(q).matches;
  } catch {
    return false;
  }
}
