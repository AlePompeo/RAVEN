// SPDX-License-Identifier: Apache-2.0
// Modello del link nel browser: parità con il motore Python (vettori di scripts/dump_link_parity.py, tolleranza
// 0,01 dB sui termini in dB), casi limite, indicatori di validità, curva e mappa.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { fresnelCS, knifeEdgeDb } from '../grazinglink/grazing';
import {
  computeLink,
  DEFAULT_INPUT,
  failElevation,
  heatPick,
  marginCurve,
  p526RoundedTermDb,
  parseCompTable,
  sanitizeInput,
  tableCorrection,
  validityHeat,
  variants,
  type LinkInput,
} from './linkModel';

const here = dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(readFileSync(resolve(here, 'fixtures/link_parity.json'), 'utf8')) as {
  table_sha256: string;
  knife_edge: { nu: number; db: number }[];
  cases: { name: string; input: Partial<LinkInput>; output: Record<string, unknown> }[];
};
// la stessa tabella servita da GET /api/raven/compensation
const table = parseCompTable(JSON.parse(readFileSync(resolve(here, '../../../../backend/domain/grazing/data/compensation_table.json'), 'utf8')))!;
const TOL_DB = 0.01;

describe('parità con backend/domain/grazing (tolleranza 0,01 dB)', () => {
  it('la tabella si legge', () => {
    expect(table).not.toBeNull();
    expect(table.nu.length).toBe(91);
    // the validation matrix (s5.browser_mirror) quotes these counts: change both together
    expect(fx.cases).toHaveLength(32);
    expect(fx.knife_edge).toHaveLength(61);
    expect(table.radiusM).toEqual([0, 5, 10, 20, 50, 100, 200, 400]);
  });

  it('bordo a lama esatto J(nu) per nu in [-3, 12]: |TS - scipy| < 1e-6 dB', () => {
    for (const k of fx.knife_edge) expect(Math.abs(knifeEdgeDb(k.nu) - k.db)).toBeLessThan(1e-6);
  });

  it('integrali di Fresnel: valori noti e simmetria', () => {
    const [c, s] = fresnelCS(1);
    expect(c).toBeCloseTo(0.7798934003768228, 12);
    expect(s).toBeCloseTo(0.4382591473903548, 12);
    expect(fresnelCS(-2.5)[0]).toBeCloseTo(-fresnelCS(2.5)[0], 14);
    expect(fresnelCS(1e6)[0]).toBeCloseTo(0.5, 5);
  });

  for (const c of fx.cases) {
    it(`caso "${c.name}"`, () => {
      const o = computeLink(c.input, table) as unknown as Record<string, unknown>;
      const e = c.output;
      for (const k of ['knifeEdgeDb', 'ituDb', 'correctionDb', 'correctionSplitStepDb', 'correctionUncertaintyDb', 'fsplDb', 'gainDbi', 'pointingLossDb', 'pointingScriptDb', 'multipathGainDb', 'cn0DbHz', 'marginDb']) {
        expect(Math.abs((o[k] as number) - (e[k] as number)), k).toBeLessThan(TOL_DB);
      }
      // l'Airy usa bessj1 di Numerical Recipes (errore ~1e-8 su J1): stessa tolleranza in dB
      expect(Math.abs((o.pointingAiryDb as number) - (e.pointingAiryDb as number))).toBeLessThan(TOL_DB);
      for (const k of ['nu', 'hAboveLosM', 'd1LosM', 'diameterM', 'hpbwScriptDeg', 'hpbwUniformDeg']) {
        expect(Math.abs((o[k] as number) - (e[k] as number)) / Math.max(1, Math.abs(e[k] as number)), k).toBeLessThan(1e-9);
      }
      expect(o.correctionClamped).toBe(e.correctionClamped);
      expect(o.multipathApplicable).toBe(e.multipathApplicable);
      expect(o.maxRateBps).toBe(e.maxRateBps);
      expect(o.state).toBe(e.state);
      (e.marginByRateDb as number[]).forEach((m, i) => expect(Math.abs((o.marginByRateDb as number[])[i]! - m)).toBeLessThan(TOL_DB));
      if (e.specularDistanceM === null) expect(o.specularDistanceM === null || !(c.input.earthElDeg! > 0)).toBe(true);
      else expect(Math.abs((o.specularDistanceM as number) - (e.specularDistanceM as number))).toBeLessThan(1e-6);
    });
  }

  it('differenza voluta: con la Terra sotto l’orizzonte il backend dà distanza speculare nan, qui null', () => {
    const c = fx.cases.find((x) => x.name === 'multipath earth below horizon')!;
    expect(c.output.specularDistanceM).toBeNull();
    expect(computeLink(c.input, table).specularDistanceM).toBeNull();
  });
});

