// SPDX-License-Identifier: Apache-2.0
// Modello chiuso del link nel browser per Simula (nessun DOM). Stesse equazioni del motore backend/domain/grazing
// (docs/domain/grazinglink-model.md): parametro nu e bordo a lama esatto (JPL226 eq. 38-39, integrali di Fresnel di
// grazinglink/grazing.ts), correzione della cresta arrotondata T(m,n) di ITU-R P.526-9 par. 4.2 eq. (28)-(32) con la
// tabella split-step versionata (GET /api/raven/compensation) come confronto: |ITU - split-step| è l'incertezza
// (compensation.ridge_correction, docs/domain/validation.md "Validazione radio"), spazio libero (CB79 sez. 2.7), guadagno/HPBW/puntamento dell'antenna (varianti dello
// script e corrette), due raggi sul regolite (polarizzazione circolare co-polare), C/N0, margine, bit-rate massimo,
// stato aperto/transizione/bloccato e indicatori di validità. Parità con il motore: src/pages/simula/linkModel.test.ts.
//
// Geometria del scenario manuale: terreno piano (raggio lunare -> infinito, limite di terrain.dominant_ridge), antenna a
// quota `mastM`, cima del crinale a distanza orizzontale e = d1 e quota H sul suolo: u = H - mast,
// h = u cos(el) - e sin(el) (> 0: la cima sta sopra la linea di vista), d1_los = e cos(el) + u sin(el).
import { knifeEdgeDb } from '../grazinglink/grazing';
import { RAVEN_PARAM, RAVEN_RATES_BPS, RAVEN_STATION_GAIN_DBI } from '../../contracts/raven_params';

/**
 * MIRROR of stage S5 (closed form) of the RAVEN Core Model: the same equations and the same numbers, here so that the sliders answer
 * instantly. The defaults, the radio set, the bit rates and the station gains come from the generated registry
 * (contracts/raven_params.ts); the parity fixture is produced by the Python engine (scripts/dump_link_parity.py).
 * It does not read terrain, ephemerides, battery or DSN visibility: those exist only in /api/raven.
 */
export const MIRROR_OF_STAGE = 'S5';

export const C_MS = 299_792_458;
/** CB79 sez. 3.1 eq. (4): 10 log10(1.380649e-23), tag V (lo script usa -228,6). */
export const BOLTZMANN_DBW = RAVEN_PARAM['grazing.boltzmann_dbw_per_k_hz'].default;
/** Fascio gaussiano: 10 log10(e) 4 ln 2 (D). */
export const GAUSSIAN_DB_PER_X2 = 12.041199826559248;
export const SCRIPT_DB_PER_X2 = 12;
/** HPBW dell'apertura circolare uniforme in lambda/D gradi (D, calcolato dal backend con brentq). */
export const HPBW_UNIFORM_FACTOR = 58.957011623244725;
export const HPBW_SCRIPT_FACTOR = 70;
export const RATES_BPS: readonly number[] = RAVEN_RATES_BPS;
export const STATION_GAIN_DBI = RAVEN_STATION_GAIN_DBI;
export type StationId = keyof typeof STATION_GAIN_DBI;
export const TABLE_REFERENCE_D1_M = 2000;
export const TABLE_NU_RANGE = [-1.5, 3] as const;
export const OSC_NU = -0.78;
export const MIN_GRAZING_DEG = 0.05;
/** Incertezza della correzione oltre la quale il risultato è "incerto" (I, scelta di questa pagina). */
export const UNCERTAINTY_LIMIT_DB = 0.25;
/** Angolo tra linea di vista e cima oltre il quale l'approssimazione parassiale è dubbia / non vale (I). */
export const PARAXIAL_DEG = [10, 20] as const;

export interface MultipathInput {
  enabled: boolean;
  epsReal: number;
  epsImag: number;
  roughnessM: number;
}

export interface LinkInput {
  frequencyGhz: number;
  earthElDeg: number;
  /** Quota della cima sul suolo sotto l'antenna (m); ignorata se c'è `ridgeAngleDeg`. */
  ridgeHeightM?: number;
  /** Elevazione della cima vista dall'antenna (gradi), alternativa a `ridgeHeightM`. */
  ridgeAngleDeg?: number;
  ridgeDistanceM: number;
  ridgeRadiusM: number;
  /** Diametro della parabola del rover (m); ignorato se c'è `gainDbi`. */
  diameterM?: number;
  gainDbi?: number;
  eta: number;
  pointingErrorDeg: number;
  txPowerDbw: number;
  tsysK: number;
  ebn0Db: number;
  miscLossDb: number;
  rateBps: number;
  station: StationId;
  /** Guadagno della stazione (dBi) se diverso da quello della classe; assente = valore del registro per la classe. */
  stationGainDbi?: number | null;
  earthDistanceKm: number;
  mastM: number;
  applyCorrection: boolean;
  multipath: MultipathInput;
  /** Solo con un sito reale: raggio della cresta risolto dal DEM. Assente = scenario manuale (N/A). */
  radiusResolved?: boolean;
}

