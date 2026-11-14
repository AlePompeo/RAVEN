// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it, vi } from 'vitest';
import { buildPdfPayload, collectReportCss, fetchReportPdf, PdfUnavailable, serializeReport } from './reportPdf';
import { collectToc } from './reportToc';

afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = ''; document.head.innerHTML = ''; });

function report(): HTMLElement {
  const el = document.createElement('article');
  el.className = 'report-preview';
  el.innerHTML = `<header><h2>Report</h2></header>
    <section><h3>Phase 0</h3><button>Edit</button><input value="x"><svg viewBox="0 0 1 1"><title>chart</title><path d="M0 0"/></svg>
      <details><summary>Config</summary><p>kept</p></details><h4>ESG</h4></section>
    <section><h3>Costs</h3><script>alert(1)</script><p data-no-pdf>hidden</p></section>`;
  document.body.append(el);
  return el;
}

it('serialises the report without interactive controls and with the details open', () => {
  const html = serializeReport(report());
  expect(html).not.toMatch(/<(button|input|script)/);
  expect(html).not.toContain('hidden');
  expect(html).toContain('data-report-root');
  expect(html).toContain('<path d="M0 0">'); // chart kept as inline SVG
  expect(html).toMatch(/<details[^>]* open/);
  expect(html).toContain('<title>chart</title>');
});

it('builds the short table of contents from h3 (parts and appendices only) and gives each heading a stable id', () => {
  const root = report();
  const nav = document.createElement('nav');
  nav.setAttribute('data-toc-skip', '');
  nav.innerHTML = '<h3>Contents</h3>';
  root.prepend(nav);
  const entries = collectToc(root);
  expect(entries.map((e) => [e.text, e.level])).toEqual([['Phase 0', 1], ['Costs', 1]]); // h4 (ESG) is a subsection, not in the contents
  expect(new Set(entries.map((e) => e.id)).size).toBe(2);
  for (const e of entries) expect(root.querySelector(`#${e.id}`)).not.toBeNull();
  expect(collectToc(root)).toEqual(entries); // idempotent: ids are kept
});

it('keeps existing ids and de-duplicates repeated ones', () => {
  const root = document.createElement('div');
  root.innerHTML = '<h3 id="a">One</h3><h3 id="a">Two</h3>';
  const ids = collectToc(root).map((e) => e.id);
  expect(ids[0]).toBe('a');
  expect(ids[1]).not.toBe('a');
});

it('copies the computed SVG presentation onto the serialised shapes (the PDF engine ignores page classes and var())', () => {
  document.head.innerHTML = '<style>:root{--k:#112233} .ln{fill:none;stroke:var(--k);stroke-width:2}</style>';
  const el = document.createElement('article');
  el.innerHTML = '<svg viewBox="0 0 10 10"><polyline class="ln" points="0,0 5,5"/></svg>';
  document.body.append(el);
  const html = serializeReport(el);
  expect(html).toMatch(/<polyline[^>]*fill="none"/);
  expect(html).toMatch(/stroke-width="2/);
});

it('moves every heading up one level (real h1-h4 outline) and keeps its role, id and text', () => {
  const root = document.createElement('article');
  root.innerHTML = '<h2>Title</h2><h3 id="s">Section</h3><h4>Sub</h4><h5>Minor</h5><h6>Tiny</h6>';
  document.body.append(root);
  const html = serializeReport(root);
  expect(html).toMatch(/<h1[^>]*data-rp="cover"[^>]*>Title<\/h1>/);
  expect(html).toMatch(/<h2[^>]*id="s"[^>]*data-rp="section"[^>]*>Section<\/h2>/);
  expect(html).toMatch(/<h3[^>]*data-rp="sub"[^>]*>Sub<\/h3>/);
  expect(html).toMatch(/<h4[^>]*data-rp="minor"[^>]*>Minor<\/h4>/);
  expect(html).not.toContain('<h6');
  expect(root.querySelector('h2')!.textContent).toBe('Title'); // the page itself is untouched
});

it('collects only the stylesheet rules that apply to the report', () => {
  const style = document.createElement('style');
  style.textContent = `.report-preview h3 { color: red } .other { color: blue }
    @media print { .report-preview { margin: 0 } body * { visibility: hidden } } @media (max-width: 500px) { .report-preview { gap: 1px } }
    @font-face { font-family: X; src: url(/assets/x.woff2) } :root { --a: 1 }`;
  document.head.append(style);
  const css = collectReportCss(report());
  expect(css).toContain('.report-preview h3');
  expect(css).toContain('margin: 0');
  expect(css).toContain('--a');
  expect(css).not.toContain('.other');
  expect(css).not.toContain('visibility: hidden');
  expect(css).not.toContain('max-width');
  expect(css).not.toContain('font-face');
});

it('posts the serialised report and treats 503 and non-PDF answers as unavailable', async () => {
  const root = report();
  const job = { root, title: 'T', subtitle: 'S', lang: 'en' as const, created: '2026-11-09T10:00:00Z', filename: 'f' };
  const payload = buildPdfPayload(job, 'p{}', '<p>x</p>');
  expect(payload).toMatchObject({ html: '<style>p{}</style><p>x</p>', title: 'T', lang: 'en', created: job.created });
  const fetchMock = vi.fn().mockResolvedValue(new Response('%PDF', { status: 200, headers: { 'content-type': 'application/pdf' } }));
  vi.stubGlobal('fetch', fetchMock);
  expect((await fetchReportPdf(job)).size).toBe(4);
  expect(fetchMock.mock.calls[0]![0]).toMatch(/api\/raven\/report\/pdf$/);
  fetchMock.mockResolvedValue(new Response('{}', { status: 503 }));
  await expect(fetchReportPdf(job)).rejects.toMatchObject({ message: '503' });
  fetchMock.mockResolvedValue(new Response('<html>', { status: 200, headers: { 'content-type': 'text/html' } }));
  await expect(fetchReportPdf(job)).rejects.toBeInstanceOf(PdfUnavailable);
  fetchMock.mockRejectedValue(new TypeError('offline'));
  await expect(fetchReportPdf(job)).rejects.toMatchObject({ message: 'network' });
});
