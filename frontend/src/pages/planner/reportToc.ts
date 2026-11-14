// SPDX-License-Identifier: Apache-2.0
// Table of contents of the report, built from the headings that are really rendered (so it follows the
// section picker): phases 0-F, ESG, reliability, appendix and the other main sections.
export interface TocEntry { id: string; text: string; level: 1 | 2 }

const HEADINGS = 'h3';
const slug = (text: string) => text.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);

const ROLES: Record<string, string> = { H2: 'cover', H3: 'section', H4: 'sub', H5: 'minor', H6: 'minor' };

/** Marks each heading with its role in the report (print styles key on it, whatever tag the PDF later uses). */
export function stampHeadingRoles(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>('h2, h3, h4, h5, h6').forEach((h) => {
    if (!h.hasAttribute('data-rp')) h.setAttribute('data-rp', ROLES[h.tagName]!);
  });
}

/** Gives every h3/h4 an id (kept when already present) and returns the entries in document order. */
export function collectToc(root: ParentNode): TocEntry[] {
  stampHeadingRoles(root);
  const entries: TocEntry[] = [];
  const used = new Set<string>();
  let n = 0;
  root.querySelectorAll<HTMLElement>(HEADINGS).forEach((h) => {
    if (h.closest('[data-toc-skip]')) return;
    const text = (h.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (!text) return;
    n += 1;
    let id = h.id;
    if (!id || used.has(id)) {
      id = `rpt-${n}-${slug(text) || 'section'}`;
      h.id = id;
    }
    used.add(id);
    entries.push({ id, text, level: h.tagName === 'H3' ? 1 : 2 });
  });
  return entries;
}

const same = (a: TocEntry[], b: TocEntry[]) =>
  a.length === b.length && a.every((e, i) => e.id === b[i]!.id && e.text === b[i]!.text && e.level === b[i]!.level);

/** Svelte action: keeps `onentries` up to date while the report content changes. */
export function reportToc(node: HTMLElement, onentries: (entries: TocEntry[]) => void) {
  let last: TocEntry[] = [];
  let frame = 0;
  const run = () => {
    frame = 0;
    const next = collectToc(node);
    if (!same(last, next)) { last = next; onentries(next); }
  };
  const schedule = () => { if (!frame) frame = requestAnimationFrame(run); };
  const observer = new MutationObserver(schedule);
  observer.observe(node, { childList: true, subtree: true, characterData: true });
  schedule();
  return {
    update(next: (entries: TocEntry[]) => void) { onentries = next; },
    destroy() { observer.disconnect(); if (frame) cancelAnimationFrame(frame); },
  };
}
