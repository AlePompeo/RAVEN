// SPDX-License-Identifier: Apache-2.0
export interface LicenseEntry {
  name: string;
  version: string;
  license: string;
}

/** Formato atteso da CI: array di {name, version, license}. Voci malformate scartate. */
export function parseLicenses(data: unknown): LicenseEntry[] {
  if (!Array.isArray(data)) return [];
  const out: LicenseEntry[] = [];
  for (const e of data as unknown[]) {
    if (typeof e !== 'object' || e === null) continue;
    const { name, version, license } = e as Record<string, unknown>;
    if (typeof name !== 'string' || typeof license !== 'string') continue;
    out.push({ name, version: typeof version === 'string' ? version : '', license });
  }
  return out;
}

/** Legge /licenses.json; file assente, non JSON o rete giu -> elenco vuoto. */
export type LicensesResult =
  | { status: 'ok'; entries: LicenseEntry[] }
  | { status: 'empty' } // file presente ma senza voci valide
  | { status: 'absent' } // 404: non ancora generato da CI
  | { status: 'error' }; // rete, errore HTTP o contenuto non JSON

export async function loadLicenses(fetchFn: typeof fetch): Promise<LicensesResult> {
  try {
    const res = await fetchFn('/licenses.json');
    if (res.status === 404) return { status: 'absent' };
    if (!res.ok) return { status: 'error' };
    const entries = parseLicenses(JSON.parse(await res.text()));
    return entries.length > 0 ? { status: 'ok', entries } : { status: 'empty' };
  } catch {
    return { status: 'error' };
  }
}
