// SPDX-License-Identifier: Apache-2.0
// ONE registry of the variables and formulas of the RAVEN engine, used by the report (part 3), the chart captions
// and the Model page. Names are the readable, translated names of the variables; the formulas are written as the
// engine computes them (backend/domain/raven/s3..s7, grazing/analysis.py link_series, grazing/diffraction.py,
// lunar/energy.py). Where the engine differs from the textbook, the formula states what the engine does.
// Numbers are NOT in the formulas: values for this run come from `variableValues`, a third small table.
import { rt, nf } from './reportText';
import type { RavenEvaluation, RavenValidation } from '../../shell/ravenApi';
import { earthVisibility } from './journey';
import { hoursText } from './reportCompare';

export type Origin = 'engine' | 'param' | 'formula' | 'constant';
/** Where the engine returns the variable: a metric, a step series, or a used parameter. null = not returned by the API. */
export type Field = { src: 'metrics' | 'steps' | 'rf' | 'energy' | 'scenario' | 'window'; key: string } | null;
export interface VarDef { unit: string; origin: Origin; field: Field; stage: string; value?: (e: RavenEvaluation) => string | null }

const f1 = (v: number, d = 1) => nf(v, { minimumFractionDigits: 0, maximumFractionDigits: d });
const known = (xs: readonly (number | null)[]) => xs.filter((v): v is number => v !== null && Number.isFinite(v));
const range = (xs: readonly (number | null)[], unit: string, d = 1) => {
  const k = known(xs);
  if (!k.length) return null;
  const lo = f1(Math.min(...k), d); const hi = f1(Math.max(...k), d);
  return lo === hi ? `${lo}${unit ? ` ${unit}` : ''}` : `${lo} … ${hi}${unit ? ` ${unit}` : ''}`;
};
/** Range of a series that older responses may not carry: absent or all unknown = null (a dash), never zero. */
const optRange = (e: RavenEvaluation, key: string, unit: string, d = 1) => {
  const s = (e.steps as unknown as Record<string, readonly (number | null)[] | undefined> | undefined)?.[key];
  return s ? range(s, unit, d) : null;
};
const param = (g: 'rf' | 'energy' | 'scenario', key: string, unit: string, d = 3) => (e: RavenEvaluation): string | null => {
  const v = (e.parameters_used?.[g] as Record<string, unknown> | undefined)?.[key];
  return typeof v === 'number' ? `${f1(v, d)}${unit ? ` ${unit}` : ''}` : typeof v === 'string' ? v : null;
};
const count = (xs: readonly (boolean | null)[]) => ({ yes: xs.filter((v) => v === true).length, unk: xs.filter((v) => v === null).length, n: xs.length });
const shareOf = (xs: readonly (boolean | null)[]) => { const c = count(xs); return c.n ? `${f1(c.yes / c.n * 100)}%${c.unk ? ` (${rt('unknownN', { n: f1(c.unk) })})` : ''}` : null; };
const meanRange = (e: RavenEvaluation) => { const k = known(e.steps?.earth_range_km ?? []); return k.length ? k.reduce((a, b) => a + b, 0) / k.length : null; };
const freqGhz = (e: RavenEvaluation) => { const v = e.parameters_used?.rf.frequency_ghz; return typeof v === 'number' ? v : null; };
const C = 299792458;
/** Free-space loss exactly as the engine: 20 log10(4 pi d f / c), d in metres. */
export const freeSpaceDb = (rangeKm: number, ghz: number) => 20 * Math.log10(4 * Math.PI * rangeKm * 1000 * ghz * 1e9 / C);
const n = (v: unknown) => (typeof v === 'number' ? v : NaN);