export const DEFAULT_INPUT: Readonly<LinkInput> = Object.freeze({
  frequencyGhz: RAVEN_PARAM['rf.frequency_ghz'].default,
  earthElDeg: 1.5,
  ridgeHeightM: 33,
  ridgeDistanceM: 2000,
  ridgeRadiusM: 100,
  diameterM: 0.0861,
  eta: 0.55,
  pointingErrorDeg: 0,
  txPowerDbw: RAVEN_PARAM['rf.tx_power_dbw'].default,
  tsysK: RAVEN_PARAM['rf.tsys_k'].default,
  ebn0Db: RAVEN_PARAM['rf.ebn0_db'].default,
  miscLossDb: RAVEN_PARAM['rf.misc_loss_db'].default,
  rateBps: 1e5,
  station: 'dsn34',
  earthDistanceKm: 384_400,
  mastM: 2,
  applyCorrection: true,
  multipath: Object.freeze({ enabled: false, epsReal: 3.7, epsImag: 0.01, roughnessM: 0.25 }),
}) as Readonly<LinkInput>;

/** Intervalli ammessi (slider e validazione dell'URL); fuori intervallo -> il valore è riportato al bordo. */
export const RANGES = {
  frequencyGhz: [0.3, 40],
  earthElDeg: [-2, 10],
  ridgeHeightM: [0, 150],
  ridgeAngleDeg: [-5, 20],
  ridgeDistanceM: [100, 10_000],
  ridgeRadiusM: [0, 1000],
  diameterM: [0.02, 3],
  gainDbi: [-10, 45],
  eta: [0.2, 1],
  pointingErrorDeg: [0, 30],
  txPowerDbw: [-20, 40],
  tsysK: [10, 300],
  ebn0Db: [0, 15],
  miscLossDb: [0, 20],
  earthDistanceKm: [356_000, 407_000],
  mastM: [0.1, 100],
  epsReal: [1, 20],
  epsImag: [0, 5],
  roughnessM: [0, 5],
} as const satisfies Record<string, readonly [number, number]>;
export type RangeKey = keyof typeof RANGES;

export type LinkState = 'open' | 'transition' | 'blocked';
export type FlagLevel = 'ok' | 'uncertain' | 'outside' | 'na';
export type FlagCode =
  | 'invalid_input'
  | 'earth_below_horizon'
  | 'paraxial'
  | 'nu_outside_table'
  | 'fresnel_oscillation'
  | 'd1_outside_table'
  | 'radius_unresolved'
  | 'reflection_beyond_ridge'
  | 'correction_unavailable';
export interface Flag {
  code: FlagCode;
  level: FlagLevel;
}
export type ValidityLevel = 'reliable' | 'uncertain' | 'outside';
export interface Validity {
  level: ValidityLevel;
  /** Tutti i controlli, con il loro esito (Avanzato li elenca). */
  flags: Flag[];
  /** Solo quelli che rendono il risultato incerto o fuori modello, dal più grave. */
  reasons: FlagCode[];
}

export interface LinkOutput {
  input: LinkInput;
  wavelengthM: number;
  tipElevationDeg: number;
  angleAboveLosDeg: number;
  hAboveLosM: number;
  d1LosM: number;
  blocksLos: boolean;
  fresnelR1M: number;
  nu: number;
  knifeEdgeDb: number;
  ituDb: number;
  /** 'itu': T(m,n) di P.526-9 con banda split-step; 'not-available': ITU applicata ma tabella di confronto assente. */
  correctionStatus: 'itu' | 'off' | 'not-available';
  correctionDb: number;
  /** Correzione della tabella split-step (solo confronto, non sommata al link). */
  correctionSplitStepDb: number;
  correctionUncertaintyDb: number;
  correctionClamped: boolean;
  diffractionLossDb: number;
  fsplDb: number;
  gainDbi: number;
  diameterM: number;
  hpbwScriptDeg: number;
  hpbwUniformDeg: number;
  pointingLossDb: number;
  pointingScriptDb: number;
  pointingAiryDb: number;
  gainCrudeDbi: number;
  multipathGainDb: number;
  multipathApplicable: boolean;
  specularDistanceM: number | null;
  stationGainDbi: number;
  n0Dbw: number;
  cn0DbHz: number;
  marginDb: number;
  marginByRateDb: number[];
  maxRateBps: number;
  state: LinkState;
  validity: Validity;
}

/* --------------------------------------------- tabella di correzione --------------------------------------------- */

export interface CompTable {
  nu: number[];
  logRadius: number[];
  radiusM: number[];
  correction: number[][]; // [radius][nu]
  envelope: number[][];
  version: string;
}

