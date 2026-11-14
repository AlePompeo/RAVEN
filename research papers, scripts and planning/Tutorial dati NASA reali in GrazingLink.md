# Tutorial: usare i dati NASA reali in GrazingLink

Backend GrazingLink v0.1. Verificato con le effemeridi reali `de440.bsp`. I DEM LOLA non erano scaricabili dalla sandbox: gli script sono testati su file sintetici con le stesse caratteristiche, quindi vanno provati sui vostri file veri.

## Correzione al messaggio precedente

Avevo consigliato `gdal_translate -unscale` per convertire i DEM. Con i prodotti LOLA può dare il **raggio planetario** (DN × 0,5 + 1.737.400 m) invece dell'**altezza** (DN × 0,5), e l'orizzonte uscirebbe sbagliato senza alcun errore. Usate invece `scripts/prepare_lola_dem.py` (passo 3). Il lettore ora rifiuta i file con valori da raggio.

## 1. Cosa serve

| Dato | Fonte | Serve per | Dimensione |
| --- | --- | --- | --- |
| Posizioni di Sole, Terra, Luna | NAIF/JPL, `de440s.bsp` | geometria | circa 32 MB |
| Secondi intercalari | NAIF, `naif0012.tls` | tempo UTC | piccolo |
| Orientamento della Luna | NAIF, `moon_pa_de440_200625.bpc` e `moon_de440_250416.tf` | frame lunare ME | pochi MB |
| Topografia | LOLA GDR polare sud (PDS) | orizzonte | da 21 MB a 1,8 GB |
| Riferimenti | Horizons, Quickmap, Moon Trek | validazione | n.d. |

Ordine dei passi: kernel, DEM, conversione, verifica, uso, validazione.

## 2. Prerequisiti

```
pip install -r requirements.txt
```

`rasterio` include GDAL: non serve installarlo a parte.

## 3. Passo 1: kernel SPICE

```
python scripts/fetch_kernels.py
```

Scarica in `./kernels` i quattro file della tabella. Se un indirizzo non risponde, i file sono nelle cartelle `lsk/`, `spk/planets/`, `pck/` e `fk/satellites/` di https://naif.jpl.nasa.gov/pub/naif/generic\_kernels/ . I nomi con data possono cambiare: prendete l'ultima versione di `moon_de440_*.tf` e aggiornate l'elenco nello script.

**Verifica.** Avviate il server (`uvicorn grazinglink.api:app`) e aprite `/health`:

- `orientation: spice:MOON_ME_DE440_ME421`: tutto a posto.
- `orientation: iau2009`: mancano il `.bpc` o il `.tf`. Funziona, ma con errori di centinaia di metri sulla superficie, e i risultati lo dichiarano nei warning.

**Perché proprio questo frame.** I DEM LOLA sono nel frame Mean Earth/Polar Axis di DE421. `MOON_ME_DE440_ME421` è il frame DE440 allineato a quello. `de440s.bsp` copre gli anni 1849-2150.

## 4. Passo 2: scegliere e scaricare il DEM

Prodotti polari sud: https://imbrium.mit.edu/BROWSE/LOLA\_GDR/POLAR/SOUTH\_POLE (gli stessi dati sono sul PDS Geosciences Node). Ogni prodotto ha una versione IMG con label LBL e una JP2.

| Prodotto | Risoluzione | Copre | IMG | JP2 |
| --- | --- | --- | --- | --- |
| `LDEM_85S_40M` | 40 m | 85°S fino al polo | 110 MB | 21 MB |
| `LDEM_85S_20M` | 20 m | 85°S fino al polo | 439 MB | 60 MB |
| `LDEM_85S_10M` | 10 m | 85°S fino al polo | 1756 MB | 175 MB |
| `LDEM_80S_40M` | 40 m | 80°S fino al polo | 441 MB | 69 MB |
| `LDEM_80S_20M` | 20 m | 80°S fino al polo | 1763 MB | 194 MB |
| `LDEM_875S_5M` | 5 m | 87,5°S fino al polo | 1756 MB | 163 MB |

Per un primo test scaricate `LDEM_85S_40M`.

**Il sito deve stare lontano dal bordo del tile.** Distanza dal polo ≈ (90 − |lat|) × 30,3 km, e il tile 85°S arriva a circa 152 km dal polo. Un sito a 86°S sta a circa 122 km dal polo, quindi a circa 30 km dal bordo sul lato degli assi. Con l'orizzonte a 60 km (default) serve il tile 80°S, oppure un `horizonRangeKm` più basso. Se i dati mancano, `dem_limited` lo segnala.

