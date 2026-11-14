// SPDX-License-Identifier: Apache-2.0
// Budget del bundle iniziale: fallisce se il JS iniziale (entry + grafo degli import STATICI dal
// manifest di Vite, `vite build --manifest`) supera la soglia o include three/uplot.
// La logica è in bundleCheck.mjs (testata). Uso: node scripts/check-bundle.mjs [dist-dir]
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyzeBundle } from './bundleCheck.mjs';

// Misurato il 2026-10-12: chunk iniziale 51006 B (19617 B gzip). Soglia = misura + ~25% (vedi docs/versions.md).
// 2026-10-20: 64112 B con la pagina Contatti (registro + voce nel piè di pagina, +442 B); soglia alzata di 500 B
// (docs/design/design-system.md). La pagina e i suoi dati stanno nel chunk lazy, non qui.
// 2026-10-27: 64553 B con la navigazione TV della shell (freccia giù dalla barra -> primo controllo della pagina,
// pulsante fluttuante "Spiega" per ultimo); soglia alzata di 500 B (docs/design/design-system.md §12).
// 2026-10-27: 69825 B con l'i18n della shell (t(), catalogo inglese del primo rendering, selettore della lingua) al netto
// della navigazione spaziale TV resa lazy (-3,5 kB); soglia alzata a 70000 B, il tetto concordato (design-system.md §12).
export const MAX_INITIAL_JS_BYTES = 70000;

const dist = resolve(process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'dist'));
const indexPath = join(dist, 'index.html');
const manifestPath = join(dist, '.vite', 'manifest.json');
for (const p of [indexPath, manifestPath]) {
  if (!existsSync(p)) {
    console.error(`check-bundle: ${p} non trovato. Esegui prima "npm run build" (usa --manifest).`);
    process.exit(2);
  }
}

const r = analyzeBundle({
  html: readFileSync(indexPath, 'utf8'),
  manifest: JSON.parse(readFileSync(manifestPath, 'utf8')),
  readFile: (f) => readFileSync(join(dist, f)),
  maxBytes: MAX_INITIAL_JS_BYTES,
});
console.log(`JS iniziale: ${r.raw} B raw, ${r.gz} B gzip, ${r.chunks.length} chunk (soglia ${MAX_INITIAL_JS_BYTES} B raw)`);
if (r.problems.length) {
  for (const p of r.problems) console.error(`check-bundle: ${p}`);
  process.exit(1);
}
console.log('check-bundle: OK');
