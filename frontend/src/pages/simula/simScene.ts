// SPDX-License-Identifier: Apache-2.0
// Scena sintetica per i renderer della Scena lander (threeLander / canvasLander) costruita dal modello nel browser:
// terreno piano con un crinale parametrico (quota H a distanza d1, cresta di raggio R), stessa geometria dei numeri.
// NON è un sito reale: la scena porta `terrain.synthetic = true` e l'etichetta "Scenario didattico".
// Con un sito reale la scena arriva invece da /api/raven/scene (LOLA); `inputFromScene` ne ricava gli ingressi del
// modello (crinale dominante dell'istante, approssimazione a ostacolo singolo su terreno piano) per curva e confronto.
import type { LanderScene, Patch } from '../lander/model';
import { DEFAULT_INPUT, RANGES, sanitizeInput, type LinkInput, type LinkOutput } from './linkModel';

export const PATCH_N = 96;
const EARTH_RADIUS_KM = 6371;

/** Quota del crinale sintetico (m sul suolo dell'antenna) alla distanza e lungo la direzione della Terra, laterale n. */
export function ridgeHeightAt(e: number, n: number, H: number, d1: number, R: number, spacing: number): number {
  const w = Math.max(Math.sqrt(2 * Math.max(H, 0) * Math.max(R, 0)), 1.5 * spacing, 1);
  const flank = Math.max(4 * w, 0.35 * d1);
  const x = e - d1;
  // cresta gaussiana (curvatura in cima = H * 2 / w^2 -> raggio R) e fianchi lineari
  const core = Math.exp(-((x / w) ** 2));
  const side = Math.max(0, 1 - Math.abs(x) / flank);
  const along = 1 + 0.12 * (1 - Math.cos((2 * Math.PI * n) / 1800)); // il crinale si alza lontano dalla linea di vista
  const bumps = 0.6 * Math.sin(e / 37) * Math.cos(n / 53) * (1 - Math.exp(-((n / 60) ** 2))); // mai sulla linea di vista
  return Math.max(0, H * Math.max(core, side) * along) + (e > 30 ? bumps : 0);
}

export function patchFor(H: number, d1: number, R: number, n = PATCH_N): { patch: Patch; half: number } {
  const half = Math.max(400, Math.min(5000, Math.ceil((1.3 * d1) / 100) * 100));
  const spacing = (2 * half) / (n - 1);
  const heights = new Float32Array(n * n);
  let lo = Infinity;
  let hi = -Infinity;
  for (let j = 0; j < n; j++) {
    const nn = -half + j * spacing;
    for (let i = 0; i < n; i++) {
      const e = -half + i * spacing;
      const z = e < -50 ? 0.4 * Math.sin(e / 41) * Math.cos(nn / 47) : ridgeHeightAt(e, nn, H, d1, R, spacing);
      heights[j * n + i] = z;
      lo = Math.min(lo, z);
      hi = Math.max(hi, z);
    }
  }
  return {
    half,
    patch: { n, sizeM: 2 * half, spacingM: spacing, nativeResolutionM: spacing, heights, minM: lo, maxM: hi, sampling: 'synthetic' },
  };
}

/** Profilo lungo la linea di vista (n = 0): quota esatta del modello in cima (e = d1, u = H). */
export function profileFor(H: number, d1: number, R: number, spacing: number, points = 300): { e: number[]; u: number[]; arc: number[] } {
  const end = Math.min(Math.max(d1 * 1.6, d1 + 500), 20_000);
  const e: number[] = [];
  const u: number[] = [];
  for (let k = 0; k < points; k++) {
    const x = (end * k) / (points - 1);
    e.push(x);
    u.push(ridgeHeightAt(x, 0, H, d1, R, spacing));
  }
  // la cima esatta tra i campioni
  const at = e.findIndex((x) => x >= d1);
  if (at >= 0) {
    e.splice(at, 0, d1);
    u.splice(at, 0, H);
  }
  return { e, u, arc: e.slice() };
}

const cache = { key: '', patch: null as Patch | null, half: 0 };

