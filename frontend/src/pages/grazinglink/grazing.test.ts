// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import {
  antennaRequest,
  buildRequest,
  classify,
  diffractionCurve,
  fresnelCS,
  heatmap,
  heatCsv,
  intervalSegments,
  ituDb,
  knifeEdgeDb,
  nearestIndex,
  parseNumberList,
  parseProfileCsv,
  syntheticRidgeCsv,
  timeCsv,
  timeData,
  toCsv,
  toStartUtc,
  tradeData,
  validateForm,
  windowStats,
  type AnalysisResult,
  type Compensation,
  type Form,
  type ParamRow,
} from './grazing';

const rows: ParamRow[] = [
  { key: 'tx_power_dbw', value: 10, unit: 'dBW', min: -20, max: 40, status: 'I', source: 's' },
  { key: 'tx_gain_dbi', value: 3, unit: 'dBi', min: 0, max: 30, status: 'I', source: 's' },
  { key: 'rate_bps', value: 1e5, unit: 'bit/s', min: 1e4, max: 3e6, status: 'I', source: 's' },
  { key: 'tsys_k', value: 30, unit: 'K', min: 10, max: 300, status: 'I', source: 's' },
  { key: 'frequency_ghz', value: 8.4, unit: 'GHz', status: 'V', source: 'p. 1' },
];
const st = {
  sites: [
    { id: 'a', name: 'A', lat_deg: -89, lon_deg_east: 0, dem_covered: true },
    { id: 'b', name: 'B', lat_deg: 0.7, lon_deg_east: 23, dem_covered: false },
  ],
  limits: { days_max: 90, step_min_min: 1, max_profile_points: 1500, max_samples: 5000 },
};
const form = (o: Partial<Form> = {}): Form => ({
  siteId: 'a',
  start: '2027-04-07T00:00',
  days: 2,
  stepMin: 30,
  station: 'dsn34',
  rate: 1e5,
  profile: null,
  sweep: false,
  elStart: -1,
  elEnd: 3,
  values: { tx_power_dbw: 10, tx_gain_dbi: 3, rate_bps: 1e5, tsys_k: 30 },
  ...o,
});

describe('richiesta', () => {
  it('toStartUtc accetta solo date reali', () => {
    expect(toStartUtc('2027-04-07T00:00')).toBe('2027-04-07T00:00:00Z');
    expect(toStartUtc('2027-04-07T00:00:59')).toBe('2027-04-07T00:00:59Z');
    expect(toStartUtc('2027-04-07T00:00:60')).toBeNull();
    expect(toStartUtc('2027-02-30T00:00')).toBeNull();
    expect(toStartUtc('boh')).toBeNull();
  });
  it('invia stazione e rate e solo gli override I modificati', () => {
    const r = buildRequest(form({ values: { tx_power_dbw: 12, tx_gain_dbi: 3, rate_bps: 1e5, tsys_k: 30 } }), rows);
    expect(r).toEqual({ site_id: 'a', start_utc: '2027-04-07T00:00:00Z', days: 2, step_min: 30, overrides: { station: 'dsn34', rate_bps: 1e5, tx_power_dbw: 12 } });
  });
  it('con profilo e spazzolamento: niente site_id, profilo e sweep presenti', () => {
    const p = { distance_m: [0, 10], height_m: [0, 1] };
    const r = buildRequest(form({ profile: p, sweep: true }), rows);
    expect(r.site_id).toBeUndefined();
    expect(r.profile).toEqual(p);
    expect(r.earth_sweep).toEqual({ el_start_deg: -1, el_end_deg: 3 });
  });
  it('validazione: sito fuori copertura senza profilo, con profilo ok', () => {
    expect(validateForm(form({ siteId: 'b' }), rows, st).site).toMatch(/fuori copertura DEM/);
    expect(validateForm(form({ siteId: 'b', profile: { distance_m: [0, 1], height_m: [0, 0] } }), rows, st).site).toBeUndefined();
  });
  it('validazione: durata, passo, troppi istanti, parametri fuori limite, sweep senza profilo', () => {
    const e = validateForm(form({ days: 0, stepMin: 0, values: { tx_power_dbw: 99, tx_gain_dbi: null, rate_bps: 1e5, tsys_k: 30 } }), rows, st);
    expect(e.days && e.step && e['p-tx_power_dbw'] && e['p-tx_gain_dbi']).toBeTruthy();
    expect(validateForm(form({ days: 90, stepMin: 1 }), rows, st).step).toMatch(/Troppi istanti/);
    expect(validateForm(form({ sweep: true }), rows, st).profile).toBeTruthy();
    expect(validateForm(form(), rows, st)).toEqual({});
  });
  it('elenco di numeri', () => {
    expect(parseNumberList('1e3, 1e4;1e5', 1e2, 1e10)).toEqual([1e3, 1e4, 1e5]);
    expect(parseNumberList('', 0, 1)).toBeNull();
    expect(parseNumberList('1 x', 0, 10)).toBeNull();
    expect(parseNumberList('5', 0, 1)).toBeNull();
  });
});

