// SPDX-License-Identifier: Apache-2.0
// One model: no page may call the legacy endpoints (/api/lunar/*, /api/grazing/*) that compute with older rules.
// The allow-list names the files that still do, each with its reason; a new use fails this test.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function walk(dir: string, out: string[] = []): string[] {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|svelte)$/.test(n) && !/\.test\.ts$/.test(n)) out.push(p);
  }
  return out;
}
const isComment = (l: string) => /^\s*(\/\/|\/\*|\*|<!--)/.test(l);

describe('no page calls the legacy endpoints', () => {
  it('no production code calls lunar, grazing or standalone sky endpoints', () => {
    const hits: string[] = [];
    for (const f of walk(SRC)) {
      const rel = relative(SRC, f);
      readFileSync(f, 'utf8').split('\n').forEach((l, i) => {
        if (/\/api\/(lunar|grazing|sky)\//.test(l) && !isComment(l)) hits.push(`${rel}:${i + 1}`);
      });
    }
    expect(hits).toEqual([]);
  });
});