const finiteArr = (v: unknown, min = 2, max = 4096): v is number[] =>
  Array.isArray(v) && v.length >= min && v.length <= max && v.every((x) => typeof x === 'number' && Number.isFinite(x));

/** Valida la risposta di /api/raven/compensation (o il file della tabella); null se non usabile. */
export function parseCompTable(json: unknown): CompTable | null {
  if (typeof json !== 'object' || json === null) return null;
  const o = json as Record<string, unknown>;
  const nu = o.nu;
  const rad = o.radius_m;
  if (!finiteArr(nu) || !finiteArr(rad)) return null;
  for (let i = 1; i < nu.length; i++) if (!(nu[i]! > nu[i - 1]!)) return null;
  for (let i = 1; i < rad.length; i++) if (!(rad[i]! > rad[i - 1]!) || rad[0]! < 0) return null;
  const grid = (v: unknown): number[][] | null =>
    Array.isArray(v) && v.length === rad.length && v.every((row) => finiteArr(row, nu.length, nu.length)) ? (v as number[][]) : null;
  const corr = grid(o.correction_db);
  const env = grid(o.oscillation_envelope_db);
  if (!corr || !env) return null;
  const info = o.info as { version?: unknown } | undefined;
  const version = typeof o.version === 'string' ? o.version : typeof info?.version === 'string' ? info.version : '';
  return { nu, radiusM: rad, logRadius: rad.map((r) => Math.log10(r + 1)), correction: corr, envelope: env, version: version.slice(0, 40) };
}

function locate(grid: number[], x: number): [number, number] {
  // come numpy: searchsorted(side='right') - 1, limitato a [0, n-2]
  let i = 0;
  while (i < grid.length - 1 && grid[i + 1]! <= x) i++;
  i = Math.min(Math.max(i, 0), grid.length - 2);
  return [i, (x - grid[i]!) / (grid[i + 1]! - grid[i]!)];
}
function bilinear(t: number[][], i: number, j: number, ti: number, tj: number): number {
  const a = t[i]![j]! * (1 - tj) + t[i]![j + 1]! * tj;
  const b = t[i + 1]![j]! * (1 - tj) + t[i + 1]![j + 1]! * tj;
  return a * (1 - ti) + b * ti;
}

/** Correzione (dB), incertezza (dB) e saturazione ai bordi: compensation.table_correction. */
export function tableCorrection(tb: CompTable, nu: number, radiusM: number): { db: number; uncertaintyDb: number; clamped: boolean } {
  const y = Math.log10(radiusM + 1);
  const n0 = tb.nu[0]!;
  const n1 = tb.nu[tb.nu.length - 1]!;
  const l0 = tb.logRadius[0]!;
  const l1 = tb.logRadius[tb.logRadius.length - 1]!;
  const clamped = nu < n0 || nu > n1 || y > l1;
  const [j, tj] = locate(tb.nu, Math.min(Math.max(nu, n0), n1));
  const [i, ti] = locate(tb.logRadius, Math.min(Math.max(y, l0), l1));
  const db = bilinear(tb.correction, i, j, ti, tj);
  const env = bilinear(tb.envelope, i, j, ti, tj);
  return { db, uncertaintyDb: clamped ? Math.max(env, Math.abs(db)) : env, clamped };
}

/** T(m,n) di ITU-R P.526-9 par. 4.2 eq. (30a)-(32), h dall'eq. (22); R = 0 -> 0: compensation.p526_rounded_term_db. */
export function p526RoundedTermDb(nu: number, radiusM: number, d1: number, d2: number, lam: number): number {
  if (!(radiusM > 0)) return 0;
  const h = nu / Math.sqrt((2 * (d1 + d2)) / (lam * d1 * d2));
  const k = (Math.PI * radiusM) / lam;
  const m = (radiusM * (d1 + d2)) / (d1 * d2) / Math.cbrt(k);
  const n = (h * k ** (2 / 3)) / radiusM;
  const mn = m * n;
  const sq = Math.sqrt(m);
  const tail = 3.6 * m * sq - 0.8 * m * m;
  if (mn <= 4) return 7.2 * sq - (2 - 12.5 * n) * m + tail;
  return -6 - 20 * Math.log10(mn) + 7.2 * sq - (2 - 17 * n) * m + tail;
}

/* ------------------------------------------------- antenna ------------------------------------------------- */

export const wavelengthM = (ghz: number): number => C_MS / (ghz * 1e9);
export const gainFromDiameter = (d: number, ghz: number, eta: number): number => 10 * Math.log10(eta * ((Math.PI * d) / wavelengthM(ghz)) ** 2);
export const diameterFromGain = (g: number, ghz: number, eta: number): number => (wavelengthM(ghz) / Math.PI) * Math.sqrt(10 ** (g / 10) / eta);

