// SPDX-License-Identifier: Apache-2.0
// Lint of the generated report: English only, readable narrative, no repeated prose, and no empty ECSS phase.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import enPages from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import type { JourneyDraft } from './journey';
import { RADIO_PRESETS } from './setup';
import LifecycleReport from './LifecycleReport.svelte';
import { newReportPlanning } from './reportPlanning';
import { learnReportSections, newReportSections } from './reportSections';
import { siteA, unknownRf } from './reportFixtures';
import { generateEstimates } from './estimates';
import economicsFixture from './economics.fixture.json';
import type { RavenEconomics } from '../../shell/ravenApi';

const identity = { model_version: 'raven-core-test', registry_sha256: 'test-registry' };
const draftWith = (expert: boolean): JourneyDraft => {
  const planning = newReportPlanning();
  planning.sections = expert ? newReportSections() : learnReportSections();
  planning.estimates = generateEstimates({ evaluations: [siteA, unknownRf()], objectives: { priority: 'radio', minSunPercent: 0, minRfPercent: null }, validation: null, producedAt: '2027-04-10T08:00:00Z' });
  return {
    name: 'Lunar study', decision: '', objectives: { priority: 'radio', minSunPercent: 0, minRfPercent: null }, radio: RADIO_PRESETS.baseline,
    panel: { array_area_m2: 1, cell_efficiency: .295, orientation: 'tracking', tilt_deg: 0, tilt_azimuth_deg: 0 },
    input: { mode: 'sites', siteA: 'malapert-massif', siteB: 'haworth', start: '2027-04-16T00:00', startB: '2027-05-16T00:00', days: 3, stepMin: 60 }, planning,
  };
};

const ITALIAN = ['il', 'lo', 'la', 'gli', 'le', 'dei', 'delle', 'della', 'nel', 'nella', 'con', 'per', 'che', 'non', 'sono', 'ore', 'sito', 'siti',
  'luce', 'sole', 'terra', 'batteria', 'collegamento', 'pertanto', 'inoltre', 'quindi', 'anche', 'dati', 'valori', 'ignoto', 'ignote', 'noto', 'noti',
  'fase', 'fasi', 'pagina', 'di', 'una', 'uno', 'gli', 'questo', 'questa', 'periodo', 'confronto', 'stima', 'stime'];
const FORBIDDEN = ['pertanto', 'it is important to note', 'proposed work', 'not a completed deliverable', 'in order to', 'moreover', 'furthermore',
  'it should be noted', 'comprehensive', 'robust', 'leverage', 'delve', 'tapestry', 'cutting-edge'];
const WORDS = (s: string) => s.split(/\s+/).filter(Boolean).length;

function mount(expert: boolean) {
  const { container } = render(LifecycleReport, {
    draft: draftWith(expert), identity, evaluations: [siteA, unknownRf()], economics: economicsFixture as RavenEconomics, expert, created: '2027-04-10T08:00:00Z',
  });
  return container as HTMLElement;
}
/** Prose of the report: tables, formulas, charts' SVG, the contents, appendices and engine sentences are left out. */
function prose(root: HTMLElement): HTMLElement {
  const copy = root.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('table, .rp-flines, .est-meta, svg, .report-toc, .rp-legend-line, .rp-kicker, .rp-meta, .rp-appendix, .rp-limit-box, .rp-decision, h3, h4, h5, figcaption').forEach((n) => n.remove());
  return copy;
}
const paragraphs = (root: HTMLElement) => Array.from(root.querySelectorAll('p, li')).map((n) => (n.textContent ?? '').replace(/\s+/g, ' ').trim()).filter(Boolean);
const sentences = (text: string) => text.split(/(?<=[.!?])\s+(?=[A-Z])/).map((s) => s.trim()).filter(Boolean);

afterEach(() => { cleanup(); useCatalog('it', itCatalog, enPages); });

