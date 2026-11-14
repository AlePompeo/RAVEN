// SPDX-License-Identifier: Apache-2.0
// Markdown-lite sicuro: il testo diventa un albero di nodi che Svelte rende con elementi veri. Nessun
// innerHTML, nessun {@html}, nessun link o immagine dal testo: tutto ciò che non è riconosciuto resta testo.
// Supporta: paragrafi, **grassetto**, `codice`, elenchi (- * 1.), blocchi ``` ```, tabelle |a|b|,
// intestazioni #, la riga "Formula: ..." e l'elenco "Variabili:" dell'assistente estrattivo.
// I marcatori di citazione [id] / [a, b] diventano nodi 'cite' SOLO se l'id è tra quelli noti.

export type Inline =
  | { t: 'text'; v: string }
  | { t: 'code'; v: string }
  | { t: 'bold'; c: Inline[] }
  | { t: 'cite'; id: string };

export interface VarRow {
  symbol: string;
  name: string;
  unit: string;
  range: string;
}

export type Block =
  | { t: 'p'; lines: Inline[][] }
  | { t: 'h'; level: 3 | 4; c: Inline[] }
  | { t: 'ul'; items: Inline[][] }
  | { t: 'ol'; items: Inline[][] }
  | { t: 'pre'; v: string }
  | { t: 'formula'; v: string }
  | { t: 'vars'; rows: VarRow[] }
  | { t: 'table'; head: string[]; rows: string[][]; after: string };

const ID = '[A-Za-z0-9][A-Za-z0-9._-]{0,63}';
const CITE = new RegExp(`^\\[(${ID}(?:\\s*,\\s*${ID})*)\\]`);

const MAX_DEPTH = 3;

export function parseInline(src: string, known: ReadonlySet<string>, depth = 0): Inline[] {
  const out: Inline[] = [];
  let buf = '';
  const flush = () => {
    if (buf !== '') {
      out.push({ t: 'text', v: buf });
      buf = '';
    }
  };
  let i = 0;
  while (i < src.length) {
    const ch = src[i]!;
    if (ch === '`') {
      const end = src.indexOf('`', i + 1);
      if (end > i + 1) {
        flush();
        out.push({ t: 'code', v: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    } else if (ch === '*' && src.startsWith('**', i) && depth < MAX_DEPTH) {
      const end = src.indexOf('**', i + 2);
      if (end > i + 2) {
        flush();
        out.push({ t: 'bold', c: parseInline(src.slice(i + 2, end), known, depth + 1) });
        i = end + 2;
        continue;
      }
    } else if (ch === '[') {
      const m = CITE.exec(src.slice(i, i + 400));
      if (m) {
        const ids = m[1]!.split(',').map((s) => s.trim());
        if (ids.some((id) => known.has(id))) {
          flush();
          for (const id of ids) {
            if (known.has(id)) out.push({ t: 'cite', id });
            else out.push({ t: 'text', v: `[${id}]` }); // id non noto: testo semplice, mai un collegamento
          }
          i += m[0].length;
          continue;
        }
      }
    }
    buf += ch;
    i++;
  }
  flush();
  return out;
}

const BULLET = /^\s*(?:[-*•])\s+(.*)$/;
const ORDERED = /^\s*\d{1,3}[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;
const VAR_ROW = /^(.+?) = (.+?)(?: \[([^\]]+)\])?(?:, intervallo (.+))?$/;

function tableCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());
}

/**
 * Tabella su righe separate o "appiattita" su una riga sola dall'estrattivo ("| a | b | | 1 | 2 |"):
 * le righe si separano su "| |". Le celle oltre la larghezza dell'intestazione sono testo che segue la tabella.
 */
function parseTable(lines: string[]): Block | null {
  const rowsRaw: string[] = [];
  for (const l of lines) {
    const t = l.trim();
    if (t.includes('| |')) rowsRaw.push(...t.split(/\|\s+\|(?=\s)/).map((p) => `|${p.replace(/^\|/, '').replace(/\|$/, '')}|`));
    else rowsRaw.push(t);
  }
  const rows = rowsRaw.map(tableCells).filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c) || c === ''));
  const head = rows[0];
  if (!head || head.length < 2 || rows.length < 2) return null;
  const n = head.length;
  const body = rows.slice(1).map((r) => r.slice(0, n));
  const after = rows
    .slice(1)
    .map((r) => r.slice(n).join(' | '))
    .filter(Boolean)
    .join(' ');
  return { t: 'table', head, rows: body.map((r) => [...r, ...Array<string>(Math.max(0, n - r.length)).fill('')]), after };
}

