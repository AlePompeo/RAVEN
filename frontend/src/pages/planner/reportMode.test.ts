// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { effectiveReportMode } from './reportMode';
import { newReportPlanning, readReportPlanning } from './reportPlanning';
import { learnReportSections, newReportSections, REPORT_APPENDICES, REPORT_SECTION_IDS, reportModeFor, sectionsForMode } from './reportSections';

describe('report modes', () => {
  it('defaults from the site mode and an explicit choice wins', () => {
    expect(reportModeFor('learning')).toBe('learn');
    expect(reportModeFor('avanzato')).toBe('expert');
    const p = newReportPlanning();
    expect(effectiveReportMode(p, 'avanzato')).toBe('expert');
    p.reportMode = 'learn';
    expect(effectiveReportMode(p, 'avanzato')).toBe('learn');
  });
  it('keeps methodology, reliability and parameter details optional in both modes', () => {
    const learn = REPORT_SECTION_IDS.filter((id) => learnReportSections()[id]);
    expect(learn.length).toBeLessThan(REPORT_SECTION_IDS.length);
    expect(learn).toEqual(['summary']); // no appendix key
    expect(REPORT_APPENDICES.flatMap((a) => a.keys).filter((k) => learnReportSections()[k])).toEqual([]);
    expect(sectionsForMode('expert')).toEqual(newReportSections());
    expect(newReportSections()).toMatchObject({
      methodology: false, reliability: false, configuration: false, provenance: false,
    });
  });
  it('ignores the legal keys of drafts saved before the legal part was removed', () => {
    const old = JSON.parse(JSON.stringify(newReportPlanning()));
    old.text.jurisdiction = 'Italy'; old.text.authority = 'x';
    old.sections = { ...old.sections, legal: true };
    const read = readReportPlanning(old);
    expect(read).not.toBeNull();
    expect(read!.sections).toEqual(newReportSections());
    expect('jurisdiction' in read!.text).toBe(false);
    const { reliability: _r, ...legacy } = old.sections; // oldest drafts: no reliability key
    expect(readReportPlanning({ ...old, sections: legacy })).not.toBeNull();
    expect(readReportPlanning({
      ...old, sections: { ...newReportSections(), seal: false, paper: false },
    })?.sections).toEqual(newReportSections());
  });
  it('persists the mode and rejects a bad one', () => {
    const p = newReportPlanning();
    p.reportMode = 'learn';
    expect(readReportPlanning(JSON.parse(JSON.stringify(p)))?.reportMode).toBe('learn');
    expect(readReportPlanning({ ...p, reportMode: 'brief' })).toBeNull();
  });
});
