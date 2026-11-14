// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { readBody, STORAGE_KEY, VIEWER_BODIES, writeBody } from './bodyState';

function mem(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m };
}
const throwing = {
  getItem: () => {
    throw new Error('SecurityError');
  },
  setItem: () => {
    throw new Error('QuotaExceeded');
  },
};

describe('stato del corpo scelto (URL + localStorage)', () => {
  it('il link ha la precedenza, poi la scelta salvata, poi la Luna', () => {
    expect(readBody('?body=earth', mem({ [STORAGE_KEY]: 'moon' }))).toBe('earth');
    expect(readBody('', mem({ [STORAGE_KEY]: 'earth' }))).toBe('earth');
    expect(readBody('?body=pluto', mem())).toBe('moon');
    expect(readBody('', null)).toBe('moon');
  });

  it('ignora valori salvati non validi e archivi che lanciano', () => {
    expect(readBody('', mem({ [STORAGE_KEY]: 'x' }))).toBe('moon');
    expect(readBody('', throwing)).toBe('moon');
  });

  it('scrive il link senza parametri per la Luna e preserva gli altri parametri', () => {
    const calls: string[] = [];
    const h = { replaceState: (_s: unknown, _t: string, u?: string | URL | null) => void calls.push(String(u)) };
    const store = mem();
    expect(writeBody('earth', { pathname: '/viewer', search: '?tv=1', hash: '' }, h, store)).toBe('/viewer?tv=1&body=earth');
    expect(store.m.get(STORAGE_KEY)).toBe('earth');
    expect(writeBody('moon', { pathname: '/viewer', search: '?body=earth', hash: '#x' }, h, store)).toBe('/viewer#x');
    expect(calls).toEqual(['/viewer?tv=1&body=earth', '/viewer#x']);
    expect(() => writeBody('earth', { pathname: '/v', search: '', hash: '' }, h, throwing)).not.toThrow();
  });
});

describe('Sole e Marte escono dal selettore su questo ramo', () => {
  it('il selettore ha solo Luna e Terra', () => {
    expect([...VIEWER_BODIES]).toEqual(['moon', 'earth']);
  });
  it('un link o un valore salvato con sole/marte torna alla Luna', () => {
    expect(readBody('?body=mars', mem())).toBe('moon');
    expect(readBody('?body=sun', mem())).toBe('moon');
    expect(readBody('', mem({ [STORAGE_KEY]: 'mars' }))).toBe('moon');
  });
});
