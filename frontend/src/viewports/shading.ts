// SPDX-License-Identifier: Apache-2.0
// Ombreggiatura software di un corpo sferico da mappe equirettangolari reali (colore + rilievo).
// Proiezione ortografica, luce in spazio lineare (LUT sRGB), rilievo come perturbazione della normale.
// Funzioni pure: le usa sia il Worker (shadeWorker.ts) sia il ripiego sul thread principale.
// Lo shader WebGL di threeViewport.ts replica la stessa formula.

export interface Tex {
  w: number;
  h: number;
  /** RGBA 8 bit. */
  data: Uint8ClampedArray;
}

/** Pendenze (est, nord) per texel, quantizzate su ±127 = ±`max`. */
export interface Relief {
  w: number;
  h: number;
  ge: Int8Array;
  gn: Int8Array;
  max: number;
}

export interface ShadeParams {
  /** Lato del quadrato di uscita (px). */
  S: number;
  /** Righe di R = Rx(pitch)·Ry(yaw). */
  rows: number[];
  /** Direzione della luce nel riferimento della vista (unitaria). */
  light: [number, number, number];
  albedo: number;
  /** Modello lunare (bordo piatto, Lommel-Seeliger) invece di Lambert. */
  lunar: boolean;
  /** Colore del bordo atmosferico (lineare 0..1) o null. */
  atmosphere: [number, number, number] | null;
}

/** Esagerazione verticale del rilievo (dichiarata nella descrizione e in credits.md). */
export const RELIEF_EXAGGERATION = 3;
/** Luce cinerea / riflessa minima sul lato notturno. */
export const AMBIENT = 0.012;

