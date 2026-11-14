// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import {
  countByStatus,
  entriesFor,
  exportMatrix,
  filterParams,
  rangeText,
  worstStatus,
  type Param,
  type Validation,
} from './model';

const e = (id: string, stage: string, status: any) => ({
  id, stage, status, what: '', against: '', residual: '', not_validated: '', evidence: [], phrase: '',
});
const V: Validation = {
  statuses: ['verified', 'plausibility_only', 'not_validated', 'unknown'],
  note: 'n',
  stages: [e('a', 's1', 'verified'), e('b', 's1', 'plausibility_only'), e('c', 's5', 'not_validated'), e('d', 's5', 'verified')],
  parameter_groups: [],
};
const P = (key: string, stage: string, tag: 'V' | 'D' | 'I', source = 'x'): Param => ({
  key, stage, group: 'g', tag, default: 1, unit: '', min: null, max: null, source, note: '',
});

describe('mappatura della matrice', () => {
  it('stato peggiore per stadio, ignoto se senza voci', () => {
    expect(worstStatus(entriesFor(V, 's1'))).toBe('plausibility_only');
    expect(worstStatus(entriesFor(V, 's5'))).toBe('not_validated');
    expect(worstStatus(entriesFor(V, 's3'))).toBe('unknown');
  });
  it('conteggio per stato', () => {
    expect(countByStatus(V)).toEqual({ verified: 2, plausibility_only: 1, not_validated: 1, unknown: 0 });
  });
  it('verified solo con tutti i controlli chiusi; uno stato invalido resta ignoto', () => {
    expect(worstStatus([{ status: 'verified' }, { status: 'verified' }])).toBe('verified');
    expect(worstStatus([{ status: 'verified' }, { status: 'unknown' }])).toBe('unknown');
    expect(worstStatus([{ status: 'verified' }, { status: 'pending' }])).toBe('unknown');
  });
  it('esportazione JSON fedele, con la versione', () => {
    const o = JSON.parse(exportMatrix(V, '9.9'));
    expect(o.model_version).toBe('9.9');
    expect(o.stages).toHaveLength(4);
  });
});

describe('filtri dei parametri', () => {
  const rows = [P('lunar.a', 's5', 'I'), P('lunar.b', 's5', 'V', 'DSN'), P('lunar.c', 's1', 'V')];
  it('per stadio, tag e testo', () => {
    expect(filterParams(rows, { stage: 's5', tag: '', text: '' })).toHaveLength(2);
    expect(filterParams(rows, { stage: '', tag: 'V', text: '' }).map((p) => p.key)).toEqual(['lunar.b', 'lunar.c']);
    expect(filterParams(rows, { stage: '', tag: '', text: 'dsn' })).toHaveLength(1);
    expect(filterParams(rows, { stage: 's1', tag: 'I', text: '' })).toEqual([]);
  });
  it('intervallo', () => {
    expect(rangeText({ min: null, max: null })).toBe('—');
    expect(rangeText({ min: 1, max: 2 })).toBe('1 – 2');
  });
});