describe('correzione della cresta', () => {
  it('interpolazione bilineare in (nu, log10(R+1)) sui nodi e tra i nodi', () => {
    const j = table.nu.indexOf(1);
    expect(tableCorrection(table, 1, 100).db).toBeCloseTo(table.correction[5]![j]!, 12);
    const mid = tableCorrection(table, 1, 50).db;
    expect(mid).toBeCloseTo(table.correction[4]![j]!, 12);
  });
  it('fuori griglia: saturata e segnalata, incertezza >= |correzione|', () => {
    const c = tableCorrection(table, 5, 1000);
    expect(c.clamped).toBe(true);
    expect(c.uncertaintyDb).toBeGreaterThanOrEqual(Math.abs(c.db));
  });
  it('tabella assente: correzione ITU senza confronto, l’indicatore lo dice', () => {
    const o = computeLink({ earthElDeg: 0.7 }, null);
    expect(o.correctionStatus).toBe('not-available');
    expect(o.correctionDb).toBeCloseTo(Math.max(p526RoundedTermDb(o.nu, o.input.ridgeRadiusM, o.d1LosM, o.input.earthDistanceKm * 1000 - o.d1LosM, o.wavelengthM), 0), 12);
    expect(o.correctionUncertaintyDb).toBeCloseTo(o.correctionDb, 12);
    expect(o.validity.reasons).toContain('correction_unavailable');
  });
  it('T(m,n) di ITU-R P.526-9: valori del confronto del motore (d1 = 2000 m, Terra all’infinito)', () => {
    expect(p526RoundedTermDb(2, 400, 2000, 1e12, 0.0357)).toBeCloseTo(3.0, 2);
    expect(p526RoundedTermDb(3, 400, 2000, 1e12, 0.0357)).toBeCloseTo(4.223, 2);
    expect(p526RoundedTermDb(2, 0, 2000, 1e12, 0.0357)).toBe(0);
  });
  it('varianti: cresta ITU con incertezza e cresta split-step come confronto', () => {
    const v = variants({ earthElDeg: 0.7, ridgeRadiusM: 100 }, table);
    const ids = v.map((x) => x.id);
    expect(ids).toContain('rounded');
    expect(ids).toContain('rounded_splitstep');
    const r = v.find((x) => x.id === 'rounded')!;
    const s = v.find((x) => x.id === 'rounded_splitstep')!;
    expect(r.uncertaintyDb!).toBeGreaterThanOrEqual(Math.abs(r.marginDb - s.marginDb) - 1e-9);
    expect(variants({ earthElDeg: 0.7, ridgeRadiusM: 100 }, null).map((x) => x.id)).not.toContain('rounded_splitstep');
  });
  it('tabella malformata rifiutata', () => {
    expect(parseCompTable(null)).toBeNull();
    expect(parseCompTable({ nu: [0, 1], radius_m: [0, 5], correction_db: [[0, NaN], [0, 0]], oscillation_envelope_db: [[0, 0], [0, 0]] })).toBeNull();
    expect(parseCompTable({ nu: [1, 0], radius_m: [0, 5], correction_db: [[0, 0], [0, 0]], oscillation_envelope_db: [[0, 0], [0, 0]] })).toBeNull();
    expect(parseCompTable({ nu: [0, 1], radius_m: [0, 5], correction_db: [[0, 0]], oscillation_envelope_db: [[0, 0], [0, 0]] })).toBeNull();
  });
});

