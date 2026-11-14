// SPDX-License-Identifier: Apache-2.0
// Registro dei corpi celesti del visualizzatore: mappe, fatti e luoghi, ciascuno con la sua fonte verificata
// (docs/design/credits.md). Nessun valore senza fonte.
import { ASSETS, type AssetId } from './assets';
import type { BodyId } from '../scene';

export type PlaceKind = 'landing' | 'crater' | 'feature' | 'polar' | 'station' | 'custom';

export interface Place {
  id: string;
  name: string;
  kind: PlaceKind;
  lat: number;
  /** Longitudine Est positiva, −180..180. */
  lon: number;
  note?: string;
  source: string;
  /** Id del sito nel registro dell'analisi lunare (backend/domain/data/sites.json), se il luogo e' confrontabile. */
  siteId?: string;
}

export interface Fact {
  label: string;
  value: number;
  unit: string;
  digits?: number;
}

export interface BodyDef {
  id: BodyId;
  name: string;
  /** Il Sole è emissivo: niente terminatore né cursore della luce. */
  emissive: boolean;
  /** Mappe per livello di qualità. */
  color: { hi: AssetId; lo: AssetId };
  height?: { hi: AssetId; lo: AssetId; kmMin: number; kmMax: number; radiusKm: number };
  /** Il cielo terrestre: un bordo azzurro sottile al lembo. */
  atmosphere?: [number, number, number];
  /** Riflettanza media usata dallo shading (le mappe sono normalizzate per l'aspetto). */
  albedo: number;
  keyStat: Fact;
  facts: Fact[];
  factsSource: string;
  places: Place[];
  /** Telemetria del sito lunare (LIVE, ultimo campione, Sole dal sito): solo per la Luna. */
  telemetry: boolean;
  /** Attribuzione breve sempre visibile sul palco (i crediti completi sono sotto). */
  shortCredit: string;
}

const NSSDC = 'https://nssdc.gsfc.nasa.gov/planetary/factsheet/';
const APOLLO = 'NSSDCA, Apollo Landing Site Coordinates (Wagner et al. 2017)';
const NSS_ARTIFACT = 'NSSDCA, Lunar Artifact Landings and Impacts (DE421, Mean Earth/Polar Axis)';
const GAZ = (id: number) => `USGS/IAU Gazetteer of Planetary Nomenclature, Feature ${id}`;
const m360 = (lon: number) => (lon > 180 ? lon - 360 : lon);

