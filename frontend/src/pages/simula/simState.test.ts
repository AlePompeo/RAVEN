// SPDX-License-Identifier: Apache-2.0
// Stato di Simula: URL (anche malevolo), preset, missione, frase, esportazione, scena sintetica, passaggio all'onda.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { initialForm, validateForm } from '../wave/wave';
import { getWaveHandoff, setWaveHandoff } from './handoff';
import { computeLink, DEFAULT_INPUT, parseCompTable, sanitizeInput, type LinkInput } from './linkModel';
import { inputFromScene, profileFor, ridgeHeightAt, syntheticScene } from './simScene';
import { advanceMission, exportCsv, exportJson, newMission, parseSimQuery, PRESETS, sentence, STR, writeSimQuery } from './simState';

const here = dirname(fileURLToPath(import.meta.url));
const table = parseCompTable(JSON.parse(readFileSync(resolve(here, '../../../../backend/domain/grazing/data/compensation_table.json'), 'utf8')))!;
const run = (p: Partial<LinkInput>) => computeLink({ ...DEFAULT_INPUT, ...p }, table);

describe('URL', () => {
  it('Avanzato scrive solo ciò che differisce dal predefinito e si rilegge uguale', () => {
    const input = sanitizeInput({ ...DEFAULT_INPUT, earthElDeg: 0.7, ridgeRadiusM: 400, rateBps: 3e5, station: 'dsn18', multipath: { enabled: true, epsReal: 4, epsImag: 0.01, roughnessM: 0.25 }, applyCorrection: false }).input;
    const q = writeSimQuery('?tab=scena&mode=avanzato', input, false, null, true);
    expect(q).toContain('tab=scena');
    expect(q).toContain('mode=avanzato');
    expect(q).toContain('el=0.7');
    expect(q).not.toContain('ghz=');
    const back = parseSimQuery(q);
    expect(sanitizeInput({ ...DEFAULT_INPUT, ...back.input }).input).toEqual(input);
  });
  it('Learning tiene l’URL pulito (solo sito reale se scelto)', () => {
    const input = sanitizeInput({ ...DEFAULT_INPUT, earthElDeg: 3 }).input;
    expect(writeSimQuery('?tab=scena&el=3&rh=9', input, false, null, false)).toBe('?tab=scena');
    expect(writeSimQuery('', input, true, 'shackleton', false)).toBe('?real=1&site=shackleton');
  });
  it('valori malevoli o fuori intervallo ignorati senza eco', () => {
    const q = parseSimQuery(
      '?el=NaN&rh=1e999&rd=Infinity&rr=-5&dia=%3Cscript%3E&ghz=8.4.4&perr=999999999999999&ptx=0x10&tsys=&rate=12345&station=evil&site=..%2F..%2Fetc&mast=' + '9'.repeat(40) + '&eps=  3&mp=true&corr=no',
    );
    expect(q.input).toEqual({});
    expect(q.site).toBeNull();
    expect(q.real).toBe(false);
    expect(parseSimQuery('%%%').input).toEqual({});
  });
  it('valori validi letti', () => {
    const q = parseSimQuery('?el=-1.5&rh=80&rate=3e6&station=dsn18&mp=1&sig=0&corr=0&real=1&site=de-gerlache');
    expect(q.input).toMatchObject({ earthElDeg: -1.5, ridgeHeightM: 80, rateBps: 3e6, station: 'dsn18', applyCorrection: false });
    expect(q.input.multipath).toMatchObject({ enabled: true, roughnessM: 0 });
    expect(q).toMatchObject({ real: true, site: 'de-gerlache' });
  });
});

describe('preset', () => {
  it('ogni preset dà lo stato che il nome promette', () => {
    expect(run(PRESETS.high).state).toBe('open');
    expect(run(PRESETS.grazing).state).toBe('transition');
    expect(run(PRESETS.blocking).state).toBe('blocked');
    const small = run(PRESETS.small);
    expect(small.state).toBe('blocked');
    expect(small.maxRateBps).toBeGreaterThan(0);
    expect(PRESETS.small.diameterM).toBeLessThan(DEFAULT_INPUT.diameterM!);
  });
});

describe('missione guidata', () => {
  it('i passi si completano in ordine solo facendo la cosa richiesta', () => {
    let m = newMission(sanitizeInput(DEFAULT_INPUT).input);
    m = advanceMission(m, run({ earthElDeg: 2 }));
    expect(m.done).toBe(0); // 2° non basta
    m = advanceMission(m, run({ ridgeHeightM: 120, earthElDeg: 0.5 })); // un passo successivo non conta
    expect(m.done).toBe(0);
    m = advanceMission(m, run({ earthElDeg: 6 }));
    expect(m.done).toBe(1);
    m = advanceMission(m, run({ earthElDeg: 0.8 }));
    expect(m.done).toBe(2);
    m = advanceMission(m, run({ earthElDeg: 0.8, ridgeHeightM: 90 }));
    expect(m.done).toBe(3);
    m = advanceMission(m, run({ earthElDeg: 0.8, ridgeHeightM: 90, diameterM: 0.06 })); // ancora bloccato
    expect(m.done).toBe(3);
    m = advanceMission(m, run({ earthElDeg: 0.8, ridgeHeightM: 90, diameterM: 1.5 }));
    expect(m.done).toBe(4);
    m = advanceMission(m, run({ earthElDeg: 0.8, ridgeHeightM: 90, diameterM: 1.5, rateBps: 3e6 }));
    expect(m.done).toBe(5);
    expect(advanceMission(m, run({})).done).toBe(5);
    expect(STR.mission.steps.length).toBe(5);
  });
});

