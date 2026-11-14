// SPDX-License-Identifier: Apache-2.0
// The report is English only whatever the site language is. Components that the report shares with the site pages
// read this flag from the Svelte context (set by LifecycleReport) and take English text and numbers when it is on.
import { getContext, setContext } from 'svelte';
import { t, tEn, formatNumber, formatNumberEn } from './i18n.svelte';
const KEY = Symbol('report-english');
export const enterReportEnglish = (): void => { setContext(KEY, true); };
export function scopedI18n(): { t: typeof t; formatNumber: typeof formatNumber } {
  return getContext(KEY) === true ? { t: tEn, formatNumber: formatNumberEn } : { t, formatNumber };
}
