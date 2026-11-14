// SPDX-License-Identifier: Apache-2.0
// Verifica AA sulle coppie di token effettivamente usate dai componenti, per ogni schema/tono.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { composite, contrastRatio, parseRgba, parseTokenBlocks } from './contrast';

const TEXT = 4.5;
const UI = 3;

/** [primo piano, sfondo, soglia, uso] */
const PAIRS: [string, string, number, string][] = [
  ['--c-text', '--c-bg', TEXT, 'testo su tile'],
  ['--c-text', '--c-bg-alt', TEXT, 'testo su tile alternata'],
  ['--c-text', '--c-raised', TEXT, 'testo su pannello'],
  ['--c-muted', '--c-bg', TEXT, 'testo secondario su tile'],
  ['--c-muted', '--c-bg-alt', TEXT, 'testo secondario su tile alternata'],
  ['--c-muted', '--c-raised', TEXT, 'testo secondario su pannello'],
  ['--c-link', '--c-bg', TEXT, 'link su tile'],
  ['--c-link', '--c-bg-alt', TEXT, 'link su tile alternata'],
  ['--c-link', '--c-raised', TEXT, 'link e pulsante ghost su pannello'],
  ['--c-on-action', '--c-action', TEXT, 'testo del pulsante primario'],
  ['--c-danger', '--c-bg', TEXT, 'errore su tile'],
  ['--c-danger', '--c-bg-alt', TEXT, 'errore su tile alternata'],
  ['--c-danger', '--c-raised', TEXT, 'errore su pannello'],
  ['--c-success', '--c-bg-alt', TEXT, 'stato ok su tile alternata'],
  ['--c-success', '--c-raised', TEXT, 'stato ok su pannello'],
  ['--c-text', '--c-bubble', TEXT, 'messaggio dell’assistente'],
  ['--c-on-bubble-user', '--c-bubble-user', TEXT, 'messaggio dell’utente'],
  ['--c-focus', '--c-bg', UI, 'anello di focus su tile'],
  ['--c-focus', '--c-bg-alt', UI, 'anello di focus su tile alternata'],
  ['--c-focus', '--c-raised', UI, 'anello di focus su pannello'],
  ['--c-control', '--c-bg', UI, 'bordo dei campi su tile'],
  ['--c-control', '--c-bg-alt', UI, 'bordo dei campi su tile alternata'],
  ['--c-control', '--c-raised', UI, 'bordo dei campi su pannello'],
  ['--c-link', '--c-raised', UI, 'bordo del pulsante ghost'],
  ['--c-power', '--c-raised', UI, 'serie potenza nel grafico'],
  ['--c-uplink', '--c-raised', UI, 'serie margine di link nel grafico'],
  ['--c-power', '--c-bg', UI, 'traccia potenza nella home'],
  ['--c-success', '--c-bg', UI, 'indicatore di stato'],
];

// lettura dal disco: il loader CSS di Vitest restituirebbe una stringa vuota per `?raw`
const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), 'tokens.css'), 'utf8');
const { scrim, ...blocks } = parseTokenBlocks(css);

describe('token di colore', () => {
  it('tokens.css espone i blocchi attesi', () => {
    expect(Object.keys(parseTokenBlocks(css)).sort()).toEqual(['dark', 'light', 'scrim', 'tone-dark']);
  });

  for (const [name, vars] of Object.entries(blocks)) {
    describe(name, () => {
      for (const [fg, bg, min, use] of PAIRS) {
        it(`${use}: ${fg} su ${bg} >= ${min}:1`, () => {
          const a = vars[fg];
          const b = vars[bg];
          expect(a, `${fg} mancante in ${name}`).toBeDefined();
          expect(b, `${bg} mancante in ${name}`).toBeDefined();
          const r = contrastRatio(a!, b!);
          expect(r, `${name}: ${fg} ${a} su ${bg} ${b} = ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(min);
        });
      }
    });
  }

  for (const [name, vars] of Object.entries(blocks)) {
    it(`${name}: testo della barra smerigliata AA su qualunque sfondo (nero e bianco)`, () => {
      const frost = parseRgba(vars['--c-frost']!);
      for (const under of ['#000000', '#ffffff']) {
        const bg = composite(frost.hex, frost.alpha, under);
        const r = contrastRatio(vars['--c-text']!, bg);
        expect(r, `${name}: --c-text su frost sopra ${under} = ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(TEXT);
      }
    });
  }

  for (const name of ['--scrim-min', '--scrim-strong']) {
    it(`${name}: il testo del tono scuro resta AA sopra lo scrim anche su un pixel bianco`, () => {
      const s = parseRgba(scrim![name]!);
      expect(s.hex).toBe('#000000');
      const worst = composite(s.hex, s.alpha, '#ffffff');
      const r = contrastRatio(blocks['tone-dark']!['--c-text']!, worst);
      expect(r, `${name} su bianco = ${worst}, ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(TEXT);
      // il link della CTA è un pulsante pieno; il testo secondario non va sopra i media
    });
  }
});

describe('funzioni di contrasto', () => {
  it('bianco su nero = 21:1, colore su sé stesso = 1:1', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeCloseTo(21, 5);
    expect(contrastRatio('#0066cc', '#0066cc')).toBeCloseTo(1, 5);
  });
  it('rifiuta colori non esadecimali', () => {
    expect(() => contrastRatio('rgb(0 0 0)', '#ffffff')).toThrow();
  });
  it('composite: metà nero su bianco', () => {
    expect(composite('#000000', 0.5, '#ffffff')).toBe('#808080');
  });
});