export const VARS = {
  useful_pct: { unit: '%', origin: 'formula', field: null, stage: 's7', value: (e) => `${f1(e.metrics.useful_hours / (e.window.n_steps * e.window.step_min / 60) * 100, 2)}%` },
  useful_hours_confirmed: { unit: 'h', origin: 'engine', field: { src: 'metrics', key: 'useful_hours' }, stage: 's7', value: (e) => `${hoursText(e.metrics.useful_hours)} h` },
  sampled_hours: { unit: 'h', origin: 'formula', field: null, stage: 's0', value: (e) => `${hoursText(e.window.n_steps * e.window.step_min / 60)} h` },
  n_steps: { unit: '', origin: 'engine', field: { src: 'metrics', key: 'n_steps' }, stage: 's0', value: (e) => String(e.metrics.n_steps) },
  step_min: { unit: 'min', origin: 'param', field: { src: 'window', key: 'step_min' }, stage: 's0', value: (e) => `${e.window.step_min} min` },
  unknown_hours: { unit: 'h', origin: 'engine', field: { src: 'metrics', key: 'unknown_hours' }, stage: 's7', value: (e) => `${hoursText(e.metrics.unknown_hours)} h` },
  useful_step: { unit: '', origin: 'engine', field: { src: 'steps', key: 'useful' }, stage: 's7', value: (e) => { const c = count(e.steps!.useful); return `${c.yes} / ${c.n}${c.unk ? ` (${rt('unknownN', { n: String(c.unk) })})` : ''}`; } },
  operational: { unit: '', origin: 'engine', field: { src: 'steps', key: 'state' }, stage: 's4', value: (e) => { const s = e.steps!.state; return `${s.filter((x) => x === 'operational').length} / ${s.length}`; } },
  link_margin_db: { unit: 'dB', origin: 'engine', field: { src: 'steps', key: 'margin_db' }, stage: 's5', value: (e) => range(e.steps!.margin_db, 'dB') },
  required_margin: { unit: 'dB', origin: 'param', field: { src: 'scenario', key: 'required_margin_db' }, stage: 's7', value: param('scenario', 'required_margin_db', 'dB') },
  dsn_visible: { unit: '', origin: 'engine', field: { src: 'steps', key: 'dsn_visible' }, stage: 's6', value: (e) => { const c = count(e.steps!.dsn_visible); return `${c.yes} / ${c.n}${c.unk ? ` (${rt('unknownN', { n: String(c.unk) })})` : ''}`; } },
  dsn_min_elevation: { unit: '°', origin: 'param', field: { src: 'scenario', key: 'dsn_min_elevation_deg' }, stage: 's6', value: param('scenario', 'dsn_min_elevation_deg', '°') },
  sun_share: { unit: '%', origin: 'formula', field: null, stage: 's3', value: (e) => shareOf(e.steps!.lit) },
  earth_share: { unit: '%', origin: 'formula', field: null, stage: 's2', value: (e) => shareOf(earthVisibility(e)) },
  rf_share: { unit: '%', origin: 'formula', field: null, stage: 's5', value: (e) => shareOf(e.steps!.rf_closes) },
  sun_lit: { unit: '', origin: 'engine', field: { src: 'steps', key: 'lit' }, stage: 's3' },
  visible_sun_disc_fraction: { unit: '0…1', origin: 'engine', field: { src: 'steps', key: 'disc_fraction' }, stage: 's3', value: (e) => range(e.steps!.disc_fraction, '', 2) },
  sun_elevation: { unit: '°', origin: 'engine', field: { src: 'steps', key: 'sun_el_deg' }, stage: 's1', value: (e) => range(e.steps!.sun_el_deg, '°') },
  sun_semidiameter: { unit: '°', origin: 'formula', field: null, stage: 's1', value: () => `${f1(Math.asin(695700 / 149597870.7) * 180 / Math.PI, 3)}° (${rt('at1au')})` },
  earth_elevation: { unit: '°', origin: 'engine', field: { src: 'steps', key: 'earth_el_deg' }, stage: 's1', value: (e) => range(e.steps!.earth_el_deg, '°') },
  terrain_horizon: { unit: '°', origin: 'engine', field: { src: 'steps', key: 'earth_horizon_deg' }, stage: 's2', value: (e) => range(e.steps!.earth_horizon_deg, '°') },
  earth_distance: { unit: 'km', origin: 'engine', field: { src: 'steps', key: 'earth_range_km' }, stage: 's1', value: (e) => range(e.steps!.earth_range_km, 'km', 0) },
  solar_irradiance: { unit: 'W/m²', origin: 'formula', field: null, stage: 's4' },
  sun_distance_au: { unit: 'AU', origin: 'engine', field: null, stage: 's1' },
  array_area: { unit: 'm²', origin: 'param', field: { src: 'energy', key: 'array_area_m2' }, stage: 's4', value: param('energy', 'array_area_m2', 'm²') },
  cell_efficiency: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'cell_efficiency' }, stage: 's4', value: param('energy', 'cell_efficiency', '') },
  packing_factor: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'packing_factor' }, stage: 's4', value: param('energy', 'packing_factor', '') },
  degradation: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'degradation_fraction' }, stage: 's4', value: param('energy', 'degradation_fraction', '') },
  cos_incidence: { unit: '0…1', origin: 'formula', field: null, stage: 's4', value: (e) => { const o = e.parameters_used?.energy.orientation; return typeof o === 'string' ? o : null; } },
  generation: { unit: 'W', origin: 'engine', field: { src: 'steps', key: 'gen_w' }, stage: 's4', value: (e) => range(e.steps!.gen_w, 'W') },
  battery_charge: { unit: '0…1', origin: 'engine', field: { src: 'steps', key: 'soc' }, stage: 's4', value: (e) => range(e.steps!.soc.map((v) => (v === null ? null : v * 100)), '%') },
  battery_capacity: { unit: 'Wh', origin: 'param', field: { src: 'energy', key: 'battery_capacity_wh' }, stage: 's4', value: param('energy', 'battery_capacity_wh', 'Wh') },
  reserve_threshold: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'min_soc' }, stage: 's4', value: param('energy', 'min_soc', '') },
  min_battery: { unit: '0…1', origin: 'engine', field: { src: 'metrics', key: 'min_soc' }, stage: 's4', value: (e) => (e.metrics.min_soc === null ? null : `${f1(e.metrics.min_soc * 100)}%`) },
  active_load: { unit: 'W', origin: 'param', field: { src: 'energy', key: 'active_load_w' }, stage: 's4', value: param('energy', 'active_load_w', 'W') },
  survival_load: { unit: 'W', origin: 'param', field: { src: 'energy', key: 'survival_load_w' }, stage: 's4', value: param('energy', 'survival_load_w', 'W') },
  comms_load: { unit: 'W', origin: 'formula', field: null, stage: 's4', value: (e) => { const p = e.parameters_used; return p ? `${f1(n(p.energy.comms_duty) * 10 ** (n(p.rf.tx_power_dbw) / 10) / n(p.energy.pa_efficiency))} W` : null; } },
  comms_duty: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'comms_duty' }, stage: 's4', value: param('energy', 'comms_duty', '') },
  pa_efficiency: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'pa_efficiency' }, stage: 's4', value: param('energy', 'pa_efficiency', '', 4) },
  charge_efficiency: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'charge_efficiency' }, stage: 's4', value: param('energy', 'charge_efficiency', '') },
  discharge_efficiency: { unit: '0…1', origin: 'param', field: { src: 'energy', key: 'discharge_efficiency' }, stage: 's4', value: param('energy', 'discharge_efficiency', '') },
  tx_power: { unit: 'dBW', origin: 'param', field: { src: 'rf', key: 'tx_power_dbw' }, stage: 's5', value: param('rf', 'tx_power_dbw', 'dBW') },
  tx_gain: { unit: 'dBi', origin: 'param', field: { src: 'rf', key: 'tx_gain_dbi' }, stage: 's5', value: param('rf', 'tx_gain_dbi', 'dBi') },
  station_gain: { unit: 'dBi', origin: 'param', field: { src: 'rf', key: 'station_gain_dbi' }, stage: 's5', value: param('rf', 'station_gain_dbi', 'dBi') },
  misc_loss: { unit: 'dB', origin: 'param', field: { src: 'rf', key: 'misc_loss_db' }, stage: 's5', value: param('rf', 'misc_loss_db', 'dB') },
  frequency: { unit: 'GHz', origin: 'param', field: { src: 'rf', key: 'frequency_ghz' }, stage: 's5', value: param('rf', 'frequency_ghz', 'GHz') },
  system_temp: { unit: 'K', origin: 'param', field: { src: 'rf', key: 'tsys_k' }, stage: 's5', value: param('rf', 'tsys_k', 'K') },
  ebn0_required: { unit: 'dB', origin: 'param', field: { src: 'rf', key: 'ebn0_db' }, stage: 's5', value: param('rf', 'ebn0_db', 'dB') },
  bit_rate: { unit: 'bit/s', origin: 'param', field: { src: 'rf', key: 'rate_bps' }, stage: 's5', value: param('rf', 'rate_bps', 'bit/s', 0) },
  noise_density: { unit: 'dBW/Hz', origin: 'formula', field: null, stage: 's5', value: (e) => { const T = e.parameters_used?.rf.tsys_k; return typeof T === 'number' ? `${f1(-228.599 + 10 * Math.log10(T), 2)} dBW/Hz` : null; } },
  free_space_loss_db: { unit: 'dB', origin: 'formula', field: { src: 'steps', key: 'free_space_loss_db' }, stage: 's5', value: (e) => { const m = meanRange(e); const g = freqGhz(e); return m === null || g === null ? null : `${f1(freeSpaceDb(m, g), 2)} dB (${rt('meanDistance')})`; } },
  pointing_loss: { unit: 'dB', origin: 'formula', field: null, stage: 's5', value: (e) => { const m = e.parameters_used?.rf.mount; const d = e.parameters_used?.rf.tracking_error_deg; return m === 'tracking' && d === 0 ? '0 dB (tracking error 0°)' : null; } },
  diffraction_loss: { unit: 'dB', origin: 'formula', field: { src: 'steps', key: 'diffraction_loss_db' }, stage: 's5', value: (e) => optRange(e, 'diffraction_loss_db', 'dB', 2) },
  knife_edge_loss: { unit: 'dB', origin: 'formula', field: { src: 'steps', key: 'knife_edge_loss_db' }, stage: 's5', value: (e) => optRange(e, 'knife_edge_loss_db', 'dB', 2) },
  ridge_correction: { unit: 'dB', origin: 'engine', field: { src: 'steps', key: 'ridge_correction_db' }, stage: 's5', value: (e) => optRange(e, 'ridge_correction_db', 'dB', 2) },
  nu: { unit: '', origin: 'formula', field: { src: 'steps', key: 'diffraction_nu' }, stage: 's5', value: (e) => optRange(e, 'diffraction_nu', '', 2) },
  ridge_height: { unit: 'm', origin: 'engine', field: null, stage: 's2' },
  dist_tx_ridge: { unit: 'm', origin: 'engine', field: null, stage: 's2' },
  dist_ridge_rx: { unit: 'm', origin: 'engine', field: null, stage: 's2' },
  wavelength: { unit: 'm', origin: 'formula', field: null, stage: 's5', value: (e) => { const g = freqGhz(e); return g === null ? null : `${f1(C / (g * 1e9), 4)} m`; } },
  multipath_gain: { unit: 'dB', origin: 'engine', field: { src: 'steps', key: 'multipath_gain_db' }, stage: 's5', value: (e) => optRange(e, 'multipath_gain_db', 'dB', 2) },
  fresnel_c: { unit: '', origin: 'constant', field: null, stage: 's5' },
  fresnel_s: { unit: '', origin: 'constant', field: null, stage: 's5' },
  battery_energy: { unit: 'Wh', origin: 'formula', field: null, stage: 's4' },
  reserve_energy: { unit: 'Wh', origin: 'formula', field: null, stage: 's4', value: (e) => { const p = e.parameters_used?.energy; return p ? `${f1(n(p.min_soc) * n(p.battery_capacity_wh))} Wh` : null; } },
  load: { unit: 'W', origin: 'formula', field: null, stage: 's4' },
  surplus: { unit: 'Wh', origin: 'formula', field: null, stage: 's4' },
  deficit: { unit: 'Wh', origin: 'formula', field: null, stage: 's4' },
  hazard: { unit: '1/h', origin: 'formula', field: null, stage: 'rel' },
  permanent_rate: { unit: '1/h', origin: 'param', field: null, stage: 'rel' },
  upset_rate: { unit: '1/h', origin: 'param', field: null, stage: 'rel' },
  recovery_prob: { unit: '0…1', origin: 'param', field: null, stage: 'rel' },
  recovery_mean: { unit: 'h', origin: 'param', field: null, stage: 'rel' },
  availability: { unit: '0…1', origin: 'formula', field: null, stage: 'rel' },
  dose: { unit: 'krad(Si)', origin: 'formula', field: null, stage: 'rel' },
} as const satisfies Record<string, VarDef>;
export type VarId = keyof typeof VARS;
export const varIds = Object.keys(VARS) as VarId[];

