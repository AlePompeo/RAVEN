// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import {
  beamDirection,
  fetchScene,
  fresnelAt,
  fresnelRadius,
  parseScene,
  pointing,
  ridgeObstruction,
  SceneClient,
  SceneError,
  sceneJson,
  sceneUrl,
  STATE_INFO,
  sunLocal,
  textAlternative,
  FALLBACK_SUN,
  type LanderScene,
  type SceneParams,
} from './model';
import { beamLength, buildTerrain, coneRing, fresnelBand, fresnelRings, orbit, presetCamera, sectionLayout, shadeTerrain, terrainHeightAt, tubeIndices, zoomBy, eyeOf, viewDir } from './view';
import { skyWorldFromTexture } from './threeLander';
import { drawSection } from './canvasLander';

export function apiFixture(over: Record<string, unknown> = {}): Record<string, unknown> {
  const n = 8;
  const heights = Array.from({ length: n * n }, (_, k) => ((k % n) - 3) * 2);
  return {
    t_utc: '2027-04-07T00:00:00Z',
    site: { id: 'haworth', lat_deg: -87.45, lon_deg_east: -5.17 },
    earth: { az_deg: 359.8, el_deg: 5.0, range_km: 385000, angular_diameter_deg: 1.9, parallax_deg: 0.2, el_geocentric_deg: 5.2 },
    terrain: {
      source: 'lola',
      synthetic: false,
      label: 'LOLA ldem_85s_20m_float',
      product_id: 'ldem_85s_20m_float',
      native_resolution_m: 20,
      profile_spacing_m: 20,
      radius_resolved: true,
      coverage: 'LOLA',
      patch: { n, size_m: 700, spacing_m: 100, native_resolution_m: 20, height_m: heights, min_m: -6, max_m: 8, sampling: 'puntuale' },
      patch_half_size_m: 350,
      profile: { e_m: [0, 100, 200, 300, 400], u_m: [0, 1, 5, 12, 4], arc_m: [0, 100, 200, 300, 400] },
    },
    antenna: { station: 'dsn34', mast_height_m: 2, mast_tag: 'I', gain_dbi: 15, diameter_m: 0.3, hpbw_deg: 12, pointing_db_per_hpbw2: 12.04, wavelength_m: 0.03569, frequency_ghz: 8.4 },
    ridge: { e_m: 300, u_m: 12, arc_distance_m: 300, height_m: 12, d1_m: 300, d2_m: 3.8e8, height_above_los_m: 2.4, tip_elevation_deg: 6.5, angle_above_los_deg: 1.5, radius_of_curvature_m: 120, radius_resolved: true, blocks_los: true, nu: 1.2 },
    fresnel: { wavelength_m: 0.03569, range_m: 385000000, r1_at_ridge_m: 3.27, samples: [{ d_m: 0, r_m: 0 }, { d_m: 480, r_m: 4.1 }] },
    diffraction: { knife_edge_db: 9.4, correction_db: 0.3, correction_uncertainty_db: 0.1, correction_label: 'correzione simulata, non validata', diffraction_loss_db: 9.7, multipath_applicable: false, multipath_gain_db: null, multipath_reason: 'non applicabile: punto speculare oltre il crinale', total_loss_db: 9.7 },
    link: { rate_bps: 100000, station: 'dsn34', margin_db: 4.2, state: 'transition', state_label: 'transizione', geometric_visible: false, fspl_db: 222.1, pointing_loss_db: 0 },
    tags: { radio: 'I' },
    declared_limits: ['Ostacolo singolo dominante'],
    disclaimer: 'Risultati: potenziale',
    ...over,
  };
}
const scene = (over: Record<string, unknown> = {}): LanderScene => parseScene(apiFixture(over));

