// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import en from '../../i18n/en.pages.json';
import it_ from '../../i18n/it.json';
import { GROUPS, PLAN_IDS } from './plans';

const rows = GROUPS.flatMap((g) => g.rows);

describe('tabella di confronto dei piani', () => {
  it('ha tre piani e id di riga unici', () => {
    expect(PLAN_IDS).toEqual(['free', 'premium', 'enterprise']);
    expect(new Set(rows.map((r) => r.id)).size).toBe(rows.length);
  });
  it('ogni piano include quello precedente', () => {
    for (const r of rows) {
      expect(Number(r.in[1]) >= Number(r.in[0]), r.id).toBe(true);
      expect(Number(r.in[2]) >= Number(r.in[1]), r.id).toBe(true);
    }
  });
  it('tutte le chiavi usate esistono in en e it', () => {
    const keys = [...GROUPS.map((g) => `pricing.group.${g.id}`), ...rows.map((r) => `pricing.row.${r.id}`)];
    for (const k of keys) {
      expect(k in en, `en ${k}`).toBe(true);
      expect(k in it_, `it ${k}`).toBe(true);
    }
  });
});
