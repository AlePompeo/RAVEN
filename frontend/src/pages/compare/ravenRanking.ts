// SPDX-License-Identifier: Apache-2.0
// Classifica unica (D5) di /api/raven/compare: logica pura. Nessun punteggio: l'ordine e' lessicografico sulle
// componenti scelte (le prime), a parita' vale l'id del sito (dichiarato). Qui si sceglie solo l'ordine da chiedere
// e si leggono le righe; il calcolo resta nel backend (raven/ranking.py).
import type { RankingRow, RavenRanking } from '../../shell/ravenApi';

export const RANK_COMPONENTS = ['useful_hours', 'unknown_hours', 'margin_min_db', 'margin_median_db', 'min_soc'] as const;
export type RankComponent = (typeof RANK_COMPONENTS)[number];
/** Ordine predefinito del modello (raven/ranking.py DEFAULT_ORDER): ore utili, ore ignote, margine minimo. */
export const DEFAULT_ORDER: readonly RankComponent[] = ['useful_hours', 'unknown_hours', 'margin_min_db'];

/** L'ordine da chiedere: il criterio scelto per primo, poi i predefiniti non ancora usati. */
export function orderFrom(first: RankComponent): RankComponent[] {
  return [first, ...DEFAULT_ORDER.filter((c) => c !== first)];
}

export interface RankedRow {
  rank: number;
  site_id: string;
  tied_with: string[];
  components: {
    margin_blocked: boolean; useful_hours: number | null; unknown_hours: number | null;
    margin_min_db: number | null; margin_median_db: number | null; min_soc: number | null;
    time_to_first_blackout_h: number | null; known_steps: number; n_steps: number;
  };
}

/** Righe della classifica con le componenti sempre presenti (un campo mancante resta null, mai 0). */
export function rankRows(r: RavenRanking): RankedRow[] {
  return r.ranking.map((row: RankingRow) => {
    const c = row.components as Record<string, number | boolean | null | undefined>;
    const n = (k: string) => (typeof c[k] === 'number' ? (c[k] as number) : null);
    return {
      rank: row.rank, site_id: row.site_id, tied_with: Array.isArray(row['tied_with']) ? (row['tied_with'] as string[]) : [],
      components: {
        margin_blocked: c['margin_blocked'] === true, useful_hours: n('useful_hours'), unknown_hours: n('unknown_hours'),
        margin_min_db: n('margin_min_db'), margin_median_db: n('margin_median_db'), min_soc: n('min_soc'),
        time_to_first_blackout_h: n('time_to_first_blackout_h'), known_steps: n('known_steps') ?? 0, n_steps: n('n_steps') ?? 0,
      },
    };
  });
}

/** Una riga che dichiara la regola: componenti nell'ordine usato, senso (piu' e' meglio o meno e' meglio), pareggio. */
export function rankingLine(r: RavenRanking, label: (c: string) => string, dir: (d: string) => string): string {
  const parts = r.order.map((c) => `${label(c)} (${dir(r.directions[c] ?? 'desc')})`);
  return `${parts.join(' > ')}; ${r.tie_break}`;
}