describe('ingressi e casi limite', () => {
  it('NaN, Infinity e tipi sbagliati: valore predefinito e indicatore "fuori modello"', () => {
    const o = computeLink({ earthElDeg: NaN, ridgeHeightM: Infinity, rateBps: 'x' as unknown as number }, table);
    expect(o.input.earthElDeg).toBe(DEFAULT_INPUT.earthElDeg);
    expect(o.input.ridgeHeightM).toBe(DEFAULT_INPUT.ridgeHeightM);
    expect(o.validity.level).toBe('outside');
    expect(o.validity.reasons[0]).toBe('invalid_input');
    expect(Number.isFinite(o.marginDb)).toBe(true);
  });
  it('valori fuori intervallo riportati al bordo; bit-rate al valore ammesso più vicino', () => {
    const { input, bad } = sanitizeInput({ earthElDeg: 99, diameterM: -1, rateBps: 2.9e6, station: 'evil' as never });
    expect(input.earthElDeg).toBe(10);
    expect(input.diameterM).toBe(0.02);
    expect(input.rateBps).toBe(3e6);
    expect(input.station).toBe('dsn34');
    expect(bad).toBe(true);
  });
  it('stessi numeri a ogni chiamata (nessuno stato nascosto)', () => {
    expect(computeLink({}, table)).toEqual(computeLink({}, table));
  });
  it('Terra sotto o sull’orizzonte: fuori modello', () => {
    expect(computeLink({ earthElDeg: 0 }, table).validity.level).toBe('outside');
    expect(computeLink({ earthElDeg: -1 }, table).validity.reasons).toContain('earth_below_horizon');
  });
  it('approssimazione parassiale: angolo cima-linea di vista oltre 10° incerto, oltre 20° fuori', () => {
    expect(computeLink({ ridgeDistanceM: 300, ridgeHeightM: 80, earthElDeg: 1 }, table).validity.flags.find((f) => f.code === 'paraxial')!.level).toBe('uncertain');
    expect(computeLink({ ridgeDistanceM: 200, ridgeHeightM: 120, earthElDeg: 1 }, table).validity.flags.find((f) => f.code === 'paraxial')!.level).toBe('outside');
  });
  it('d1 fuori da 0,25-4 volte i 2000 m della tabella: correzione incerta (solo con R > 0)', () => {
    expect(computeLink({ ridgeDistanceM: 300, ridgeHeightM: 8, earthElDeg: 1 }, table).validity.reasons).toContain('d1_outside_table');
    expect(computeLink({ ridgeDistanceM: 300, ridgeHeightM: 8, earthElDeg: 1, ridgeRadiusM: 0 }, table).validity.reasons).not.toContain('d1_outside_table');
  });
  it('nu oltre la tabella con cresta arrotondata: correzione saturata, incerta', () => {
    const o = computeLink({ earthElDeg: 0.2, ridgeHeightM: 120, ridgeRadiusM: 200 }, table);
    expect(o.correctionClamped).toBe(true);
    expect(o.validity.reasons).toContain('nu_outside_table');
  });
  it('raggio non risolto: N/A nello scenario manuale, incerto con un sito reale non risolto', () => {
    expect(computeLink({}, table).validity.flags.find((f) => f.code === 'radius_unresolved')!.level).toBe('na');
    expect(computeLink({ radiusResolved: false, earthElDeg: 0.7 }, table).validity.reasons).toContain('radius_unresolved');
  });
  it('riflessione oltre il crinale: multipath non applicato e segnalato', () => {
    const o = computeLink({ earthElDeg: 0.05, ridgeHeightM: 3, multipath: { enabled: true, epsReal: 3.7, epsImag: 0.01, roughnessM: 0.25 } }, table);
    expect(o.multipathApplicable).toBe(false);
    expect(o.multipathGainDb).toBe(0);
  });

  it('il limite numerico non sposta il punto speculare entro il crinale', () => {
    const o = computeLink({ earthElDeg: .01, ridgeDistanceM: 5000, multipath: { enabled: true, epsReal: 3.7, epsImag: .01, roughnessM: .25 } }, table);
    expect(o.specularDistanceM).toBeCloseTo(11459.155786261179, 6);
    expect(o.multipathApplicable).toBe(false);
    expect(o.multipathGainDb).toBe(0);
    expect(o.validity.reasons).toContain('reflection_beyond_ridge');
  });
  it('lo scenario predefinito è affidabile e aperto', () => {
    const o = computeLink({}, table);
    expect(o.state).toBe('open');
    expect(o.validity.level).toBe('reliable');
  });
});

describe('curva, varianti, mappa di validità', () => {
  it('margine contro elevazione: cresce con l’elevazione e indica dove si rompe', () => {
    const c = marginCurve({ ridgeHeightM: 80, diameterM: 0.05 }, table);
    expect(c.el.length).toBe(201);
    expect(c.margin[200]!).toBeGreaterThan(c.margin[0]!);
    const f = failElevation(c);
    expect(f).not.toBeNull();
    expect(computeLink({ ridgeHeightM: 80, diameterM: 0.05, earthElDeg: f! }, table).marginDb).toBeGreaterThanOrEqual(0);
    expect(computeLink({ ridgeHeightM: 80, diameterM: 0.05, earthElDeg: f! - 0.05 }, table).marginDb).toBeLessThan(0);
  });
  it('varianti: la lama è la cresta senza correzione; antenna dello script e corretta differiscono di ~0,52 dB', () => {
    const v = variants({ earthElDeg: 0.7 }, table);
    const knife = computeLink({ earthElDeg: 0.7, applyCorrection: false }, table).marginDb;
    expect(v.find((x) => x.id === 'knife')!.marginDb).toBe(knife);
    const d = v.find((x) => x.id === 'antenna_script')!.marginDb - v.find((x) => x.id === 'antenna_corrected')!.marginDb;
    expect(d).toBeCloseTo(0.52, 2);
  });
  it('mappa 60 x 40 in meno di 100 ms, con zone fuori modello (el <= 0 non c’è: la prima colonna è a 0,083°) e bloccate', () => {
    const t0 = performance.now();
    const h = validityHeat({}, table);
    const ms = performance.now() - t0;
    expect(h.cells.length).toBe(2400);
    expect(ms).toBeLessThan(100 * 3); // margine per macchine di CI lente; la misura nel browser è nella e2e
    const states = new Set(h.cells.map((c) => c.state));
    expect(states.has('open') && states.has('blocked') && states.has('transition')).toBe(true);
    expect(h.cells.some((c) => c.validity === 'uncertain')).toBe(true);
  });
  it('clic sulla mappa -> valori dei controlli arrotondati e limitati', () => {
    const h = validityHeat({}, table, 6, 4);
    expect(heatPick(h, 0.5, 0.5)).toEqual({ earthElDeg: 5, ridgeHeightM: 75 });
    expect(heatPick(h, -3, 9)).toEqual({ earthElDeg: 0, ridgeHeightM: 150 });
  });
});
