# Regioni candidate Artemis e DEM LOLA a 5 m: fonti lette

Data della ricerca: 2026-11-05. Dati machine-readable: `docs/domain/artemis_regions.json`. Tutto ciò che segue è stato letto in una fonte citata; dove una fonte non lo pubblica è scritto "non pubblicato".

## 1. Elenco delle regioni e origine del numero 17

| Fonte | Data | Contenuto letto | URL |
| --- | --- | --- | --- |
| NASA, "NASA Identifies Candidate Regions for Landing Next Americans on Moon" (RELEASE22-089) | 2022-08-19 (pagina aggiornata 2024-01-08) | 13 regioni; "approximately 15 by 15 kilometers"; sito di atterraggio "approximate 100-meter radius"; entro 6 gradi di latitudine dal polo sud. **Nessuna coordinata.** | https://www.nasa.gov/press-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/ |
| NASA, "NASA Provides Update on Artemis III Moon Landing Regions" (RELEASE24-136) | 2024-10-28 | 9 regioni, senza ordine di priorità; "multiple potential sites" per regione. **Nessuna coordinata, nessuna dimensione.** | https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ |

Il numero **17 non compare in alcuna fonte NASA letta**: è l'unione 13 (2022) + 4 nomi presenti solo nella lista 2024 (Peak near Cabeus B, Mons Mouton Plateau, Mons Mouton, Slater Plain). Viene dal `Tutorial dati NASA reali in GrazingLink.md` §9 (che cita Scientific American e SatNow, non riletti qui; SatNow ha risposto 403) e da `data/artemis_regions.json` dentro `grazinglink_backend.zip`. `DESCRIZIONE AGGIORNATA PROGETTO.pdf` e `GRAZINGLINK-descrizione-tecnica.md` non contengono "17 regioni". La lista 2024 contiene 5 nomi della lista 2022 (Haworth, Malapert Massif, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2) più i 4 nuovi. Stato del programma (Tutorial §9, SpacePolicyOnline 2026-10-23): non riletto qui.

## 2. Le 17 regioni: coordinate e DEM a 5 m

Coordinate di centro, di box o di sito: **non pubblicate** da NASA per nessuna regione (verificato sulle due release). Frame: non applicabile. Nel JSON `lat_deg` e `lon_deg_east` sono `null`, `status` = `not_published`.

| Regione | 2022 | 2024 | Prodotto Barker 5 m (PGDA 78) | Affidabilità del collegamento nome-prodotto |
| --- | --- | --- | --- | --- |
| Faustini Rim A | sì | no | LM7 (Tutorial) | non verificato: l'ordine della pagina PGDA darebbe LM8 |
| Peak Near Shackleton | sì | no | Site07 | nome PGDA identico |
| Connecting Ridge | sì | no | Site01 | nome PGDA identico |
| Connecting Ridge Extension | sì | no | SL3 | nome PGDA identico |
| de Gerlache Rim 1 | sì | no | Site11 o SL2 | ambiguo, non verificato |
| de Gerlache Rim 2 | sì | sì | Site11 o SL2 | ambiguo, non verificato |
| de Gerlache-Kocher Massif | sì | no | Site42 | nome PGDA identico |
| Haworth | sì | sì | Haworth | identico |
| Malapert Massif | sì | sì | Site23 | identico |
| Leibnitz Beta Plateau | sì | no | Site20, Site20v2 | identico |
| Nobile Rim 1 | sì | sì | Site06 | identico |
| Nobile Rim 2 | sì | sì | DM2 | identico |
| Amundsen Rim | sì | no | DM1 | identico |
| Peak near Cabeus B | no | sì | nessuno (NPA è "Cabeus exterior wall 1") | nessun prodotto identificato |
| Mons Mouton Plateau | no | sì | nessuno | nessun prodotto identificato |
| Mons Mouton | no | sì | nessuno | nessun prodotto identificato |
| Slater Plain | no | sì | nessuno | nessun prodotto identificato |

Fonte dei nomi dei prodotti: PGDA product 78, "High-Resolution LOLA Topography for Lunar South Pole Sites", M. K. Barker, https://pgda.gsfc.nasa.gov/products/78 (aggiornamenti elencati 2021-04-26 .. 2022-08-15; nessuna data di pubblicazione). Numerazione Site01.. da Mazarico et al. 2011, Icarus 211(2), 1066-1081, Table 3: tabella **non letta** (articolo non in accesso aperto; NTRS 20120010094 senza download). Articolo: Barker et al. 2021, Planet. Space Sci. 203, 105119, https://doi.org/10.1016/j.pss.2020.105119 (letta la versione NTRS 20205009660: nessuna tabella di lat/lon dei siti; riquadri "16 x 16 km" per i Site 1, 4, 7, 11).

## 3. DEM a 5 m (PGDA 78): prodotti reali, misurati il 2026-11-05