describe('profilo CSV', () => {
  it('legge intestazione, separatori misti e commenti', () => {
    const r = parseProfileCsv('# prova\ndistanza,quota\n0,1.5\n10;2\n20\t3\n');
    expect(r).toEqual({ ok: true, profile: { distance_m: [0, 10, 20], height_m: [1.5, 2, 3] } });
  });
  it('rifiuta: prima distanza diversa da 0, distanze non crescenti, non numerico, troppo corto', () => {
    expect(parseProfileCsv('5,1\n6,2')).toMatchObject({ ok: false, error: expect.stringMatching(/deve essere 0/) });
    expect(parseProfileCsv('0,1\n10,1\n10,2')).toMatchObject({ ok: false, error: expect.stringMatching(/Riga 3.*crescere/) });
    expect(parseProfileCsv('0,1\nx,2')).toMatchObject({ ok: false, error: expect.stringMatching(/Riga 2/) });
    expect(parseProfileCsv('0,1')).toMatchObject({ ok: false });
    expect(parseProfileCsv('0,1\n1,2,3')).toMatchObject({ ok: false });
  });
  it('limiti come l\'API: quota, distanza, numero di punti, dimensione', () => {
    expect(parseProfileCsv('0,0\n10,30000')).toMatchObject({ ok: false, error: expect.stringMatching(/quota/) });
    expect(parseProfileCsv('0,0\n200000,1')).toMatchObject({ ok: false, error: expect.stringMatching(/100 km/) });
    expect(parseProfileCsv('0,0\n1,0\n2,0\n3,0', 3)).toMatchObject({ ok: false, error: expect.stringMatching(/Troppi punti/) });
    expect(parseProfileCsv('0,0\n'.repeat(20_000))).toMatchObject({ ok: false, error: expect.stringMatching(/troppo grande/) });
  });
  it('il crinale di prova e\' valido', () => {
    const r = parseProfileCsv(syntheticRidgeCsv());
    expect(r.ok).toBe(true);
    if (r.ok) expect(Math.max(...r.profile.height_m)).toBeCloseTo(12, 6);
  });
});

const win = (o: Partial<AnalysisResult['windows']> = {}): AnalysisResult['windows'] => ({
  rate_bps: 1e5,
  geometric_hours: 30,
  real_hours: 50,
  transition_hours: 25,
  geometric_not_closing_hours: 5,
  both_hours: 25,
  total_hours: 100,
  geometric_intervals_unix: [],
  real_intervals_unix: [],
  transition_intervals_unix: [],
  rule: '',
  ...o,
});

describe('finestre', () => {
  it('ore e percentuali, zona di transizione, barre che sommano 100', () => {
    const s = windowStats(win());
    expect([s.geometricPct, s.realPct, s.transitionPct]).toEqual([30, 50, 25]);
    expect(s.closed).toBe(45);
    const g = s.geometricBar;
    const r = s.realBar;
    expect(g.both + g.notClosing + g.blocked).toBeCloseTo(100);
    expect(r.both + r.transition + r.closed).toBeCloseTo(100);
    expect(r.transition).toBe(25);
  });
  it('finestra vuota: nessuna divisione per zero', () => {
    const s = windowStats(win({ total_hours: 0, geometric_hours: 0, real_hours: 0, both_hours: 0, transition_hours: 0, geometric_not_closing_hours: 0 }));
    expect(s.geometricPct).toBe(0);
    expect(s.realBar.closed).toBe(0);
  });
  it('intervalli in percentuale della finestra, con larghezza minima visibile', () => {
    expect(intervalSegments([[100, 200], [300, 300]], 0, 400)).toEqual([
      { left: 25, width: 25 },
      { left: 75, width: 0.3 },
    ]);
    expect(intervalSegments([[0, 1]], 5, 5)).toEqual([]);
  });
});

const res = {
  series_time_unix: [0, 900, 1800],
  rates_bps: [1e4, 1e5],
  series: {
    earth_el_deg: [0.5, 1, null],
    ridge_angle_above_los_deg: [0.2, -0.1, 0.3],
    margin_by_rate_db: [[3, 2, 1], [0, null, -1]],
    range_km: [384_000, 385_000, 386_000],
  },
  parameters: [{ key: 'tx_power_dbw', value: 12, unit: 'dBW', status: 'I', source: '' }],
  antenna: { libration_excursion_deg: 10.123456 },
} as unknown as AnalysisResult;

