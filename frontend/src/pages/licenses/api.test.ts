// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { parseLicenses, loadLicenses } from './api';

const f = (impl: (u: string) => Promise<Response>) => impl as unknown as typeof fetch;

describe('parseLicenses', () => {
  it('accetta un array di voci valide e scarta le altre', () => {
    expect(
      parseLicenses([{ name: 'svelte', version: '5.0.0', license: 'MIT' }, { name: 3 }, null, { name: 'x', license: 'ISC' }]),
    ).toEqual([
      { name: 'svelte', version: '5.0.0', license: 'MIT' },
      { name: 'x', version: '', license: 'ISC' },
    ]);
  });
  it('non array vale come vuoto', () => {
    expect(parseLicenses({})).toEqual([]);
    expect(parseLicenses('x')).toEqual([]);
  });
});

describe('loadLicenses distingue errore, assente e vuoto', () => {
  it('404 -> absent', async () => {
    expect(await loadLicenses(f(async () => new Response('no', { status: 404 })))).toEqual({ status: 'absent' });
  });
  it('500, non JSON o rete giu -> error', async () => {
    expect(await loadLicenses(f(async () => new Response('x', { status: 500 })))).toEqual({ status: 'error' });
    expect(await loadLicenses(f(async () => new Response('<html>')))).toEqual({ status: 'error' });
    expect(
      await loadLicenses(
        f(async () => {
          throw new TypeError('x');
        }),
      ),
    ).toEqual({ status: 'error' });
  });
  it('[] -> empty', async () => {
    expect(await loadLicenses(f(async () => new Response('[]')))).toEqual({ status: 'empty' });
  });
  it('legge /licenses.json', async () => {
    let url = '';
    const r = await loadLicenses(
      f(async (u) => {
        url = u;
        return new Response(JSON.stringify([{ name: 'a', version: '1', license: 'MIT' }]));
      }),
    );
    expect(r.status).toBe('ok');
    expect(url).toBe('/licenses.json');
  });
});