/** Bessel J1 (Numerical Recipes bessj1, errore ~1e-8): per la perdita di puntamento dell'apertura uniforme. */
export function besselJ1(x: number): number {
  const ax = Math.abs(x);
  if (ax < 8) {
    const y = x * x;
    const a1 = x * (72362614232.0 + y * (-7895059235.0 + y * (242396853.1 + y * (-2972611.439 + y * (15704.4826 + y * -30.16036606)))));
    const a2 = 144725228442.0 + y * (2300535178.0 + y * (18583304.74 + y * (99447.43394 + y * (376.9991397 + y))));
    return a1 / a2;
  }
  const z = 8 / ax;
  const y = z * z;
  const xx = ax - 2.356194491;
  const b1 = 1 + y * (0.183105e-2 + y * (-0.3516396496e-4 + y * (0.2457520174e-5 + y * -0.240337019e-6)));
  const b2 = 0.04687499995 + y * (-0.2002690873e-3 + y * (0.8449199096e-5 + y * (-0.88228987e-6 + y * 0.105787412e-6)));
  const ans = Math.sqrt(0.636619772 / ax) * (Math.cos(xx) * b1 - z * Math.sin(xx) * b2);
  return x < 0 ? -ans : ans;
}

export function pointingAiryDb(errDeg: number, diameterM: number, ghz: number): number {
  const u = (Math.PI * diameterM * Math.sin((Math.abs(errDeg) * Math.PI) / 180)) / wavelengthM(ghz);
  if (u < 1e-9) return 0;
  return -20 * Math.log10(Math.max(Math.abs((2 * besselJ1(u)) / u), 1e-12));
}

/* -------------------------------------------- due raggi (multipath) -------------------------------------------- */

type Cx = [number, number];
const cadd = (a: Cx, b: Cx): Cx => [a[0] + b[0], a[1] + b[1]];
const csub = (a: Cx, b: Cx): Cx => [a[0] - b[0], a[1] - b[1]];
const cmul = (a: Cx, b: Cx): Cx => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
const cdiv = (a: Cx, b: Cx): Cx => {
  const d = b[0] * b[0] + b[1] * b[1];
  return [(a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d];
};
/** Radice principale (come numpy). */
const csqrt = (a: Cx): Cx => {
  const r = Math.hypot(a[0], a[1]);
  const re = Math.sqrt((r + a[0]) / 2);
  const im = Math.sqrt(Math.max(0, (r - a[0]) / 2));
  return [re, a[1] < 0 || Object.is(a[1], -0) ? -im : im];
};

export interface TwoRay {
  gainDb: number;
  applicable: boolean;
  specularDistanceM: number | null;
  reflectionMagnitude: number;
}

/** multipath.two_ray con polarizzazione circolare co-polare; non applicabile oltre il crinale o con el <= 0. */
export function twoRay(psiDeg: number, mastM: number, lambdaM: number, mp: MultipathInput, ridgeDistanceM: number): TwoRay {
  if (!(psiDeg > 0)) return { gainDb: 0, applicable: false, specularDistanceM: null, reflectionMagnitude: 0 };
  const used = Math.max(psiDeg, MIN_GRAZING_DEG);
  const psi = (used * Math.PI) / 180;
  const spec = mastM / Math.tan(psiDeg * Math.PI / 180);
  const s = Math.sin(psi);
  const eps: Cx = [mp.epsReal, -mp.epsImag];
  const q = csqrt([eps[0] - Math.cos(psi) ** 2, eps[1]]);
  const sc: Cx = [s, 0];
  const gh = cdiv(csub(sc, q), cadd(sc, q));
  const es = cmul(eps, sc);
  const gv = cdiv(csub(es, q), cadd(es, q));
  const gamma: Cx = [(gh[0] + gv[0]) / 2, (gh[1] + gv[1]) / 2];
  const g = ((4 * Math.PI * mp.roughnessM * s) / lambdaM) ** 2;
  const rho = Math.exp(-g / 2);
  const ph = (-4 * Math.PI * mastM * s) / lambdaM;
  const r = cmul([gamma[0] * rho, gamma[1] * rho], [Math.cos(ph), Math.sin(ph)]);
  const field = Math.hypot(1 + r[0], r[1]);
  const ok = !(spec > ridgeDistanceM);
  return {
    gainDb: ok ? 20 * Math.log10(Math.max(field, 1e-12)) : 0,
    applicable: ok,
    specularDistanceM: spec,
    reflectionMagnitude: Math.hypot(gamma[0], gamma[1]) * rho,
  };
}

/* ------------------------------------------------- ingresso ------------------------------------------------- */

const clampTo = (v: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, v));