describe('sky orientation', () => {
  it('accepts a proper rotation, rejects malformed or reflected matrices and supports older responses', () => {
    const identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    expect(scene().sky).toBeNull();
    expect(scene({ sky: { icrf_to_scene: identity } }).sky?.icrfToScene).toEqual(identity);
    for (const matrix of [[[1, 0, 0], [0, 1, 0]], [[1, 0, 0], [0, 1, 0], [0, 0, -1]], [[2, 0, 0], [0, 1, 0], [0, 0, 1]]]) {
      expect(() => scene({ sky: { icrf_to_scene: matrix } })).toThrow(SceneError);
    }
  });
  it('maps ICRF directions to the NASA texture without reflecting the sky', () => {
    const icrfToScene: [number[], number[], number[]] = [[0, -1, 0], [0, 0, 1], [-1, 0, 0]];
    const worldFromTexture = skyWorldFromTexture(THREE, icrfToScene);
    expect(worldFromTexture.determinant()).toBeCloseTo(1, 12);
    const textureFromWorld = worldFromTexture.clone().invert();
    // Three.js equirectUv samples atan(z,x)/2π+0.5; NASA RA increases left.
    for (const [world, u, v] of [
      [[0, 0, -1], 0.5, 0.5], // RA 0, dec 0
      [[-1, 0, 0], 0.25, 0.5], // RA 90, dec 0
      [[0, 1, 0], 0.5, 1], // north celestial pole
    ] as const) {
      const d = new THREE.Vector3(...world).applyMatrix4(textureFromWorld);
      expect(Math.atan2(d.z, d.x) / (2 * Math.PI) + 0.5).toBeCloseTo(u, 12);
      expect(Math.asin(d.y) / Math.PI + 0.5).toBeCloseTo(v, 12);
    }
    const euler = new THREE.Euler().setFromRotationMatrix(worldFromTexture);
    new THREE.Matrix4().makeRotationFromEuler(euler).elements.forEach((value, i) => {
      expect(value).toBeCloseTo(worldFromTexture.elements[i]!, 12);
    });
  });
});

describe('Fresnel zone radius', () => {
  it('matches the model-doc table T6 (lambda 0.035690 m, d2 = 384 400 km)', () => {
    const table: [number, number][] = [
      [10, 0.597],
      [50, 1.336],
      [100, 1.889],
      [500, 4.224],
      [1000, 5.974],
      [2000, 8.449],
      [5000, 13.358],
      [10000, 18.891],
    ];
    for (const [d, r] of table) expect(fresnelRadius(1, 0.03569, d, 384_400_000)).toBeCloseTo(r, 2);
    expect(fresnelRadius(1, 0.03569, 1000, 1000)).toBeCloseTo(4.224, 2);
    expect(fresnelRadius(1, 0.03569, 0, 5)).toBe(0);
    expect(fresnelRadius(2, 0.03569, 1000, 1000)).toBeCloseTo(4.224 * Math.SQRT2, 2);
  });
  it('fresnelAt uses the scene range and wavelength', () => {
    const s = scene();
    expect(fresnelAt(s, 300)).toBeCloseTo(fresnelRadius(1, 0.03569, 300, 385_000_000 - 300), 9);
    expect(ridgeObstruction(s)).toBeCloseTo(2.4 / 3.27, 6);
  });
  it('tube rings: radius grows as sqrt(d), scaled only in drawing, axis follows the Earth elevation', () => {
    const s = scene();
    const r = fresnelRings(s, 10, 1, 8, 12);
    expect(r.radius[0]).toBe(0);
    expect(r.radius[8]!).toBeCloseTo(fresnelAt(s, s.fresnel.dEndM), 3);
    expect(r.radius[8]! / r.radius[2]!).toBeCloseTo(2, 1); // sqrt(4)
    // centre of the last ring lies on the line of sight (before the radial offset)
    const o = (8 * 12) * 3;
    let cx = 0;
    let cy = 0;
    for (let a = 0; a < 12; a++) {
      cx += r.positions[o + a * 3]!;
      cy += r.positions[o + a * 3 + 1]!;
    }
    const d = s.fresnel.dEndM;
    expect(cx / 12).toBeCloseTo(d * Math.cos((5 * Math.PI) / 180), 1);
    expect(cy / 12).toBeCloseTo(2 + d * Math.sin((5 * Math.PI) / 180), 1);
    expect(tubeIndices(8, 12).length).toBe(8 * 12 * 6);
  });
});

describe('link state to colour and text', () => {
  it('every state has a distinct colour AND a text label and a symbol', () => {
    const states = Object.values(STATE_INFO);
    expect(new Set(states.map((s) => s.color)).size).toBe(states.length);
    expect(new Set(states.map((s) => s.symbol)).size).toBe(states.length);
    expect(STATE_INFO.open.label).toBe('Aperto');
    expect(STATE_INFO.transition.label).toBe('Transizione');
    expect(STATE_INFO.blocked.label).toBe('Bloccato');
    expect(STATE_INFO.open.color).toBe('#30d158'); // verde
    expect(STATE_INFO.transition.color).toBe('#ffb340'); // ambra
    expect(STATE_INFO.blocked.color).toBe('#ff6961'); // rosso
  });
});

