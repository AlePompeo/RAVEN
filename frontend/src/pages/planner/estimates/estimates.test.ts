// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useCatalog } from '../../../i18n/i18n.svelte';
import en from '../../../i18n/en.pages.json';
import itCatalog from '../../../i18n/it.json';
import evaluationFixture from '../../../shell/fixtures/raven/evaluate.json';
import type { RavenEvaluation, RavenValidation } from '../../../shell/ravenApi';
import { defaultObjectives } from '../objectives';
import { newReportPlanning } from '../reportPlanning';
import { reportCompletion } from '../reportCompletion';
import type { JourneyDraft } from '../journey';
import { RADIO_PRESETS } from '../setup';
import { acceptedFor, defaultMassDefaults, generateEstimates, mergeEstimates, readEstimates, readMassDefaults, setEstimateStatus,
  type EngineEstimate } from './index';
import { estimateLines } from './render';
import { milestone } from './calendar';
import { topRisks } from './risks';
import { requirementsOf } from './requirements';
import { launchCo2T, MISSION_CLASS_IDS, NO_SOURCE_CHECKLIST, type MissionClassId } from './missionClass';
import { co2Totals, costTotals } from './totals';
import type { BudgetEstimate, CarbonEstimate } from '../reportPlanning';

const base = () => structuredClone(evaluationFixture) as unknown as RavenEvaluation;
/** Scenario A: Malapert, fully known. Scenario B: Haworth, the last two samples unknown (RF outside the model), battery known only for a prefix. */
function standard(): RavenEvaluation[] {
  const a = base();
  const b = base();
  b.site = { ...b.site, id: 'haworth', name: 'Haworth' };
  b.window = { start_utc: '2027-05-16T00:00:00Z', step_min: 360, n_steps: 4 };
  b.metrics = { ...b.metrics, known_steps: 2, unknown_steps: 2, unknown_hours: 12, useful_hours: 12, min_soc_scope: 'known prefix',
    state_hours: { operational: 12, comms_only: 0, survival: 0, dark: 0, unknown: 12 } };
  b.inputs_state = { ...b.inputs_state, rf_reason_counts: { ok: 2, outside_model: 2 } };
  const steps = b.steps!;
  steps.state = ['operational', 'operational', 'unknown', 'unknown'];
  steps.useful = [true, true, null, null];
  steps.margin_db = [21.6, 22.6, null, null];
  steps.rf_closes = [true, true, null, null];
  steps.time_unix = [1810425600, 1810447200, 1810468800, 1810490400];
  return [a, b];
}
const validation = {
  model_version: 'raven-core-1.4', statuses: [], note: '',
  stages: [{ id: 's2.terrain', stage: 's2', status: 'not_validated' }, { id: 's0.coordinates', stage: 's0', status: 'verified' },
    { id: 's5.link', stage: 's5', status: 'plausibility_only' }],
  parameter_groups: [],
} as unknown as RavenValidation;
const objectives = { priority: 'balanced' as const, minSunPercent: 50, minRfPercent: 90 };
const AT = '2027-01-01T00:00:00.000Z';
const ctx = (over = {}) => ({ evaluations: standard(), objectives, validation, producedAt: AT, ...over });
const byId = (list: EngineEstimate[], id: string) => list.find((e) => e.id === id)!;

beforeEach(() => useCatalog('en', en, en));
afterEach(() => useCatalog('it', itCatalog, en));

