// SPDX-License-Identifier: Apache-2.0
// Serialises the rendered report (the same element the page shows and prints) and asks the server for a
// PDF, so the file is identical on every browser. Loaded on demand (not part of the initial bundle).
import { BASE } from '../../registry';
import { stampHeadingRoles } from './reportToc';
export class PdfUnavailable extends Error {}

const CONTROLS = 'button, input, select, textarea, script, iframe, object, embed, link, [data-no-pdf], [contenteditable]';
const SELECTOR_PSEUDO = /::?(before|after|first-line|first-letter|marker|placeholder|selection|backdrop)\b/g;

// Presentation properties that the PDF engine's own SVG renderer cannot take from the page stylesheet
// (scoped classes, var() colours): they are copied from the live computed style onto each SVG element.
const SVG_PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-opacity', 'fill-opacity', 'opacity',
  'font-size', 'font-weight', 'text-anchor', 'dominant-baseline'] as const;

/** Copies the computed presentation of every shape inside the SVG `live` onto the matching element of `copy`. */
export function inlineSvgStyles(live: Element, copy: Element): void {
  const a = Array.from(live.querySelectorAll('*'));
  const b = Array.from(copy.querySelectorAll('*'));
  if (a.length !== b.length) return;
  a.forEach((src, i) => {
    const dst = b[i]!;
    if (!(src instanceof SVGElement)) return;
    const cs = getComputedStyle(src);
    for (const prop of SVG_PROPS) {
      const v = cs.getPropertyValue(prop).trim();
      if (v && v !== 'normal' && v !== 'auto') dst.setAttribute(prop, v);
    }
    dst.removeAttribute('vector-effect');
  });
}

/** The page's report title is an h2 under the page's own h1: in the PDF the report is the whole document, so
 *  every heading moves up one level (h2 -> h1 ... h6 -> h5) and the outline is a real h1-h4 sequence. */
export function shiftHeadings(root: ParentNode): void {
  stampHeadingRoles(root);
  root.querySelectorAll<HTMLElement>('h2, h3, h4, h5, h6').forEach((h) => {
    const next = document.createElement(`h${Number(h.tagName[1]) - 1}`);
    for (const attr of Array.from(h.attributes)) next.setAttribute(attr.name, attr.value);
    next.append(...Array.from(h.childNodes));
    h.replaceWith(next);
  });
}

/** Clone of the report without interactive controls; every <details> open so its text is printed. */
export function serializeReport(root: HTMLElement): string {
  const clone = root.cloneNode(true) as HTMLElement;
  shiftHeadings(clone);
  const liveSvgs = Array.from(root.querySelectorAll('svg'));
  const copySvgs = Array.from(clone.querySelectorAll('svg'));
  if (liveSvgs.length === copySvgs.length) liveSvgs.forEach((svg, i) => inlineSvgStyles(svg, copySvgs[i]!));
  // canvases drawn for the report (Moon with the sites) travel as PNG data: URIs, the only image form the PDF engine accepts
  const liveCanvases = Array.from(root.querySelectorAll<HTMLCanvasElement>('canvas[data-pdf-image]'));
  const copyCanvases = Array.from(clone.querySelectorAll('canvas[data-pdf-image]'));
  if (liveCanvases.length === copyCanvases.length) liveCanvases.forEach((live, i) => {
    let url = '';
    try {
      // a drawing made for the dark page (data-pdf-image="dark") is painted on its own dark ground so that its light strokes stay visible
      if (live.getAttribute('data-pdf-image') === 'dark') {
        const flat = document.createElement('canvas'); flat.width = live.width; flat.height = live.height;
        const fx = flat.getContext('2d');
        if (fx) { fx.fillStyle = '#05070b'; fx.fillRect(0, 0, flat.width, flat.height); fx.drawImage(live, 0, 0); url = flat.toDataURL('image/png'); }
      } else url = live.toDataURL('image/png');
    } catch { url = ''; }
    if (!url.startsWith('data:image/png;base64,')) return;
    const img = document.createElement('img');
    img.setAttribute('src', url);
    img.setAttribute('alt', live.getAttribute('aria-label') ?? '');
    // data-pdf-width: the width in CSS pixels the picture must have on the page (a table cell: the engine ignores max-width there)
    const want = Number(live.getAttribute('data-pdf-width'));
    const wpx = want > 0 ? want : live.width;
    img.setAttribute('width', String(wpx));
    img.setAttribute('height', String(want > 0 ? Math.round((want * live.height) / live.width) : live.height));
    img.className = 'rp-moon-img';
    copyCanvases[i]!.replaceWith(img);
  });
  clone.querySelectorAll(CONTROLS).forEach((el) => el.remove());
  clone.querySelectorAll('details').forEach((el) => el.setAttribute('open', ''));
  clone.setAttribute('data-report-root', '');
  return clone.outerHTML;
}

