// SPDX-License-Identifier: Apache-2.0
// Logica pura del controllo budget (testata in src/viewports/bundleCheck.test.ts).
import { gzipSync } from 'node:zlib';

const FORBIDDEN_MODULE = /(^|\/)node_modules\/(three|uplot)\//;
const FORBIDDEN_CHUNK_NAME = /(^|[\\/-])(three|uplot)[.\-_]/i;
// Secondario (difesa in profondità): marcatori nel codice minificato.
const FORBIDDEN_CODE = [/WebGLRenderer/, /\buPlot\b/];

/** Percorsi (relativi a dist) dei JS referenziati da index.html: script, modulepreload/preload; URL assoluti ok. */
export function htmlScripts(html) {
  const out = new Set();
  for (const tag of html.matchAll(/<(script|link)\b([^>]*)>/gi)) {
    const attrs = {};
    for (const m of tag[2].matchAll(/([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/g)) {
      attrs[m[1].toLowerCase()] = m[2] ?? m[3] ?? m[4];
    }
    const name = tag[1].toLowerCase();
    const url =
      name === 'script' && attrs.src
        ? attrs.src
        : name === 'link' && /\b(modulepreload|preload)\b/i.test(attrs.rel ?? '') && attrs.href
          ? attrs.href
          : null;
    if (!url) continue;
    let pathname = url;
    try {
      pathname = new URL(url, 'http://x.invalid').pathname;
    } catch {
      /* si usa com'è */
    }
    if (!/\.m?js$/.test(pathname)) continue;
    const i = pathname.indexOf('assets/');
    // fuori da assets/ ci sono i file di public/ (es. tv-init.js, classico e minuscolo): non sono chunk del manifest
    if (i >= 0) out.add(pathname.slice(i));
    else if (!/(^|\/)tv-init\.js$/.test(pathname)) out.add(pathname.replace(/^\//, ''));
  }
  return out;
}

/**
 * @param {{html: string, manifest: Record<string, {file: string, imports?: string[], isEntry?: boolean}>,
 *   readFile: (file: string) => Uint8Array, maxBytes: number}} a
 * @returns {{raw: number, gz: number, chunks: string[], problems: string[]}}
 */
export function analyzeBundle({ html, manifest, readFile, maxBytes }) {
  const problems = [];
  const byFile = new Map(Object.entries(manifest).map(([key, v]) => [v.file, key]));
  const roots = new Set();
  for (const f of htmlScripts(html)) {
    const key = byFile.get(f);
    if (key) roots.add(key);
    else problems.push(`${f} referenziato da index.html ma assente dal manifest`);
  }
  for (const [key, v] of Object.entries(manifest)) if (v.isEntry) roots.add(key);
  if (roots.size === 0) problems.push('nessun entry iniziale trovato');

  // Solo import statici (`imports`); `dynamicImports` è escluso per costruzione.
  const initial = new Set();
  const walk = (key) => {
    if (initial.has(key)) return;
    const v = manifest[key];
    if (!v) {
      problems.push(`chiave di manifest sconosciuta: ${key}`);
      return;
    }
    initial.add(key);
    (v.imports ?? []).forEach(walk);
  };
  roots.forEach(walk);

  let raw = 0;
  let gz = 0;
  for (const key of initial) {
    const { file } = manifest[key];
    if (FORBIDDEN_MODULE.test(key)) problems.push(`modulo vietato nel grafo iniziale: ${key}`);
    if (FORBIDDEN_CHUNK_NAME.test(file)) problems.push(`chunk vietato nel grafo iniziale: ${file}`);
    if (!file.endsWith('.js')) continue;
    const code = readFile(file);
    raw += code.length;
    gz += gzipSync(code).length;
    const text = Buffer.from(code).toString('utf8');
    for (const re of FORBIDDEN_CODE) if (re.test(text)) problems.push(`${file} contiene codice ${re} (three/uplot)`);
  }
  if (raw > maxBytes) problems.push(`JS iniziale ${raw} B supera la soglia ${maxBytes} B`);
  return { raw, gz, chunks: [...initial], problems };
}