**DEM già pronti dei siti candidati** (5 m/px, GeoTIFF): su imbrium.mit.edu e su https://pgda.gsfc.nasa.gov/products/90 (stereografica polare sud, frame MOON\_ME di DE421). Passateli comunque da `check_dem.py`: unità e convenzioni vanno verificate.

Scaricate `.IMG` e `.LBL` nella stessa cartella. Per i `.JP2`, se GDAL non vede il georiferimento, serve anche il file `.AUX.XML` descritto nelle FAQ del PDS Geosciences Node.

## 5. Passo 3: convertire e ritagliare

```
python scripts/prepare_lola_dem.py LDEM_85S_20M.LBL -o data/dem/LDEM_85S_20M_sito.tif --crop LAT LON 90
```

- `--crop LAT LON RAGGIO_KM` ritaglia attorno al sito (raggio = `horizonRangeKm` più un margine). Senza `--crop` converte tutto il tile, fino a 1,8 GB.
- Regola applicata: **altezza = DN × 0,5**. L'OFFSET 1.737.400 del label è il raggio di riferimento e NON si somma.
- Lo script stampa min, max e mediana delle quote e si ferma se sembrano raggi.
- Il file in uscita è Float32, in metri, con lo stesso CRS e lo stesso georiferimento dell'originale.

## 6. Passo 4: verificare (obbligatorio)

```
python scripts/check_dem.py data/dem/LDEM_85S_20M_sito.tif --lat LAT --lon LON --range-km 60
```

| Controllo | Cosa verifica | Se fallisce |
| --- | --- | --- |
| 1. Unità | le quote sono altezze, non raggi | FAIL: riconvertire con `prepare_lola_dem.py` |
| 2. Proiezione | il CRS del file coincide con la convenzione del backend (x = ρ sin lon, y = ρ cos lon, longitudine 0 in alto, 90°E a destra) | FAIL: il DEM verrebbe letto nel posto sbagliato, non usarlo. WARN (file senza CRS): fare il controllo 5 |
| 3. Copertura | distanza del sito dal bordo almeno pari al raggio dell'orizzonte | WARN: tile più grande o `horizonRangeKm` minore |
| 4. Sito e orizzonte | quota del sito, orizzonte massimo e minimo, azimut con dati mancanti | FAIL se non c'è dato al sito |
| 5. Caratteristiche | lat/lon del punto più alto e più basso entro 20 km | se la cima o il cratere sono altrove, orientamento o proiezione sono sbagliati |

Per il controllo 5 confrontate le coordinate stampate con Quickmap o Moon Trek. Valori attesi: al polo sud le quote sono di alcuni km (crateri profondi e creste), mai decine di km né milioni di metri.

## 7. Passo 5: usarlo nel backend

Mettete il file in `data/dem/` (oppure impostate `GL_DEM_DIR`) e riavviate. `/health` elenca i DEM; se più DEM coprono il sito il motore li sovrappone, dal più fine al più grosso.

Controllo rapido: `POST /horizon` con `latitude` e `longitude` restituisce `site_elevation_m`, `dem_id` e `dem_limited_fraction`.

Scenario completo:

```
curl -X POST 'localhost:8000/simulate?series=false' -H 'content-type: application/json' -d '{"id":"A","latitude":-85.5,"longitude":0.0,"startTime":"2027-04-07T00:00:00Z","durationHours":720,"timeStepMinutes":30,"antenna":{}}'
```

In `provenance` controllate che:

- `dem` sia presente, con id, risoluzione e quota del sito;
- `ephemeris.orientation` sia `spice:MOON_ME_DE440_ME421`;
- nei `warnings` non compaiano più gli avvisi sul DEM mancante e sul modello IAU 2009.

## 8. Passo 6: validare con riferimenti NASA

Sono i controlli da portare ai giudici.

1. **Sole e Terra (Horizons).** Su https://ssd.jpl.nasa.gov/horizons/ scegliete Observer Table, bersaglio Sun (10) e poi Earth (399), osservatore sulla superficie lunare (Moon, 301) alle coordinate del sito, quantità 4 (azimut ed elevazione apparenti) e gli stessi istanti UTC dello scenario. Confrontate con `sun_az_deg`, `sun_el_deg`, `earth_az_deg`, `earth_el_deg`. Scarti piccoli sono attesi; scarti di gradi indicano un errore di frame, di segno est/ovest o di azimut (0 = Nord, in senso orario). Non ho potuto misurare lo scarto reale con Horizons: fatelo voi e riportate il numero.
2. **Quote e rilievo (Quickmap, Moon Trek).** Confrontate quota del sito e posizione di cime e crateri vicini con i valori di `check_dem.py`.
3. **Illuminazione.** Confrontate struttura e ordine di grandezza con le mappe di illuminazione polari del LOLA PDS Archive (`Polar_illumination` su imbrium.mit.edu). I siti luminosi e quelli in ombra devono coincidere; i numeri esatti no, perché altezza del punto, periodo e modello del Sole differiscono.
4. **Test automatici.** `python -m pytest -q`. Includono il punto sub-solare del 2027-04-07 00:00 UTC (1,30°N, 174,61°E), uguale a quello della vostra app.