describe('pointing and beam cone', () => {
  it('loss is 12.04 (err/HPBW)^2 and the cone turns red beyond HPBW/2', () => {
    const s = scene();
    expect(pointing(s, 0).lossDb).toBe(0);
    expect(pointing(s, 12).lossDb).toBeCloseTo(12.04, 6);
    expect(pointing(s, 6).beyond).toBe(false); // esattamente HPBW/2: ancora entro
    expect(pointing(s, 6.01).beyond).toBe(true);
    expect(pointing(s, 6).lossDb).toBeCloseTo(3.01, 2);
    expect(pointing(s, 6).marginDb).toBeCloseTo(4.2 - 3.01, 2);
    expect(pointing(s, -3).errorDeg).toBe(0);
    expect(pointing(s, 12).state).toBe('blocked');
    expect(pointing(s, 0).state).toBe('transition');
  });
  it('the beam axis is the Earth direction rotated up by the error', () => {
    const [e0, u0] = beamDirection(5, 0);
    expect(Math.atan2(u0, e0)).toBeCloseTo((5 * Math.PI) / 180, 9);
    const [e1, u1] = beamDirection(5, 3);
    expect(Math.atan2(u1, e1)).toBeCloseTo((8 * Math.PI) / 180, 9);
    expect(Math.hypot(e1, u1)).toBeCloseTo(1, 9);
  });
  it('cone ring: base points are at half-angle from the axis', () => {
    const apex: [number, number, number] = [0, 2, 0];
    const ring = coneRing(apex, beamDirection(5, 0), 6, 100, 1, 16);
    for (let k = 0; k < 16; k++) {
      const v = [ring[k * 3]! - apex[0], ring[k * 3 + 1]! - apex[1], ring[k * 3 + 2]! - apex[2]];
      const ax = beamDirection(5, 0);
      const dot = (v[0]! * ax[0] + v[1]! * ax[1]) / Math.hypot(v[0]!, v[1]!, v[2]!);
      expect((Math.acos(dot) * 180) / Math.PI).toBeCloseTo(6, 4);
    }
    expect(beamLength(scene())).toBeGreaterThanOrEqual(40);
  });
});

describe('sun direction', () => {
  it('zenith, east and relative azimuth in the scene frame', () => {
    // sito all'equatore lon 0: su = z, est = x, nord = y (assi del visualizzatore)
    const z = sunLocal(0, 0, [0, 0, 1], 0);
    expect(z.elDeg).toBeCloseTo(90, 6);
    const east = sunLocal(0, 0, [1, 0, 0], 0);
    expect(east.elDeg).toBeCloseTo(0, 6);
    expect(east.azDeg).toBeCloseTo(90, 6);
    // la Terra a est (az 90): il Sole a est e' davanti (e = 1); a nord e' a sinistra (n > 0)
    const front = sunLocal(0, 0, [1, 0, 0], 90);
    expect(front.dir[0]).toBeCloseTo(1, 6);
    const north = sunLocal(0, 0, [0, 1, 0], 90);
    expect(north.dir[1]).toBeCloseTo(1, 6);
  });
});

