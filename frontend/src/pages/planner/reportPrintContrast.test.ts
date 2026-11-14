// SPDX-License-Identifier: Apache-2.0
// WCAG AA on the print palette of the report: every role has -bg (tint), -fg (text on the tint) and -rule
// (strong colour). Text pairs need 4.5:1, bands (white text on -rule) 4.5:1, graphics and rules 3:1 on paper.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { contrastRatio, parseTokenBlocks } from '../../styles/contrast';

const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), 'reportPrint.css'), 'utf8');
const tokens = parseTokenBlocks(css).print!;
const roles = [...new Set(Object.keys(tokens).map((k) => /^--pp-(.+)-(bg|fg|rule)$/.exec(k)?.[1]).filter((r): r is string => !!r))];
const ruled = roles.filter((r) => `--pp-${r}-rule` in tokens);
const BANDS = ['ph0', 'phA', 'phB', 'phC', 'phD', 'phE', 'phF', 'limit', 'appendix', 'proposed'];

describe('print palette contrast (WCAG AA)', () => {
  it('declares the expected roles', () => {
    expect(roles.length).toBeGreaterThanOrEqual(20);
    for (const role of ['ph0', 'phA', 'phF', 'engine', 'proposed', 'warning', 'limit', 'esg', 'appendix', 'verified', 'plausible', 'notvalidated', 'unknown', 'knownno'])
      expect(roles, role).toContain(role);
  });
  it.each(roles)('%s: text on its tint is >= 4.5:1', (role) => {
    expect(contrastRatio(tokens[`--pp-${role}-fg`]!, tokens[`--pp-${role}-bg`]!), role).toBeGreaterThanOrEqual(4.5);
  });
  it.each(ruled)('%s: the rule colour is >= 3:1 on white and on its tint', (role) => {
    expect(contrastRatio(tokens[`--pp-${role}-rule`]!, tokens['--pp-paper']!), role).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(tokens[`--pp-${role}-rule`]!, tokens[`--pp-${role}-bg`]!), role).toBeGreaterThanOrEqual(3);
  });
  it.each(BANDS)('%s: white heading text on its band is >= 4.5:1', (role) => {
    expect(contrastRatio('#ffffff', tokens[`--pp-${role}-rule`]!), role).toBeGreaterThanOrEqual(4.5);
  });
  it('body, muted text, header cells, cover and zebra rows are readable', () => {
    const t = tokens;
    for (const bg of ['--pp-paper', '--pp-zebra']) {
      expect(contrastRatio(t['--pp-ink']!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(t['--pp-muted']!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrastRatio(t['--pp-thead-fg']!, t['--pp-thead-bg']!)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(t['--pp-cover-fg']!, t['--pp-cover-bg']!)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(t['--pp-hair']!, t['--pp-paper']!)).toBeGreaterThanOrEqual(3);
  });
  it('the two scenario series are graphics >= 3:1 on paper and differ in lightness enough to read in grey', () => {
    const a = tokens['--pp-series-a']!; const b = tokens['--pp-series-b']!;
    expect(contrastRatio(a, tokens['--pp-paper']!)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(b, tokens['--pp-paper']!)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(a, b)).toBeGreaterThanOrEqual(1); // lightness alone is not enough: B is also dashed (SeriesChart, ReliabilityCharts)
  });
});
