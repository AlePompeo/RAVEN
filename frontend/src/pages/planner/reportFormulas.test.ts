// SPDX-License-Identifier: Apache-2.0
// The registry of variables and formulas is the single source of the report (part 3, chart captions, Model page):
// every variable used in a formula is defined and explained, and the engine fields it names exist in a real response.
import { describe, expect, it } from 'vitest';
import { CHART_FORMULAS, FORMULAS, VARS, freeSpaceDb, placeholders, pieces, plainLine, stageStatus, variableValue, wordTokens, type VarId } from './reportFormulas';
import { EN, rt } from './reportText';
import { siteA } from './reportFixtures';
import type { RavenValidation } from '../../shell/ravenApi';

const OPTIONAL_SERIES = ['free_space_loss_db', 'diffraction_nu', 'knife_edge_loss_db', 'ridge_correction_db', 'diffraction_loss_db', 'multipath_gain_db'];
const lines = [...FORMULAS.flatMap((f) => f.lines), ...Object.values(CHART_FORMULAS).flat()];

describe('formula registry', () => {
  it('defines in the legend every variable used in a formula, and explains it in words', () => {
    for (const f of FORMULAS) {
      expect(`f.${f.id}` in EN, f.id).toBe(true);
      for (const line of f.lines) for (const id of placeholders(line)) {
        expect(id in VARS, `${f.id}: ${id}`).toBe(true);
        expect(f.vars, `${f.id}: ${id} missing from its legend`).toContain(id);
      }
      for (const v of f.vars) expect(`varw.${v}` in EN, `meaning of ${v}`).toBe(true);
    }
    for (const line of Object.values(CHART_FORMULAS).flat()) for (const id of placeholders(line)) expect(id in VARS, id).toBe(true);
    for (const line of lines) for (const w of wordTokens(line)) expect(`fw.${w}` in EN, w).toBe(true);
  });

  it('has a compact Learn version of the six main formulas that still defines every variable it uses', () => {
    const learn = FORMULAS.filter((f) => f.learn);
    expect(learn.map((f) => f.id)).toEqual(['useful', 'step', 'shares', 'battery', 'fspl', 'margin']);
    for (const f of learn) {
      for (const i of f.learn!.lines) {
        expect(f.lines[i], `${f.id} line ${i}`).toBeDefined();
        for (const id of placeholders(f.lines[i]!)) expect(f.learn!.vars, `${f.id}: ${id} missing from the Learn legend`).toContain(id);
      }
      for (const v of f.learn!.vars) expect(f.vars).toContain(v);
    }
  });

  it('keeps one readable English snake_case name per variable and uses every variable somewhere', () => {
    const used = new Set(FORMULAS.flatMap((f) => f.vars));
    for (const id of Object.keys(VARS)) {
      expect(id).toMatch(/^[a-z][a-z0-9_]*$/);
      expect(used.has(id as VarId), `${id} is never used`).toBe(true);
      expect(rt(`varw.${id}`)).not.toBe(`varw.${id}`);
    }
    expect(Object.keys(VARS)).toEqual(expect.arrayContaining(['useful_hours_confirmed', 'sampled_hours', 'link_margin_db', 'free_space_loss_db', 'visible_sun_disc_fraction', 'battery_charge', 'reserve_threshold']));
    expect(plainLine('{useful_pct} = {useful_hours_confirmed} ÷ {sampled_hours} × 100')).toBe('useful_pct = useful_hours_confirmed ÷ sampled_hours × 100');
  });

  it('matches the fields the engine really returns', () => {
    const e = siteA as unknown as { metrics: Record<string, unknown>; steps: Record<string, unknown>; window: Record<string, unknown>; parameters_used: Record<string, Record<string, unknown>> };
    for (const [id, def] of Object.entries(VARS)) {
      const f = (def as { field: { src: string; key: string } | null }).field;
      if (!f || (f.src === 'steps' && OPTIONAL_SERIES.includes(f.key))) continue; // optional series: absent in older responses (a dash)
      const holder = f.src === 'metrics' ? e.metrics : f.src === 'steps' ? e.steps : f.src === 'window' ? e.window : e.parameters_used[f.src];
      expect(holder && f.key in holder, `${id} -> ${f.src}.${f.key}`).toBe(true);
    }
  });

  it('writes the compound definitions the engine uses, with the real thresholds', () => {
    const text = FORMULAS.find((f) => f.id === 'step')!.lines.map(plainLine).join(' | ');
    expect(text).toContain('useful_step = operational AND (link_margin_db ≥ required_margin) AND dsn_visible');
    expect(text).toContain('operational = (generation ≥ active_load) OR (battery_charge > reserve_threshold)');
    expect(FORMULAS.find((f) => f.id === 'margin')!.lines.map(plainLine).join(' ')).toContain('− 10 · log10(bit_rate)');
    expect(variableValue('required_margin', siteA)).toBe('3 dB');
    expect(variableValue('dsn_min_elevation', siteA)).toBe('6 °');
  });

  it('computes the values of the run from its data, never invents one', () => {
    expect(freeSpaceDb(384400, 8.425)).toBeCloseTo(222.65, 1);
    expect(variableValue('noise_density', siteA)).toBe('-214.42 dBW/Hz');
    expect(variableValue('sampled_hours', siteA)).toBe('24 h');
    expect(variableValue('useful_pct', siteA)).toBe('100%');
    expect(variableValue('nu', siteA)).toBeNull(); // the API does not return nu: a dash, not a number
    expect(variableValue('multipath_gain', siteA)).toBeNull();
  });

  it('fills the diffraction terms from the steps the API returns, and stays a dash when it does not', () => {
    const withTerms = { ...siteA, steps: { ...siteA.steps!, diffraction_nu: [0.5, 1.25, null], knife_edge_loss_db: [6.1, 9.5, null],
      ridge_correction_db: [0.25, 0.5, null], diffraction_loss_db: [6.35, 10, null] } } as unknown as typeof siteA;
    expect(variableValue('nu', withTerms)).toBe('0.5 … 1.25');
    expect(variableValue('knife_edge_loss', withTerms)).toBe('6.1 … 9.5 dB');
    expect(variableValue('ridge_correction', withTerms)).toBe('0.25 … 0.5 dB');
    expect(variableValue('diffraction_loss', withTerms)).toBe('6.35 … 10 dB');
    expect(variableValue('diffraction_loss', siteA)).toBeNull();
  });

  it('shows the formula first and the names as variables', () => {
    const p = pieces('{useful_pct} = {sampled_hours} × 2');
    expect(p.filter((x) => x.kind === 'var').map((x) => x.text)).toEqual(['useful_pct', 'sampled_hours']);
  });

  it('takes the weakest validation status of the stages, and Unknown when there is none', () => {
    const v = { stages: [{ stage: 's5', status: 'verified' }, { stage: 's5', status: 'not_validated' }, { stage: 's3', status: 'plausibility_only' }] } as unknown as RavenValidation;
    expect(stageStatus(v, ['s5'])).toBe('notvalidated');
    expect(stageStatus(v, ['s3'])).toBe('plausible');
    expect(stageStatus(v, ['s9'])).toBe('unknown');
    expect(stageStatus(null, ['s5'])).toBe('unknown');
  });
});