export const BODIES: Record<BodyId, BodyDef> = {
  moon: {
    id: 'moon',
    name: 'Luna',
    emissive: false,
    color: { hi: 'moonColor2k', lo: 'moonColor1k' },
    height: { hi: 'moonHeight2k', lo: 'moonHeight1k', kmMin: -8.8135, kmMax: 10.64, radiusKm: 1737.4 },
    albedo: 0.92,
    keyStat: { label: 'distanza media dalla Terra', value: 384400, unit: 'km' },
    facts: [
      { label: 'Raggio medio', value: 1737.4, unit: 'km', digits: 1 },
      { label: 'Gravità', value: 1.62, unit: 'm/s²', digits: 2 },
      { label: 'Rotazione', value: 655.72, unit: 'h', digits: 1 },
    ],
    factsSource: `${NSSDC}moonfact.html`,
    telemetry: true,
    shortCredit: 'Mappe NASA LRO (LROC e LOLA) dal CGI Moon Kit di NASA SVS; stelle NASA SVS',
    places: [
      { id: 'apollo11', name: 'Apollo 11', kind: 'landing', lat: 0.67416, lon: 23.47314, note: 'luglio 1969', source: APOLLO, siteId: 'apollo11' },
      { id: 'apollo12', name: 'Apollo 12', kind: 'landing', lat: -3.0128, lon: -23.4219, note: 'novembre 1969', source: APOLLO, siteId: 'apollo12' },
      { id: 'apollo14', name: 'Apollo 14', kind: 'landing', lat: -3.64589, lon: -17.47194, note: 'febbraio 1971', source: APOLLO, siteId: 'apollo14' },
      { id: 'apollo15', name: 'Apollo 15', kind: 'landing', lat: 26.13239, lon: 3.6333, note: 'luglio 1971', source: APOLLO, siteId: 'apollo15' },
      { id: 'apollo16', name: 'Apollo 16', kind: 'landing', lat: -8.9734, lon: 15.5011, note: 'aprile 1972', source: APOLLO, siteId: 'apollo16' },
      { id: 'apollo17', name: 'Apollo 17', kind: 'landing', lat: 20.1911, lon: 30.7723, note: 'dicembre 1972', source: APOLLO, siteId: 'apollo17' },
      { id: 'change4', name: "Chang'e 4", kind: 'landing', lat: -45.45, lon: 177.6, note: 'Statio Tianhe, lato nascosto', source: GAZ(15781), siteId: 'change4' },
      { id: 'chandrayaan3', name: 'Chandrayaan-3', kind: 'landing', lat: -69.37, lon: 32.32, note: 'Statio Shiv Shakti', source: GAZ(16272), siteId: 'chandrayaan3' },
      { id: 'luna9', name: "Luna 9", kind: 'landing', lat: 7.13, lon: -64.37, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna9' },
      { id: 'surveyor1', name: "Surveyor 1", kind: 'landing', lat: -2.4745, lon: -43.3398, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'surveyor1' },
      { id: 'luna13', name: "Luna 13", kind: 'landing', lat: 18.87, lon: -62.05, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna13' },
      { id: 'surveyor3', name: "Surveyor 3", kind: 'landing', lat: -3.0162, lon: -23.418, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'surveyor3' },
      { id: 'surveyor5', name: "Surveyor 5", kind: 'landing', lat: 1.4551, lon: 23.1943, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'surveyor5' },
      { id: 'surveyor6', name: "Surveyor 6", kind: 'landing', lat: 0.4742, lon: -1.4275, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'surveyor6' },
      { id: 'surveyor7', name: "Surveyor 7", kind: 'landing', lat: -40.9812, lon: -11.5127, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'surveyor7' },
      { id: 'luna16', name: "Luna 16", kind: 'landing', lat: -0.5137, lon: 56.3638, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna16' },
      { id: 'luna17', name: "Luna 17", kind: 'landing', lat: 38.23764, lon: -35.00163, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna17' },
      { id: 'luna20', name: "Luna 20", kind: 'landing', lat: 3.7863, lon: 56.6242, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna20' },
      { id: 'luna21', name: "Luna 21", kind: 'landing', lat: 25.9994, lon: 30.4076, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna21' },
      { id: 'luna23', name: "Luna 23", kind: 'landing', lat: 12.6667, lon: 62.1511, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna23' },
      { id: 'luna24', name: "Luna 24", kind: 'landing', lat: 12.7142, lon: 62.2129, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'luna24' },
      { id: 'change3', name: "Chang'e 3", kind: 'landing', lat: 44.1214, lon: -19.5117, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'change3' },
      { id: 'change5', name: "Chang'e 5", kind: 'landing', lat: 43.0576, lon: -51.9161, note: 'atterraggio morbido robotico', source: NSS_ARTIFACT, siteId: 'change5' },
      { id: 'amundsen', name: "Amundsen", kind: 'polar', lat: -84.44, lon: 83.07, note: 'cratere polare (centro della feature)', source: GAZ(247), siteId: 'amundsen' },
      { id: 'cabeus', name: "Cabeus", kind: 'polar', lat: -85.33, lon: -42.13, note: 'cratere polare (centro della feature)', source: GAZ(953), siteId: 'cabeus' },
      { id: 'bay', name: "Bay", kind: 'polar', lat: -88.76, lon: -36.85, note: 'cratere polare (centro della feature)', source: GAZ(16417), siteId: 'bay' },
      { id: 'brill', name: "Brill", kind: 'polar', lat: -88.27, lon: -93.41, note: 'cratere polare (centro della feature)', source: GAZ(16195), siteId: 'brill' },
      { id: 'burbidge', name: "Burbidge", kind: 'polar', lat: -86.35, lon: 48.6, note: 'cratere polare (centro della feature)', source: GAZ(16250), siteId: 'burbidge' },
      { id: 'cartwright', name: "Cartwright", kind: 'polar', lat: -87.65, lon: -46.95, note: 'cratere polare (centro della feature)', source: GAZ(16416), siteId: 'cartwright' },
      { id: 'boguslawsky', name: "Boguslawsky", kind: 'polar', lat: -72.9, lon: 43.26, note: 'cratere polare (centro della feature)', source: GAZ(796), siteId: 'boguslawsky' },
      { id: 'boussingault', name: "Boussingault", kind: 'polar', lat: -70.21, lon: 53.73, note: 'cratere polare (centro della feature)', source: GAZ(844), siteId: 'boussingault' },
      { id: 'casatus', name: "Casatus", kind: 'polar', lat: -72.7, lon: -30.75, note: 'cratere polare (centro della feature)', source: GAZ(1040), siteId: 'casatus' },
      { id: 'boltzmann', name: "Boltzmann", kind: 'polar', lat: -74.82, lon: -90.41, note: 'cratere polare (centro della feature)', source: GAZ(805), siteId: 'boltzmann' },
      { id: 'bailly', name: "Bailly", kind: 'polar', lat: -66.82, lon: -68.9, note: 'cratere polare (centro della feature)', source: GAZ(561), siteId: 'bailly' },
      { id: 'brashear', name: "Brashear", kind: 'polar', lat: -73.54, lon: -171.57, note: 'cratere polare (centro della feature)', source: GAZ(864), siteId: 'brashear' },
      { id: 'antoniadi', name: "Antoniadi", kind: 'polar', lat: -69.3, lon: -173.06, note: 'cratere polare (centro della feature)', source: GAZ(296), siteId: 'antoniadi' },
      { id: 'alekhin', name: "Alekhin", kind: 'polar', lat: -67.94, lon: -131.85, note: 'cratere polare (centro della feature)', source: GAZ(174), siteId: 'alekhin' },
      { id: 'ashbrook', name: "Ashbrook", kind: 'polar', lat: -81.1, lon: -110.58, note: 'cratere polare (centro della feature)', source: GAZ(422), siteId: 'ashbrook' },
      { id: 'braude', name: "Braude", kind: 'polar', lat: -81.82, lon: 158.88, note: 'cratere polare (centro della feature)', source: GAZ(14564), siteId: 'braude' },
      { id: 'blancanus', name: "Blancanus", kind: 'polar', lat: -63.77, lon: -21.63, note: 'cratere polare (centro della feature)', source: GAZ(767), siteId: 'blancanus' },
      { id: 'bettinus', name: "Bettinus", kind: 'polar', lat: -63.4, lon: -45.16, note: 'cratere polare (centro della feature)', source: GAZ(724), siteId: 'bettinus' },
      { id: 'berlage', name: "Berlage", kind: 'polar', lat: -63.04, lon: -163.61, note: 'cratere polare (centro della feature)', source: GAZ(703), siteId: 'berlage' },
      { id: 'cabannes', name: "Cabannes", kind: 'polar', lat: -61.24, lon: -170.21, note: 'cratere polare (centro della feature)', source: GAZ(952), siteId: 'cabannes' },
      { id: 'bellinsgauzen', name: "Bellinsgauzen", kind: 'polar', lat: -60.72, lon: -164.85, note: 'cratere polare (centro della feature)', source: GAZ(674), siteId: 'bellinsgauzen' },
      { id: 'change6', name: "Chang'e 6", kind: 'landing', lat: -41.63, lon: -153.98, note: 'sito di atterraggio, centro della stazione', source: GAZ(16328), siteId: 'change6' },
      { id: 'malapert-massif', name: 'Malapert Massif', kind: 'polar', lat: -85.98, lon: -1.67, note: 'massiccio polare, regione candidata Artemis III (centro della feature)', source: GAZ(16338), siteId: 'malapert-massif' },
      { id: 'haworth', name: 'Haworth', kind: 'polar', lat: -87.45, lon: -5.17, note: 'cratere polare, regione candidata Artemis III (centro della feature)', source: GAZ(14502), siteId: 'haworth' },
      { id: 'mons-mouton', name: 'Mons Mouton', kind: 'polar', lat: -84.6, lon: 31.0, note: 'massiccio polare, regione candidata Artemis III (centro della feature)', source: GAZ(16070), siteId: 'mons-mouton' },
      { id: 'nobile-rim', name: 'Nobile (bordo)', kind: 'polar', lat: -85.28, lon: 53.27, note: 'bordo di cratere polare, regione candidata Artemis III (centro della feature)', source: GAZ(4321), siteId: 'nobile-rim' },
      { id: 'de-gerlache', name: 'de Gerlache (bordo)', kind: 'polar', lat: -88.48, lon: -88.34, note: 'bordo di cratere polare, regione candidata Artemis III (centro della feature)', source: GAZ(1439), siteId: 'de-gerlache' },
      { id: 'shackleton', name: 'Shackleton', kind: 'polar', lat: -89.67, lon: 129.78, note: 'cratere vicino al polo sud, regione candidata Artemis III (centro della feature)', source: GAZ(5450), siteId: 'shackleton' },
      { id: 'tycho', name: 'Tycho', kind: 'crater', lat: -43.3, lon: -11.22, note: 'cratere di 85 km', source: GAZ(6163) },
      { id: 'copernicus', name: 'Copernicus', kind: 'crater', lat: 9.62, lon: -20.08, note: 'cratere di 96 km', source: GAZ(1296) },
    ],
  },
  earth: {
    id: 'earth',
    name: 'Terra',
    emissive: false,
    color: { hi: 'earthColor2k', lo: 'earthColor1k' },
    atmosphere: [0.42, 0.66, 1],
    albedo: 1,
    keyStat: { label: 'distanza media dal Sole', value: 149.598, unit: 'milioni di km', digits: 1 },
    facts: [
      { label: 'Raggio medio', value: 6371.0, unit: 'km', digits: 0 },
      { label: 'Gravità', value: 9.82, unit: 'm/s²', digits: 2 },
      { label: 'Rotazione', value: 23.9345, unit: 'h', digits: 2 },
    ],
    factsSource: `${NSSDC}earthfact.html`,
    telemetry: false,
    shortCredit: 'NASA Earth Observatory, Blue Marble: Next Generation; stelle NASA SVS',
    places: [],
  },
  sun: {
    id: 'sun',
    name: 'Sole',
    emissive: true,
    color: { hi: 'sun1024', lo: 'sun512' },
    albedo: 1,
    keyStat: { label: 'distanza media dalla Terra', value: 149.6, unit: 'milioni di km', digits: 1 },
    facts: [
      { label: 'Raggio medio', value: 695700, unit: 'km', digits: 0 },
      { label: 'Gravità', value: 274.0, unit: 'm/s²', digits: 0 },
      { label: 'Rotazione a 16° di latitudine', value: 609.12, unit: 'h', digits: 0 },
    ],
    factsSource: `${NSSDC}sunfact.html`,
    telemetry: false,
    shortCredit: 'Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams; stelle NASA SVS',
    places: [],
  },
  mars: {
    id: 'mars',
    name: 'Marte',
    emissive: false,
    color: { hi: 'marsColor1440', lo: 'marsColor1k' },
    atmosphere: [0.95, 0.62, 0.42],
    albedo: 1,
    keyStat: { label: 'distanza media dal Sole', value: 227.956, unit: 'milioni di km', digits: 1 },
    facts: [
      { label: 'Raggio medio', value: 3389.5, unit: 'km', digits: 1 },
      { label: 'Gravità', value: 3.73, unit: 'm/s²', digits: 2 },
      { label: 'Rotazione', value: 24.6229, unit: 'h', digits: 2 },
    ],
    factsSource: `${NSSDC}marsfact.html`,
    telemetry: false,
    shortCredit: 'Mappa di Marte NASA 3D Resources; stelle NASA SVS',
    places: [
      { id: 'olympus', name: 'Olympus Mons', kind: 'feature', lat: 18.65, lon: m360(226.2), note: 'vulcano a scudo', source: GAZ(4453) },
      { id: 'valles', name: 'Valles Marineris', kind: 'feature', lat: -14.01, lon: m360(301.41), note: 'sistema di canyon', source: GAZ(6288) },
      { id: 'jezero', name: 'Jezero', kind: 'crater', lat: 18.41, lon: 77.69, note: 'cratere del rover Perseverance (centro del cratere)', source: GAZ(14300) },
      { id: 'gale', name: 'Gale', kind: 'crater', lat: -5.37, lon: 137.81, note: 'cratere del rover Curiosity (centro del cratere)', source: GAZ(2071) },
      { id: 'hellas', name: 'Hellas Planitia', kind: 'feature', lat: -42.43, lon: 70.5, note: 'bacino da impatto', source: GAZ(2432) },
    ],
  },
};

export const KIND_LABEL: Record<PlaceKind, string> = { landing: 'Allunaggi e atterraggi', crater: 'Crateri', feature: 'Rilievi e bacini', polar: 'Siti polari candidati', station: 'Complessi DSN', custom: 'Siti personalizzati' };

/** Immagini richieste per mostrare un corpo (più il cielo). */
export function assetsFor(id: BodyId, tier: 'hi' | 'lo'): AssetId[] {
  const b = BODIES[id];
  const list: AssetId[] = [b.color[tier]];
  if (b.height) list.push(b.height[tier]);
  return list;
}

export function starsAsset(tier: 'hi' | 'lo'): AssetId {
  return tier === 'hi' ? 'stars3072' : 'stars2048';
}

/** Crediti unici dei file usati da un corpo, nell'ordine di visualizzazione. */
export function creditsFor(id: BodyId): string[] {
  const ids = [...assetsFor(id, 'hi'), starsAsset('hi')];
  return [...new Set(ids.map((a) => ASSETS[a].credit))];
}
