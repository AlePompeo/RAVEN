// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { analyzeBundle, htmlScripts, type ManifestChunk } from '../../scripts/bundleCheck.mjs';

const manifest: Record<string, ManifestChunk> = {
  'index.html': { file: 'assets/index-AAA.js', isEntry: true, imports: ['_shared.js'], dynamicImports: ['src/viewports/threeViewport.ts'] },
  '_shared.js': { file: 'assets/shared-BBB.js' },
  'src/viewports/threeViewport.ts': {
    file: 'assets/threeViewport-CCC.js',
    imports: ['node_modules/three/build/three.module.js'],
  },
  'node_modules/three/build/three.module.js': { file: 'assets/three.module-DDD.js' },
};
const files: Record<string, string> = {
  'assets/index-AAA.js': 'console.log(1)',
  'assets/shared-BBB.js': 'export{}',
  'assets/threeViewport-CCC.js': 'x',
  'assets/three.module-DDD.js': 'class WebGLRenderer{}',
};
const readFile = (f: string) => new TextEncoder().encode(files[f] ?? '');
const run = (html: string, m = manifest, maxBytes = 1000) => analyzeBundle({ html, manifest: m, readFile, maxBytes });
const clean = '<script type="module" crossorigin src="/assets/index-AAA.js"></script>';
const text = (r: { problems: string[] }) => r.problems.join('\n');

describe('analyzeBundle', () => {
  it('passes for a clean graph, ignoring dynamic chunks', () => {
    const r = run(clean);
    expect(r.problems).toEqual([]);
    expect([...r.chunks].sort()).toEqual(['_shared.js', 'index.html']);
  });

  it('fails when the entry statically imports the three chunk', () => {
    const m = structuredClone(manifest);
    m['_shared.js']!.imports = ['node_modules/three/build/three.module.js'];
    const r = run(clean, m);
    expect(text(r)).toMatch(/modulo vietato/);
    expect(text(r)).toMatch(/chunk vietato/);
  });

  it('fails on an absolute-URL modulepreload of the three chunk', () => {
    const r = run(`${clean}<link rel="modulepreload" href="https://cdn.example/base/assets/three.module-DDD.js">`);
    expect(text(r)).toMatch(/modulo vietato/);
  });

  it('parses single-quoted and unquoted attributes', () => {
    expect(htmlScripts(`<script type='module' src='/assets/index-AAA.js'></script>`)).toEqual(
      new Set(['assets/index-AAA.js']),
    );
    expect(htmlScripts('<link rel=modulepreload href=/assets/x.js>')).toEqual(new Set(['assets/x.js']));
    const r = run(`${clean}<link rel='modulepreload' href='/assets/three.module-DDD.js'>`);
    expect(text(r)).toMatch(/modulo vietato/);
  });

  it('fails when over budget, and when html references a chunk missing from the manifest', () => {
    expect(text(run(clean, manifest, 5))).toMatch(/supera la soglia/);
    expect(text(run('<script src="/assets/ghost-ZZZ.js"></script>'))).toMatch(/assente dal manifest/);
  });

  it('secondary code-marker check catches innocent-looking names', () => {
    const m = structuredClone(manifest);
    m['_shared.js']!.file = 'assets/vendor-EEE.js';
    files['assets/vendor-EEE.js'] = 'new WebGLRenderer()';
    expect(text(run(clean, m))).toMatch(/WebGLRenderer/);
  });
});