/**
 * Ingresso pulito: ogni numero non finito torna al predefinito, ogni valore fuori intervallo al bordo, il bit-rate al
 * valore ammesso più vicino. `bad` = almeno un valore non finito o di tipo sbagliato (indicatore "fuori modello").
 */
export function sanitizeInput(raw: Partial<LinkInput>): { input: LinkInput; bad: boolean } {
  let bad = false;
  const n = (v: unknown, key: RangeKey, def: number): number => {
    if (v === undefined) return def;
    if (typeof v !== 'number' || !Number.isFinite(v)) {
      bad = true;
      return def;
    }
    return clampTo(v, RANGES[key]);
  };
  const d = DEFAULT_INPUT;
  const mpRaw: Partial<MultipathInput> = (raw.multipath ?? {}) as Partial<MultipathInput>;
  const rate = typeof raw.rateBps === 'number' && Number.isFinite(raw.rateBps) ? raw.rateBps : (raw.rateBps === undefined ? d.rateBps : ((bad = true), d.rateBps));
  const nearest = RATES_BPS.reduce((a, b) => (Math.abs(Math.log(b / rate)) < Math.abs(Math.log(a / rate)) ? b : a));
  const station: StationId = raw.station === 'dsn18' || raw.station === 'dsn34' ? raw.station : d.station;
  if (raw.station !== undefined && raw.station !== station) bad = true;
  const input: LinkInput = {
    frequencyGhz: n(raw.frequencyGhz, 'frequencyGhz', d.frequencyGhz),
    earthElDeg: n(raw.earthElDeg, 'earthElDeg', d.earthElDeg),
    ridgeDistanceM: n(raw.ridgeDistanceM, 'ridgeDistanceM', d.ridgeDistanceM),
    ridgeRadiusM: n(raw.ridgeRadiusM, 'ridgeRadiusM', d.ridgeRadiusM),
    eta: n(raw.eta, 'eta', d.eta),
    pointingErrorDeg: n(raw.pointingErrorDeg, 'pointingErrorDeg', d.pointingErrorDeg),
    txPowerDbw: n(raw.txPowerDbw, 'txPowerDbw', d.txPowerDbw),
    tsysK: n(raw.tsysK, 'tsysK', d.tsysK),
    ebn0Db: n(raw.ebn0Db, 'ebn0Db', d.ebn0Db),
    miscLossDb: n(raw.miscLossDb, 'miscLossDb', d.miscLossDb),
    rateBps: rate > 0 ? nearest : d.rateBps,
    station,
    earthDistanceKm: n(raw.earthDistanceKm, 'earthDistanceKm', d.earthDistanceKm),
    mastM: n(raw.mastM, 'mastM', d.mastM),
    applyCorrection: raw.applyCorrection === undefined ? d.applyCorrection : raw.applyCorrection === true,
    multipath: {
      enabled: mpRaw.enabled === true,
      epsReal: n(mpRaw.epsReal, 'epsReal', d.multipath.epsReal),
      epsImag: n(mpRaw.epsImag, 'epsImag', d.multipath.epsImag),
      roughnessM: n(mpRaw.roughnessM, 'roughnessM', d.multipath.roughnessM),
    },
  };
  if (raw.ridgeAngleDeg !== undefined) input.ridgeAngleDeg = n(raw.ridgeAngleDeg, 'ridgeAngleDeg', 0.9);
  else input.ridgeHeightM = n(raw.ridgeHeightM, 'ridgeHeightM', d.ridgeHeightM!);
  if (raw.gainDbi !== undefined) input.gainDbi = n(raw.gainDbi, 'gainDbi', 15);
  else input.diameterM = n(raw.diameterM, 'diameterM', d.diameterM!);
  if (raw.radiusResolved !== undefined) input.radiusResolved = raw.radiusResolved === true;
  return { input, bad };
}

/* ------------------------------------------------- calcolo ------------------------------------------------- */

const DEG = Math.PI / 180;
const ORDER: Record<FlagLevel, number> = { outside: 3, uncertain: 2, ok: 0, na: 0 };