describe('terrain shading and meshes', () => {
  it('a wall casts a shadow on its lee side and the sun below the horizon darkens everything', () => {
    const n = 16;
    const h = new Float32Array(n * n);
    for (let j = 0; j < n; j++) h[j * n + 8] = 40; // muro a e fisso
    const low = { elDeg: 3, azDeg: 0, dir: [Math.cos(0.05), 0, Math.sin(0.05)] as [number, number, number] }; // Sole dietro (e positivo = davanti)
    const lit = shadeTerrain(h, n, 20, low);
    // il Sole e' davanti (+e): il lato a e > muro e' illuminato, il lato a e < muro e' in ombra
    expect(lit.light[3 * n + 12]!).toBeGreaterThan(0.01);
    expect(lit.light[3 * n + 4]!).toBe(0);
    expect(lit.shadowFraction).toBeGreaterThan(0.2);
    const night = shadeTerrain(h, n, 20, { elDeg: -5, azDeg: 0, dir: [1, 0, -0.1] });
    expect(night.sunUp).toBe(false);
    expect(night.shadowFraction).toBe(1);
  });
  it('buildTerrain applies the vertical exaggeration to y only', () => {
    const s = scene();
    const a = buildTerrain(s, 1, { elDeg: 1.5, azDeg: 0, dir: [0.9, -0.3, 0.03] })!;
    const b = buildTerrain(s, 5, { elDeg: 1.5, azDeg: 0, dir: [0.9, -0.3, 0.03] })!;
    expect(a.n).toBe(10);
    expect(b.positions[1 * 3 + 1]!).toBeCloseTo(a.positions[1 * 3 + 1]! * 5, 4);
    expect(b.positions[1 * 3]!).toBe(a.positions[1 * 3]!);
    expect(a.indices.length).toBe(9 * 9 * 6);
    expect(buildTerrain(scene({ terrain: { ...(apiFixture().terrain as object), patch: null } }), 1, { elDeg: 1, azDeg: 0, dir: [1, 0, 0.02] })).toBeNull();
  });
  it('keeps the rover footprint at the antenna origin without changing the original samples', () => {
    const s = scene();
    const patch = s.terrain.patch!;
    const mesh = buildTerrain(s, 3, { elDeg: 2, azDeg: 0, dir: [1, 0, 0.04] })!;
    for (let k = 0; k < mesh.positions.length; k += 3) {
      const e = mesh.positions[k]!;
      const north = -mesh.positions[k + 2]!;
      if (Math.abs(e) <= 3 && Math.abs(north) <= 3) expect(mesh.positions[k + 1]).toBe(0);
    }
    for (const [e, z] of [[0, 0], [-1.7, -0.62], [-0.5, 0.62]]) {
      expect(terrainHeightAt(mesh, e!, z!)).toBeCloseTo(0, 8);
    }
    expect(terrainHeightAt(mesh, patch.sizeM, 0)).toBeNull();
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(mesh.positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(mesh.indices, 1));
    const surface = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
    for (const [e, z] of [[-25, -40], [16, 20], [3, 0], [-1, 0]]) {
      const ray = new THREE.Raycaster(new THREE.Vector3(e, 500, z), new THREE.Vector3(0, -1, 0));
      expect(terrainHeightAt(mesh, e!, z!)).toBeCloseTo(ray.intersectObject(surface)[0]!.point.y, 5);
    }
    geometry.dispose();
    surface.material.dispose();
    for (let j = 0; j < patch.n; j++) {
      for (let i = 0; i < patch.n; i++) {
        const e = -patch.sizeM / 2 + i * patch.spacingM;
        const north = -patch.sizeM / 2 + j * patch.spacingM;
        const index = Array.from({ length: mesh.n * mesh.n }, (_, k) => k).find((k) =>
          Math.abs(mesh.positions[k * 3]! - e) < 1e-4 && Math.abs(mesh.positions[k * 3 + 2]! + north) < 1e-4,
        )!;
        expect(mesh.positions[index * 3 + 1]).toBeCloseTo(patch.heights[j * patch.n + i]! * 3, 5);
      }
    }
  });
});

describe('camera', () => {
  it('orbit clamps the pitch, zoom clamps the distance and presets look in the right direction', () => {
    const c = presetCamera('side', scene());
    expect(eyeOf(c)[1]).toBeGreaterThan(c.target[1]);
    expect(viewDir(c)[1]).toBeLessThan(0);
    orbit(c, 0, 10);
    expect(c.pitch).toBeLessThan(Math.PI / 2);
    zoomBy(c, 1e9);
    expect(c.dist).toBeGreaterThanOrEqual(4);
    zoomBy(c, 1e-9);
    expect(c.dist).toBeLessThanOrEqual(30000);
    const l = presetCamera('lander', scene());
    expect(viewDir(l)[0]).toBeGreaterThan(0.9); // guarda verso la Terra (+x)
    const eye = eyeOf(l);
    expect(eye[0]).toBeLessThan(l.target[0]);
    expect(l.pitch).toBeLessThan(0);
    expect(l.target[0]).toBeCloseTo(-0.8);
    expect(l.target[1]).toBeLessThan(scene().antenna.mastM);
    const top = presetCamera('top', scene());
    expect(viewDir(top)[1]).toBeLessThan(-0.99);
  });
});

