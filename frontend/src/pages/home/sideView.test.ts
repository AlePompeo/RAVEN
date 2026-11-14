// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { computeLink } from '../simula/linkModel';
import { parseSimQuery } from '../simula/simState';
import { pointAt, sideGeometry, simulaHref, VIEW_TOP_M, type SideInput } from './sideView';
import { missionStrip, runs, STRIP_DAYS, STRIP_INPUT, stripElevation } from './missionStrip';

const side = (el: number, rh: number): SideInput => {
  const o = computeLink({ earthElDeg: el, ridgeHeightM: rh }, null);
  return { earthElDeg: el, ridgeHeightM: rh, ridgeDistanceM: o.input.ridgeDistanceM, mastM: o.input.mastM, fresnelR1M: o.fresnelR1M, blocksLos: o.blocksLos };
};

describe('vista di lato', () => {
  it('Terra alta: linea di vista libera, percorso diritto, tutto dentro il disegno', () => {
    const g = sideGeometry(side(8, 33), 600, 320);
    expect(g.bent).toBe(false);
    expect(g.path).toHaveLength(2);
    for (const [x, y] of [g.antenna, g.tip, [g.earth.x, g.earth.y] as const]) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(600);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(320);
    }
    // la linea di vista passa sopra la cima (y più piccolo = più in alto)
    const atTip = g.los[0][1] + ((g.los[1][1] - g.los[0][1]) * (g.tip[0] - g.los[0][0])) / (g.los[1][0] - g.los[0][0]);
    expect(atTip).toBeLessThan(g.tip[1]);
  });
  it('crinale che copre la Terra: percorso piegato sulla cima', () => {
    const g = sideGeometry(side(0.5, 80), 600, 320);
    expect(g.bent).toBe(true);
    expect(g.path[1]).toEqual(g.tip);
  });
  it('alzare il crinale alza la cima; alzare la Terra alza la fine della linea di vista', () => {
    expect(sideGeometry(side(1, 100), 600, 320).tip[1]).toBeLessThan(sideGeometry(side(1, 20), 600, 320).tip[1]);
    expect(sideGeometry(side(3, 33), 600, 320).los[1][1]).toBeLessThan(sideGeometry(side(1, 33), 600, 320).los[1][1]);
  });
  it('la zona di Fresnel avvolge la linea di vista e si allarga verso la Terra', () => {
    const g = sideGeometry(side(1.5, 33), 600, 320);
    const n = g.fresnel.length / 2;
    const w0 = g.fresnel[g.fresnel.length - 1]![1] - g.fresnel[0]![1];
    const w1 = g.fresnel[n]![1] - g.fresnel[n - 1]![1];
    expect(w0).toBeCloseTo(0, 6);
    expect(w1).toBeGreaterThan(0);
  });
  it('valori estremi: niente NaN, crinale limitato alla quota rappresentata', () => {
    const g = sideGeometry({ earthElDeg: 99, ridgeHeightM: 1e6, ridgeDistanceM: 0, mastM: 2, fresnelR1M: 8, blocksLos: true }, 10, 10);
    const all = [g.antenna, g.tip, ...g.ridge, ...g.fresnel, ...g.path, [g.earth.x, g.earth.y] as const].flat();
    expect(all.every(Number.isFinite)).toBe(true);
    expect(VIEW_TOP_M).toBeGreaterThan(150);
  });
  it('pointAt segue la spezzata per lunghezza', () => {
    const p = [[0, 0], [10, 0], [10, 10]] as const;
    expect(pointAt(p, 0)).toEqual([0, 0]);
    expect(pointAt(p, 0.25)).toEqual([5, 0]);
    expect(pointAt(p, 0.75)).toEqual([10, 5]);
    expect(pointAt(p, 2)).toEqual([10, 10]);
    expect(pointAt([], 0.5)).toEqual([0, 0]);
  });
  it('il link a Simula porta i due valori, letti da parseSimQuery', () => {
    const h = simulaHref('/simula', 0.8500001, 47.25);
    expect(h).toBe('/simula?el=0.85&rh=47.3');
    expect(parseSimQuery(h.slice(h.indexOf('?'))).input).toMatchObject({ earthElDeg: 0.85, ridgeHeightM: 47.3 });
  });
});

describe('striscia della missione (passo 4)', () => {
  it('elevazione sintetica tra 0,4° e 1,5°', () => {
    for (let h = 0; h < STRIP_DAYS * 24; h += 7) {
      expect(stripElevation(h)).toBeGreaterThanOrEqual(0.39);
      expect(stripElevation(h)).toBeLessThanOrEqual(1.51);
    }
  });
  it('il link reale chiude per più ore di quelle che la geometria dà per visibili', () => {
    const s = missionStrip(STRIP_INPUT);
    expect(s.cells).toHaveLength(STRIP_DAYS * 24);
    expect(s.geometricHours).toBeGreaterThan(0);
    expect(s.realHours).toBeGreaterThan(s.geometricHours);
    expect(s.cells.some((c) => c === 1)).toBe(true);
  });
  it('runs raggruppa le ore consecutive', () => {
    expect(runs(Uint8Array.from([0, 0, 1, 2, 2, 2]))).toEqual([
      { start: 0, len: 2, v: 0 },
      { start: 2, len: 1, v: 1 },
      { start: 3, len: 3, v: 2 },
    ]);
  });
});
