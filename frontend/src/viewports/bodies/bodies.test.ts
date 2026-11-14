// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ASSETS, type ImageAsset } from './assets';
import { assetsFor, BODIES, creditsFor, starsAsset } from './registry';
import { BODY_IDS, centerOn, defaultFrame, isBodyId, projectLatLon } from '../scene';

describe('registro delle immagini', () => {
  it('ogni asset ha credito, licenza, pagina sorgente e file originale (fallisce se ne manca uno)', () => {
    for (const a of Object.values(ASSETS) as ImageAsset[]) {
      expect(a.credit.trim().length, `${a.id}: credito`).toBeGreaterThan(10);
      expect(a.licence.trim().length, `${a.id}: licenza`).toBeGreaterThan(10);
      expect(a.sourcePage, `${a.id}: pagina sorgente`).toMatch(/^https:\/\/(svs\.gsfc\.nasa\.gov|visibleearth\.nasa\.gov|sdo\.gsfc\.nasa\.gov|github\.com\/nasa\/)/);
      expect(a.sourceFile.length, `${a.id}: file originale`).toBeGreaterThan(3);
      expect(a.url, `${a.id}: url`).toMatch(/\.webp$/);
    }
  });

  it('budget: mappe colore <= 500 KB, rilievo <= 400 KB, cielo <= 600 KB', () => {
    for (const a of Object.values(ASSETS) as ImageAsset[]) {
      const max = a.id.startsWith('stars') ? 600_000 : a.id.includes('Height') ? 400_000 : 500_000;
      expect(a.bytes, a.id).toBeLessThanOrEqual(max);
    }
  });

  it('ogni corpo usa solo asset registrati, con crediti visibili', () => {
    for (const id of BODY_IDS) {
      for (const t of ['hi', 'lo'] as const) for (const a of assetsFor(id, t)) expect(ASSETS[a]).toBeDefined();
      expect(creditsFor(id).length).toBeGreaterThanOrEqual(2); // mappa + cielo
    }
    expect(ASSETS[starsAsset('lo')].width).toBeLessThan(ASSETS[starsAsset('hi')].width);
  });
});

describe('registro dei corpi', () => {
  it('quattro corpi: il Sole è emissivo e senza luoghi; la telemetria solo per la Luna', () => {
    expect(BODY_IDS).toEqual(['moon', 'earth', 'sun', 'mars']);
    expect(BODIES.sun.emissive).toBe(true);
    expect(BODIES.sun.places).toHaveLength(0);
    expect(BODY_IDS.filter((b) => BODIES[b].telemetry)).toEqual(['moon']);
    expect(isBodyId('mars')).toBe(true);
    expect(isBodyId('pluto')).toBe(false);
  });

  it('fatti e luoghi hanno fonte e coordinate valide', () => {
    for (const id of BODY_IDS) {
      const b = BODIES[id];
      expect(b.factsSource).toMatch(/^https:\/\/nssdc\.gsfc\.nasa\.gov\/planetary\/factsheet\//);
      for (const p of b.places) {
        expect(p.source.length).toBeGreaterThan(10);
        expect(Math.abs(p.lat)).toBeLessThanOrEqual(90);
        expect(Math.abs(p.lon)).toBeLessThanOrEqual(180);
      }
    }
    expect(BODIES.moon.keyStat.value).toBe(384400);
    expect(BODIES.mars.places.find((p) => p.id === 'olympus')!.lon).toBeCloseTo(-133.8, 1);
  });
});

describe('geometria dei marcatori', () => {
  const f = defaultFrame(1000, 800);
  it('centerOn porta il luogo al centro del disco, visibile', () => {
    const tycho = BODIES.moon.places.find((p) => p.id === 'tycho')!;
    const p = projectLatLon(tycho.lat, tycho.lon, centerOn(tycho.lat, tycho.lon), f);
    expect(p.x).toBeCloseTo(f.cx, 5);
    expect(p.y).toBeCloseTo(f.cy, 5);
    expect(p.visible).toBe(true);
  });

  it('il lato nascosto non è visibile; Est a destra a rotazione zero', () => {
    const view = { yaw_deg: 0, pitch_deg: 0 };
    expect(projectLatLon(-45.45, 177.6, view, f).visible).toBe(false); // Chang'e 4
    expect(projectLatLon(0, 30, view, f).x).toBeGreaterThan(f.cx);
    expect(projectLatLon(30, 0, view, f).y).toBeLessThan(f.cy); // Nord in alto
  });
});

describe('siti dell analisi lunare sulla Luna', () => {
  const sites = (
    JSON.parse(readFileSync(resolve(__dirname, '../../../../backend/domain/data/sites.json'), 'utf8')) as {
      sites: { id: string; lat_deg: number; lon_deg_east: number }[];
    }
  ).sites;
  const f = defaultFrame(1000, 800);

  it('tutti i 51 siti del backend sono luoghi del viewer con le stesse coordinate', () => {
    expect(sites).toHaveLength(51);
    for (const s of sites) {
      const p = BODIES.moon.places.find((q) => q.siteId === s.id);
      expect(p, s.id).toBeDefined();
      expect(p!.lat).toBeCloseTo(s.lat_deg, 5);
      expect(p!.lon).toBeCloseTo(s.lon_deg_east, 5);
    }
    expect(BODIES.moon.places.filter((p) => p.siteId).length).toBe(51);
  });

  it('con la vista centrata sul sito il marcatore e visibile al centro; sul lato opposto no', () => {
    for (const s of sites) {
      const v = centerOn(s.lat_deg, s.lon_deg_east);
      const p = projectLatLon(s.lat_deg, s.lon_deg_east, v, f);
      expect(p.visible, s.id).toBe(true);
      const far = projectLatLon(s.lat_deg, s.lon_deg_east, { yaw_deg: v.yaw_deg + 180, pitch_deg: -v.pitch_deg }, f);
      expect(far.visible, s.id).toBe(false);
    }
  });

  it('i luoghi degli altri corpi non hanno siteId', () => {
    expect(BODIES.mars.places.some((p) => p.siteId)).toBe(false);
  });
});