describe('side section projection', () => {
  it('maps the antenna, the ridge and the profile inside the frame; band follows the Fresnel radius', () => {
    const s = scene();
    const L = sectionLayout(s, 800, 400);
    for (const [e, u] of [[0, 2], [s.ridge.e, s.ridge.u], [L.eMax, 0]] as [number, number][]) {
      expect(L.toX(e)).toBeGreaterThanOrEqual(0);
      expect(L.toX(e)).toBeLessThanOrEqual(800);
      expect(L.toY(u)).toBeGreaterThan(0);
      expect(L.toY(u)).toBeLessThan(400);
    }
    expect(L.toX(300)).toBeGreaterThan(L.toX(0));
    expect(L.toY(12)).toBeLessThan(L.toY(2)); // piu' in alto = y minore
    expect(L.exaggeration).toBeGreaterThan(1);
    const band = fresnelBand(s, 10);
    const k = band.length - 1;
    expect(band[k]!.r).toBeCloseTo(fresnelAt(s, s.fresnel.dEndM), 6);
    expect(band[k]!.hi - band[k]!.lo).toBeCloseTo((2 * band[k]!.r) / Math.cos((5 * Math.PI) / 180), 6);
    expect(band[0]!.r).toBe(0);
  });
});

describe('parsing, text and export', () => {
  it('parseScene rejects malformed answers and keeps the numbers', () => {
    expect(() => parseScene({})).toThrow(SceneError);
    expect(() => parseScene(apiFixture({ link: { state: 'weird' } }))).toThrow(SceneError);
    const bad = apiFixture();
    (bad.terrain as { patch: { height_m: number[] } }).patch.height_m = [1, 2, 3];
    expect(() => parseScene(bad)).toThrow(SceneError);
    const s = scene();
    expect(s.link.margin).toBe(4.2);
    expect(s.terrain.patch?.heights.length).toBe(64);
    expect(s.fresnel.dEndM).toBe(480);
  });
  it('does not accept a legacy numeric margin when the authoritative RF result is unknown', () => {
    const answer = apiFixture({ model: { state: 'unknown', margin_db: null, rf_reason: 'outside_model' } });
    const parsed = parseScene(answer);
    expect(parsed.link.margin).toBeNull();
    expect(parsed.link.state).toBe('unknown');
    expect(parsed.diffraction.totalLossDb).toBeNull();
    expect(pointing(parsed, 6).marginDb).toBeNull();
    expect(pointing(parsed, 6).state).toBe('unknown');
    expect((parsed.raw.link as Record<string, unknown>).margin_db).toBeNull();
    expect(textAlternative(parsed, pointing(parsed, 6), null, false)).toContain('margine con puntamento ? dB');
  });
  it('preserves a known far-terrain block without fabricating its margin', () => {
    const parsed = parseScene(apiFixture({ model: { state: 'blocked', margin_db: null, rf_reason: 'blocked_far_terrain' } }));
    expect(parsed.link.state).toBe('blocked');
    expect(pointing(parsed, 6).state).toBe('blocked');
    expect(pointing(parsed, 6).marginDb).toBeNull();
  });
  it('text alternative and JSON carry the numbers, the multipath reason and the labels', () => {
    const s = scene();
    const txt = textAlternative(s, pointing(s, 7), null, false);
    expect(txt).toContain('5,00 gradi');
    expect(txt).toContain('Termine multipath non applicabile');
    expect(txt).toContain('transizione');
    expect(txt).toContain('oltre meta');
    const j = JSON.parse(sceneJson(s, { pointingErrorDeg: 7, verticalExaggeration: 2, tubeScale: 20, sunReal: false, sunElevationDeg: 1.5 })) as Record<string, any>;
    expect(j.link.margin_db).toBe(4.2);
    expect(j.declared_limits).toEqual(['Ostacolo singolo dominante']);
    expect(j.pointing.beyond_half_hpbw).toBe(true);
    expect(j.drawing.fresnel_tube_scale).toBe(20);
    expect(j.terrain.patch.posts).toBe(64);
    expect(j.terrain.patch.heights).toBeUndefined();
    expect(j.fresnel.obstruction_h_over_r1).toBeCloseTo(2.4 / 3.27, 6);
  });
  it('uses English and decimal points for the scene text when English is selected', () => {
    const s = scene();
    const txt = textAlternative(s, pointing(s, 7), null, false, 'en');
    expect(txt).toContain('Earth is at 5.00 degrees');
    expect(txt).toContain('Multipath term not applicable');
    expect(txt).toContain('state transition');
    expect(txt).toContain('pointing margin');
    expect(txt).toContain(s.diffraction.multipathReason);
  });
  it('sceneUrl is the documented request', () => {
    const u = sceneUrl({ site: 'haworth', ms: Date.UTC(2027, 3, 7), station: 'dsn18', gain: 12, rate: 1e5, mast: 3 });
    expect(u).toBe('/api/raven/scene?site=haworth&t=2027-04-07T00%3A00%3A00Z&station=dsn18&gain_dbi=12&rate_bps=100000&antenna_height_m=3');
  });
});