describe('step 1: the few risks that matter', () => {
  it('merges A and B into at most five plain rows, ordered by severity, with a consequence and a next action', () => {
    const risks = topRisks(standard());
    expect(risks.length).toBeGreaterThan(0);
    expect(risks.length).toBeLessThanOrEqual(5);
    const unknown = risks.find((r) => r.kind === 'unknown')!;
    expect(unknown.what).toContain('B for 12 h');
    expect(unknown.what).toContain('unknown, not zero');
    for (const r of risks) { expect(r.consequence.length).toBeGreaterThan(10); expect(r.action.length).toBeGreaterThan(10); }
    const order = risks.map((r) => (r.severity === 'high' ? 0 : 1));
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(JSON.stringify(risks)).not.toMatch(/evaluations\[|inputs_state|\.metrics\./); // no internal field paths
  });
  it('reports far terrain, survival and blackout with the real hours, and keeps the example numbers', () => {
    const b = base();
    b.window = { start_utc: '2027-04-07T00:00:00Z', step_min: 60, n_steps: 168 };
    b.inputs_state.rf_reason_counts = { ok: 63, blocked_far_terrain: 105 };
    const a = base();
    a.window = { ...b.window };
    a.metrics.state_hours = { ...a.metrics.state_hours, survival: 33 };
    const risks = topRisks([a, b]);
    expect(risks.find((r) => r.kind === 'blocked')!.what).toBe('Far terrain blocks the radio link: B for 105 of 168 h.');
    expect(risks.find((r) => r.kind === 'survival')!.what).toBe('Survival mode or no power: A 33 h in survival mode.');
    expect(risks[0]!.kind).toBe('blocked'); // 62 percent of the window is the largest share
  });
  it('severity follows the share of the window: high from 25 percent, medium below', () => {
    const e = base();
    e.metrics.unknown_hours = 6;
    expect(topRisks([e])[0]!.severity).toBe('high');
    e.metrics.unknown_hours = 5;
    expect(topRisks([e])[0]!.severity).toBe('medium');
  });
  it('a blackout is high, a custom terrain medium, and when nothing fires there is no row (not a claim of no risk)', () => {
    const e = base();
    expect(topRisks([e])).toEqual([]);
    e.metrics.time_to_first_blackout_h = 12;
    e.terrain = { state: 'known', reason: 'ok', products: [], resolution_m: 120, horizon_range_km: 20, custom: true };
    const risks = topRisks([e]);
    expect(risks.map((r) => [r.kind, r.severity])).toEqual([['blackout', 'high'], ['custom', 'medium']]);
    expect(risks[1]!.what).toContain('120 m');
  });
  it('never more than five rows', () => {
    const e = base();
    e.inputs_state.rf_reason_counts = { ok: 1, blocked_far_terrain: 3 };
    e.metrics.unknown_hours = 3; e.metrics.state_hours = { ...e.metrics.state_hours, survival: 2, dark: 1 };
    e.metrics.time_to_first_blackout_h = 5;
    e.terrain = { state: 'known', reason: 'ok', products: [], resolution_m: 120, horizon_range_km: 20, custom: true };
    expect(topRisks([e, e]).length).toBeLessThanOrEqual(5);
  });
});

describe('step 2: requirements and verification matrix', () => {
  it('compares each threshold with the evaluated value and never turns an unknown into met', () => {
    const [a, b] = standard();
    const ra = requirementsOf(a!, 0, objectives);
    expect(ra.find((r) => r.id === 'REQ-SUN-A')).toMatchObject({ threshold: 50, evaluated: 0, status: 'not_met' });
    expect(ra.find((r) => r.id === 'REQ-RF-A')).toMatchObject({ threshold: 90, evaluated: 100, status: 'met' });
    expect(ra.find((r) => r.id === 'REQ-MARGIN-A')).toMatchObject({ threshold: 3, status: 'met' });
    expect(ra.find((r) => r.id === 'REQ-BATT-A')).toMatchObject({ threshold: 20, status: 'met' });
    expect(ra.find((r) => r.id === 'REQ-USEFUL-A')).toMatchObject({ threshold: null, evaluated: 24, status: 'unknown' });
    const rb = requirementsOf(b!, 1, objectives);
    expect(rb.find((r) => r.id === 'REQ-RF-B')).toMatchObject({ evaluated: null, status: 'unknown' });
    expect(rb.find((r) => r.id === 'REQ-MARGIN-B')).toMatchObject({ status: 'unknown' });
    expect(rb.find((r) => r.id === 'REQ-BATT-B')).toMatchObject({ status: 'unknown', note: 'scope: known prefix' });
  });
  it('a known failure wins over unknown samples; thresholds not set give no row', () => {
    const [, b] = standard();
    b!.steps!.margin_db = [1, 22.6, null, null];
    expect(requirementsOf(b!, 1, objectives).find((r) => r.metric === 'margin')!.status).toBe('not_met');
    expect(requirementsOf(b!, 1, defaultObjectives()).map((r) => r.metric)).toEqual(['useful', 'battery', 'margin']);
  });
  it('derives the verification plan and the AIT plan from the matrix with a fixed template', () => {
    const list = generateEstimates(ctx());
    const matrix = byId(list, 'est.requirements'), plan = byId(list, 'est.verification_plan'), ait = byId(list, 'est.ait_plan');
    expect(plan.items.length).toBe(matrix.items.length * 2);
    expect(plan.items.every((i) => matrix.items.some((m) => m.id === i.cells.requirement))).toBe(true);
    expect(plan.items.every((i) => (i.cells.status as { key: string }).key === 'est.vp.notPerformed')).toBe(true);
    expect(ait.items[0]!.cells.step).toMatchObject({ key: 'est.ait.baseline', params: { scenario: 'A', area: 1, capacity: 10000, gain: 15, rate: 100000 } });
    expect(String(ait.items.find((i) => (i.cells.step as { key: string }).key === 'est.ait.functional')!.cells.requirement)).toContain('REQ-SUN-A');
  });
});

describe('step 3: operational calendar', () => {
  it('reads milestones from the evaluated series, and keeps unknown separate from none', () => {
    const [a, b] = standard();
    expect(milestone(a!, 'first_useful')).toBe('2027-01-01T00:00Z');
    expect(milestone(a!, 'first_sunlit')).toBe('none');
    expect(milestone(a!, 'first_unknown')).toBe('none');
    expect(milestone(b!, 'first_unknown')).toBe('2027-05-16T12:00Z');
    expect(milestone(b!, 'last_useful')).toBeNull();
    expect(milestone(b!, 'first_blackout')).toBeNull();
  });
  it('lists window start, end, duration and never invents a development or launch date', () => {
    const cal = byId(generateEstimates(ctx()), 'est.calendar');
    const row = (id: string) => cal.items.find((i) => i.id === id)!.cells;
    expect(row('CAL-A-01')).toMatchObject({ time: '2027-01-01T00:00Z' });
    expect(row('CAL-A-02')).toMatchObject({ time: '2027-01-02T00:00Z' });
    expect(row('CAL-A-03')).toMatchObject({ time: '24 h; 4 × 360 min' });
    expect(row('CAL-USER')).toMatchObject({ time: null });
    expect(cal.field).toBe('schedule');
  });
});

describe('step 4: power and mass', () => {
  it('the power budget uses only existing numbers', () => {
    const power = byId(generateEstimates(ctx()), 'est.power');
    const cell = (id: string) => power.items.find((i) => i.id === id)!.cells;
    expect(cell('PWR-A-01')).toMatchObject({ value: '10 W' });
    expect(cell('PWR-A-02')).toMatchObject({ value: '50 W' });
    expect(cell('PWR-A-06')).toMatchObject({ value: '10000 Wh' });
    expect(cell('PWR-A-07')).toMatchObject({ value: '8000 Wh' });
    expect(cell('PWR-A-08')).toMatchObject({ value: '800 h' });
    expect(power.tag).toBe('D');
  });
  it('mass is estimated automatically with the declared tag-I defaults, and not when the user switches them off', () => {
    expect(generateEstimates(ctx()).some((e) => e.id.startsWith('est.mass'))).toBe(true);
    const d = defaultMassDefaults();
    expect(generateEstimates(ctx({ massDefaults: { ...d, applied: false } })).some((e) => e.id.startsWith('est.mass'))).toBe(false);
    const mass = byId(generateEstimates(ctx({ massDefaults: { ...d, applied: true } })), 'est.mass.A');
    expect(mass.tag).toBe('I');
    // min (1.5 + 10000/200) / (1 - .03 - .15); typ (3 + 10000/150) / .75; max (6 + 10000/100) / (1 - .08 - .3)
    expect(mass.range).toEqual({ unit: 'kg', min: 62.8, typical: 92.9, max: 171 });
    expect(mass.inputs_used.filter((i) => i.tag === 'I')).toHaveLength(4);
    const bad = { ...d, applied: true, radioFraction: { min: 0.5, typical: 0.6, max: 0.7 }, structureFraction: { min: 0.2, typical: 0.3, max: 0.4 } };
    expect(generateEstimates(ctx({ massDefaults: bad })).some((e) => e.id.startsWith('est.mass'))).toBe(false);
  });
  it('without an energy configuration the mass stays unknown', () => {
    const e = base();
    e.parameters_used!.energy.array_area_m2 = 0;
    expect(generateEstimates(ctx({ evaluations: [e], massDefaults: { ...defaultMassDefaults(), applied: true } })).some((x) => x.id.startsWith('est.mass'))).toBe(false);
  });
  it('round-trips the declared defaults and rejects malformed ones', () => {
    const d = { ...defaultMassDefaults(), applied: true };
    expect(readMassDefaults(JSON.parse(JSON.stringify(d)))).toEqual(d);
    expect(readMassDefaults({ ...d, arrayKgPerM2: { min: 'x' } })).toBeNull();
  });
});

describe('model: determinism, accept/dismiss, merge, storage', () => {
  it('is deterministic: same context, same estimates, same order', () => {
    expect(JSON.stringify(generateEstimates(ctx()))).toBe(JSON.stringify(generateEstimates(ctx())));
    expect(generateEstimates(ctx()).map((e) => e.id)).toEqual(['est.requirements',
      'est.verification_plan', 'est.ait_plan', 'est.calendar', 'est.power', 'est.mass.A', 'est.mass.B', 'est.cost', 'est.devtime', 'est.vehicle', 'est.launch_co2', 'est.stats']);
    expect(generateEstimates(ctx({ evaluations: [] }))).toEqual([]);
  });
  it('golden: Malapert vs Haworth standard scenario', () => {
    const list = generateEstimates(ctx());
    expect(list.map((e) => [e.id, e.field, e.tag, e.items.length, e.digest])).toMatchInlineSnapshot(`
      [
        [
          "est.requirements",
          "high_level_requirements",
          "D",
          10,
          "4a482d9b",
        ],
        [
          "est.verification_plan",
          "verification_plan",
          "D",
          20,
          "fa669ce5",
        ],
        [
          "est.ait_plan",
          "ait_plan",
          "D",
          6,
          "1ac01512",
        ],
        [
          "est.calendar",
          "schedule",
          "D",
          17,
          "42c76583",
        ],
        [
          "est.power",
          "mass_and_power_budgets",
          "D",
          18,
          "d5c95501",
        ],
        [
          "est.mass.A",
          "mass_and_power_budgets",
          "I",
          5,
          "44b1305e",
        ],
        [
          "est.mass.B",
          "mass_and_power_budgets",
          "I",
          5,
          "cf78ab7c",
        ],
        [
          "est.cost",
          "economic_feasibility",
          "D",
          1,
          "b20f4f21",
        ],
        [
          "est.devtime",
          "schedule",
          "D",
          1,
          "cde1cc58",
        ],
        [
          "est.vehicle",
          "mass_and_power_budgets",
          "D",
          2,
          "58da08cc",
        ],
        [
          "est.launch_co2",
          "environmental_footprint",
          "I",
          2,
          "a886a222",
        ],
        [
          "est.stats",
          "orbit_or_landing",
          "D",
          4,
          "8f19c260",
        ],
      ]
    `);
  });
  it('every estimate starts proposed, carries method, source, inputs and limits', () => {
    for (const e of generateEstimates(ctx())) {
      expect(e).toMatchObject({ status: 'proposed', produced_at: AT });
      expect(e.method_id).toMatch(/^raven\./);
      expect(e.source.length).toBeGreaterThan(10);
      expect(e.inputs_used.length).toBeGreaterThan(0);
      expect(e.validity_limits.length).toBeGreaterThan(0);
    }
  });
  it('accept and dismiss change only the status; a regenerated estimate keeps the decision only if its digest is unchanged', () => {
    const first = generateEstimates(ctx());
    const decided = setEstimateStatus(setEstimateStatus(first, 'est.calendar', 'accepted'), 'est.power', 'dismissed');
    expect(byId(decided, 'est.calendar').status).toBe('accepted');
    expect(byId(decided, 'est.power').status).toBe('dismissed');
    expect(byId(decided, 'est.requirements').status).toBe('proposed');
    expect(JSON.stringify({ ...byId(decided, 'est.calendar'), status: 'proposed' })).toBe(JSON.stringify(byId(first, 'est.calendar')));
    expect(mergeEstimates(decided, generateEstimates(ctx())).map((e) => e.status)).toEqual(decided.map((e) => e.status));
    const changedEvals = standard();
    changedEvals[0]!.parameters_used!.energy.battery_capacity_wh = 5000;
    const merged = mergeEstimates(decided, generateEstimates(ctx({ evaluations: changedEvals })));
    expect(byId(merged, 'est.power').status).toBe('proposed');
    expect(byId(merged, 'est.calendar').status).toBe('accepted');
  });
  it('the stored list is validated; an invalid one is dropped, never trusted', () => {
    const list = setEstimateStatus(generateEstimates(ctx()), 'est.ait_plan', 'accepted');
    expect(readEstimates(JSON.parse(JSON.stringify(list)))).toEqual(list);
    expect(readEstimates([{ ...list[0], status: 'done' }, { ...list[1], field: 'other' }])).toEqual([]);
    expect(readEstimates('x')).toEqual([]);
  });
  it('renders a row per item in the reader language, with unknown spelled out', () => {
    const power = byId(generateEstimates(ctx()), 'est.power');
    const text = estimateLines(power);
    expect(text).toContain('PWR-A-01: Scenario A; Quantity Survival load; Value 10 W');
    expect(text).toContain('Quantity Minimum battery charge');
  });
});

describe('integration with the report completion: no overwrite, excluded until accepted', () => {
  const draft = (over: Partial<JourneyDraft> = {}): JourneyDraft => ({
    name: 'Standard', decision: '', objectives, radio: RADIO_PRESETS.baseline,
    panel: { array_area_m2: 1, cell_efficiency: .295, orientation: 'tracking', tilt_deg: 0, tilt_azimuth_deg: 0 },
    input: { mode: 'sites', siteA: 'malapert-massif', siteB: 'haworth', start: '2027-01-01T00:00', startB: '2027-05-16T00:00', days: 1, stepMin: 360 },
    planning: newReportPlanning(), ...over,
  });
  it('dismissed estimates add nothing; the others fill only fields the user left empty', () => {
    const evals = standard();
    const d = draft();
    d.planning!.estimates = generateEstimates(ctx({ evaluations: evals }));
    const before = reportCompletion(d, evals, null).statements;
    expect(before.verification_plan?.origin).toBe('engine_estimate'); // automatic: no accept step
    d.planning!.estimates = setEstimateStatus(setEstimateStatus(d.planning!.estimates, 'est.verification_plan', 'dismissed'), 'est.ait_plan', 'dismissed');
    expect(reportCompletion(d, evals, null).statements.ait_plan).toBeUndefined();
    expect(reportCompletion(d, evals, null).statements.verification_plan?.origin).toBe('draft_proposal');
    d.planning!.estimates = setEstimateStatus(setEstimateStatus(d.planning!.estimates, 'est.verification_plan', 'accepted'), 'est.requirements', 'accepted');
    const after = reportCompletion(d, evals, null).statements;
    expect(after.verification_plan).toMatchObject({ origin: 'engine_estimate' });
    expect(after.high_level_requirements?.origin).toBe('user_input'); // thresholds typed by the user are not replaced
    expect(acceptedFor(d.planning!.estimates, 'high_level_requirements')).toHaveLength(1);
  });
  it('a user text in the dossier is never replaced by an accepted estimate of the same field', () => {
    const evals = standard();
    const d = draft({ objectives: defaultObjectives() });
    d.planning!.estimates = generateEstimates(ctx({ evaluations: evals, objectives: defaultObjectives() }));
    expect(reportCompletion(d, evals, null).statements.high_level_requirements?.origin).toBe('engine_estimate');
    d.objectives = objectives;
    expect(reportCompletion(d, evals, null).statements.high_level_requirements?.origin).toBe('user_input');
  });
});

describe('mission class slider: automatic estimates with range, assumptions and source', () => {
  const at = (c: MissionClassId) => generateEstimates(ctx({ missionClass: c }));
  const range = (c: MissionClassId, id: string) => byId(at(c), id).range;

  it('every class estimate has a method, assumptions, a range or an explicit unknown, a source and a tag D or I', () => {
    for (const c of MISSION_CLASS_IDS) {
      for (const e of at(c).filter((x) => ['est.cost', 'est.devtime', 'est.vehicle', 'est.launch_co2', 'est.stats'].includes(x.id))) {
        expect(e.method_id, e.id).toMatch(/^raven\./);
        expect(e.source.length, e.id).toBeGreaterThan(20);
        expect(['D', 'I']).toContain(e.tag);
        expect(e.inputs_used.length, e.id).toBeGreaterThan(0);
        expect(e.validity_limits.length, e.id).toBeGreaterThan(0);
        expect(e.items.length, e.id).toBeGreaterThan(0);
        if (e.range) expect(e.range.min !== null || e.range.typical !== null, e.id).toBe(true);
        else expect(JSON.stringify(e.items), e.id).toContain('no adequate public source');
      }
    }
  });
  it('default class is the small commercial lander; the default does not change when the position is explicit', () => {
    expect(JSON.stringify(generateEstimates(ctx()))).toBe(JSON.stringify(at('small_lander')));
  });
  it('cost, mass and development time grow with the class where a source exists; unknown stays unknown where none does', () => {
    const cost = (c: MissionClassId) => range(c, 'est.cost');
    expect(cost('rover')).toBeNull(); // no adequate public source
    expect(cost('small_lander')!.max!).toBeLessThan(cost('medium_lander')!.typical!);
    expect(cost('medium_lander')!.typical!).toBeLessThan(cost('large_lander')!.min!);
    const mass = (c: MissionClassId) => range(c, 'est.vehicle')!;
    expect(mass('rover').max!).toBeLessThan(mass('small_lander').min!);
    expect(mass('small_lander').typical!).toBeLessThan(mass('medium_lander').max!);
    expect(mass('medium_lander').max!).toBeLessThan(mass('large_lander').min!);
    expect(range('rover', 'est.devtime')).toBeNull();
    expect(range('large_lander', 'est.devtime')).toBeNull();
    expect(range('small_lander', 'est.devtime')!.max!).toBeLessThan(range('medium_lander', 'est.devtime')!.min!);
    expect(byId(at('rover'), 'est.vehicle').tag).toBe('I'); // mass of a small rover has no public source
  });
  it('launch CO2 is propellant burned x a combustion factor, min <= typical <= max, and none for a rover', () => {
    expect(at('rover').some((e) => e.id === 'est.launch_co2')).toBe(false);
    for (const c of ['small_lander', 'medium_lander', 'large_lander'] as const) {
      const r = range(c, 'est.launch_co2')!;
      expect(r.min!).toBeLessThanOrEqual(r.typical!); expect(r.typical!).toBeLessThanOrEqual(r.max!);
    }
    expect(range('small_lander', 'est.launch_co2')!.typical!).toBeLessThan(range('medium_lander', 'est.launch_co2')!.typical!);
    // Falcon 9: 155.8 t RP-1 x 0.85..1 burned x 0.85..0.87 x 44.01/12.011
    expect(launchCo2T('falcon9').max).toBe(Math.round(155.8 * 0.87 * 44.01 / 12.011));
    expect(launchCo2T('newglenn').max).toBe(Math.round(710 * 0.43 * 44.01 / 16.04));
  });
  it('the totals have two lines; the user value wins and an estimate is never added to a declared quantity', () => {
    const list = at('small_lander');
    const noBudget = costTotals(null, list);
    expect(noBudget.declared).toBeNull();
    expect(noBudget.including).toEqual({ min: 47e6, typical: 100.65e6, max: 118e6 });
    const full = { known_cost_items: 9, missing_cost_items: [], known_subtotal: 900, contingency_amount: 180, total_lifecycle_cost: 1080, funding_gap: null,
      within_declared_funding: null, economic_feasibility: null, currency: 'EUR', price_base_year: 2026, basis: 'x', source: 'user_estimates' } as BudgetEstimate;
    expect(costTotals(full, list).including).toEqual({ min: 1080, typical: 1080, max: 1080 });
    const partial = { ...full, known_cost_items: 3, total_lifecycle_cost: null };
    expect(costTotals(partial, list)).toMatchObject({ declared: 900, including: null, note: 'currency' }); // EUR cannot be added to USD
    const dismissed = setEstimateStatus(list, 'est.cost', 'dismissed');
    expect(costTotals(null, dismissed).including).toBeNull();
    const carbon = { mission: { known_phases: 1, known_subtotal_kg_co2e: 50, phase_emissions_kg_co2e: { '0': 50, A: null, B: null, C: null, D: null, E: null, F: null } } } as unknown as CarbonEstimate;
    const t1 = co2Totals(carbon, list);
    expect(t1.declared).toBe(50);
    expect(t1.including!.min!).toBe(50 + launchCo2T('falcon9').min * 1000);
    const withE = { mission: { ...carbon.mission, phase_emissions_kg_co2e: { ...carbon.mission.phase_emissions_kg_co2e, E: 9 } } } as unknown as CarbonEstimate;
    expect(co2Totals(withE, list).including).toEqual({ min: 50, typical: 50, max: 50 }); // declared launch phase: no estimate added
  });
  it('no numeric report field is left without a state: estimated or in the owner-only / no-source checklist', () => {
    expect(NO_SOURCE_CHECKLIST.length).toBeGreaterThan(0);
    const names = at('small_lander').map((e) => e.id);
    for (const id of ['est.cost', 'est.devtime', 'est.vehicle', 'est.launch_co2', 'est.stats', 'est.power', 'est.mass.A']) expect(names).toContain(id);
    expect(NO_SOURCE_CHECKLIST.join(' ')).toMatch(/Manufacturing CO2e/);
  });
});
