// SPDX-License-Identifier: Apache-2.0
// Dati dei tre piani e della tabella di confronto. Le righe vengono dal business plan (§2.2, §6.1);
// `planned: true` = funzionalità NON ancora implementata nel prodotto (etichetta "Prevista" visibile).

export type PlanId = 'free' | 'premium' | 'enterprise';
export const PLAN_IDS: readonly PlanId[] = ['free', 'premium', 'enterprise'];

export interface FeatureRow {
  id: string;
  /** Incluso in [free, premium, enterprise]. */
  in: readonly [boolean, boolean, boolean];
  planned: boolean;
}
export interface FeatureGroup {
  id: 'analysis' | 'data' | 'reports' | 'support';
  rows: readonly FeatureRow[];
}

export const GROUPS: readonly FeatureGroup[] = [
  {
    id: 'analysis',
    rows: [
      { id: 'geometry', in: [true, true, true], planned: false },
      { id: 'compare', in: [true, true, true], planned: false },
      { id: 'rf', in: [false, true, true], planned: false },
      { id: 'compensation', in: [false, true, true], planned: false },
      { id: 'multi', in: [false, true, true], planned: false },
      { id: 'relay', in: [false, false, true], planned: true },
    ],
  },
  {
    id: 'data',
    rows: [
      { id: 'sites', in: [true, true, true], planned: false },
      { id: 'custom', in: [false, true, true], planned: false },
      { id: 'hardware', in: [false, true, true], planned: false },
      { id: 'learning', in: [true, true, true], planned: false },
      { id: 'classroom', in: [false, false, true], planned: true },
    ],
  },
  {
    id: 'reports',
    rows: [
      { id: 'export', in: [false, true, true], planned: false },
      { id: 'pdf', in: [false, true, true], planned: true },
      { id: 'history', in: [false, true, true], planned: true },
      { id: 'dedicated', in: [false, false, true], planned: true },
    ],
  },
  {
    id: 'support',
    rows: [
      { id: 'accounts', in: [false, true, true], planned: true },
      { id: 'metering', in: [false, true, true], planned: true },
      { id: 'support', in: [false, true, true], planned: true },
      { id: 'priority', in: [false, false, true], planned: true },
      { id: 'multiuser', in: [false, false, true], planned: true },
      { id: 'api', in: [false, false, true], planned: true },
      { id: 'deploy', in: [false, false, true], planned: true },
    ],
  },
];
