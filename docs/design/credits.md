# Crediti, licenze e fonti dei dati (UI v2)

Ogni pagina sorgente è stata aperta e letta **prima** del download (15 ottobre 2026). Nessun logo NASA, nessuna
persona ritratta, nessuna formula che suggerisca approvazione. Le stesse informazioni sono nel registro
`frontend/src/viewports/bodies/assets.ts` (un test fallisce se un asset non ha credito, licenza o fonte) e nella
sezione "Crediti" visibile del visualizzatore.

## Termini verificati

| Fonte | Testo letto (estratto) | URL |
| --- | --- | --- |
| NASA SVS FAQ | "All of our content is in the public domain (unless otherwise noted) … free to download, use, and redistribute" | https://svs.gsfc.nasa.gov/help/ |
| Linee guida NASA sui media | "NASA content – images … texture maps … generally are not subject to copyright in the United States … used in a factual manner that does not imply endorsement … NASA should be acknowledged as the source" | https://www.nasa.gov/nasa-brand-center/images-and-media/ |
| Regole dati SDO | "SDO images and movies are not copyrighted unless explicitly noted … attributes the source … as: 'Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams.'" | https://sdo.gsfc.nasa.gov/data/rules.php |
| NASA 3D Resources (README) | "These assets are free and without copyright." | https://github.com/nasa/NASA-3D-Resources |

## Immagini auto-ospitate (`frontend/src/assets/bodies/`, generate da `build-bodies.py`)