function relevant(root: Element, selector: string): boolean {
  if (/^body\s+\*$/.test(selector.trim())) return false; // print rule that hides the page chrome: it would also hide the PDF header/footer
  if (/(^|[\s,])(:root|html|body|\*)([\s,.:#[>+~]|$)/.test(selector)) return true;
  try {
    const plain = selector.replace(SELECTOR_PSEUDO, '');
    return root.matches(plain) || root.querySelector(plain) !== null;
  } catch { return true; }
}

function mediaApplies(text: string): boolean {
  const t = text.trim().toLowerCase();
  return t === '' || t === 'all' || t === 'print' || t === 'only print' || t === 'print, screen' || t === 'screen, print';
}

function ruleText(rule: CSSRule, root: Element): string {
  if (rule instanceof CSSStyleRule) return relevant(root, rule.selectorText) ? rule.cssText : '';
  if (rule instanceof CSSMediaRule) {
    if (!mediaApplies(rule.media.mediaText)) return '';
    const inner = Array.from(rule.cssRules).map((r) => ruleText(r, root)).join('\n');
    return inner ? `@media print { ${inner} }` : '';
  }
  if ((typeof CSSSupportsRule !== 'undefined' && rule instanceof CSSSupportsRule) || (typeof CSSLayerBlockRule !== 'undefined' && rule instanceof CSSLayerBlockRule)) {
    return Array.from((rule as CSSGroupingRule).cssRules).map((r) => ruleText(r, root)).join('\n');
  }
  return ''; // @font-face (the server embeds its own font), @keyframes, @page (the server decides), @import
}

/** Stylesheet rules of the page that apply to the report (screen look plus the print rules). */
export function collectReportCss(root: Element, sheets: StyleSheetList = document.styleSheets): string {
  const parts: string[] = [];
  for (const sheet of Array.from(sheets)) {
    let rules: CSSRuleList;
    try { rules = sheet.cssRules; } catch { continue; }
    for (const rule of Array.from(rules)) {
      const text = ruleText(rule, root);
      if (text) parts.push(text);
    }
  }
  return parts.join('\n');
}

export interface PdfJob { root: HTMLElement; title: string; subtitle: string; lang: 'it' | 'en'; created: string; filename: string }

export function buildPdfPayload(job: PdfJob, css: string, markup: string) {
  const html = `<style>${css}</style>${markup}`;
  return { html, title: job.title, subtitle: job.subtitle, lang: job.lang, created: job.created, filename: job.filename };
}

/** Returns the PDF, or throws PdfUnavailable when the server cannot produce it (503/404/network). */
export async function fetchReportPdf(job: PdfJob, signal?: AbortSignal): Promise<Blob> {
  const payload = buildPdfPayload(job, collectReportCss(job.root), serializeReport(job.root));
  let response: Response;
  try {
    response = await fetch(`${BASE}api/raven/report/pdf`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new PdfUnavailable('network');
  }
  if (!response.ok) throw new PdfUnavailable(String(response.status));
  if (!(response.headers.get('content-type') ?? '').includes('application/pdf')) throw new PdfUnavailable('type');
  return response.blob();
}

export function saveBlob(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