describe('fetchScene errors', () => {
  const resp = (status: number, body: unknown) => async () => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
  const p: SceneParams = { site: 'haworth', ms: 0, station: 'dsn34', gain: 15, rate: 1e5, mast: 2 };
  it('maps 422 coverage, 422 generic, 503 and network failures to distinct kinds', async () => {
    await expect(fetchScene(p, undefined, resp(422, { detail: 'sito fuori copertura DEM (...)' }) as typeof fetch)).rejects.toMatchObject({ kind: 'coverage' });
    await expect(fetchScene(p, undefined, resp(422, { detail: 'parametri non validi' }) as typeof fetch)).rejects.toMatchObject({ kind: 'range' });
    await expect(fetchScene(p, undefined, resp(503, { detail: 'dati DEM non disponibili' }) as typeof fetch)).rejects.toMatchObject({ kind: 'unavailable' });
    await expect(fetchScene(p, undefined, resp(503, { detail: 'troppe analisi in corso' }) as typeof fetch)).rejects.toMatchObject({ kind: 'busy' });
    await expect(fetchScene(p, undefined, (async () => { throw new TypeError('x'); }) as typeof fetch)).rejects.toMatchObject({ kind: 'network' });
    const ok = await fetchScene(p, undefined, resp(200, apiFixture()) as typeof fetch);
    expect(ok.site.id).toBe('haworth');
  });
  it('sends custom coordinates as query parameters of the single-model scene', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(apiFixture()), { status: 200 }));
    const customSite = { id: 'c-a', name: 'A', lat_deg: -88, lon_deg_east: 12 };
    await fetchScene({ ...p, site: 'c-a', customSite }, undefined, fetcher);
    const [url] = fetcher.mock.calls[0]!;
    const q = new URL(String(url), 'http://x').searchParams;
    expect(String(url).startsWith('/api/raven/scene?')).toBe(true);
    expect([q.get('site'), q.get('lat_deg'), q.get('lon_deg_east')]).toEqual(['c-a', '-88', '12']);
  });
});