/** Il link per un ingresso (sanificato qui). `table` = null: correzione omessa (lo dice l'indicatore). */
export function computeLink(raw: Partial<LinkInput>, table: CompTable | null): LinkOutput {
  const { input: x, bad } = sanitizeInput(raw);
  const lam = wavelengthM(x.frequencyGhz);
  const e = x.ridgeDistanceM;
  const u = x.ridgeAngleDeg !== undefined ? e * Math.tan(x.ridgeAngleDeg * DEG) : x.ridgeHeightM! - x.mastM;
  const el = x.earthElDeg * DEG;
  const h = u * Math.cos(el) - e * Math.sin(el);
  const d1 = e * Math.cos(el) + u * Math.sin(el);
  const rangeM = x.earthDistanceKm * 1000;
  const d2 = rangeM - d1;
  const d1s = Math.max(d1, 1e-3); // d1 <= 0 solo per geometrie fuori modello (cima dietro l'antenna)
  const nu = h * Math.sqrt((2 * (d1s + d2)) / (lam * d1s * d2));
  const tipEl = Math.atan2(u, e) / DEG;
  const j = knifeEdgeDb(nu);
  const itu = nu > OSC_NU ? 6.9 + 20 * Math.log10(Math.sqrt((nu - 0.1) ** 2 + 1) + nu - 0.1) : 0;

  let corr = 0;
  let unc = 0;
  let split = 0;
  let clamped = false;
  const correctionStatus: LinkOutput['correctionStatus'] = !x.applyCorrection ? 'off' : table ? 'itu' : 'not-available';
  if (x.applyCorrection) {
    corr = Math.max(p526RoundedTermDb(nu, x.ridgeRadiusM, d1s, d2, lam), 0);
    if (table) {
      const c = tableCorrection(table, nu, x.ridgeRadiusM);
      split = c.db;
      unc = Math.max(c.uncertaintyDb, Math.abs(corr - split));
      clamped = c.clamped;
    } else unc = Math.abs(corr); // nessun confronto: incertezza pari alla correzione
    if (x.radiusResolved === false) unc = Math.max(unc, Math.abs(corr));
  }

  const gain = x.gainDbi !== undefined ? x.gainDbi : gainFromDiameter(x.diameterM!, x.frequencyGhz, x.eta);
  const dia = x.gainDbi !== undefined ? diameterFromGain(x.gainDbi, x.frequencyGhz, x.eta) : x.diameterM!;
  const hp70 = (HPBW_SCRIPT_FACTOR * lam) / dia;
  const hpu = (HPBW_UNIFORM_FACTOR * lam) / dia;
  const err = Math.abs(x.pointingErrorDeg);
  const pt = GAUSSIAN_DB_PER_X2 * (err / hp70) ** 2;
  const ptScript = SCRIPT_DB_PER_X2 * (err / hp70) ** 2;
  const ptAiry = pointingAiryDb(err, dia, x.frequencyGhz);
  const fspl = 20 * Math.log10((4 * Math.PI * rangeM) / lam);

  let mp: TwoRay = { gainDb: 0, applicable: false, specularDistanceM: null, reflectionMagnitude: 0 };
  if (x.multipath.enabled) mp = twoRay(x.earthElDeg, x.mastM, lam, x.multipath, e);

  const st = x.stationGainDbi ?? STATION_GAIN_DBI[x.station];
  const n0 = BOLTZMANN_DBW + 10 * Math.log10(x.tsysK);
  const cn0 = x.txPowerDbw + gain + st - x.miscLossDb - pt - fspl - (j + corr) + mp.gainDb - n0;
  const byRate = RATES_BPS.map((r) => cn0 - x.ebn0Db - 10 * Math.log10(r));
  const margin = cn0 - x.ebn0Db - 10 * Math.log10(x.rateBps);
  let maxRate = 0;
  byRate.forEach((m, i) => {
    if (m >= 0) maxRate = Math.max(maxRate, RATES_BPS[i]!);
  });
  const blocks = h > 0;
  const state: LinkState = margin < 0 ? 'blocked' : blocks ? 'transition' : 'open';

  // ---- indicatori di validità ----
  const withRadius = correctionStatus === 'itu' && x.ridgeRadiusM > 0;
  const theta = Math.abs(tipEl - x.earthElDeg);
  const flags: Flag[] = [
    { code: 'invalid_input', level: bad ? 'outside' : 'ok' },
    { code: 'earth_below_horizon', level: x.earthElDeg <= 0 ? 'outside' : 'ok' },
    { code: 'paraxial', level: theta > PARAXIAL_DEG[1] || d1 <= 0 ? 'outside' : theta > PARAXIAL_DEG[0] ? 'uncertain' : 'ok' },
    { code: 'nu_outside_table', level: withRadius && clamped && unc >= UNCERTAINTY_LIMIT_DB ? 'uncertain' : 'ok' },
    { code: 'fresnel_oscillation', level: withRadius && nu < OSC_NU && !clamped && unc >= UNCERTAINTY_LIMIT_DB ? 'uncertain' : 'ok' },
    { code: 'd1_outside_table', level: withRadius && (d1 < 0.25 * TABLE_REFERENCE_D1_M || d1 > 4 * TABLE_REFERENCE_D1_M) ? 'uncertain' : 'ok' },
    { code: 'radius_unresolved', level: x.radiusResolved === undefined ? 'na' : x.radiusResolved || correctionStatus === 'off' ? 'ok' : 'uncertain' },
    { code: 'reflection_beyond_ridge', level: x.multipath.enabled && x.earthElDeg > 0 && !mp.applicable ? 'uncertain' : 'ok' },
    { code: 'correction_unavailable', level: correctionStatus === 'not-available' && x.ridgeRadiusM > 0 ? 'uncertain' : 'ok' },
  ];
  const active = flags.filter((f) => f.level === 'uncertain' || f.level === 'outside').sort((a, b) => ORDER[b.level] - ORDER[a.level]);
  const level: ValidityLevel = active.some((f) => f.level === 'outside') ? 'outside' : active.length ? 'uncertain' : 'reliable';

  return {
    input: x,
    wavelengthM: lam,
    tipElevationDeg: tipEl,
    angleAboveLosDeg: tipEl - x.earthElDeg,
    hAboveLosM: h,
    d1LosM: d1,
    blocksLos: blocks,
    fresnelR1M: Math.sqrt((lam * d1s * d2) / (d1s + d2)),
    nu,
    knifeEdgeDb: j,
    ituDb: itu,
    correctionStatus,
    correctionDb: corr,
    correctionSplitStepDb: split,
    correctionUncertaintyDb: unc,
    correctionClamped: clamped,
    diffractionLossDb: j + corr,
    fsplDb: fspl,
    gainDbi: gain,
    diameterM: dia,
    hpbwScriptDeg: hp70,
    hpbwUniformDeg: hpu,
    pointingLossDb: pt,
    pointingScriptDb: ptScript,
    pointingAiryDb: ptAiry,
    gainCrudeDbi: 10 * Math.log10(30000 / (hp70 * hp70)),
    multipathGainDb: mp.gainDb,
    multipathApplicable: mp.applicable,
    specularDistanceM: mp.specularDistanceM,
    stationGainDbi: st,
    n0Dbw: n0,
    cn0DbHz: cn0,
    marginDb: margin,
    marginByRateDb: byRate,
    maxRateBps: maxRate,
    state,
    validity: { level, flags, reasons: active.map((f) => f.code) },
  };
}

