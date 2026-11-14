// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { isSiteSearch } from './intent';

describe('intent of a message to RAVEN SI', () => {
  it.each([
    'trovami 5 siti vicino al polo sud per 14 giorni da aprile 2027',
    'Dammi i 3 migliori siti con almeno il 60% di Sole',
    'cerca luoghi di allunaggio con buona radio',
    'Find me 4 sites near the south pole, 14 days from April 2027',
    'recommend the best 5 landing sites for a small lander',
    'give me 3 places with at least 60% sunlight',
    'consigliami dei siti per un rover',
    'i 5 migliori siti per una missione di 10 giorni',
  ])('a request to find sites opens the search: %s', (text) => {
    expect(isSiteSearch(text)).toBe(true);
  });
  it.each([
    'come funziona la ricerca dei siti migliori?',
    'cosa significa la probabilita di raggiungere gli obiettivi',
    'How does the site search choose the best sites?',
    'what is a non comparable site?',
    'perche il sito Haworth e il migliore',
    'spiegami la perdita nello spazio libero',
    'ciao',
    '',
    'trova',
    'x'.repeat(2500),
  ])('a question or an unrelated message goes to the assistant: %s', (text) => {
    expect(isSiteSearch(text)).toBe(false);
  });
});