/** Scena per i renderer dalle uscite del modello (il terreno si ricalcola solo se cambia il crinale). */
export function syntheticScene(o: LinkOutput, label: string): LanderScene {
  const x = o.input;
  const d1 = x.ridgeDistanceM;
  const H = x.ridgeHeightM !== undefined ? x.ridgeHeightM : x.mastM + d1 * Math.tan((x.ridgeAngleDeg! * Math.PI) / 180);
  const R = x.ridgeRadiusM;
  const key = `${H.toFixed(3)}|${d1}|${R}`;
  if (cache.key !== key) {
    const p = patchFor(H, d1, R);
    cache.key = key;
    cache.patch = p.patch;
    cache.half = p.half;
  }
  const patch = cache.patch!;
  const rangeM = x.earthDistanceKm * 1000;
  return {
    tUtc: '',
    site: { id: null, lat: -86, lon: 0 },
    sky: null,
    earth: {
      azDeg: 0,
      elDeg: x.earthElDeg,
      rangeKm: x.earthDistanceKm,
      angularDiameterDeg: (2 * Math.atan(EARTH_RADIUS_KM / x.earthDistanceKm) * 180) / Math.PI,
      parallaxDeg: 0,
    },
    terrain: {
      source: 'synthetic',
      synthetic: true,
      label,
      productId: null,
      nativeResolutionM: null,
      profileSpacingM: patch.spacingM,
      radiusResolved: true,
      coverage: 'synthetic',
      patch,
      patchHalfM: cache.half,
      profile: profileFor(H, d1, R, patch.spacingM),
    },
    antenna: {
      station: x.station,
      mastM: x.mastM,
      mastTag: 'I',
      gainDbi: o.gainDbi,
      diameterM: o.diameterM,
      hpbwDeg: o.hpbwScriptDeg,
      pointingDbPerX2: 12.04,
      wavelengthM: o.wavelengthM,
      frequencyGhz: x.frequencyGhz,
    },
    ridge: {
      e: d1,
      u: H,
      arcDistanceM: d1,
      heightM: H,
      d1M: o.d1LosM,
      d2M: rangeM - o.d1LosM,
      heightAboveLosM: o.hAboveLosM,
      tipElevationDeg: o.tipElevationDeg,
      angleAboveLosDeg: o.angleAboveLosDeg,
      radiusM: R,
      radiusResolved: true,
      blocksLos: o.blocksLos,
      nu: o.nu,
    },
    fresnel: { wavelengthM: o.wavelengthM, rangeM, r1AtRidgeM: o.fresnelR1M, dEndM: Math.min(Math.max(d1 * 1.6, d1 + 500), 20_000) },
    diffraction: {
      knifeEdgeDb: o.knifeEdgeDb,
      correctionDb: o.correctionDb,
      correctionUncertaintyDb: o.correctionUncertaintyDb,
      correctionLabel: 'ITU-R P.526-9 T(m,n), banda split-step; non misurata',
      lossDb: o.diffractionLossDb,
      multipathApplicable: o.multipathApplicable,
      multipathGainDb: o.multipathApplicable ? o.multipathGainDb : null,
      multipathReason: null,
      totalLossDb: o.diffractionLossDb - o.multipathGainDb,
    },
    link: { rateBps: x.rateBps, margin: o.marginDb, state: o.state, stateLabel: o.state, geometricVisible: !o.blocksLos, fsplDb: o.fsplDb, station: x.station },
    tags: {},
    raw: {},
    limits: [],
    disclaimer: '',
  };
}

const clamp = (v: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, v));

/**
 * Ingressi del modello dal crinale dominante di una scena reale (per la curva e il confronto, non per il margine
 * mostrato, che è quello dell'API). Terreno piano, ostacolo singolo, multipath attivo come il motore.
 */
export function inputFromScene(s: LanderScene, base: LinkInput): LinkInput {
  const raw: Partial<LinkInput> = {
    ...base,
    earthElDeg: s.earth.elDeg,
    ridgeHeightM: clamp(s.ridge.u, RANGES.ridgeHeightM),
    ridgeDistanceM: clamp(s.ridge.e, RANGES.ridgeDistanceM),
    ridgeRadiusM: clamp(s.ridge.radiusM ?? 0, RANGES.ridgeRadiusM),
    mastM: s.antenna.mastM,
    earthDistanceKm: clamp(s.earth.rangeKm, RANGES.earthDistanceKm),
    gainDbi: s.antenna.gainDbi,
    radiusResolved: s.ridge.radiusResolved,
    multipath: { ...DEFAULT_INPUT.multipath, enabled: true },
  };
  delete raw.ridgeAngleDeg;
  delete raw.diameterM;
  return sanitizeInput(raw).input;
}
