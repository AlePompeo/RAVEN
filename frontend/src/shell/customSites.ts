// SPDX-License-Identifier: Apache-2.0
// Siti personalizzati (RAVEN S0): definizione, validazione, normalizzazione della longitudine e codifica compatta per
// l'URL (`cs=`) e sessionStorage. Ogni valore letto da URL o storage e' non fidato: chi non passa la validazione viene
// scartato senza errore ne' eco. Gli stessi limiti sono ripetuti dal backend (backend/api/raven_custom.py).

export const MAX_CUSTOM_SITES = 8;
export const CUSTOM_PREFIX = 'c-';
export const CUSTOM_ID_RE = /^c-[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/;
export const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._,()'-]{0,39}$/;
export const HEIGHT_RANGE = [0.1, 100] as const;
/** Lunghezza massima della stringa `cs`: 8 siti da circa 90 caratteri al massimo. */
export const MAX_ENCODED = 900;
const NUM_RE = /^-?\d{1,3}(?:\.\d{1,6})?$/;
const HEIGHT_RE = /^\d{1,3}(?:\.\d{1,3})?$/;

export interface CustomSiteDef {
  id: string;
  name: string;
  lat_deg: number;
  lon_deg_east: number;
  panel_height_m?: number;
  antenna_height_m?: number;
}
export type CustomField = 'name' | 'lat' | 'lon' | 'panel' | 'antenna';
export type CustomIssue = 'required' | 'range' | 'format';
export type CustomErrors = Partial<Record<CustomField, CustomIssue>>;

export const isCustomId = (id: unknown): id is string => typeof id === 'string' && CUSTOM_ID_RE.test(id);

const round5 = (v: number): number => Number(v.toFixed(5));

/** Longitudine est in (-180, 180]; accetta anche 0..360. Fuori da [-180, 360] -> null. */
export function normaliseLon(lon: number): number | null {
  if (!Number.isFinite(lon) || lon < -180 || lon > 360) return null;
  const w = ((((lon + 180) % 360) + 360) % 360) - 180;
  return w === -180 && lon >= 180 ? 180 : w;
}

/** Numero da un campo di testo (virgola decimale ammessa); null se vuoto o non numerico. */
export function parseNumber(raw: unknown): number | null {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw !== 'string') return null;
  const s = raw.trim().replace(',', '.');
  if (s === '' || s.length > 16 || !/^[+-]?\d+(?:\.\d+)?$/.test(s)) return null;
  const v = Number(s);
  return Number.isFinite(v) ? v : null;
}

export interface CustomForm { name: string; lat: unknown; lon: unknown; panel?: unknown; antenna?: unknown }

/** Valida i campi del modulo; restituisce il sito (senza id) o i messaggi per campo. */
export function validateForm(f: CustomForm): { ok: true; value: Omit<CustomSiteDef, 'id'> } | { ok: false; errors: CustomErrors } {
  const errors: CustomErrors = {};
  const name = typeof f.name === 'string' ? f.name.trim() : '';
  if (name === '') errors.name = 'required';
  else if (!NAME_RE.test(name)) errors.name = 'format';
  const lat = parseNumber(f.lat);
  if (f.lat === '' || f.lat === null || f.lat === undefined) errors.lat = 'required';
  else if (lat === null) errors.lat = 'format';
  else if (lat < -90 || lat > 90) errors.lat = 'range';
  const lonRaw = parseNumber(f.lon);
  let lon: number | null = null;
  if (f.lon === '' || f.lon === null || f.lon === undefined) errors.lon = 'required';
  else if (lonRaw === null) errors.lon = 'format';
  else {
    lon = normaliseLon(lonRaw);
    if (lon === null) errors.lon = 'range';
  }
  const heights: Partial<Record<'panel' | 'antenna', number>> = {};
  for (const k of ['panel', 'antenna'] as const) {
    const raw = f[k];
    if (raw === undefined || raw === null || raw === '') continue;
    const v = parseNumber(raw);
    if (v === null) errors[k] = 'format';
    else if (v < HEIGHT_RANGE[0] || v > HEIGHT_RANGE[1]) errors[k] = 'range';
    else heights[k] = v;
  }
  if (Object.keys(errors).length || lat === null || lon === null) return { ok: false, errors };
  return {
    ok: true,
    value: {
      name,
      lat_deg: round5(lat),
      lon_deg_east: round5(lon),
      ...(heights.panel !== undefined ? { panel_height_m: heights.panel } : {}),
      ...(heights.antenna !== undefined ? { antenna_height_m: heights.antenna } : {}),
    },
  };
}