describe('serie, diffrazione, mappa, esportazione', () => {
  it('elevazione della cresta = Terra + angolo sopra la linea di vista; null diventa NaN', () => {
    const t = timeData(res);
    expect(t.ridgeEl[0]).toBeCloseTo(0.7);
    expect(t.ridgeEl[1]).toBeCloseTo(0.9);
    expect(Number.isNaN(t.ridgeEl[2])).toBe(true);
    expect(Number.isNaN(t.margins[1]![1])).toBe(true);
    expect(timeCsv(res).split('\n')[0]).toBe('time_unix,earth_el_deg,ridge_el_deg,margin_db_10000bps,margin_db_100000bps');
  });
  it('richiesta antenna dai parametri usati e dalla librazione', () => {
    const a = antennaRequest(res, 'dsn18', [1e4], [0.3]);
    expect(a).toMatchObject({ station: 'dsn18', tx_power_dbw: 12, distance_km: 385_000, excursion_deg: 10.123, frequency_ghz: 8.4 });
  });
  it('Fresnel e lama esatta contro valori noti', () => {
    const [c, s] = fresnelCS(1);
    expect(c).toBeCloseTo(0.7798934, 5);
    expect(s).toBeCloseTo(0.4382591, 5);
    expect(fresnelCS(-1)[0]).toBeCloseTo(-0.7798934, 5);
    expect(knifeEdgeDb(0)).toBeCloseTo(6.0206, 3); // bordo sulla linea di vista: 6 dB
    expect(knifeEdgeDb(-3)).toBeLessThan(0.5);
    expect(knifeEdgeDb(1)).toBeCloseTo(13.86, 1);
  });
  it('approssimazione ITU: vicina all\'esatta per nu > -0,78 e zero sotto', () => {
    expect(ituDb(-1)).toBe(0);
    for (const v of [0, 1, 2.4]) expect(Math.abs(ituDb(v) - knifeEdgeDb(v))).toBeLessThan(0.5);
  });
  it('curva: griglia unita agli nu di funzionamento, punti solo li\'', () => {
    const c = diffractionCurve([0.123, null, 1.5], -1, 2, 0.5);
    expect(c.nu.length).toBe(c.exact.length);
    const ops = [...c.points].filter((v) => !Number.isNaN(v));
    expect(ops.length).toBe(2);
    expect(c.nu).toContain(0.123);
    expect(Math.min(...c.nu)).toBeLessThanOrEqual(-1);
  });
  const comp: Compensation = {
    nu: [-1, 0, 1],
    radius_m: [0, 100],
    correction_db: [[0, 0, 0], [1, 2, 0.5]],
    oscillation_envelope_db: [[0, 0, 0], [0.1, 0.2, 0.3]],
    anomaly: [[0, 0, 0], [0, 1, 0]],
    info: { version: '1', status: 's', file_sha256: 'x' },
    inconsistency: { status: 'aperta', text: '' },
  };
  it('mappa di calore: indice [raggio][nu], intensita\' relativa al massimo, anomalie', () => {
    const h = heatmap(comp);
    expect(h.cells.length).toBe(6);
    const c = h.cells.find((x) => x.radius === 100 && x.nu === 0)!;
    expect(c).toMatchObject({ value: 2, t: 1, anomaly: true, envelope: 0.2 });
    expect(h.cells.find((x) => x.radius === 0)!.t).toBe(0);
    expect(h.anomalies).toBe(1);
    expect(h.max).toBe(2);
    expect(heatCsv(h).split('\n')[0]).toBe('radius_m,nu,correction_db,oscillation_envelope_db,anomaly');
    expect(nearestIndex(comp.nu, 0.4)).toBe(1);
  });
  it('compromesso: ordinato per k, dati relativi in percento', () => {
    const t = tradeData([
      { k: 2, outage_pct: 1, relative_data: 0.5 },
      { k: 0, outage_pct: 9, relative_data: null },
    ] as never);
    expect([...t.k]).toEqual([0, 2]);
    expect(Number.isNaN(t.data[0])).toBe(true);
    expect(t.data[1]).toBe(50);
  });
  it('CSV: virgolette e difesa dalle formule, NaN vuoto', () => {
    expect(toCsv(['a', 'b'], [['x,y', NaN], ['=1+1', 2]])).toBe("a,b\n\"x,y\",\n'=1+1,2\n");
  });
  it('classificazione degli errori HTTP', async () => {
    const r = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });
    expect(await classify(r(503, 'dati DEM non disponibili'))).toBe('dem');
    expect(await classify(r(503, 'efemeridi non disponibili'))).toBe('ephemeris');
    expect(await classify(r(503, 'simulatore gimbal C non disponibile'))).toBe('gimbal');
    expect(await classify(r(503, 'troppe analisi in corso'))).toBe('busy');
    expect(await classify(r(422, 'sito fuori copertura DEM (il prodotto LOLA copre latitudini <= -85 gradi)'))).toBe('coverage');
    expect(await classify(r(422, 'parametri non validi'))).toBe('invalid');
    expect(await classify(new Response('x', { status: 500 }))).toBe('server');
  });
});
