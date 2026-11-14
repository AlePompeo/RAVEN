// SPDX-License-Identifier: Apache-2.0
// JSON.parse keeps the LAST of two equal keys: a new key that reuses an existing name silently changes another screen.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('catalogs', () => {
  for (const file of ['en.json', 'en.pages.json', 'it.json']) {
    it(`${file} has no duplicated key`, () => {
      const keys = [...readFileSync(resolve(here, file), 'utf8').matchAll(/^\s+"([^"]+)":/gm)].map((m) => m[1]!);
      const seen = new Set<string>();
      const dup = keys.filter((k) => (seen.has(k) ? true : (seen.add(k), false)));
      expect(dup).toEqual([]);
    });
  }
});