| File (KB) | Sorgente (ID, file, SHA-256 del file scaricato) | Riga di credito |
| --- | --- | --- |
| `moon-color-2k.webp` (234), `moon-color-1k.webp` (58) | NASA SVS **4720** "CGI Moon Kit", `lroc_color_16bit_srgb_4k.tif` (mappa colore 2025 da LROC WAC Hapke Normalized Mosaic), sha256 `9731fa8a…` | NASA's Scientific Visualization Studio; dati LRO LROC (Arizona State University) |
| `moon-height-2k.webp` (190), `moon-height-1k.webp` (75) | SVS 4720, `ldem_16_uint.tif` (LOLA, 16 px/grado, mezzi metri + 20000), sha256 `45a2b32d…`; normalizzato 8 bit da −8,81 a +10,64 km | NASA's Scientific Visualization Studio; dati LRO LOLA |
| `earth-color-2k.webp` (200), `earth-color-1k.webp` (64) | NASA Earth Observatory, **Blue Marble: Next Generation** con topografia e batimetria, dicembre 2004, `world.topo.bathy.200412.3x5400x2700.jpg`, sha256 `a9f00889…` (pagina https://visibleearth.nasa.gov/images/73909) | NASA Earth Observatory, Blue Marble: Next Generation |
| `mars-color-1440.webp` (151), `mars-color-1k.webp` (69) | NASA 3D Resources, `Images and Textures/Mars/Mars.jpg` (1440x720), sha256 `12ec6bf0…` | NASA 3D Resources |
| `sun-aia304-1024.webp` (82), `sun-aia304-512.webp` (27) | NASA SDO, AIA 304 Å (He II, 30,4 nm, ultravioletto estremo, falsi colori), 2026-10-01 00:08:30 UT, `20261001_000830_2048_0304.jpg`, sha256 `972bc602…`; ritagliato sul disco, fuori da 1,25 raggi tutto nero (via la scritta impressa) | Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams |
| `stars-3072.webp` (223), `stars-2048.webp` (101) | NASA SVS **4851** "Deep Star Maps 2020", `starmap_2020_4k.exr` (Hipparcos-2, Tycho-2, Gaia DR2; coordinate celesti ICRF/J2000), sha256 `69b841cd…`; mappatura tonale morbida e stelle deboli attenuate (potenza 1,7) | NASA's Scientific Visualization Studio |
| `earthrise-*` (v1) | NASA AS08-14-2383 (vedi design-system.md §11) | Foto NASA, pubblico dominio |

Non usati (licenza non verificabile o budget): luci notturne e nuvole della Terra (budget), rilievo di Marte (nessuna
mappa MOLA NASA/USGS scaricabile in dimensione ragionevole: il file USGS Viking MDIM 2.1 è 12,7 GB e la pagina
Astropedia risponde 404), quindi Marte è ombreggiato senza rilievo.

## Dati numerici (NSSDCA Planetary Fact Sheets, consultati il 15/10/2026)

| Corpo | Valore mostrato | Fonte |
| --- | --- | --- |
| Luna | raggio medio 1737,4 km; gravità 1,62 m/s²; rotazione siderale 655,720 h; semiasse maggiore 0,3844·10⁶ km (**384.400 km**, distanza media dalla Terra) | https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html |
| Terra | raggio medio 6371,0 km; gravità 9,820 m/s²; rotazione siderale 23,9345 h; semiasse maggiore 149,598·10⁶ km | https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html |
| Marte | raggio medio 3389,5 km; gravità 3,73 m/s²; rotazione siderale 24,6229 h; semiasse maggiore 227,956·10⁶ km | https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html |
| Sole | raggio medio 695.700 km; gravità 274,0 m/s²; rotazione siderale 609,12 h (a 16° di latitudine); distanza media dalla Terra 149,6·10⁶ km | https://nssdc.gsfc.nasa.gov/planetary/factsheet/sunfact.html |

## Luoghi (marcatori)

Coordinate planetocentriche, longitudine Est positiva.

| Corpo | Luogo | Lat, Lon | Fonte |
| --- | --- | --- | --- |
| Luna | Apollo 11 (modulo lunare) | 0,67416, 23,47314 | NSSDCA, *Apollo Landing Site Coordinates* (Wagner et al. 2017), https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html |
| Luna | Apollo 12 (LM) | −3,0128, −23,4219 | idem |
| Luna | Apollo 14 (LM) | −3,64589, −17,47194 | idem |
| Luna | Apollo 15 (LM) | 26,13239, 3,63330 | idem |
| Luna | Apollo 16 (LM) | −8,9734, 15,5011 | idem |
| Luna | Apollo 17 (LM) | 20,1911, 30,7723 | idem |
| Luna | Chang'e 4 (Statio Tianhe) | −45,45, 177,60 | USGS/IAU Gazetteer of Planetary Nomenclature, Feature 15781 |
| Luna | Chandrayaan-3 (Statio Shiv Shakti) | −69,37, 32,32 | Gazetteer, Feature 16272 |
| Luna | Tycho (cratere, 85,29 km) | −43,30, −11,22 | Gazetteer, Feature 6163 |
| Luna | Copernicus (cratere, 96,07 km) | 9,62, −20,08 | Gazetteer, Feature 1296 |
| Marte | Olympus Mons | 18,65, 226,20 (= −133,80) | Gazetteer, Feature 4453 |
| Marte | Valles Marineris | −14,01, 301,41 (= −58,59) | Gazetteer, Feature 6288 |
| Marte | Cratere Jezero (sito di Perseverance) | 18,41, 77,69 | Gazetteer, Feature 14300 (centro del cratere, non la posizione del rover) |
| Marte | Cratere Gale (sito di Curiosity) | −5,37, 137,81 | Gazetteer, Feature 2071 (centro del cratere) |
| Marte | Hellas Planitia | −42,43, 70,50 | Gazetteer, Feature 2432 |

Gazetteer: https://planetarynames.wr.usgs.gov/Feature/&lt;ID&gt;. Pagine NSSDCA delle singole missioni (Chang'e 4
2018-103A, Chandrayaan-3 2023-098A) rispondevano con errore il 15/10/2026: per questi due si usa la denominazione
IAU del sito di atterraggio, la cui origine nel Gazetteer cita esplicitamente il lander.

**Non verificato**: la precisione posizionale dell'allineamento delle mappe (assunto: centrate su 0° di longitudine come
dichiarato da SVS; per Marte NASA 3D Resources non lo dichiara, verificato a occhio con Hellas e Syrtis Major).