/** Translated name of a variable: the one name used in formulas, legends and captions. */
export const varName = (id: VarId): string => id;
export const varMeaning = (id: VarId): string => rt(`varw.${id}`);

export interface FormulaDef {
  id: string;
  /** Lines with {variable_id} placeholders; compound definitions are separate lines, nested ones on the next. */
  lines: string[];
  /** Variables of the legend (every placeholder of the lines, plus any explained extra). */
  vars: VarId[];
  /** Validation stage ids whose status the chip shows. */
  stages: string[];
  /** Tag of the method: V verified source, D derived, I design choice or illustrative. */
  tag: 'V' | 'D' | 'I';
  appendix?: 'reliability';
  /** Compact version for the Learn report (the main formulas on one page): indexes of the lines kept and the variables explained. */
  learn?: { lines: number[]; vars: VarId[] };
}

export const FORMULAS: FormulaDef[] = [
  { id: 'useful', tag: 'I', stages: ['s7'], learn: { lines: [0], vars: ['useful_pct', 'useful_hours_confirmed', 'sampled_hours'] }, vars: ['useful_pct', 'useful_hours_confirmed', 'sampled_hours', 'n_steps', 'step_min', 'useful_step', 'unknown_hours'],
    lines: ['{useful_pct} = {useful_hours_confirmed} ÷ {sampled_hours} × 100', '{sampled_hours} = {n_steps} × {step_min} ÷ 60',
      '{useful_hours_confirmed} = Σ {useful_step} × {step_min} ÷ 60', '{unknown_hours} = Σ <<unknownStep>> × {step_min} ÷ 60'] },
  { id: 'step', tag: 'I', stages: ['s4', 's5', 's6', 's7'], learn: { lines: [0, 1], vars: ['useful_step', 'operational', 'link_margin_db', 'required_margin', 'dsn_visible', 'generation', 'active_load', 'battery_charge', 'reserve_threshold'] }, vars: ['useful_step', 'operational', 'link_margin_db', 'required_margin', 'dsn_visible', 'dsn_min_elevation', 'generation', 'active_load', 'battery_charge', 'reserve_threshold'],
    lines: ['{useful_step} = {operational} <<and>> ({link_margin_db} ≥ {required_margin}) <<and>> {dsn_visible}',
      '{operational} = ({generation} ≥ {active_load}) <<or>> ({battery_charge} > {reserve_threshold})', '{dsn_visible} = <<moonEl>> ≥ {dsn_min_elevation} <<atOneDsn>>'] },
  { id: 'unknown', tag: 'I', stages: ['s2', 's4', 's5', 's7'], vars: ['useful_step', 'link_margin_db', 'battery_charge', 'unknown_hours'],
    lines: ['<<unkLogic>>', '{link_margin_db} = <<unkRf>>',
      '{battery_charge} = <<unkBattery>>'] },
  { id: 'shares', tag: 'D', stages: ['s1', 's2', 's3', 's5'], learn: { lines: [0, 1, 2, 3], vars: ['sun_share', 'earth_share', 'rf_share', 'sun_lit', 'earth_elevation', 'terrain_horizon', 'visible_sun_disc_fraction', 'n_steps', 'link_margin_db'] }, vars: ['sun_share', 'earth_share', 'rf_share', 'sun_lit', 'earth_elevation', 'terrain_horizon', 'link_margin_db', 'visible_sun_disc_fraction', 'n_steps'],
    lines: ['{sun_share} = <<stepsWith>> {sun_lit} ÷ {n_steps} × 100', '{sun_lit} = ({visible_sun_disc_fraction} > 0)',
      '{earth_share} = <<stepsWith>> ({earth_elevation} > {terrain_horizon}) ÷ {n_steps} × 100', '{rf_share} = <<stepsWith>> ({link_margin_db} ≥ 0) ÷ {n_steps} × 100'] },
  { id: 'disc', tag: 'D', stages: ['s1', 's2', 's3'], vars: ['visible_sun_disc_fraction', 'sun_elevation', 'sun_semidiameter', 'terrain_horizon'],
    lines: ['{visible_sun_disc_fraction} = <<discArea>>', '{sun_semidiameter} = asin(<<rSun>> ÷ <<sunDist>>)',
      '<<discNote>>'] },
  { id: 'power', tag: 'I', stages: ['s4'], vars: ['generation', 'solar_irradiance', 'sun_distance_au', 'array_area', 'cell_efficiency', 'packing_factor', 'degradation', 'cos_incidence', 'visible_sun_disc_fraction'],
    lines: ['{generation} = {solar_irradiance} × {array_area} × {cell_efficiency} × {packing_factor} × (1 − {degradation}) × {cos_incidence} × {visible_sun_disc_fraction}',
      '{solar_irradiance} = 1360.8 ÷ {sun_distance_au}²'] },
  { id: 'battery', tag: 'I', stages: ['s4'], learn: { lines: [2, 3, 4], vars: ['battery_charge', 'battery_energy', 'battery_capacity', 'step_min', 'load', 'surplus', 'deficit', 'generation', 'charge_efficiency', 'discharge_efficiency', 'min_battery'] }, vars: ['battery_charge', 'step_min', 'battery_energy', 'battery_capacity', 'reserve_threshold', 'reserve_energy', 'load', 'active_load', 'survival_load', 'comms_load', 'comms_duty', 'tx_power', 'pa_efficiency', 'charge_efficiency', 'discharge_efficiency', 'surplus', 'deficit', 'generation', 'min_battery'],
    lines: ['{comms_load} = {comms_duty} × 10^({tx_power} ÷ 10) ÷ {pa_efficiency}', '{reserve_energy} = {reserve_threshold} × {battery_capacity}',
      '{surplus} = ({generation} − min({generation}, {load})) × {step_min}/60;  {battery_energy} += min({surplus} × {charge_efficiency}, {battery_capacity} − {battery_energy})',
      '{deficit} = ({load} − min({generation}, {load})) × {step_min}/60;  {battery_energy} −= min({deficit} ÷ {discharge_efficiency}, {battery_energy})',
      '{battery_charge} = {battery_energy} ÷ {battery_capacity};  {min_battery} = min({battery_charge}) <<overKnown>>'] },
  { id: 'fspl', tag: 'V', stages: ['s5'], learn: { lines: [0, 1], vars: ['free_space_loss_db', 'earth_distance', 'frequency'] }, vars: ['free_space_loss_db', 'earth_distance', 'frequency', 'wavelength'],
    lines: ['{free_space_loss_db} = 20 · log10(4π · {earth_distance} · {frequency} ÷ c)', '<<fsplNote>>'] },
  { id: 'margin', tag: 'D', stages: ['s5'], learn: { lines: [0, 1, 2], vars: ['link_margin_db', 'tx_power', 'tx_gain', 'station_gain', 'misc_loss', 'pointing_loss', 'free_space_loss_db', 'diffraction_loss', 'multipath_gain', 'noise_density', 'system_temp', 'ebn0_required', 'bit_rate'] }, vars: ['link_margin_db', 'tx_power', 'tx_gain', 'station_gain', 'misc_loss', 'pointing_loss', 'free_space_loss_db', 'diffraction_loss', 'multipath_gain', 'noise_density', 'system_temp', 'ebn0_required', 'bit_rate'],
    lines: ['{link_margin_db} = {tx_power} + {tx_gain} + {station_gain} − {misc_loss} − {pointing_loss} − {free_space_loss_db} − {diffraction_loss} + {multipath_gain} − {noise_density} − {ebn0_required} − 10 · log10({bit_rate})',
      '{noise_density} = −228.6 + 10 · log10({system_temp})', '<<rxMinusReq>>;  <<closesWhen>> {link_margin_db} ≥ 0'] },
  { id: 'diffraction', tag: 'V', stages: ['s2', 's5'], vars: ['diffraction_loss', 'knife_edge_loss', 'ridge_correction', 'nu', 'ridge_height', 'dist_tx_ridge', 'dist_ridge_rx', 'wavelength', 'fresnel_c', 'fresnel_s'],
    lines: ['{diffraction_loss} = {knife_edge_loss} + {ridge_correction}', '{nu} = {ridge_height} · √(2 · ({dist_tx_ridge} + {dist_ridge_rx}) ÷ ({wavelength} · {dist_tx_ridge} · {dist_ridge_rx}))',
      '{knife_edge_loss} = −20 · log10 | (1 + j)/2 · ((½ − {fresnel_c}({nu})) − j · (½ − {fresnel_s}({nu}))) |',
      '<<ituCheck>>: 6.9 + 20 · log10(√(({nu} − 0.1)² + 1) + {nu} − 0.1), <<for>> {nu} > −0.78',
      '{ridge_correction} = <<ridgeTable>>'] },
  { id: 'reliability', tag: 'I', stages: ['rel'], appendix: 'reliability', vars: ['hazard', 'permanent_rate', 'upset_rate', 'recovery_prob', 'recovery_mean', 'availability', 'dose'],
    lines: ['{hazard} = {permanent_rate} + {upset_rate} · (1 − {recovery_prob})', '{availability}(t) = μ ÷ (k + μ) + k ÷ (k + μ) · e^(−(k + μ) · t);  k = {upset_rate} · {recovery_prob};  μ = 1 ÷ {recovery_mean}',
      '{dose} = <<doseRhs>>'] },
];