/* ------------------------------------------- curve, varianti, mappa ------------------------------------------- */

/** Margine contro l'elevazione della Terra (parametri correnti), per il grafico 2D. */
export function marginCurve(input: Partial<LinkInput>, table: CompTable | null, lo = 0, hi = 10, step = 0.05): { el: Float64Array; margin: Float64Array; blocked: Float64Array } {
  const n = Math.round((hi - lo) / step) + 1;
  const el = new Float64Array(n);
  const margin = new Float64Array(n);
  const blocked = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const v = Math.round((lo + i * step) * 1e6) / 1e6;
    const o = computeLink({ ...input, earthElDeg: v }, table);
    el[i] = v;
    margin[i] = o.marginDb;
    blocked[i] = o.blocksLos ? o.marginDb : NaN;
  }
  return { el, margin, blocked };
}

/** Prima elevazione (dall'alto) in cui il margine scende sotto 0: dove il link "smette di funzionare". */
export function failElevation(c: { el: Float64Array; margin: Float64Array }): number | null {
  for (let i = c.el.length - 1; i >= 0; i--) if (c.margin[i]! < 0) return i === c.el.length - 1 ? c.el[i]! : c.el[i + 1]!;
  return null;
}

export interface MarginChart {
  x: Float64Array;
  margin: Float64Array;
  /** solo dove il crinale copre la linea di vista geometrica (NaN altrove) */
  covered: Float64Array;
  zero: Float64Array;
  /** punto corrente (NaN altrove) */
  current: Float64Array;
  /** orizzonte geometrico del crinale sulla soglia 0 dB (NaN altrove) */
  horizon: Float64Array;
  horizonDeg: number;
  failDeg: number | null;
}
/** Dati del grafico margine-elevazione: griglia di 0,05° più il punto corrente e l'orizzonte geometrico. */
export function marginChart(input: Partial<LinkInput>, table: CompTable | null, lo = 0, hi = 10): MarginChart {
  const cur = computeLink(input, table);
  const hz = cur.tipElevationDeg;
  const grid = new Set<number>();
  for (let i = 0; i <= Math.round((hi - lo) / 0.05); i++) grid.add(Math.round((lo + i * 0.05) * 1e6) / 1e6);
  const e0 = Math.round(cur.input.earthElDeg * 1e6) / 1e6;
  if (e0 >= lo && e0 <= hi) grid.add(e0);
  const h0 = Math.round(hz * 1e6) / 1e6;
  if (h0 >= lo && h0 <= hi) grid.add(h0);
  const xs = Float64Array.from([...grid].sort((a, b) => a - b));
  const n = xs.length;
  const out: MarginChart = {
    x: xs,
    margin: new Float64Array(n),
    covered: new Float64Array(n),
    zero: new Float64Array(n),
    current: new Float64Array(n).fill(NaN),
    horizon: new Float64Array(n).fill(NaN),
    horizonDeg: hz,
    failDeg: null,
  };
  for (let i = 0; i < n; i++) {
    const o = computeLink({ ...input, earthElDeg: xs[i]! }, table);
    out.margin[i] = o.marginDb;
    out.covered[i] = o.blocksLos ? o.marginDb : NaN;
    if (xs[i] === e0) out.current[i] = cur.marginDb;
    if (xs[i] === h0) out.horizon[i] = 0;
  }
  out.failDeg = failElevation({ el: xs, margin: out.margin });
  return out;
}