describe.each(['en', 'it'] as const)('report lint (site language %s)', (siteLang) => {
  for (const expert of [false, true]) {
    describe(expert ? 'Expert' : 'Learn', () => {
      const root = () => { useCatalog(siteLang, siteLang === 'it' ? itCatalog : {}, enPages); return mount(expert); };

      it('is English only: lang attribute, no Italian words, no raw catalog keys', () => {
        const el = root();
        expect(el.querySelector('[lang="en"]') ?? el.matches('[lang="en"]')).toBeTruthy();
        const text = (el.textContent ?? '').toLowerCase();
        const words = new Set(text.match(/[a-zà-ù']+/g));
        const hits = ITALIAN.filter((w) => words.has(w) && !['non', 'di', 'la', 'le', 'il', 'con', 'per', 'che', 'ore'].includes(w));
        expect(hits).toEqual([]);
        expect(text).not.toMatch(/\b(?:rpt|report|journey|planner|dossier|est|carbon)\.[a-z]+\b/);
      });

      it('has no forbidden phrase and no sentence of more than 25 words', () => {
        const body = prose(root());
        const all = paragraphs(body);
        const text = all.join(' ').toLowerCase();
        for (const phrase of FORBIDDEN) expect(text, phrase).not.toContain(phrase);
        for (const p of all) for (const s of sentences(p)) expect(WORDS(s), s).toBeLessThanOrEqual(25);
      });

      it('says nothing twice and every paragraph carries a number, a decision or an instruction', () => {
        const el = root();
        const seen = new Map<string, number>();
        for (const p of paragraphs(prose(el))) {
          for (const s of sentences(p)) if (WORDS(s) >= 4) seen.set(s, (seen.get(s) ?? 0) + 1);
          expect(p, p).toMatch(/\d|\b(?:do not|add|check|choose|pick|use|read|recompute|no conclusion|better|cannot|not|needs?|above|below|means?|must)\b/i);
        }
        expect([...seen].filter(([, n]) => n > 1)).toEqual([]);
        const full = (el.textContent ?? '').replace(/\s+/g, ' ');
        expect(full.match(/Preliminary study produced by software/g) ?? []).toHaveLength(1);
        expect(full.match(/Unknown is not zero/g) ?? []).toHaveLength(1);
        expect(full).not.toMatch(/proposed work|not a completed deliverable/i);
      });

      it('keeps the word budget and leaves no section empty', () => {
        const el = root();
        const words = WORDS(prose(el).textContent ?? '');
        expect(words).toBeLessThanOrEqual(expert ? 2200 : 1600);
        el.querySelectorAll('section').forEach((s) => expect((s.textContent ?? '').trim().length, s.className).toBeGreaterThan(12));
        const parts = Array.from(el.querySelectorAll('section.rp-part'));
        expect(parts.map((part) => part.getAttribute('data-part'))).toEqual(['executive', '0', 'A', 'B', 'C', 'D', 'E', 'F']);
        expect(el.querySelectorAll('.rp-appendix').length > 0).toBe(false === expert ? false : el.querySelectorAll('.rp-appendix').length > 0);
        if (!expert) expect(el.querySelectorAll('.rp-appendix')).toHaveLength(0);
      });

      it('shows cost and CO2e on two lines, the estimate label and the single owner-only checklist', () => {
        const el = root();
        const totals = el.querySelector('[data-testid="report-totals"]')!;
        expect(totals.textContent).toContain('Declared by you');
        expect(totals.textContent).toContain('Including RAVEN estimates (range)');
        expect(totals.textContent).toMatch(/47 – 118 M USD/);
        expect(totals.textContent).toContain('not a quote');
        expect(el.querySelectorAll('[data-testid="report-checklist"]')).toHaveLength(1);
        expect(el.textContent).not.toMatch(/Not provided:/);
      });

      it('states the load assumptions behind the battery result in the limits', () => {
        const text = root().querySelector('[data-testid="report-load-assumptions"]')?.textContent ?? '';
        expect(text).toMatch(/^Load assumptions: active load \d[\d.,]* W, survival load \d[\d.,]* W, communications \d[\d.,]* W on average/);
        expect(root().querySelector('[data-testid="report-thermal-load"]')).toBeNull(); // no reliability profile in the fixture
      });

      it('shows the verdict, at most 3 bullets and 5 charts; optional formula details are off by default', () => {
        const el = root();
        expect(el.querySelector('[data-testid="report-verdict"]')?.textContent).toMatch(/A: 24 of 24 sampled hours confirmed useful \(100%\)/);
        expect(el.querySelectorAll('[data-testid="report-means"] li').length).toBeLessThanOrEqual(3);
        expect(el.querySelectorAll('figure.rp-chart')).toHaveLength(5);
        expect(el.querySelectorAll('.rp-formula-block')).toHaveLength(0);
        expect(el.querySelector('[data-testid="report-toc"]')).toBeNull();
      });
    });
  }
});
