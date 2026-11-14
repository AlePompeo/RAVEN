// SPDX-License-Identifier: Apache-2.0
// Stato di Simula senza DOM: lettura/scrittura dell'URL (valori non fidati), preset a un tocco, missione guidata,
// frase "cosa significa" e testi degli indicatori. Tutte le stringhe visibili stanno in STR (chiavi stabili, i18n in
// arrivo). Learning e Avanzato usano gli stessi numeri: cambia solo cosa si vede e cosa finisce nell'URL.
import { DEFAULT_INPUT, RANGES, RATES_BPS, type FlagCode, type LinkInput, type LinkOutput, type LinkState, type RangeKey, type ValidityLevel } from './linkModel';

export const STR = {
  rate: (bps: number, format = fmt) => (bps >= 1e6 ? `${format(bps / 1e6, 0)} Mbps` : `${format(bps / 1e3, 0)} kbps`),
  sentence: {
    below: 'La Terra è sotto l’orizzonte: il segnale non può arrivare (qui il modello non vale).',
    open: (m: string, r: string) => `Il segnale arriva con ${m} dB di margine: puoi inviare ${r}.`,
    transition: (m: string, r: string) => `Il crinale copre la Terra ma il segnale arriva piegato con ${m} dB di margine: puoi inviare ${r}.`,
    blockedSome: (m: string, r: string, max: string) => `Mancano ${m} dB: a ${r} il segnale non basta, ma ${max} passano.`,
    blockedNone: (m: string) => `Il segnale non arriva: mancano ${m} dB anche a 10 kbps.`,
  },
  state: {
    open: { word: 'Aperto', symbol: '●' },
    transition: { word: 'Transizione', symbol: '◐' },
    blocked: { word: 'Bloccato', symbol: '✕' },
  } satisfies Record<LinkState, { word: string; symbol: string }>,
  validity: {
    reliable: { word: 'Affidabile', symbol: '✓', hint: 'il modello è dentro il suo campo di validità' },
    uncertain: { word: 'Incerto', symbol: '?', hint: 'il modello è ai bordi: prendi il numero con cautela' },
    outside: { word: 'Fuori modello', symbol: '⊘', hint: 'qui il modello non vale: il numero non è una previsione' },
  } satisfies Record<ValidityLevel, { word: string; symbol: string; hint: string }>,
  flag: {
    invalid_input: 'Un valore non era valido: è stato usato il predefinito.',
    earth_below_horizon: 'La Terra è sotto l’orizzonte (elevazione ≤ 0°): il modello non vale.',
    paraxial: 'Il crinale è molto ripido rispetto alla linea di vista (oltre 10°): l’approssimazione parassiale non vale bene.',
    nu_outside_table: 'Il punto è fuori dalla tabella split-step di confronto (ν fuori da −1,5…3): la banda di incertezza è saturata al bordo.',
    fresnel_oscillation: 'Oscillazioni di Fresnel (ν < −0,78): la correzione è incerta.',
    d1_outside_table: 'Il crinale è fuori da 500–8000 m (la tabella split-step è calcolata a 2000 m): la banda di incertezza è indicativa.',
    radius_unresolved: 'Il raggio della cresta non è risolto dal DEM a 20 m: correzione incerta.',
    reflection_beyond_ridge: 'Il punto di riflessione cade oltre il crinale: il multipath non è applicato.',
    correction_unavailable: 'Tabella split-step non disponibile: correzione ITU applicata senza confronto (incertezza pari alla correzione).',
  } satisfies Record<FlagCode, string>,
  flagOk: 'nessun problema',
  flagNa: 'non applicabile (raggio scelto a mano)',
  honesty:
    'Cosa non è modellato: un solo ostacolo; nessuna misura radio reale al polo Sud; regolite da letteratura; parametri radio illustrativi; cresta arrotondata da ITU-R P.526-9 (formula verificata, non misurata) con lo split-step come banda.',
  presets: {
    high: 'Terra alta',
    grazing: 'Terra radente',
    blocking: 'Crinale che blocca',
    small: 'Antenna piccola',
  },
  mission: {
    title: 'Missione guidata',
    done: 'fatto',
    todo: 'da fare',
    all: 'Missione completata: hai visto quando il segnale passa, quando si piega e quando si blocca.',
    steps: [
      { id: 'high', task: 'Metti la Terra alta nel cielo (almeno 5°).', expect: 'Il segnale passa diritto: indicatore verde.' },
      { id: 'low', task: 'Abbassa la Terra finché scende dietro il crinale (sotto 1° circa).', expect: 'Il crinale copre la Terra ma il segnale si piega e arriva: indicatore ambra.' },
      { id: 'ridge', task: 'Alza il crinale finché il segnale si blocca.', expect: 'Il crinale è troppo alto: indicatore rosso.' },
      { id: 'antenna', task: 'Ingrandisci l’antenna finché il segnale torna.', expect: 'Un’antenna più grande raccoglie più segnale: di nuovo ambra o verde.' },
      { id: 'rate', task: 'Chiedi più dati al secondo finché il link si blocca (se resta verde, rimpicciolisci un po’ l’antenna).', expect: 'Più dati al secondo chiedono più segnale: 10 volte i dati costano 10 dB.' },
    ],
  },
} as const;