## 9. Dati Artemis: regioni candidate e luce continua

Il backend contiene il catalogo delle regioni candidate NASA e calcola la luce continua per tutta la permanenza. Le coordinate vanno inserite da voi da una fonte verificata.

**Stato del programma (ottobre 2026).** Artemis III è ora un test in orbita terrestre previsto a metà 2027. Il primo allunaggio è Artemis IV, nel 2028, e il polo sud resta la destinazione: NASA ha detto che servono altri dati dai lander robotici prima della decisione finale ([SpacePolicyOnline, 23 ottobre 2026](https://spacepolicyonline.com/news/nasa-is-full-steam-ahead-on-artemis-iii-iv-and-v/)). Chiamate le regioni «Artemis landing candidate regions», non «Artemis III».

### Il catalogo

In `data/artemis_regions.json` ci sono 17 regioni: le 13 annunciate nel 2022 ([Scientific American](https://www.scientificamerican.com/article/nasa-unveils-candidate-landing-sites-for-artemis-astronauts/)) e 4 comparse nella lista di 9 del 2024 ([SatNow](https://www.satnow.com/news/details/2491-nasa-reveals-nine-potential-landing-sites-for-artemis-iii-near-lunar-south-pole)). Ogni regione indica il prodotto DEM a 5 m di Barker et al. ([PGDA 78](https://pgda.gsfc.nasa.gov/products/78)); per le 13 originali esistono anche i DEM shape-from-shading di Bertone et al. ([PGDA 104](https://pgda.gsfc.nasa.gov/products/104)).

| Regione | Lista 2022 (13) | Lista 2024 (9) | DEM 5 m Barker (PGDA 78) |
| --- | --- | --- | --- |
| Faustini Rim A | sì | no | LM7 |
| Peak Near Shackleton | sì | no | Site07 |
| Connecting Ridge | sì | no | Site01 |
| Connecting Ridge Extension | sì | no | SL3 |
| de Gerlache Rim 1 | sì | no | Site11 o SL2 (da verificare) |
| de Gerlache Rim 2 | sì | sì | Site11 o SL2 (da verificare) |
| de Gerlache-Kocher Massif | sì | no | Site42 |
| Haworth | sì | sì | Haworth |
| Malapert Massif | sì | sì | Site23 |
| Leibnitz Beta Plateau | sì | no | Site20 (anche Site20v2) |
| Nobile Rim 1 | sì | sì | Site06 |
| Nobile Rim 2 | sì | sì | DM2 |
| Amundsen Rim | sì | no | DM1 |
| Peak near Cabeus B | no | sì | nessuno identificato |
| Mons Mouton Plateau | no | sì | nessuno identificato |
| Mons Mouton | no | sì | nessuno identificato |
| Slater Plain | no | sì | nessuno identificato |

Per le quattro regioni senza DEM a 5 m usate il tile polare LDEM (20 o 40 m) e controllate PGDA.

### Perché le coordinate sono vuote

Nelle fonti consultate NASA indica regioni di circa 15 × 15 km, con siti di circa 100 m di raggio, ma non le coordinate delle singole regioni. Non le ho inventate: impostatele da Quickmap, Moon Trek o da una pubblicazione NASA.

```
python scripts/add_artemis_site.py --list
python scripts/add_artemis_site.py --region malapert-massif --lat LAT --lon LON --source "Quickmap" --verified
python scripts/add_artemis_site.py --region haworth --from-dem data/dem/Haworth.tif --source "centro DEM PGDA"
```

`--from-dem` usa il centro del DEM: è un punto di partenza, non il sito. Le coordinate devono stare entro 6° dal polo (da −90° a −84°). `GET /artemis/regions` mostra per ogni regione `needs_coordinates`, `no_dem` oppure `ready`.

### Usare i DEM regionali a 5 m

I DEM Barker sono GeoTIFF in stereografica polare sud, nel frame MOON\_ME di DE421, con il pixel uguale all'altezza in metri, e coprono zone piccole. Mettete in `data/dem/` sia il DEM a 5 m sia il tile polare a 20 o 40 m: il motore li sovrappone dal più fine al più grosso. Il dettaglio resta vicino al sito e, oltre il bordo del DEM fine, si ripiega sul tile grosso invece che sulla sfera.

- Controllate ogni file con `check_dem.py` e un `--range-km` piccolo per i DEM regionali.
- Leggete `provenance.dem.layers` nel risultato: elenca i DEM usati.
- Alla giunzione tra DEM possono esserci piccoli salti di quota.
- Circa il 90% dei pixel a 5 m è interpolato (Barker et al.): presentate l'orizzonte come una stima.

### Luce continua per tutta la permanenza

Nel 2022 NASA ha dichiarato che ogni regione ha siti con luce continua per i 6,5 giorni previsti sulla superficie dell'Artemis III originale. Il backend lo calcola per ogni data di arrivo:

```
curl -X POST localhost:8000/stay-windows -H 'content-type: application/json' -d '{"scenario":{"id":"A","latitude":-85.5,"longitude":0.0,"startTime":"2027-04-07T00:00:00Z","durationHours":1},"n_days":120,"stay_hours":156,"stride_hours":6,"step_minutes":30}'
```

Per ogni data di arrivo la risposta dà `ok` (luce continua), `sunlit_percent`, `longest_dark_h`, `earth_visible_percent` e `longest_earth_blackout_h`. In `summary.ok_start_ranges` trovate gli intervalli di date adatte. Potete aggiungere vincoli con `max_earth_blackout_h` e `min_earth_visible_percent`.

- `stay_hours` = 156 è la durata dell'Artemis III originale: impostate quella della vostra missione.
- La risoluzione è `step_minutes`: un'ombra più breve del passo può sfuggire. Riducetelo per le decisioni critiche.
- La data di inizio dello scenario e `n_days` fissano l'intervallo di date di arrivo da analizzare.

Fonti consultate con ricerca web il 2 novembre 2026; non ho aperto le pagine per intero.

## 10. Problemi frequenti

| Sintomo | Causa probabile | Rimedio |
| --- | --- | --- |
| `orientation: iau2009` | mancano `.bpc` o `.tf` lunari | rieseguire `fetch_kernels.py` |
| FAIL: le quote sembrano il RAGGIO | offset del label sommato | `prepare_lola_dem.py` |
| FAIL: proiezione diversa | file in un'altra proiezione o con un altro centro | non usarlo; scegliere il prodotto polare standard |
| WARN: bordo del DEM vicino | sito vicino al bordo del tile | tile più grande o `horizonRangeKm` minore |
| Warning «No DEM covers» | file fuori da `data/dem` o sito fuori dal tile | controllare `/health` e la copertura |
| Memoria esaurita | tile intero da 1,8 GB | usare `--crop` |
| Sole sempre al 0% | data vicina alla luna nuova o sito in ombra permanente | provare date a +14 giorni (`/compare/shift`) |
| Siti Apollo senza DEM | il lettore gestisce solo DEM polari sud | estendere il lettore ai prodotti cilindrici |

## 11. Cosa scrivere sulle fonti (da copiare)

Data and models: Sun, Earth and Moon positions come from NASA/JPL NAIF SPICE (DE440 ephemeris, lunar orientation in the MOON\_ME\_DE440\_ME421 frame). Terrain comes from LRO LOLA gridded DEMs (PDS, PRODUCT NAME, RESOLUTION m/px, heights relative to the 1737.4 km reference sphere). Sun and Earth are treated as discs, with no atmosphere. The RF link is a simplified, unvalidated estimate with illustrative parameters.

Sostituite PRODUCT NAME e RESOLUTION con i valori del campo `provenance.dem`.

## 12. Limiti

- Il lettore supporta solo DEM in stereografica polare sud, con quote sulla sfera di 1737,4 km (non rispetto al geoide).
- Gli script non sono stati provati su file LOLA veri, perché la rete della sandbox non raggiunge i server NASA.
- L'orizzonte campiona il terreno alla risoluzione del DEM fino a `horizonRangeKm`; dove nessun DEM ha dati il terreno è trattato come sfera.

## 13. Fonti

- Prodotti LOLA polari sud: https://imbrium.mit.edu/BROWSE/LOLA\_GDR/POLAR/SOUTH\_POLE
- Conversione da DN a quota (FAQ PDS): https://pds-geosciences.wustl.edu/missions/lro/lola\_faq.htm
- Descrizione dei prodotti GDRDEM: https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions\_Instruments/LRO/LOLA/GDR/GDRDEM.htm
- A New View of the Lunar South Pole from LOLA (DEM dei siti): https://pgda.gsfc.nasa.gov/products/90
- Kernel lunari NAIF (PCK): https://naif.jpl.nasa.gov/pub/naif/generic\_kernels/pck/aareadme.txt
- Frame kernel lunare NAIF: https://naif.jpl.nasa.gov/pub/naif/generic\_kernels/fk/satellites/a\_old\_versions/moon\_de440\_220930.tf
