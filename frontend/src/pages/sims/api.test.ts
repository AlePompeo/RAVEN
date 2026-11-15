// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { buildInputs, runSimulation, listSimulations, type InputRow } from './api';

const row = (name: string, value: string): InputRow => ({ name, value });
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('buildInputs', () => {
  it('converte righe numeriche', () => {
    expect(buildInputs([row('x', '3'), row('y_km', '-1.5e2')])).toEqual({ ok: true, inputs: { x: 3, y_km: -150 } });
  });
  it('rifiuta valori vuoti, non finiti o non numerici', () => {
    for (const v of ['', ' ', 'abc', 'NaN', 'Infinity', '1e999']) {
      expect(buildInputs([row('x', v)]).ok).toBe(false);
    }
  });
  it('nomi come toString funzionano (proprieta proprie), __proto__ e rifiutato', () => {
    const r = buildInputs([row('toString', '1'), row('constructor', '2')]);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(Object.hasOwn(r.inputs, 'toString')).toBe(true);
      expect(JSON.parse(JSON.stringify({ inputs: r.inputs })).inputs.constructor).toBe(2);
    }
    const bad = buildInputs([row('__proto__', '1')]);
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.errors[0]).toMatchObject({ index: 0, field: 'name' });
  });
  it('riporta errori per campo con indice', () => {
    const r = buildInputs([row('a', '1'), row('', 'x'), row('a', '2')]);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.errors.map((e) => `${e.index}:${e.field}`)).toEqual(['1:name', '1:value', '2:name']);
    }
  });
  it('rifiuta nomi vuoti o duplicati e nessun input', () => {
    expect(buildInputs([row('', '1')]).ok).toBe(false);
    expect(buildInputs([row('x', '1'), row('x', '2')]).ok).toBe(false);
    expect(buildInputs([]).ok).toBe(false);
  });
});

describe('listSimulations', () => {
  it('filtra kind=simulation', async () => {
    const f = (async () =>
      json({ plugins: [{ id: 'a', kind: 'simulation' }, { id: 'b', kind: 'llm' }] })) as unknown as typeof fetch;
    expect(await listSimulations(f)).toEqual(['a']);
  });
  it('errore HTTP o rete lancia', async () => {
    await expect(listSimulations((async () => json({}, 500)) as unknown as typeof fetch)).rejects.toThrow();
  });
});

describe('runSimulation', () => {
  it('invia gli input e restituisce gli output', async () => {
    let seen: { url: string; body: string } | undefined;
    const f = (async (url: string, init: RequestInit) => {
      seen = { url, body: init.body as string };
      return json({ schema_version: '1.0.0', outputs: { y: 9 } });
    }) as unknown as typeof fetch;
    const r = await runSimulation(f, 'example sim', { x: 3 });
    expect(r).toEqual({ ok: true, outputs: { y: 9 } });
    expect(seen?.url).toBe('/api/simulations/example%20sim/run');
    expect(JSON.parse(seen?.body ?? '')).toEqual({ inputs: { x: 3 } });
  });
  it('restituisce chiavi di errore per 404/504/502/422', async () => {
    for (const [status, key] of [
      [404, 'sims.errorNotFound'],
      [504, 'sims.errorTimeout'],
      [502, 'sims.errorFailed'],
      [422, 'sims.errorInvalidInputs'],
    ] as const) {
      const r = await runSimulation((async () => json({ detail: 'x' }, status)) as unknown as typeof fetch, 's', { x: 1 });
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.error.key).toBe(key);
    }
  });
  it('rete giu', async () => {
    const r = await runSimulation((async () => {
      throw new TypeError('x');
    }) as unknown as typeof fetch, 's', { x: 1 });
    expect(r.ok).toBe(false);
  });
});