export const fmt = (v: number, d = 1): string => (Object.is(Math.round(v * 10 ** d), -0) ? 0 : v).toFixed(d).replace('.', ',').replace(/^-/, '−');

/** UNA frase semplice sul risultato (Learning e Avanzato mostrano la stessa). */
type SentenceText = { [K in keyof typeof STR.sentence]: typeof STR.sentence[K] extends string ? string : typeof STR.sentence[K] };
export function sentence(o: LinkOutput, text: SentenceText = STR.sentence, format = fmt): string {
  if (o.input.earthElDeg <= 0) return text.below;
  const r = STR.rate(o.input.rateBps, format);
  if (o.state === 'blocked') {
    if (o.maxRateBps > 0) return text.blockedSome(format(-o.marginDb, 0), r, STR.rate(o.maxRateBps, format));
    return text.blockedNone(format(-o.marginByRateDb[0]!, 0));
  }
  const m = format(Math.max(0, o.marginDb), 0);
  return o.state === 'open' ? text.open(m, r) : text.transition(m, r);
}

/* -------------------------------------------------- preset -------------------------------------------------- */

export type PresetId = keyof typeof STR.presets;
/** Preset a un tocco: cambiano solo i controlli di Learning, il resto resta com'è. */
export const PRESETS: Record<PresetId, Partial<LinkInput>> = {
  high: { earthElDeg: 8, ridgeHeightM: 33, diameterM: 0.0861, rateBps: 1e5 },
  grazing: { earthElDeg: 0.85, ridgeHeightM: 33, diameterM: 0.0861, rateBps: 1e5 },
  blocking: { earthElDeg: 1, ridgeHeightM: 80, diameterM: 0.0861, rateBps: 1e5 },
  small: { earthElDeg: 0.9, ridgeHeightM: 33, diameterM: 0.03, rateBps: 3e6 },
};

/* -------------------------------------------------- missione -------------------------------------------------- */

export type StepId = (typeof STR.mission.steps)[number]['id'];
/** Controllo del passo: `o` = risultato corrente, `start` = ingressi quando il passo è diventato attivo. */
export const STEP_CHECK: Record<StepId, (o: LinkOutput, start: LinkInput) => boolean> = {
  high: (o) => o.input.earthElDeg >= 5 && o.state === 'open',
  low: (o) => o.state === 'transition',
  ridge: (o, s) => o.state === 'blocked' && o.blocksLos && (o.input.ridgeHeightM ?? 0) > (s.ridgeHeightM ?? 0),
  antenna: (o, s) => o.state !== 'blocked' && (o.input.diameterM ?? 0) > (s.diameterM ?? 0),
  rate: (o, s) => o.state === 'blocked' && o.input.rateBps > s.rateBps,
};
export interface Mission {
  done: number;
  start: LinkInput;
}
export const newMission = (input: LinkInput): Mission => ({ done: 0, start: structuredClone(input) });
/** Un passo alla volta, in ordine: se il passo attivo è soddisfatto avanza e fissa i nuovi ingressi di partenza. */
export function advanceMission(m: Mission, o: LinkOutput): Mission {
  const steps = STR.mission.steps;
  if (m.done >= steps.length) return m;
  const step = steps[m.done]!;
  if (!STEP_CHECK[step.id](o, m.start)) return m;
  return { done: m.done + 1, start: structuredClone(o.input) };
}

/* ---------------------------------------------------- URL ---------------------------------------------------- */

export interface SimQuery {
  input: Partial<LinkInput>;
  real: boolean;
  site: string | null;
}

/** Chiave dell'URL -> campo dell'ingresso (rate, station, site, t sono quelli dello scenario condiviso). */
const NUM_KEYS: readonly [string, RangeKey, (q: Partial<LinkInput>, v: number) => void][] = [
  ['ghz', 'frequencyGhz', (q, v) => (q.frequencyGhz = v)],
  ['el', 'earthElDeg', (q, v) => (q.earthElDeg = v)],
  ['rh', 'ridgeHeightM', (q, v) => (q.ridgeHeightM = v)],
  ['rd', 'ridgeDistanceM', (q, v) => (q.ridgeDistanceM = v)],
  ['rr', 'ridgeRadiusM', (q, v) => (q.ridgeRadiusM = v)],
  ['dia', 'diameterM', (q, v) => (q.diameterM = v)],
  ['eta', 'eta', (q, v) => (q.eta = v)],
  ['perr', 'pointingErrorDeg', (q, v) => (q.pointingErrorDeg = v)],
  ['ptx', 'txPowerDbw', (q, v) => (q.txPowerDbw = v)],
  ['tsys', 'tsysK', (q, v) => (q.tsysK = v)],
  ['ebn0', 'ebn0Db', (q, v) => (q.ebn0Db = v)],
  ['loss', 'miscLossDb', (q, v) => (q.miscLossDb = v)],
  ['dist', 'earthDistanceKm', (q, v) => (q.earthDistanceKm = v)],
  ['mast', 'mastM', (q, v) => (q.mastM = v)],
];
const MP_KEYS: readonly [string, RangeKey, keyof LinkInput['multipath']][] = [
  ['eps', 'epsReal', 'epsReal'],
  ['epsi', 'epsImag', 'epsImag'],
  ['sig', 'roughnessM', 'roughnessM'],
];
const NUM_RE = /^-?\d{1,6}(\.\d{1,6})?$/;
const SITE_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
export const SIM_KEYS: readonly string[] = [...NUM_KEYS.map((k) => k[0]), ...MP_KEYS.map((k) => k[0]), 'mp', 'corr', 'real'];