describe('frase e indicatori', () => {
  it('una frase semplice per ogni stato', () => {
    expect(sentence(run({ earthElDeg: 8 }))).toMatch(/^Il segnale arriva con \d+ dB di margine: puoi inviare 100 kbps\.$/);
    expect(sentence(run(PRESETS.grazing))).toMatch(/arriva piegato/);
    expect(sentence(run(PRESETS.small))).toMatch(/^Mancano \d+ dB: a 3 Mbps il segnale non basta, ma \d+ [kM]bps passano\.$/);
    expect(sentence(run({ earthElDeg: 0.2, ridgeHeightM: 150, diameterM: 0.02 }))).toMatch(/anche a 10 kbps/);
    expect(sentence(run({ earthElDeg: 0 }))).toBe(STR.sentence.below);
  });
  it('ogni codice di validità ha un testo', () => {
    for (const f of run({}).validity.flags) expect(STR.flag[f.code]).toBeTruthy();
  });
});

describe('esportazione', () => {
  it('JSON con ingressi, uscite e validità; CSV a due colonne senza formule', () => {
    const o = run({ earthElDeg: 0.7 });
    const j = JSON.parse(exportJson(o, { mode: 'avanzato' }));
    expect(j.input.earthElDeg).toBe(0.7);
    expect(j.output.marginDb).toBeCloseTo(o.marginDb, 12);
    expect(j.validity.level).toBe(o.validity.level);
    const csv = exportCsv(o);
    expect(csv.split('\n')[0]).toBe('key,value');
    expect(csv).toContain('input.earthElDeg,0.7');
    expect(csv).toMatch(/output\.marginDb,-?\d/);
  });
});

describe('scena sintetica', () => {
  it('la cima del terreno è esattamente la cima del modello; nessun rilievo sulla linea di vista prima del crinale', () => {
    const p = profileFor(33, 2000, 100, 55);
    const k = p.e.indexOf(2000);
    expect(p.u[k]).toBe(33);
    expect(Math.max(...p.u)).toBeCloseTo(33, 6);
    expect(ridgeHeightAt(0, 0, 33, 2000, 100, 55)).toBeCloseTo(0, 9);
  });
  it('raggio della cresta: curvatura gaussiana in cima = 1/R', () => {
    const H = 40;
    const R = 200;
    const dx = 1;
    const z = (x: number) => ridgeHeightAt(2000 + x, 0, H, 2000, R, 10);
    const curv = -(z(dx) - 2 * z(0) + z(-dx)) / (dx * dx);
    expect(1 / curv).toBeCloseTo(R, -1);
  });
  it('stessi numeri nella scena e nel modello', () => {
    const o = run({ earthElDeg: 0.8 });
    const s = syntheticScene(o, 'Scenario didattico');
    expect(s.terrain.synthetic).toBe(true);
    expect(s.link.margin).toBe(o.marginDb);
    expect(s.link.state).toBe(o.state);
    expect(s.ridge.nu).toBe(o.nu);
    expect(s.terrain.patch!.heights.length).toBe(96 * 96);
  });
  it('da una scena reale: ingressi del modello con il crinale dominante', () => {
    const s = syntheticScene(run({ earthElDeg: 1.2, ridgeHeightM: 50, ridgeDistanceM: 1500 }), 'x');
    const i = inputFromScene({ ...s, antenna: { ...s.antenna, gainDbi: 20 }, ridge: { ...s.ridge, radiusM: null, radiusResolved: false } }, sanitizeInput(DEFAULT_INPUT).input);
    expect(i).toMatchObject({ earthElDeg: 1.2, ridgeHeightM: 50, ridgeDistanceM: 1500, ridgeRadiusM: 0, radiusResolved: false });
    expect(i.gainDbi).toBe(20);
    expect(i.diameterM).toBeUndefined();
    expect(i.multipath.enabled).toBe(true);
  });
});

describe('passaggio all’onda', () => {
  it('l’onda usa frequenza, raggio e distanza della scena, nei suoi intervalli', () => {
    setWaveHandoff({ frequencyGhz: 2.2, radiusM: 100, distanceM: 2500 });
    const f = initialForm(getWaveHandoff());
    expect(f).toMatchObject({ frequencyGhz: 2.2, radiusM: 100, distanceM: 2500 });
    expect(validateForm(f)).toEqual({});
    const g = initialForm({ frequencyGhz: NaN, radiusM: 1000, distanceM: 20 });
    expect(g.frequencyGhz).toBe(8.4);
    expect(g.radiusM).toBe(400);
    expect(validateForm(g)).toEqual({});
    setWaveHandoff(null);
    expect(initialForm(getWaveHandoff())).toMatchObject({ frequencyGhz: 8.4, radiusM: 0, distanceM: 2000 });
  });
});