const TO_LIN = new Float32Array(256);
for (let i = 0; i < 256; i++) {
  const c = i / 255;
  TO_LIN[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
const TO_SRGB = new Uint8ClampedArray(4096);
for (let i = 0; i < 4096; i++) {
  const l = i / 4095;
  TO_SRGB[i] = Math.round(255 * (l <= 0.0031308 ? l * 12.92 : 1.055 * Math.pow(l, 1 / 2.4) - 0.055));
}

/** Pendenze dal rilievo in scala di grigi (canale R), in unità di raggio, con esagerazione. */
export function buildRelief(height: Tex, kmMin: number, kmMax: number, radiusKm: number, exaggeration = RELIEF_EXAGGERATION): Relief {
  const { w, h, data } = height;
  const kmPerUnit = (kmMax - kmMin) / 255;
  const ge = new Int8Array(w * h);
  const gn = new Int8Array(w * h);
  const max = 0.6;
  const dLon = (2 * Math.PI * radiusKm) / w;
  const dLat = (Math.PI * radiusKm) / h;
  for (let y = 0; y < h; y++) {
    const lat = (0.5 - (y + 0.5) / h) * Math.PI;
    const dx = dLon * Math.max(0.05, Math.cos(lat));
    const yu = Math.max(0, y - 1);
    const yd = Math.min(h - 1, y + 1);
    for (let x = 0; x < w; x++) {
      const xl = (x - 1 + w) % w;
      const xr = (x + 1) % w;
      const e = ((data[(y * w + xr) * 4]! - data[(y * w + xl) * 4]!) * kmPerUnit * exaggeration) / (2 * dx);
      const n = ((data[(yu * w + x) * 4]! - data[(yd * w + x) * 4]!) * kmPerUnit * exaggeration) / ((yd - yu) * dLat);
      const i = y * w + x;
      ge[i] = Math.max(-127, Math.min(127, Math.round((e / max) * 127)));
      gn[i] = Math.max(-127, Math.min(127, Math.round((n / max) * 127)));
    }
  }
  return { w, h, ge, gn, max };
}

/**
 * Disegna il disco (S x S, RGBA premoltiplicato no) in `out`. Senza mappa colore usa un grigio uniforme
 * (anteprima prima del caricamento).
 */
export function shadeDisk(out: Uint8ClampedArray, p: ShadeParams, color: Tex | null, relief: Relief | null): void {
  const { S, rows: m, light: Lv, albedo, lunar, atmosphere } = p;
  const [m00, m01, m02, m10, m11, m12, m20, m21, m22] = m as [number, number, number, number, number, number, number, number, number];
  // luce e vista nel riferimento del corpo: R^T · v
  const Lx = m00 * Lv[0] + m10 * Lv[1] + m20 * Lv[2];
  const Ly = m01 * Lv[0] + m11 * Lv[1] + m21 * Lv[2];
  const Lz = m02 * Lv[0] + m12 * Lv[1] + m22 * Lv[2];
  const Vx = m20;
  const Vy = m21;
  const Vz = m22;
  const tw = color?.w ?? 1;
  const th = color?.h ?? 1;
  const cd = color?.data;
  const rw = relief?.w ?? 1;
  const rh = relief?.h ?? 1;
  const kRel = relief ? relief.max / 127 : 0;
  const edge = 1.5 / S;
  const inv2pi = 1 / (2 * Math.PI);
  const invPi = 1 / Math.PI;
  const atmR = atmosphere?.[0] ?? 0;
  const atmG = atmosphere?.[1] ?? 0;
  const atmB = atmosphere?.[2] ?? 0;
  for (let j = 0; j < S; j++) {
    const ny = 1 - ((j + 0.5) / S) * 2;
    for (let i = 0; i < S; i++) {
      const o = (j * S + i) * 4;
      const nx = ((i + 0.5) / S) * 2 - 1;
      const r2 = nx * nx + ny * ny;
      if (r2 >= 1) {
        out[o] = out[o + 1] = out[o + 2] = out[o + 3] = 0;
        continue;
      }
      const nz = Math.sqrt(1 - r2);
      const mx = m00 * nx + m10 * ny + m20 * nz;
      const my = m01 * nx + m11 * ny + m21 * nz;
      const mz = m02 * nx + m12 * ny + m22 * nz;
      const myc = my < -1 ? -1 : my > 1 ? 1 : my;
      const u = Math.atan2(mx, mz) * inv2pi + 0.5;
      const v = 0.5 - Math.asin(myc) * invPi;
      // normale perturbata dal rilievo (base locale est/nord senza trigonometria)
      let px = mx;
      let py = my;
      let pz = mz;
      if (relief) {
        const ri = Math.min(rh - 1, (v * rh) | 0) * rw + Math.min(rw - 1, (u * rw) | 0);
        const se = relief.ge[ri]! * kRel;
        const sn = relief.gn[ri]! * kRel;
        const cl = Math.sqrt(mx * mx + mz * mz) || 1e-6;
        const sl = mx / cl;
        const cL = mz / cl;
        // est = (cos lon, 0, -sin lon); nord = (-sin lat sin lon, cos lat, -sin lat cos lon)
        px = mx - se * cL + sn * myc * sl;
        py = my - sn * cl;
        pz = mz + se * sl + sn * myc * cL;
        const inv = 1 / Math.sqrt(px * px + py * py + pz * pz);
        px *= inv;
        py *= inv;
        pz *= inv;
      }
      const mu0g = mx * Lx + my * Ly + mz * Lz; // geometria liscia: posizione del terminatore
      let mu0 = px * Lx + py * Ly + pz * Lz;
      if (mu0g < -0.05) mu0 = 0;
      else if (mu0 < 0) mu0 = 0;
      let b: number;
      if (lunar) {
        const mu = Math.max(0.02, px * Vx + py * Vy + pz * Vz);
        b = mu0 > 0 ? 0.62 * ((2 * mu0) / (mu0 + mu)) * 0.5 + 0.38 * mu0 : 0;
      } else b = mu0;
      b = albedo * b + AMBIENT;
      let R: number;
      let G: number;
      let B: number;
      if (cd) {
        // bilineare: dischi grandi (palco della home) senza scalettature
        const fx = u * tw - 0.5;
        const fy = v * th - 0.5;
        const x0 = Math.floor(fx);
        const y0 = fy < 0 ? 0 : Math.floor(fy);
        const ax = fx - x0;
        const ay = fy < 0 ? 0 : fy - y0;
        const xa = ((x0 % tw) + tw) % tw;
        const xb = (xa + 1) % tw;
        const ya = Math.min(th - 1, y0) * tw;
        const yb = Math.min(th - 1, y0 + 1) * tw;
        const i00 = (ya + xa) * 4;
        const i10 = (ya + xb) * 4;
        const i01 = (yb + xa) * 4;
        const i11 = (yb + xb) * 4;
        const w00 = (1 - ax) * (1 - ay);
        const w10 = ax * (1 - ay);
        const w01 = (1 - ax) * ay;
        const w11 = ax * ay;
        R = (TO_LIN[cd[i00]!]! * w00 + TO_LIN[cd[i10]!]! * w10 + TO_LIN[cd[i01]!]! * w01 + TO_LIN[cd[i11]!]! * w11) * b;
        G = (TO_LIN[cd[i00 + 1]!]! * w00 + TO_LIN[cd[i10 + 1]!]! * w10 + TO_LIN[cd[i01 + 1]!]! * w01 + TO_LIN[cd[i11 + 1]!]! * w11) * b;
        B = (TO_LIN[cd[i00 + 2]!]! * w00 + TO_LIN[cd[i10 + 2]!]! * w10 + TO_LIN[cd[i01 + 2]!]! * w01 + TO_LIN[cd[i11 + 2]!]! * w11) * b;
      } else {
        R = G = B = 0.18 * b;
      }
      if (atmosphere) {
        const f = 1 - nz;
        const rim = f * f * f * Math.max(0, Math.min(1, mu0g + 0.35)) * 0.55;
        R += atmR * rim;
        G += atmG * rim;
        B += atmB * rim;
      }
      out[o] = TO_SRGB[R >= 1 ? 4095 : (R * 4095) | 0]!;
      out[o + 1] = TO_SRGB[G >= 1 ? 4095 : (G * 4095) | 0]!;
      out[o + 2] = TO_SRGB[B >= 1 ? 4095 : (B * 4095) | 0]!;
      const rr = Math.sqrt(r2);
      out[o + 3] = rr > 1 - edge ? Math.max(0, Math.round(255 * (1 - (rr - (1 - edge)) / edge))) : 255;
    }
  }
}
