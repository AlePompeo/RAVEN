// SPDX-License-Identifier: Apache-2.0
// Intent of a message to RAVEN SI: a request to FIND sites (it opens the site search card) or a question (it goes to the assistant, which explains).
// Plain rules in Italian and English; no model, no network. A question about the search ("how does it work?") must stay a question.

const QUESTION = /^\s*(come|cosa|che cos|perch[eé]|quale|quali|quando|dove|chi|how|what|why|which|when|where|who|does|do|is|are|can|could)\b/i;
const ASK = /\b(trova|trovami|trovare|cerca|cercami|cercare|consigliami|consiglia|suggerisci|suggeriscimi|dammi|mostrami|elencami|find|search|recommend|suggest|give me|show me|list)\b/i;
const OBJECT = /\b(sit[oi]|luogh[oi]|local[ei]|candidat[oi]|sites?|places?|locations?|landing (?:sites?|spots?))\b/i;
const BEST = /\b(migliori|migliore|best|top)\s+(?:\d+\s+)?(sit[oi]|luogh[oi]|sites?|places?)\b/i;

/** True when the text asks the assistant to find (not to explain) landing sites. */
export function isSiteSearch(text: string): boolean {
  const t = text.trim();
  if (t.length < 8 || t.length > 2000) return false;
  if (QUESTION.test(t) && !/\b(dammi|trovami|give me|find me|show me)\b/i.test(t)) return false;
  return (ASK.test(t) && OBJECT.test(t)) || (BEST.test(t) && /\d/.test(t));
}