describe('SceneClient throttle and cancel', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  const base: SceneParams = { site: 'haworth', ms: 1_000_000, station: 'dsn34', gain: 15, rate: 1e5, mast: 2 };

  it('coalesces a burst into leading + trailing, aborts the superseded request and discards stale answers', async () => {
    const calls: { p: SceneParams; sig: AbortSignal; res: (s: LanderScene) => void }[] = [];
    const got: number[] = [];
    const c = new SceneClient({
      minIntervalMs: 500,
      fetcher: (p, sig) => new Promise((res) => calls.push({ p, sig, res })),
      onScene: (_s, p) => got.push(p.ms),
      onError: () => {},
    });
    c.request({ ...base, ms: 1_000_000 });
    await vi.advanceTimersByTimeAsync(0);
    expect(calls).toHaveLength(1);
    for (let i = 1; i <= 10; i++) c.request({ ...base, ms: 1_000_000 + i * 60_000 }); // raffica
    expect(calls).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(600);
    expect(calls).toHaveLength(2); // una sola richiesta in coda, con l'ultimo istante
    expect(calls[1]!.p.ms).toBe(1_000_000 + 10 * 60_000);
    expect(calls[0]!.sig.aborted).toBe(true);
    calls[0]!.res(scene()); // risposta superata: scartata
    calls[1]!.res(scene());
    await vi.advanceTimersByTimeAsync(0);
    expect(got).toEqual([1_000_000 + 10 * 60_000]);
    expect(c.fetches).toBe(2);
    c.dispose();
  });

  it('serves a repeated scenario from the cache without the network and cancel() silences the pending answer', async () => {
    let n = 0;
    const got: string[] = [];
    const c = new SceneClient({
      minIntervalMs: 0,
      fetcher: async () => (n++, scene()),
      onScene: (s) => got.push(s.tUtc),
      onError: () => {},
    });

    c.request(base);
    await vi.advanceTimersByTimeAsync(10);
    c.request(base);
    expect(n).toBe(1);
    expect(got).toHaveLength(2);
    c.request({ ...base, ms: base.ms + 3_600_000 });
    c.cancel();
    await vi.advanceTimersByTimeAsync(1000);
    expect(n).toBe(1);
    expect(got).toHaveLength(2);
  });

  it('does not reuse a custom scene after coordinates change', async () => {
    let count = 0;
    const c = new SceneClient({
      minIntervalMs: 0,
      fetcher: async () => (count++, scene()),
      onScene: () => {},
      onError: () => {},
    });
    const p = { ...base, site: 'c-a', customSite: { id: 'c-a', name: 'A', lat_deg: -88, lon_deg_east: 1 } };
    c.request(p);
    await vi.advanceTimersByTimeAsync(10);
    c.request({ ...p, customSite: { ...p.customSite, lon_deg_east: 2 } });
    await vi.advanceTimersByTimeAsync(10);
    expect(count).toBe(2);
    c.dispose();
  });

  it('discards an old response immediately, before the throttled request starts', async () => {
    const calls: { sig: AbortSignal; res: (s: LanderScene) => void }[] = [];
    const got: number[] = [];
    const c = new SceneClient({
      minIntervalMs: 500,
      fetcher: (_p, sig) => new Promise((res) => calls.push({ sig, res })),
      onScene: (_s, p) => got.push(p.ms),
      onError: () => {},
    });
    c.request(base);
    await vi.advanceTimersByTimeAsync(0);
    c.request({ ...base, ms: base.ms + 60_000 });
    expect(calls[0]!.sig.aborted).toBe(true);
    calls[0]!.res(scene());
    await vi.advanceTimersByTimeAsync(0);
    expect(got).toEqual([]);
    await vi.advanceTimersByTimeAsync(500);
    calls[1]!.res(scene());
    await vi.advanceTimersByTimeAsync(0);
    expect(got).toEqual([base.ms + 60_000]);
    c.dispose();
  });

  it('reports errors once and not for aborted requests', async () => {
    const errs: string[] = [];
    const c = new SceneClient({
      minIntervalMs: 0,
      fetcher: async () => {
        throw new SceneError('unavailable', 'x');
      },
      onScene: () => {},
      onError: (e) => errs.push(e.kind),
    });
    c.request(base);
    await vi.advanceTimersByTimeAsync(10);
    expect(errs).toEqual(['unavailable']);
  });
});

describe('lateral section text', () => {
  function drawn(language?: 'en'): string {
    const texts: string[] = [];
    const grad = { addColorStop: () => {} };
    const ctx = new Proxy({}, {
      get: (_t, k) => (k === 'createLinearGradient' ? () => grad : k === 'fillText' || k === 'strokeText' ? (t: string) => { texts.push(t); }
        : k === 'measureText' ? () => ({ width: 10 }) : () => {}),
      set: () => true,
    }) as unknown as CanvasRenderingContext2D;
    const s = scene();
    drawSection(ctx, 800, 400, { scene: s, sceneGen: 1, terrain: null, terrainGen: 1, cam: presetCamera('side', s, 1), vExag: 1, tubeScale: 20,
      errorDeg: 0, showOverlays: true, sun: FALLBACK_SUN, tier: 'hi', ...(language ? { language } : {}) });
    return texts.join(' | ');
  }
  it('is Italian on the site pages and English in the report', () => {
    expect(drawn()).toMatch(/scala verticale/);
    const en = drawn('en');
    expect(en).toMatch(/vertical scale/);
    expect(en).toMatch(/height u \(m\)/);
    expect(en).not.toMatch(/scala verticale|quota u|crinale|Terra a|rispetto/);
    expect(en).toMatch(/\d\.\d/); // decimal point, not comma
  });
});
