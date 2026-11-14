// SPDX-License-Identifier: Apache-2.0
export const REPORT_SECTION_GROUPS = {
  phases: ['phase0', 'phaseA', 'phaseB', 'phaseC', 'phaseD', 'phaseE', 'phaseF'],
  technical: ['summary', 'charts', 'windows', 'configuration', 'provenance', 'reliability'],
  supporting: ['deliverables', 'economics', 'sustainability', 'assistance', 'sources', 'seal', 'paper'],
} as const;
export const REPORT_SECTION_IDS = [
  ...REPORT_SECTION_GROUPS.phases, ...REPORT_SECTION_GROUPS.technical, ...REPORT_SECTION_GROUPS.supporting,
] as const;
export type ReportSectionId = typeof REPORT_SECTION_IDS[number];
export type ReportSections = Record<ReportSectionId, boolean>;

export function newReportSections(brief = false): ReportSections {
  return {
    phase0: !brief, phaseA: !brief, phaseB: !brief, phaseC: !brief, phaseD: !brief, phaseE: !brief, phaseF: !brief,
    summary: true, charts: !brief, windows: !brief, configuration: !brief, provenance: !brief, reliability: !brief,
    deliverables: !brief, economics: !brief, sustainability: !brief, assistance: !brief,
    sources: !brief, seal: !brief, paper: !brief,
  };
}
export function readReportSections(value: unknown): ReportSections | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  // Drafts saved before the legal section was removed still carry a `legal` key: it is ignored, never an error.
  const { legal: _legal, ...record } = value as Record<string, unknown>;
  const legacy = !('reliability' in record) && Object.keys(record).length === REPORT_SECTION_IDS.length - 1;
  if ((!legacy && Object.keys(record).length !== REPORT_SECTION_IDS.length) ||
      Object.keys(record).some((key) => !REPORT_SECTION_IDS.some((id) => id === key))) return null;
  const sections = newReportSections();
  for (const id of REPORT_SECTION_IDS) {
    if (legacy && id === 'reliability') {
      sections.reliability = Object.entries(record).some(([key, value]) => key !== 'summary' && value === true);
      continue;
    }
    if (typeof record[id] !== 'boolean') return null;
    sections[id] = record[id];
  }
  return sections;
}

/** Report mode: Learn (short and educational, replaces the brief report) or Expert (every section, the complete report). */
export const REPORT_MODES = ['learn', 'expert'] as const;
export type ReportMode = typeof REPORT_MODES[number];
export const parseReportMode = (v: unknown): ReportMode | null => (REPORT_MODES as readonly unknown[]).includes(v) ? v as ReportMode : null;
/** The site mode gives the default only: Learning -> Learn, Advanced -> Expert. */
export const reportModeFor = (site: 'learning' | 'avanzato'): ReportMode => site === 'avanzato' ? 'expert' : 'learn';

/**
 * Learn is parts 1-4 of the report (verdict, charts, how it was computed, limits) and no appendix; the appendices are
 * hidden, not deleted. The numbers are the same in both modes: only what is shown changes.
 */
export function learnReportSections(): ReportSections {
  return newReportSections(true);
}

/** The appendices of the Expert report, as the checkboxes of "Customise sections" (each one sets the stored keys it covers). */
export const REPORT_APPENDICES = [
  { id: 'reliability', keys: ['reliability'] },
  { id: 'parameters', keys: ['provenance', 'configuration'] },
  { id: 'dossier', keys: ['phase0', 'phaseA', 'phaseB', 'phaseC', 'phaseD', 'phaseE', 'phaseF'] },
  { id: 'estimates', keys: ['deliverables'] },
  { id: 'economics', keys: ['economics'] },
  { id: 'sustainability', keys: ['sustainability'] },
  { id: 'stamp', keys: ['seal', 'paper'] },
] as const satisfies readonly { id: string; keys: readonly ReportSectionId[] }[];
export const sectionsForMode = (mode: ReportMode): ReportSections => mode === 'learn' ? learnReportSections() : newReportSections();