/** Identificatore `c-<nome>` unico fra quelli gia' presi (mai uguale a un id del catalogo). */
export function makeId(name: string, taken: ReadonlySet<string>): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24).replace(/-+$/g, '') || 'site';
  let id = `${CUSTOM_PREFIX}${slug}`;
  for (let n = 2; taken.has(id); n++) id = `${CUSTOM_PREFIX}${slug}-${n}`.slice(0, 33);
  return id;
}

/** `id~lat~lon~nome[~pannello~antenna]` separati da `!` (ne' `~` ne' `!` possono comparire nei nomi). */
export function encodeCustom(list: readonly CustomSiteDef[]): string {
  return list
    .slice(0, MAX_CUSTOM_SITES)
    .map((s) => [s.id, s.lat_deg, s.lon_deg_east, s.name, ...(s.panel_height_m !== undefined || s.antenna_height_m !== undefined ? [s.panel_height_m ?? '', s.antenna_height_m ?? ''] : [])].join('~'))
    .join('!');
}

/** Lettura rigorosa: valori fuori dominio, duplicati, ecc. sono scartati; al massimo 8 siti; stringhe troppo lunghe -> []. */
export function parseCustom(raw: string | null | undefined): CustomSiteDef[] {
  if (typeof raw !== 'string' || raw === '' || raw.length > MAX_ENCODED) return [];
  const out: CustomSiteDef[] = [];
  const seen = new Set<string>();
  for (const item of raw.split('!')) {
    if (out.length >= MAX_CUSTOM_SITES) break;
    const f = item.split('~');
    if (f.length !== 4 && f.length !== 6) continue;
    const [id, la, lo, name, ph = '', ah = ''] = f as [string, string, string, string, string?, string?];
    if (!isCustomId(id) || seen.has(id) || !NUM_RE.test(la) || !NUM_RE.test(lo) || !NAME_RE.test(name)) continue;
    const lat = Number(la);
    const lon = normaliseLon(Number(lo));
    if (lat < -90 || lat > 90 || lon === null) continue;
    const site: CustomSiteDef = { id, name, lat_deg: round5(lat), lon_deg_east: round5(lon) };
    let bad = false;
    for (const [raw2, key] of [[ph, 'panel_height_m'], [ah, 'antenna_height_m']] as const) {
      if (raw2 === '') continue;
      const v = HEIGHT_RE.test(raw2) ? Number(raw2) : NaN;
      if (!(v >= HEIGHT_RANGE[0] && v <= HEIGHT_RANGE[1])) bad = true;
      else site[key] = v;
    }
    if (bad) continue;
    seen.add(id);
    out.push(site);
  }
  return out;
}

/** Parametro `custom` dello snapshot: `id|nome|lat|lon[|pannello|antenna]` separati da `;` (stringa vuota se non ce ne sono). */
export function snapshotParam(list: readonly CustomSiteDef[]): string {
  return list
    .map((d) => [d.id, d.name, d.lat_deg, d.lon_deg_east, ...(d.panel_height_m !== undefined || d.antenna_height_m !== undefined ? [d.panel_height_m ?? 2, d.antenna_height_m ?? 2] : [])].join('|'))
    .join(';');
}

/** Forma accettata dall'API (`CustomSiteIn`). */
export function toApi(d: CustomSiteDef): CustomSiteDef {
  return {
    id: d.id, name: d.name, lat_deg: d.lat_deg, lon_deg_east: d.lon_deg_east,
    ...(d.panel_height_m !== undefined ? { panel_height_m: d.panel_height_m } : {}),
    ...(d.antenna_height_m !== undefined ? { antenna_height_m: d.antenna_height_m } : {}),
  };
}

/** Lista dei siti personalizzati condivisa dal client e dalle pagine (aggiornata dal componente di controllo). */
type Listener = (list: readonly CustomSiteDef[]) => void;
let current: readonly CustomSiteDef[] = [];
const listeners = new Set<Listener>();
export const customSites = {
  get: (): readonly CustomSiteDef[] => current,
  find: (id: string): CustomSiteDef | undefined => current.find((s) => s.id === id),
  /** Sostituisce la lista (gia' validata dal chiamante o da `parseCustom`). */
  set(list: readonly CustomSiteDef[]): void {
    const next = parseCustom(encodeCustom(list));
    if (encodeCustom(next) === encodeCustom(current)) return;
    current = next;
    for (const l of listeners) l(current);
  },
  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    fn(current);
    return () => listeners.delete(fn);
  },
};
