// SPDX-License-Identifier: Apache-2.0
import { t as siteT, type MessageKey } from '../../../i18n/i18n.svelte';

export type Tr = typeof siteT;
import { utcMinute } from '../reportFormat';
import type { Cell, EngineEstimate } from './types';

const ISO_MINUTE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/;
/** Text of a cell in the reader's language. Unknown stays unknown (never an empty string or zero). */
export function cellText(cell: Cell | undefined, t: Tr = siteT): string {
  if (cell === null || cell === undefined) return t('report.notAssessed');
  if (typeof cell === 'number') return String(cell);
  if (typeof cell === 'string') return ISO_MINUTE.test(cell) ? utcMinute(cell) : cell;
  return t(cell.key as MessageKey, cell.params);
}
export const columnsOf = (e: EngineEstimate): string[] => [...new Set(e.items.flatMap((i) => Object.keys(i.cells)))];
export const rangeText = (e: EngineEstimate, t: Tr = siteT): string | null => {
  const r = e.range;
  if (r && r.min !== null && r.max === null) return `≥ ${r.min} ${r.unit}`;
  if (r && r.min === null && r.max === null && r.typical !== null) return `${r.typical} ${r.unit}`;
  if (!r || r.min === null || r.max === null) return null;
  return `${r.min} – ${r.max} ${r.unit}${r.typical === null ? '' : ` (${t('est.typical')} ${r.typical})`}`;
};
/** Plain-text rendering of an estimate: one line per item, used for the report statement and the JSON. */
export function estimateLines(e: EngineEstimate, t: Tr = siteT): string {
  return e.items.map((i) => `${i.id}: ${Object.entries(i.cells)
    .map(([k, v]) => `${t(`est.col.${k}` as MessageKey)} ${cellText(v, t)}`).join('; ')}`).join('\n');
}
export const estimateTitle = (e: EngineEstimate, t: Tr = siteT): string => t(`est.title.${e.id.replace(/^est\./, '').replace(/\.[AB]$/, '')}` as MessageKey, { scenario: e.id.slice(-1) });