Base: `https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/<ID>/<ID>_final_adj_5mpp_surf.tif`. Frame: stereografica polare sud, X/Y in metri, MOON_ME di DE421, centri di pixel (README della directory). Pixel 5 m, float32 non compresso, GeoTIFF classico a righe (1 riga per strip; non tile, non COG), nodata NaN. Circa il 90% dei pixel è interpolato (pagina PGDA 78). Incertezze dichiarate: orizzontale 10-20 cm, verticale 2-4 cm, RMS Z mediana 0,30-0,50 m, RMS pendenza 1,5-2,5 gradi.

HEAD e GET con `Range: bytes=0-7` su Site01, Site23 e Haworth: HTTP 200, `Accept-Ranges: bytes`, risposta 206 al range. Intestazione TIFF letta via range (64 KiB) per tutti i 27 file: dimensioni e riquadro (ModelTiepoint, scala 5 m) in tabella. L'ultima colonna è il **centro del riquadro del DEM** convertito in lat/lon con proiezione sferica R=1737,4 km e x=rho sin(lon), y=rho cos(lon) (convenzione di `dem.lock.json`): localizza il tile, **non è il sito** e non va nel catalogo.

| ID | Byte | Pixel | x (m) | y (m) | Centro riquadro: lat, lon E (derivato) |
| --- | --- | --- | --- | --- | --- |
| Site01 | 40,980,810 | 3200x3200 | -19000..-3000 | -20000..-4000 | -89.46, -137.5 |
| Site04 | 40,980,806 | 3200x3200 | -9000..7000 | -15000..1000 | -89.77, -171.9 |
| Site06 | 64,025,603 | 4000x4000 | 74000..94000 | 100000..120000 | -85.44, 37.4 |
| Site07 | 40,980,808 | 3200x3200 | 22000..38000 | -28000..-12000 | -88.81, 123.7 |
| Site11 | 40,980,806 | 3200x3200 | -45000..-29000 | 7000..23000 | -88.68, -67.9 |
| Site20 | 40,980,802 | 3200x3200 | 65000..81000 | 110000..126000 | -85.43, 31.7 |
| Site20v2 | 108,192,905 | 5200x5200 | 60000..86000 | 105000..131000 | -85.43, 31.7 |
| Site23 | 70,586,804 | 4200x4200 | -11000..10000 | 111000..132000 | -85.99, -0.2 |
| Site42 | 64,025,611 | 4000x4000 | -123400..-103400 | -66100..-46100 | -85.83, -116.3 |
| Haworth | 142,123,767 | 5960x5960 | -52900..-23100 | 75600..105400 | -86.76, -22.8 |
| Shoemaker | 64,025,605 | 4000x4000 | 66000..86000 | 29000..49000 | -87.18, 62.8 |
| DM1 | 64,033,681 | 4000x4000 | 154000..174000 | 51500..71500 | -84.23, 69.4 |
| DM2 | 64,025,607 | 4000x4000 | 147000..167000 | 85000..105000 | -83.95, 58.8 |
| SL2 | 64,025,605 | 4000x4000 | -58500..-38500 | 13000..33000 | -88.23, -64.6 |
| SL3 | 64,025,611 | 4000x4000 | -38700..-18700 | -16100..3900 | -89.03, -102.0 |
| NPA | 64,033,687 | 4000x4000 | -98500..-78500 | 19500..39500 | -86.92, -71.6 |
| NPB | 64,033,687 | 4000x4000 | 175000..195000 | -8500..11500 | -83.9, 89.5 |
| NPC | 64,033,691 | 4000x4000 | 122500..142500 | -109500..-89500 | -84.54, 126.9 |
| NPD | 64,033,687 | 4000x4000 | 13000..33000 | 146000..166000 | -84.8, 8.4 |
| LM1 | 64,033,673 | 4000x4000 | 2000..22000 | -2000..18000 | -89.52, 56.3 |
| LM2 | 64,033,675 | 4000x4000 | 2000..22000 | 47000..67000 | -88.08, 11.9 |
| LM3 | 64,033,679 | 4000x4000 | 4000..24000 | 37000..57000 | -88.38, 16.6 |
| LM4 | 64,033,675 | 4000x4000 | 9000..29000 | 15000..35000 | -88.96, 37.2 |
| LM5 | 64,033,679 | 4000x4000 | 30000..50000 | 1000..21000 | -88.63, 74.6 |
| LM6 | 64,033,677 | 4000x4000 | 49000..69000 | 10000..30000 | -87.95, 71.3 |
| LM7 | 64,033,675 | 4000x4000 | 54000..74000 | -10000..10000 | -87.89, 90.0 |
| LM8 | 64,033,679 | 4000x4000 | 60000..80000 | 30000..50000 | -87.34, 60.3 |

Altri file per sito (schema pagina 78, mostrato per Site01): `_ldec.tif`, `_slp.tif`, `_toterr.tif`, `_slperr.tif`, `.xyzi` (nuvola di punti), `_ROIs.tgz`, `Clones/` (100 cloni). Dimensioni non lette. La pagina 78 non dà dimensioni: quelle sopra sono Content-Length.

