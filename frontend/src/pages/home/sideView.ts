// SPDX-License-Identifier: Apache-2.0
// Geometria della vista di lato del mini-simulatore della home (senza DOM, testata): lander con antenna, crinale,
// linea di vista verso la Terra, zona di Fresnel attorno alla linea, percorso piegato sulla cima quando il crinale copre
// la Terra. Solo disegno: la scala verticale è esagerata (un crinale di 30 m a 2 km a scala vera non si vedrebbe);
// i numeri del risultato vengono da linkModel.computeLink, non da qui.

export type Pt = readonly [number, number];

export interface SideInput {
  earthElDeg: number;
  ridgeHeightM: number;
  ridgeDistanceM: number;
  mastM: number;
  /** Raggio della prima zona di Fresnel alla distanza del crinale (m), da computeLink. */
  fresnelR1M: number;
  /** La cima sta sopra la linea di vista (da computeLink). */
  blocksLos: boolean;
}

export interface SideGeom {
  groundY: number;
  lander: Pt;
  antenna: Pt;
  tip: Pt;
  ridge: Pt[];
  /** Linea di vista dall'antenna verso la Terra (fino al bordo del disegno). */
  los: [Pt, Pt];
  /** Poligono della zona di Fresnel attorno alla linea di vista (bordo superiore, poi inferiore all'indietro). */
  fresnel: Pt[];
  earth: { x: number; y: number; r: number };
  /** Percorso del segnale: diritto se la linea di vista è libera, piegato sulla cima se il crinale copre la Terra. */
  path: Pt[];
  bent: boolean;
}

/** Quota massima rappresentata sopra il suolo (m): il crinale più alto del cursore (150 m) entra con un po' d'aria. */
export const VIEW_TOP_M = 170;

export function sideGeometry(s: SideInput, w: number, h: number): SideGeom {
  const pad = Math.max(8, Math.min(w, h) * 0.05);
  const groundY = h * 0.84;
  const x0 = pad + w * 0.06;
  const d1 = Math.max(1, s.ridgeDistanceM);
  // il crinale al 55% della larghezza utile, la Terra oltre
  const span = d1 / 0.55;
  const sx = (w - pad - x0) / span;
  const sy = (groundY - pad) / VIEW_TOP_M;
  const X = (m: number) => x0 + m * sx;
  const Y = (m: number) => groundY - m * sy;
  const slope = Math.tan((Math.max(-2, Math.min(10, s.earthElDeg)) * Math.PI) / 180);
  const losM = (m: number) => s.mastM + m * slope;

  // fine della linea di vista: bordo destro, oppure bordo alto se la Terra è alta
  let endM = span;
  if (Y(losM(endM)) < pad && slope > 0) endM = (VIEW_TOP_M - s.mastM - pad / sy) / slope;
  endM = Math.max(d1 * 0.2, Math.min(span, endM));
  const antenna: Pt = [X(0), Y(s.mastM)];
  const losEnd: Pt = [X(endM), Y(losM(endM))];

  const hr = Math.max(0, Math.min(VIEW_TOP_M, s.ridgeHeightM));
  const half = d1 * 0.32;
  const ridge: Pt[] = [];
  for (let i = 0; i <= 32; i++) {
    const m = d1 - half * 1.6 + ((half * 3.2) * i) / 32;
    const u = (m - d1) / half;
    ridge.push([X(m), Y(hr * Math.exp(-u * u * 1.6))]);
  }
  const tip: Pt = [X(d1), Y(hr)];

  // r(x) = sqrt(λ x) per la Terra lontana: λ efficace dal raggio alla distanza del crinale
  const lam = (s.fresnelR1M * s.fresnelR1M) / d1;
  const up: Pt[] = [];
  const down: Pt[] = [];
  for (let i = 0; i <= 24; i++) {
    const m = (endM * i) / 24;
    const r = Math.sqrt(Math.max(0, lam * m));
    up.push([X(m), Y(losM(m) + r)]);
    down.push([X(m), Y(losM(m) - r)]);
  }
  const er = Math.max(6, Math.min(w, h) * 0.07);
  const earth = { x: Math.min(w - er - 2, losEnd[0]), y: Math.max(er + 2, Math.min(groundY - er, losEnd[1])), r: er };
  const bent = s.blocksLos;
  const path: Pt[] = bent ? [antenna, tip, [earth.x, earth.y]] : [antenna, [earth.x, earth.y]];
  return { groundY, lander: [X(0), groundY], antenna, tip, ridge, los: [antenna, losEnd], fresnel: [...up, ...down.reverse()], earth, path, bent };
}

/** Link a Simula con i due valori del mini-simulatore (chiavi `el` e `rh` di simState.parseSimQuery). */
export function simulaHref(path: string, earthElDeg: number, ridgeHeightM: number): string {
  const r = (v: number, d: number) => String(Math.round(v * 10 ** d) / 10 ** d);
  return `${path}?el=${r(earthElDeg, 2)}&rh=${r(ridgeHeightM, 1)}`;
}

/** Punto a frazione `t` (0..1) della lunghezza di una spezzata: l'impulso che corre lungo il segnale. */
export function pointAt(path: readonly Pt[], t: number): Pt {
  if (path.length === 0) return [0, 0];
  if (path.length === 1) return path[0]!;
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    const d = Math.hypot(path[i]![0] - path[i - 1]![0], path[i]![1] - path[i - 1]![1]);
    seg.push(d);
    total += d;
  }
  let left = Math.max(0, Math.min(1, t)) * total;
  for (let i = 0; i < seg.length; i++) {
    if (left <= seg[i]! || i === seg.length - 1) {
      const f = seg[i]! > 0 ? Math.min(1, left / seg[i]!) : 0;
      const a = path[i]!;
      const b = path[i + 1]!;
      return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
    }
    left -= seg[i]!;
  }
  return path[path.length - 1]!;
}