/** Short symbolic captions under the charts: names only, no numbers. */
export const CHART_FORMULAS = {
  sun: ['{sun_lit} = ({visible_sun_disc_fraction} > 0)'],
  earth: ['<<earthVisible>> = ({earth_elevation} > {terrain_horizon})'],
  rf: ['{link_margin_db} = <<rxMinusReq>>'],
  battery: ['{battery_charge} = {battery_energy} ÷ {battery_capacity}'],
  cum: ['{useful_hours_confirmed}(t) = {step_min} · (<<stepsWith>> {useful_step} up to t)'],
} as const satisfies Record<string, string[]>;

export interface Piece { kind: 'var' | 'text'; text: string; id?: VarId }
const PLACEHOLDER = /\{([a-z0-9_]+)\}|<<([A-Za-z]+)>>/g;
/** Placeholders used in a line, in order. */
export const placeholders = (line: string): string[] => Array.from(line.matchAll(PLACEHOLDER), (m) => m[1]).filter((x): x is string => !!x);
/** Words of a line (<<key>> tokens), translated from the catalog. */
export const wordTokens = (line: string): string[] => Array.from(line.matchAll(PLACEHOLDER), (m) => m[2]).filter((x): x is string => !!x);
/** A line as pieces: variable names (translated) and plain text, so the page can style the names. */
export function pieces(line: string): Piece[] {
  const out: Piece[] = [];
  let last = 0;
  for (const m of line.matchAll(PLACEHOLDER)) {
    if (m.index > last) out.push({ kind: 'text', text: line.slice(last, m.index) });
    if (m[2]) out.push({ kind: 'text', text: rt(`fw.${m[2]}`) });
    else {
      const id = m[1] as VarId;
      out.push({ kind: 'var', id, text: id in VARS ? varName(id) : m[1]! });
    }
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ kind: 'text', text: line.slice(last) });
  return out;
}
export const plainLine = (line: string) => pieces(line).map((p) => p.text).join('');

/** Weakest validation status of the entries of the given stages (verified > plausibility_only > not_validated > unknown). */
export function stageStatus(validation: { stages: readonly unknown[] } | null, stages: readonly string[]): 'verified' | 'plausible' | 'notvalidated' | 'unknown' {
  if (!validation) return 'unknown';
  const order = ['verified', 'plausibility_only', 'not_validated', 'unknown'];
  let worst = -1;
  for (const e of validation.stages as readonly { stage?: string; status?: string }[]) {
    if (!e.stage || !stages.includes(e.stage)) continue;
    worst = Math.max(worst, order.indexOf(e.status ?? 'unknown'));
  }
  return worst < 0 ? 'unknown' : (['verified', 'plausible', 'notvalidated', 'unknown'] as const)[worst]!;
}

/** Value of a variable for one site in this run, or null when the API does not return it (shown as a dash). */
export function variableValue(id: VarId, e: RavenEvaluation): string | null {
  const v = (VARS[id] as VarDef).value;
  try { return v ? v(e) : null; } catch { return null; }
}