Lettura minima: il file non compresso a righe rende banali i range (riga = larghezza x 4 byte, 12 800 byte per Site01). Una finestra di 2 km x 2 km (400 x 400 pixel) costa circa 5 MB per Site01 leggendo righe intere (400 x 12,8 KB), circa 9,5 MB per Haworth (5960 pixel per riga). Stima aritmetica, non misurata con un download.

## 4. Prodotti a 20 m e più grossi

| Prodotto | Dove | Letto | Stesso di `dem.lock.json`? |
| --- | --- | --- | --- |
| `ldem_85s_20m_float.img` (920 272 896 byte, 15168 x 15168, ±151,68 km) | pds-geosciences.wustl.edu; HEAD: HTTP/2 200, accept-ranges bytes, stessa lunghezza | sì | è il dataset del lock |
| `ldem_75s_240m_float.img` (58 125 376 byte) | PDS | solo dal lock | è nel lock |
| `LDEM_80S_20MPP_ADJ.TIF` (2 696 082 051 byte, 30400 x 30400, ±304 km, 20 m, tile 512x512, compressione TIFF 8 = deflate, BigTIFF, COG) | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF; HEAD: 200, Accept-Ranges bytes, Last-Modified 2023-07-07 | sì | **no**: ri-derivazione con orbite corrette di Barker et al. (PGDA 90, "A New View of the Lunar South Pole from LOLA"); stesso frame, griglia e valori diversi |
| `LDEM_83S_10MPP_ADJ` 4,8 G; `LDEM_80S_40MPP_ADJ` 685 M; `LDEM_80S_80MPP_ADJ` 181 M; `LDEM_75S_30MPP_ADJ` 2,7 G; `LDEM_60S_60MPP_ADJ` 2,9 G; `_120MPP` 785 M; `_240MPP` 210 M | stessa cartella LOLA_20mpp/; dimensioni dalla pagina https://pgda.gsfc.nasa.gov/products/90 | solo dimensioni dalla pagina; range non verificato | no |

Nomi vecchio -> nuovo (Barker et al., "A New View of the Lunar South Pole from the Lunar Orbiter Laser Altimeter (LOLA)", NTRS 20230014419, Table 1; versione NTRS, rivista non letta): LDEM_85S_10M -> LDEM_83S_10MPP_ADJ (±216,4 km), LDEM_80S_20M -> LDEM_80S_20MPP_ADJ (±304 km), 40M, 80M, 75S_30M, 60S_60M/120M/240M. I nomi `LDEM_87S_5MPP_ADJ` e `LDEM_875S_5M` citati nel Tutorial **non compaiono** nella Table 1 né nell'elenco della pagina 90: non confermati.

Bertone et al., "Enhanced Topography Models for Selected Lunar South Pole Regions with Shape-from-Shading", PGDA 104, https://pgda.gsfc.nasa.gov/products/104: SDEM a 5 m per le 13 regioni originali, oltre 4 500 km2; dati su Zenodo (DOI non estratto), non su PGDA; formato, dimensioni e supporto a range **non letti**.

## 5. Raccomandazione

1. Integrabile subito con pochi MB: i 5 m di PGDA 78 per le regioni con prodotto identificato (§2), via range HTTP su file non compresso, 5-10 MB per finestra di 2 km (aritmetica). Prima: misurare un download reale e confrontare con `ldem_85s_20m_float` sullo stesso punto (il 20 m ADJ è un prodotto diverso, la coincidenza non è garantita).
2. `LDEM_80S_20MPP_ADJ.TIF` (COG) è un'alternativa a 20 m con range a tile, ma pesa 2,7 GB e richiede un decoder deflate/BigTIFF. Non sostituisce il PDS già bloccato senza nuovo lock e nuovo SHA-256.
3. Coordinate lecite ora: **nessuna coordinata di regione NASA**. Restano valide, come oggi, le coordinate dei centri di feature IAU in `sites.json` (`coordinate_basis` = `feature_centre`). L'estensione del DEM (x, y in metri, tabella §3) è lecita come dato del prodotto, etichettata "extent del DEM", mai come centro o sito.
4. Da tenere fuori finché non c'è fonte: lat/lon delle 17 regioni; l'associazione de Gerlache Rim 1/2 con Site11/SL2; Faustini Rim A = LM7 o LM8; DEM di Peak near Cabeus B, Mons Mouton Plateau, Mons Mouton, Slater Plain; i nomi `LDEM_87S_5MPP_ADJ`/`LDEM_875S_5M`; SDEM di Bertone finché formato e dimensioni non sono letti; la Table 3 di Mazarico 2011 (potrebbe dare lat/lon dei Site 1..).
5. Sblocco possibile: leggere le coordinate dalla Table 3 di Mazarico 2011 o dalle ROI shapefile (`Site01_ROIs.tgz`; la pagina 78 dichiara ROI solo per Site 01, 04, 06, 07, 11) e citarle.
