// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import { parseMarkdown, parseInline, citedIds, type Block, type Inline } from './markdown';
import Answer from './Answer.svelte';

afterEach(cleanup);
const K = new Set(['fspl', 'link-budget']);
const flat = (n: Inline[]): string => n.map((x) => (x.t === 'bold' ? flat(x.c) : x.t === 'cite' ? `[${x.id}]` : x.v)).join('');

describe('parseInline', () => {
  it('grassetto, codice e testo', () => {
    expect(parseInline('a **b** `c`', K)).toEqual([{ t: 'text', v: 'a ' }, { t: 'bold', c: [{ t: 'text', v: 'b' }] }, { t: 'text', v: ' ' }, { t: 'code', v: 'c' }]);
  });
  it('marcatori non chiusi (streaming) restano testo', () => {
    expect(flat(parseInline('**in corso e `aperto', K))).toBe('**in corso e `aperto');
  });
  it('[id] noto diventa citazione; ignoto resta testo, mai un collegamento', () => {
    const n = parseInline('vedi [fspl] e [inventato] e [fonte non valida]', K);
    expect(n.filter((x) => x.t === 'cite')).toEqual([{ t: 'cite', id: 'fspl' }]);
    expect(flat(n)).toBe('vedi [fspl] e [inventato] e [fonte non valida]');
  });
  it('[a, b] misto: noti chip, ignoti testo', () => {
    const n = parseInline('[fspl, nope, link-budget]', K);
    expect(n.map((x) => (x.t === 'cite' ? `c:${x.id}` : x.t === 'text' ? `t:${x.v}` : '?'))).toEqual(['c:fspl', 't:[nope]', 'c:link-budget']);
  });
  it('un collegamento markdown non diventa mai un collegamento', () => {
    const n = parseInline('[clic](javascript:alert(1)) ![x](http://e/x.png)', K);
    expect(n.every((x) => x.t === 'text')).toBe(true);
  });
  it('citedIds', () => {
    expect(citedIds('a [x1] b [x1, y.z] [fonte non valida]')).toEqual(['x1', 'y.z']);
  });
});

describe('parseMarkdown', () => {
  it('paragrafi, a capo singolo come riga, elenchi puntati e numerati', () => {
    const b = parseMarkdown('uno\ndue\n\n- a\n- b\n\n1. x\n2. y', K);
    expect(b.map((x) => x.t)).toEqual(['p', 'ul', 'ol']);
    expect((b[0] as Extract<Block, { t: 'p' }>).lines).toHaveLength(2);
    expect((b[1] as Extract<Block, { t: 'ul' }>).items).toHaveLength(2);
  });
  it('blocco di codice, anche non chiuso; il contenuto non è interpretato', () => {
    const b = parseMarkdown('```\n**non grassetto** [fspl]\n```\nfine', K);
    expect(b[0]).toEqual({ t: 'pre', v: '**non grassetto** [fspl]' });
    expect(parseMarkdown('```\nx = 1', K)[0]).toEqual({ t: 'pre', v: 'x = 1' });
  });
  it('riga Formula e tabella delle variabili', () => {
    const b = parseMarkdown('Formula: A = 92.45 + 20*log10(d_km)\nVariabili:\n- FSPL = perdita [dB], intervallo da d e f\n- d_km = distanza [km], intervallo > 0', K);
    expect(b[0]).toEqual({ t: 'formula', v: 'A = 92.45 + 20*log10(d_km)' });
    expect(b[1]).toEqual({
      t: 'vars',
      rows: [
        { symbol: 'FSPL', name: 'perdita', unit: 'dB', range: 'da d e f' },
        { symbol: 'd_km', name: 'distanza', unit: 'km', range: '> 0' },
      ],
    });
  });
  it('elenco sotto "Variabili:" non nel formato atteso resta un elenco', () => {
    const b = parseMarkdown('Variabili:\n- niente uguale qui', K);
    expect(b.map((x) => x.t)).toEqual(['p', 'ul']);
  });
  it('tabella su più righe e tabella appiattita su una riga con testo che segue', () => {
    const t1 = parseMarkdown('| A | B |\n|---|---|\n| 1 | 2 |', K)[0] as Extract<Block, { t: 'table' }>;
    expect(t1).toMatchObject({ head: ['A', 'B'], rows: [['1', '2']], after: '' });
    const t2 = parseMarkdown("| Nome | Unita' | | `d` | km | | `f` | GHz | Coda finale [fspl]", K)[0] as Extract<Block, { t: 'table' }>;
    expect(t2.head).toEqual(['Nome', "Unita'"]);
    expect(t2.rows).toEqual([['`d`', 'km'], ['`f`', 'GHz']]);
    expect(t2.after).toBe('Coda finale [fspl]');
  });
  it('intestazioni e tabelle degeneri non lanciano', () => {
    expect(parseMarkdown('# Titolo', K)[0]).toMatchObject({ t: 'h' });
    expect(() => parseMarkdown('|\n||\n| |', K)).not.toThrow();
    expect(() => parseMarkdown('\u0000**`[[[]]]```|', K)).not.toThrow();
  });
  it('testo molto lungo senza struttura resta lineare', () => {
    const t0 = performance.now();
    parseMarkdown('[' .repeat(20000) + '*'.repeat(20000) + '`'.repeat(20000), K);
    expect(performance.now() - t0).toBeLessThan(1500);
  });
});

describe('Answer: carichi XSS resi come testo', () => {
  const payloads = [
    '<script>window.__x=1</script>',
    '<img src=x onerror="window.__x=1">',
    '[clic](javascript:window.__x=1)',
    '**<b onmouseover=window.__x=1>x</b>**',
    '`<svg onload=window.__x=1>`',
    '```\n<iframe src="javascript:window.__x=1"></iframe>\n```',
    '- <a href="javascript:window.__x=1">z</a>',
    '| <img src=x onerror=window.__x=1> | b |\n| 1 | 2 |',
    'Formula: <script>window.__x=1</script>',
    'Variabili:\n- <img src=x onerror=1> = <b>n</b> [<i>u</i>], intervallo <u>r</u>',
  ];
  it.each(payloads)('%s', (p) => {
    const { container } = render(Answer, { text: p, known: K, onCite: () => {} });
    expect(container.querySelector('script, img, iframe, svg, a, b, i, u')).toBeNull();
    expect(container.querySelector('[onerror], [onload], [onmouseover], [href], [src]')).toBeNull();
    expect(container.textContent).toContain(p.includes('<') ? '<' : 'clic');
    expect((window as unknown as { __x?: number }).__x).toBeUndefined();
  });
  it('chip solo per id noti, con nome accessibile del titolo', () => {
    const { container, getAllByRole } = render(Answer, { text: 'Vedi [fspl] e [fantasma].', known: K, titles: { fspl: 'Perdita nello spazio libero' }, onCite: () => {} });
    const chips = getAllByRole('button');
    expect(chips).toHaveLength(1);
    expect(chips[0]!.getAttribute('aria-label')).toBe('Fonte fspl: Perdita nello spazio libero');
    expect(container.textContent).toContain('[fantasma]');
  });
});