export interface Variant {
  id: 'knife' | 'rounded' | 'rounded_splitstep' | 'multipath' | 'antenna_script' | 'antenna_corrected';
  marginDb: number;
  state: LinkState;
  /** Solo per le varianti della cresta: incertezza della correzione (dB). */
  uncertaintyDb?: number;
}
/** Confronto tra varianti con gli stessi ingressi: lama, cresta ITU, cresta split-step, multipath; antenna script / corretta. */
export function variants(input: Partial<LinkInput>, table: CompTable | null): Variant[] {
  const knife = computeLink({ ...input, applyCorrection: false }, table);
  const rounded = computeLink({ ...input, applyCorrection: true }, table);
  const splitMargin = rounded.marginDb + rounded.correctionDb - rounded.correctionSplitStepDb;
  const splitState: LinkState = splitMargin < 0 ? 'blocked' : rounded.blocksLos ? 'transition' : 'open';
  const base = sanitizeInput(input).input;
  const multi = computeLink({ ...input, multipath: { ...base.multipath, enabled: true } }, table);
  const cur = computeLink(input, table);
  // antenna dello script: guadagno grezzo 30000/HPBW^2 e puntamento 12 (err/HPBW)^2; corretta: apertura (CB79) e gaussiana 12,04
  const scriptMargin = cur.marginDb + cur.pointingLossDb - cur.pointingScriptDb + (cur.gainCrudeDbi - cur.gainDbi);
  const st = (m: number): LinkState => (m < 0 ? 'blocked' : cur.blocksLos ? 'transition' : 'open');
  return [
    { id: 'knife', marginDb: knife.marginDb, state: knife.state },
    { id: 'rounded', marginDb: rounded.marginDb, state: rounded.state, uncertaintyDb: rounded.correctionUncertaintyDb },
    ...(table ? [{ id: 'rounded_splitstep' as const, marginDb: splitMargin, state: splitState }] : []),
    { id: 'multipath', marginDb: multi.marginDb, state: multi.state },
    { id: 'antenna_script', marginDb: scriptMargin, state: st(scriptMargin) },
    { id: 'antenna_corrected', marginDb: cur.marginDb, state: cur.state },
  ];
}

export interface HeatCell {
  el: number;
  ridgeM: number;
  state: LinkState;
  validity: ValidityLevel;
  marginDb: number;
}
export interface Heat {
  cols: number;
  rows: number;
  elRange: readonly [number, number];
  ridgeRange: readonly [number, number];
  /** riga 0 = crinale più basso */
  cells: HeatCell[];
}
export const HEAT_EL: readonly [number, number] = [0, 10];
export const HEAT_RIDGE: readonly [number, number] = [0, 150];

/** Mappa di validità: elevazione della Terra (colonne) x quota del crinale (righe), centri delle celle. */
export function validityHeat(input: Partial<LinkInput>, table: CompTable | null, cols = 60, rows = 40): Heat {
  const cells: HeatCell[] = [];
  const base = { ...input };
  delete base.ridgeAngleDeg;
  for (let r = 0; r < rows; r++) {
    const ridgeM = HEAT_RIDGE[0] + ((r + 0.5) * (HEAT_RIDGE[1] - HEAT_RIDGE[0])) / rows;
    for (let c = 0; c < cols; c++) {
      const el = HEAT_EL[0] + ((c + 0.5) * (HEAT_EL[1] - HEAT_EL[0])) / cols;
      const o = computeLink({ ...base, earthElDeg: el, ridgeHeightM: ridgeM }, table);
      cells.push({ el, ridgeM, state: o.state, validity: o.validity.level, marginDb: o.marginDb });
    }
  }
  return { cols, rows, elRange: HEAT_EL, ridgeRange: HEAT_RIDGE, cells };
}

/** Cella -> valori dei controlli (clic sulla mappa), arrotondati al passo degli slider. */
export function heatPick(h: Heat, fx: number, fy: number): { earthElDeg: number; ridgeHeightM: number } {
  const x = Math.min(1, Math.max(0, fx));
  const y = Math.min(1, Math.max(0, fy));
  const el = h.elRange[0] + x * (h.elRange[1] - h.elRange[0]);
  const rm = h.ridgeRange[0] + y * (h.ridgeRange[1] - h.ridgeRange[0]);
  return { earthElDeg: Math.round(el * 20) / 20, ridgeHeightM: Math.round(rm * 2) / 2 };
}
