// SPDX-License-Identifier: Apache-2.0
// Contrasto WCAG 2.x sui token reali di tokens.css (usato da contrast.test.ts).

/** Luminanza relativa WCAG di un colore #rrggbb. */
export function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`colore non valido (atteso #rrggbb): ${hex}`);
  const n = parseInt(m[1]!, 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0]! + 0.7152 * ch[1]! + 0.0722 * ch[2]!;
}

export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Colore risultante di `fg` con opacità `alpha` sopra `bg` (entrambi #rrggbb). */
export function composite(fg: string, alpha: number, bg: string): string {
  const p = (h: string) => {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const f = p(fg);
  const b = p(bg);
  return (
    '#' +
    f
      .map((v, i) => Math.round(v * alpha + b[i]! * (1 - alpha)))
      .map((v) => v.toString(16).padStart(2, '0'))
      .join('')
  );
}

/** Blocchi `@tokens:<nome> ... @end` di tokens.css -> { nome: { --var: valore } }. */
export function parseTokenBlocks(css: string): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  const re = /\/\*\s*@tokens:([\w-]+)\s*\*\/([\s\S]*?)\/\*\s*@end\s*\*\//g;
  for (const m of css.matchAll(re)) {
    const vars: Record<string, string> = {};
    for (const d of m[2]!.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[d[1]!] = d[2]!.trim();
    out[m[1]!] = vars;
  }
  return out;
}

/** `rgb(r g b / a)` -> { hex, alpha } (solo la sintassi usata in tokens.css). */
export function parseRgba(v: string): { hex: string; alpha: number } {
  const m = /^rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\/\s*([\d.]+)\s*\)$/.exec(v.trim());
  if (!m) throw new Error(`colore non valido (atteso rgb(r g b / a)): ${v}`);
  const hex = '#' + [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, '0')).join('');
  return { hex, alpha: Number(m[4]) };
}