function numIn(raw: string | null, key: RangeKey): number | null {
  if (raw === null || raw.length > 14 || !NUM_RE.test(raw)) return null;
  const v = Number(raw);
  const [lo, hi] = RANGES[key];
  return Number.isFinite(v) && v >= lo && v <= hi ? v : null;
}

/** Legge lo stato di Simula da una query: ogni valore non valido o fuori intervallo è ignorato, senza eco. */
export function parseSimQuery(search: string): SimQuery {
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(search);
  } catch {
    return { input: {}, real: false, site: null };
  }
  const q: Partial<LinkInput> = {};
  for (const [k, r, set] of NUM_KEYS) {
    const v = numIn(p.get(k), r);
    if (v !== null) set(q, v);
  }
  const mp = { ...DEFAULT_INPUT.multipath };
  let mpTouched = false;
  for (const [k, r, f] of MP_KEYS) {
    const v = numIn(p.get(k), r);
    if (v !== null) {
      mp[f] = v as never;
      mpTouched = true;
    }
  }
  const mpOn = p.get('mp');
  if (mpOn === '1') {
    mp.enabled = true;
    mpTouched = true;
  }
  if (mpTouched) q.multipath = mp;
  if (p.get('corr') === '0') q.applyCorrection = false;
  const rate = p.get('rate');
  if (rate !== null && NUM_RE.test(rate.replace(/e\d+$/i, ''))) {
    const v = Number(rate);
    if (RATES_BPS.includes(v)) q.rateBps = v;
  }
  const st = p.get('station');
  if (st === 'dsn34' || st === 'dsn18') q.station = st;
  const site = p.get('site');
  return { input: q, real: p.get('real') === '1', site: site !== null && SITE_RE.test(site) ? site : null };
}

const short = (v: number) => String(Math.round(v * 1e6) / 1e6);

/**
 * Query di Simula: Avanzato scrive tutto ciò che differisce dal predefinito (link riproducibile); Learning tiene l'URL
 * pulito, con il solo sito reale se scelto. Gli altri parametri (tab, mode, t, ...) restano intatti.
 */
export function writeSimQuery(search: string, input: LinkInput, real: boolean, site: string | null, advanced: boolean): string {
  const p = new URLSearchParams(search);
  for (const k of SIM_KEYS) p.delete(k);
  if (real) {
    p.set('real', '1');
    if (site) p.set('site', site);
  }
  if (advanced) {
    const d = DEFAULT_INPUT as LinkInput;
    for (const [k, field] of NUM_KEYS) {
      const v = input[field as keyof LinkInput];
      if (typeof v === 'number' && v !== d[field as keyof LinkInput]) p.set(k, short(v));
    }
    for (const [k, , f] of MP_KEYS) if (input.multipath[f] !== d.multipath[f]) p.set(k, short(input.multipath[f] as number));
    if (input.multipath.enabled) p.set('mp', '1');
    if (!input.applyCorrection) p.set('corr', '0');
    if (input.rateBps !== d.rateBps) p.set('rate', String(input.rateBps));
    else p.delete('rate');
    if (input.station !== d.station) p.set('station', input.station);
    else p.delete('station');
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

/* ------------------------------------------------ esportazione ------------------------------------------------ */

export function exportJson(o: LinkOutput, extra: Record<string, unknown>): string {
  const { input, validity, ...out } = o;
  return JSON.stringify({ generator: 'RAVEN Simula (modello nel browser)', input, output: out, validity, ...extra }, null, 2);
}

/** CSV a due colonne (chiave, valore) con ingressi e uscite numeriche/testuali. */
export function exportCsv(o: LinkOutput): string {
  const rows: [string, unknown][] = [];
  const walk = (prefix: string, v: unknown) => {
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) for (const [k, x] of Object.entries(v)) walk(prefix ? `${prefix}.${k}` : k, x);
    else if (Array.isArray(v)) v.forEach((x, i) => walk(`${prefix}[${i}]`, x));
    else rows.push([prefix, v]);
  };
  walk('input', o.input);
  const { input: _i, validity, ...out } = o;
  walk('output', out);
  walk('validity.level', validity.level);
  validity.flags.forEach((f) => rows.push([`validity.${f.code}`, f.level]));
  const cell = (v: unknown) => {
    if (typeof v === 'number') return String(v);
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) || /^[=+\-@]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return ['key,value', ...rows.map(([k, v]) => `${cell(k)},${cell(v)}`)].join('\n') + '\n';
}
