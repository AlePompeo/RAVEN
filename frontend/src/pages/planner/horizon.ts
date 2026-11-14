// SPDX-License-Identifier: Apache-2.0
import type { RavenClient } from '../../shell/ravenApi';
import { horizonFromRaven } from './ravenAdapter';
export interface HorizonSample {
  azimuth_deg: number;
  elevation_deg: number | null;
  distance_m: number | null;
  state: 'ok' | 'missing_dem' | 'outside_coverage';
}

export interface HorizonResult {
  model_version?: string;
  registry_sha256?: string;
  site: { id: string; name: string };
  samples: HorizonSample[];
  dem_product: string;
  dem_sha256: string;
  dem_label_sha256: string;
  lunar_frame: string;
  profile_length_m: number;
  profile_spacing_m: number;
  azimuth_step_deg: number;
  observer_height_m: number;
  limits: string;
  dem_policy: string;
}

export type HorizonFetch =
  | { ok: true; data: HorizonResult }
  | { ok: false; kind: 'network' | 'invalid' | 'unavailable' | 'server' };

/** Orizzonte dal modello unico (/api/raven/horizon): la stessa maschera usata da luce e collegamento. */
export async function fetchHorizon(
  client: RavenClient,
  siteId: string,
  height: number,
  signal: AbortSignal,
): Promise<HorizonFetch> {
  const r = await client.horizon({ site: siteId, height_m: height }, { signal });
  if (!r.ok) return { ok: false, kind: r.kind === 'invalid' ? 'invalid' : r.kind === 'unavailable' ? 'unavailable' : r.kind === 'network' || r.kind === 'aborted' ? 'network' : 'server' };
  return { ok: true, data: horizonFromRaven(r.data) };
}

/** Plot only measured directions; never imply values between samples or in missing profiles. */
export function validHorizonSamples(samples: readonly HorizonSample[]): HorizonSample[] {
  return samples.filter((sample) =>
    sample.state === 'ok' && sample.elevation_deg !== null && Number.isFinite(sample.elevation_deg),
  );
}