function parseVars(items: string[]): VarRow[] | null {
  const rows: VarRow[] = [];
  for (const it of items) {
    const m = VAR_ROW.exec(it);
    if (!m) return null;
    rows.push({ symbol: m[1]!.trim(), name: m[2]!.trim(), unit: (m[3] ?? '').trim(), range: (m[4] ?? '').trim() });
  }
  return rows.length > 0 ? rows : null;
}

export function parseMarkdown(text: string, known: ReadonlySet<string> = new Set()): Block[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: string[] = [];

  const inl = (s: string) => parseInline(s, known);
  const flushPara = () => {
    if (para.length) blocks.push({ t: 'p', lines: para.map(inl) });
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const label = para.length ? para[para.length - 1]! : '';
    if (!list.ordered && /^Variabili:?$/i.test(label.trim())) {
      const rows = parseVars(list.items);
      if (rows) {
        para.pop();
        flushPara();
        blocks.push({ t: 'vars', rows });
        list = null;
        return;
      }
    }
    flushPara();
    blocks.push({ t: list.ordered ? 'ol' : 'ul', items: list.items.map(inl) });
    list = null;
  };
  const flushTable = () => {
    if (!table.length) return;
    const tb = parseTable(table);
    table = [];
    if (tb) {
      flushList();
      flushPara();
      blocks.push(tb);
    }
  };
  const flushAll = () => {
    flushTable();
    flushList();
    flushPara();
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    if (/^\s*```/.test(line)) {
      flushAll();
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i]!)) code.push(lines[i++]!);
      blocks.push({ t: 'pre', v: code.join('\n') });
      continue;
    }
    if (line.trim() === '') {
      flushAll();
      continue;
    }
    if (/^\s*\|/.test(line)) {
      flushList();
      flushPara();
      table.push(line);
      continue;
    }
    flushTable();
    const h = HEADING.exec(line);
    if (h) {
      flushAll();
      blocks.push({ t: 'h', level: /^\s*#{1,2}\s/.test(line) ? 3 : 4, c: inl(h[1]!) });
      continue;
    }
    const f = /^\s*Formula:\s*(.+)$/.exec(line);
    if (f) {
      flushAll();
      blocks.push({ t: 'formula', v: f[1]! });
      continue;
    }
    const b = BULLET.exec(line);
    const o = b ? null : ORDERED.exec(line);
    if (b || o) {
      const ordered = !b;
      if (list && list.ordered !== ordered) flushList();
      list ??= { ordered, items: [] };
      list.items.push((b ?? o)![1]!);
      continue;
    }
    if (list) {
      // riga di continuazione indentata di una voce, altrimenti l'elenco finisce
      if (/^\s{2,}\S/.test(line)) {
        list.items[list.items.length - 1] += ` ${line.trim()}`;
        continue;
      }
      flushList();
    }
    para.push(line);
  }
  flushAll();
  return blocks;
}

/** Id citati nel testo (anche non noti), nell'ordine di prima apparizione. */
export function citedIds(text: string): string[] {
  const seen: string[] = [];
  const re = new RegExp(`\\[(${ID}(?:\\s*,\\s*${ID})*)\\]`, 'g');
  for (let m = re.exec(text); m !== null; m = re.exec(text)) {
    for (const id of m[1]!.split(',').map((s) => s.trim())) if (!seen.includes(id)) seen.push(id);
  }
  return seen;
}
