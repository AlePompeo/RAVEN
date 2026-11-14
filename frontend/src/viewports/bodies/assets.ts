// SPDX-License-Identifier: Apache-2.0
// Registro delle immagini dei corpi celesti: ogni voce porta provenienza, credito e licenza verificati
// (docs/design/credits.md). Gli URL sono risolti da Vite (file con hash, nessun byte nel bundle JS).

export interface ImageAsset {
  id: string;
  url: string;
  width: number;
  height: number;
  bytes: number;
  /** Anteprima minuscola inline (blur-up), solo per le varianti principali. */
  placeholder?: string;
  /** Riga di credito mostrata nell'interfaccia. */
  credit: string;
  /** Stato dei diritti verificato sulla pagina della fonte. */
  licence: string;
  /** Pagina della fonte (aperta e letta prima del download). */
  sourcePage: string;
  /** File originale scaricato. */
  sourceFile: string;
}

import { PLACEHOLDERS } from './placeholders';

const SVS ='Pubblico dominio (NASA SVS: "public domain unless otherwise noted")';
const NASA_MEDIA = 'Non protetto da copyright negli USA (linee guida NASA sui media)';
const u = (f: string) => new URL(`../../assets/bodies/${f}`, import.meta.url).href;

export const ASSETS = {
  moonColor2k: {
    id: 'moonColor2k',
    url: u('moon-color-2k.webp'),
    width: 2048,
    height: 1024,
    bytes: 239170,
    placeholder: PLACEHOLDERS['moon-color-2k.webp'],
    credit: "NASA's Scientific Visualization Studio, mappa colore LRO LROC (CGI Moon Kit)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4720',
    sourceFile: 'lroc_color_16bit_srgb_4k.tif',
  },
  moonColor1k: {
    id: 'moonColor1k',
    url: u('moon-color-1k.webp'),
    width: 1024,
    height: 512,
    bytes: 58988,
    credit: "NASA's Scientific Visualization Studio, mappa colore LRO LROC (CGI Moon Kit)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4720',
    sourceFile: 'lroc_color_16bit_srgb_4k.tif',
  },
  moonHeight2k: {
    id: 'moonHeight2k',
    url: u('moon-height-2k.webp'),
    width: 2048,
    height: 1024,
    bytes: 194212,
    credit: "NASA's Scientific Visualization Studio, altimetria LRO LOLA (CGI Moon Kit)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4720',
    sourceFile: 'ldem_16_uint.tif',
  },
  moonHeight1k: {
    id: 'moonHeight1k',
    url: u('moon-height-1k.webp'),
    width: 1024,
    height: 512,
    bytes: 76310,
    credit: "NASA's Scientific Visualization Studio, altimetria LRO LOLA (CGI Moon Kit)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4720',
    sourceFile: 'ldem_16_uint.tif',
  },
  earthColor2k: {
    id: 'earthColor2k',
    url: u('earth-color-2k.webp'),
    width: 2048,
    height: 1024,
    bytes: 204698,
    placeholder: PLACEHOLDERS['earth-color-2k.webp'],
    credit: 'NASA Earth Observatory, Blue Marble: Next Generation (dicembre 2004)',
    licence: NASA_MEDIA,
    sourcePage: 'https://visibleearth.nasa.gov/images/73909',
    sourceFile: 'world.topo.bathy.200412.3x5400x2700.jpg',
  },
  earthColor1k: {
    id: 'earthColor1k',
    url: u('earth-color-1k.webp'),
    width: 1024,
    height: 512,
    bytes: 65116,
    credit: 'NASA Earth Observatory, Blue Marble: Next Generation (dicembre 2004)',
    licence: NASA_MEDIA,
    sourcePage: 'https://visibleearth.nasa.gov/images/73909',
    sourceFile: 'world.topo.bathy.200412.3x5400x2700.jpg',
  },
  marsColor1440: {
    id: 'marsColor1440',
    url: u('mars-color-1440.webp'),
    width: 1440,
    height: 720,
    bytes: 154832,
    placeholder: PLACEHOLDERS['mars-color-1440.webp'],
    credit: 'NASA 3D Resources, mappa a colori di Marte',
    licence: 'Senza copyright ("free and without copyright", README di NASA 3D Resources)',
    sourcePage: 'https://github.com/nasa/NASA-3D-Resources/tree/master/Images%20and%20Textures/Mars',
    sourceFile: 'Mars.jpg',
  },
  marsColor1k: {
    id: 'marsColor1k',
    url: u('mars-color-1k.webp'),
    width: 1024,
    height: 512,
    bytes: 70800,
    credit: 'NASA 3D Resources, mappa a colori di Marte',
    licence: 'Senza copyright ("free and without copyright", README di NASA 3D Resources)',
    sourcePage: 'https://github.com/nasa/NASA-3D-Resources/tree/master/Images%20and%20Textures/Mars',
    sourceFile: 'Mars.jpg',
  },
  sun1024: {
    id: 'sun1024',
    url: u('sun-aia304-1024.webp'),
    width: 1024,
    height: 1024,
    bytes: 84220,
    placeholder: PLACEHOLDERS['sun-aia304-1024.webp'],
    credit: 'Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams (AIA 304, 1 ottobre 2026)',
    licence: 'Non protetto da copyright salvo indicazione (regole dati SDO), attribuzione richiesta',
    sourcePage: 'https://sdo.gsfc.nasa.gov/data/rules.php',
    sourceFile: '20261001_000830_2048_0304.jpg',
  },
  sun512: {
    id: 'sun512',
    url: u('sun-aia304-512.webp'),
    width: 512,
    height: 512,
    bytes: 27784,
    credit: 'Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams (AIA 304, 1 ottobre 2026)',
    licence: 'Non protetto da copyright salvo indicazione (regole dati SDO), attribuzione richiesta',
    sourcePage: 'https://sdo.gsfc.nasa.gov/data/rules.php',
    sourceFile: '20261001_000830_2048_0304.jpg',
  },
  stars3072: {
    id: 'stars3072',
    url: u('stars-3072.webp'),
    width: 3072,
    height: 1536,
    bytes: 228384,
    placeholder: PLACEHOLDERS['stars-3072.webp'],
    credit: "NASA's Scientific Visualization Studio, Deep Star Maps 2020 (Hipparcos-2, Tycho-2, Gaia DR2)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4851',
    sourceFile: 'starmap_2020_4k.exr',
  },
  stars2048: {
    id: 'stars2048',
    url: u('stars-2048.webp'),
    width: 2048,
    height: 1024,
    bytes: 102916,
    credit: "NASA's Scientific Visualization Studio, Deep Star Maps 2020 (Hipparcos-2, Tycho-2, Gaia DR2)",
    licence: SVS,
    sourcePage: 'https://svs.gsfc.nasa.gov/4851',
    sourceFile: 'starmap_2020_4k.exr',
  },
} satisfies Record<string, ImageAsset>;

export type AssetId = keyof typeof ASSETS;
