<!-- SPDX-License-Identifier: Apache-2.0 -->
# Efemeridi di Sole, Terra, Luna e Marte (Fase B)

Motore `backend/ephemeris/` (Python, extra opzionale `sky`) e rotte `/api/raven/sky/*`. Serve a (1) l'analisi dei siti lunari (azimut/elevazione di Sole e Terra da un punto della superficie, distanze) e (2) l'illuminazione reale del visualizzatore 3D (punto subsolare di ogni corpo a un istante UTC e punto sub-Terra della Luna, cioe' la librazione). Data di misura e di verifica: 2026-10-20.

### Cielo della scena lander

La scena di un sito restituisce `sky.icrf_to_scene`, una matrice 3×3 con righe negli assi della scena
(`x` verso l'azimut della Terra, `y` zenit, `z` a destra). Il motore ruota ICRF nel frame lunare
ME all'istante, poi nella base locale est-nord-zenit e infine negli assi della scena. La mappa
[NASA SVS Deep Star Maps 2020](https://svs.gsfc.nasa.gov/4851/) è in coordinate celesti ICRF,
centrata su ascensione retta 0h, crescente verso sinistra: il renderer converte queste convenzioni
in quelle della texture equirettangolare di Three.js senza riflettere il cielo.

È una visualizzazione di cataloghi, non una fotografia istantanea dal sito. Non corregge moti propri,
parallasse e aberrazione stellari; non rappresenta neppure occultazioni o illuminazione atmosferica.
La scena didattica e le risposte prive della matrice conservano un orientamento illustrativo dichiarato.

## Uso rapido

```bash
make venv && .venv/bin/pip install -e ".[sky]"   # skyfield 1.55 + jplephem 2.24 (Python 3.14.7 verificato)
make ephemeris                                    # scarica e verifica i 4 kernel NAIF in build/ephemeris (45 MB)
```

```python
from backend.ephemeris.engine import Engine

e = Engine()  # EphemerisUnavailable se i kernel mancano
e.subsolar_point("moon", "2026-12-24T00:00:00Z")  # LatLon(lat_deg, lon_deg_east)
e.sub_earth_point("moon", "2026-12-24T00:00:00Z")  # librazione
e.topocentric_azel("moon", -85.98, -1.67, "earth", "2027-08-09T00:00:00Z")  # az, el, range_km
e.solar_direction_body_fixed("mars", ["2027-01-01T00:00:00Z"])  # (N,3), assi del viewer
```

Tutte le funzioni accettano un istante o una sequenza (vettorizzate; risultato scalare == elemento del vettore, verificato).

## Convenzioni

| Tema | Scelta | Perche' |
|---|---|---|
| Tempo | Solo UTC: stringa `AAAA-MM-GGThh:mm:ss[.ffffff]Z` o `datetime` con offset 0. Niente fusi, niente stringhe senza `Z`. UTC -> TT/TDB con i secondi intercalari e il Delta-T di Skyfield | Nessuna ambiguita'; stesse regole in API e libreria |
| Posizioni | DE440s (Sole, Terra, Luna, **baricentro** di Marte). Il centro di Marte dista dal baricentro ~16 cm (Phobos+Deimos): trascurato | DE440s non contiene il corpo 499 |
| Direzione del Sole | **Apparente**: tempo di luce + aberrazione dalla velocita' del corpo (~20 arcsec = 0.0057 deg) + deflessione relativistica (`apparent()` di Skyfield) | E' il significato di "apparent" di JPL Horizons; senza di essa l'errore sarebbe 0.006 deg |
| Istante del corpo | Default: lo stato del corpo all'istante UTC dato ("ora del corpo"). Con `seen_from="earth"` il corpo e' quello **visto** da li' all'istante UTC (sottrae il tempo di luce) | Per Marte la differenza e' fino a ~6 gradi di rotazione (tempo di luce 4-24 min); per la Luna 1.3 s = 0.0002 deg |
| Longitudine | **Est positiva**, [-180, 180). Luna: ME/PA. Terra: ITRS. Marte: IAU_MARS dal modello IAU (si noti: JPL Horizons stampa Marte con longitudine OVEST positiva, convertita nei test) | Coincide con il viewer e con i dati dei siti |
| Latitudine dei sub-punti | **Planetocentrica** (angolo del versore dal piano equatoriale) = declinazione del Sole nel frame del corpo | Una sfera texturizzata usa direzioni, non ellissoidi. E' anche la latitudine **geodetica** del punto in cui il Sole e' allo zenit (verificato) |
| Latitudine dei siti (az-el) | **Geodetica** sull'ellissoide di riferimento: Luna sfera 1737.4 km (qui coincide col planetocentrico); Terra WGS84; Marte 3396.19 x 3376.20 km (`pck00011.tpc`) | Come JPL Horizons |
| Azimut | 0 = Nord locale (verso il polo nord del frame), orario; elevazione sul piano locale dell'ellissoide | Convenzione del sito `docs/knowledge/az-el-convention.md` |
| Rifrazione, terreno | Nessuna (la Luna non ha atmosfera; per la Terra non si applica rifrazione). Nessun orizzonte topografico | Vedi Limiti |

### Convenzione esatta del viewer (verificata sul codice)

`frontend/src/viewports/scene.ts` (`latLonToBody`) e lo shader di `threeViewport.ts` (`u = atan(m.x, m.z)/2pi + 0.5`, `v = 0.5 - asin(m.y)/pi`) definiscono lo spazio-oggetto della sfera:

- vettore di (lat, lon Est) = `(cos lat sin lon, sin lat, cos lat cos lon)`; **lon 0 / lat 0 = +z**, **lon 90 E = +x**, Nord = +y; terna **destrorsa**. Il centro della texture equirettangolare e' lon 0 (u = 0.5, v = 0.5 e' l'equatore), la longitudine cresce verso destra (Est), la latitudine verso l'alto.
- Rispetto agli assi solidali IAU (X su lon 0, Y su 90 E, Z polo Nord) il viewer usa `(x, y, z)_viewer = (Y, Z, X)_IAU`, una permutazione ciclica (nessuna riflessione).
- `solar_direction_body_fixed(body, t)` (default `frame="viewer"`) restituisce il versore **corpo -> Sole** gia' in questi assi: va usato direttamente come `lightObj` nello spazio-oggetto, **prima** della rotazione yaw/pitch della vista. `frame="iau"` restituisce gli assi IAU. Test: `test_viewer_axes_and_iau_axes`.
- Non verificato: l'allineamento reale delle texture. La Luna (NASA SVS 4720) dichiara il centro a lon 0; la texture di Marte (NASA 3D Resources) non lo dichiara (`docs/design/credits.md`: controllata a occhio con Hellas e Syrtis Major). Il punto subsolare e' corretto in coordinate; se la texture fosse traslata, lo sarebbe anche l'ombreggiatura.

## Modello e frame

| Corpo | Posizione | Orientamento (frame solidale) |
|---|---|---|
| Sole | DE440s, corpo 10 | non serve |
| Terra | DE440s, corpo 399 | `skyfield.framelib.itrs` (precessione/nutazione IAU 2000A, rotazione con UT1 **predetto** da Skyfield, nessun moto polare: effetto < 0.0001 deg (~0.3 arcsec)) |
| Luna | DE440s, corpo 301 | `MOON_ME_DE440_ME421` (alias `MOON_ME`): `moon_pa_de440_200625.bpc` (assi principali, libration DE440) + `moon_de440_250416.tf` (rotazione fissa PA -> ME). Il PCK ha 2 segmenti (1550-2426, 2426-2650): si usa il primo, che contiene tutto DE440s |
| Marte | DE440s, baricentro 4 | **Skyfield non supporta i PCK testuali** (`PlanetaryConstants.build_frame_named` richiede un segmento binario): il modello IAU e' implementato in `engine.iau_rotation` leggendo le costanti di `pck00011.tpc` (IAU 2015, Archinal et al. 2018): `alpha = a0 + a1 T + sum A_i sin(theta_i)`, `delta = ... + sum D_i cos(theta_i)`, `W = w0 + w1 d + sum W_i sin(theta_i)`, matrice `R3(W) R1(90-delta) R3(90+alpha)` |

## Accuratezza MISURATA contro JPL Horizons

Riferimenti: fixture di Fase A (3 siti x 4 epoche x Sole e Terra, API v1.2, DE441, Luna `MEAN_ME` alta precisione) e nuove fixture `tests/backend/ephemeris/fixtures/horizons_subpoints.json` (8 epoche 2026-11-15 .. 2030-05-27, orari non interi; testo grezzo in `horizons_raw/`, metadati di recupero nel file). Le tolleranze dei test (`TOL` in `test_validation.py`) sono 3-10x il valore misurato. Il motore usa DE440s, Horizons DE441: la differenza non e' stata isolata.

| Grandezza | Misurato (max) | Tolleranza nel test |
|---|---|---|
| Az-el Sole da 3 siti lunari (az x cos el / el / range) | 7e-8 deg / 8.2e-7 deg / 7.0 m | 1e-5 deg / 1e-5 deg / 50 m |
| Az-el Terra da 3 siti lunari | 4.7e-7 deg / 1.2e-6 deg / 0.16 m | 1e-5 deg / 1e-5 deg / 5 m |
| Luna: punto subsolare (visto dalla Terra), lon / lat | 1.0e-6 deg / < 1e-6 deg | 1e-5 deg |
| Luna: punto sub-Terra (librazione), lon / lat | 7.6e-7 deg / 3.3e-7 deg | 1e-5 deg |
| Marte: punto subsolare (visto dalla Terra), lon / lat | 4.6e-5 deg / < 1e-6 deg | 2e-4 / 2e-5 deg |
| Marte: sub-Terra, lon / lat | 4.6e-5 deg / 4.8e-7 deg | 2e-4 / 2e-5 deg |
| Marte: subsolare "ora del corpo" (osservatore Phobos, 0.03 s di luce) | 8.3e-5 deg | 3e-4 deg |
| Terra: punto subsolare (osservatore Luna), lon / lat geodetica | 9.3e-4 deg / 3e-6 deg | 2e-3 / 2e-5 deg |
| Terra vs NOAA (algoritmo indipendente, 100 istanti 2026-2030), lat / lon | 3.1e-3 deg / 1.2e-2 deg | 1e-2 / 3e-2 deg |
| Distanza Terra-Luna lungo il percorso della luce vs `delta` di Horizons | 1.5e-4 km | 1e-3 km |
| Distanza Sole-corpo (simultanea) vs `r` di Horizons | 7.2 km (5e-8 relativo) | 20 km |

Spiegazioni e discrepanze, dichiarate:

- **Terra, 9e-4 deg** (~0.1 km all'equatore): cresce con la data (5.7e-4 nel 2026-11, 8.4e-4 nel 2027-02, 9.3e-4 nel 2029-07) e corrisponde a ~0.14-0.22 s di UT1: Skyfield predice UT1-UTC con la sua tabella integrata, Horizons con il proprio file EOP (`eop.261019.p270114`: dati fino al 2026-10-19, predizioni fino al 2027-01-13, poi UTC costante). Non e' un errore del frame. Il confronto con NOAA conferma l'ordine di grandezza (NOAA e' meno preciso del motore). Non si usano file EOP scaricati a runtime.
- **Marte, 4.6e-5 deg** (~4 m all'equatore), costante sulle 8 epoche, **non spiegato**: ipotesi non verificate sono una piccola differenza tra il modello IAU di `pck00011.tpc` e quello interno di Horizons (`IAU_MARS`, di cui l'intestazione non dice la versione), o UT/TDB (0.2 s di rotazione di Marte = 5e-5 deg). Con osservatore Phobos lo scarto sale a **8.3e-5 deg**: la parte in piu' (~3.7e-5 deg) e' compatibile con 0.03 s di rotazione, il tempo di luce Marte-Phobos che il motore, in modo "ora del corpo", non applica. Per il viewer sono ~5 m su Marte: irrilevanti.
- **Distanze**: Horizons `delta` e' la lunghezza del percorso della luce (astrometrica). La distanza **simultanea** tra i centri (`distance_km` di default) differisce da essa di circa v_orbitale x tempo di luce (fino a ~40 km per Terra-Luna: 39 km misurati): sono due grandezze diverse, non un errore. `light_path=True` dà la prima.
- Le epoche dopo il 2027-01-13 usano UTC predetto da entrambe le parti; un futuro secondo intercalare (non noto) sposterebbe entrambi di 1 s: ~0.004 deg di rotazione terrestre, ~0.0001 deg per la Luna.

## Intervallo supportato

Derivato dai kernel (intersezione dei segmenti di DE440s e del primo segmento del PCK lunare, meno 1 giorno di margine per i tempi di luce), con inizio non prima del 1972-01-01 (era dei secondi intercalari interi; prima UTC non e' definito allo stesso modo): **1972-01-01T00:00:00Z .. 2150-01-20T23:58:50Z** (`GET /api/raven/sky/status`). Fuori: `OutOfRange` (libreria), 422 (API). La raccomandazione JPL per DE440 e' 1550-2650 (Park et al. 2021); DE440s e' la versione corta (1849-2150). L'accuratezza e' misurata solo nel 2026-2030: oltre, UT1 e Delta-T sono estrapolati (errore crescente fino a secondi, che pesa solo sulla rotazione terrestre).

## Limiti

- Nessun orizzonte topografico: l'elevazione e' rispetto al piano locale dell'ellissoide. Ai poli lunari l'illuminazione reale dipende da DEM (vedi `docs/domain/assumptions.md`).
- Nessuna rifrazione, nessuna dimensione finita di Sole/Terra, nessun limbo.
- L'aberrazione usa la velocita' del centro del corpo; la velocita' di rotazione della superficie e' trascurata (<= 1e-4 deg sulla Terra, ~1e-8 deg sulla Luna).
- Siti: quota 0 sull'ellissoide (parametro `h_m` disponibile in libreria).
- Marte e' il baricentro (16 cm dal centro). Phobos/Deimos non sono modellati.
- Skyfield 1.55 con NumPy 2.5 emette un `DeprecationWarning` (`matrix.shape`) in `planetarylib.py` alla costruzione del frame lunare: innocuo, da seguire negli aggiornamenti. Il motore usa l'attributo privato `_ephemeris` di un oggetto Skyfield (richiesto da `apparent()` per i siti di superficie): coperto da test, versione fissata a 1.55.

## Kernel NAIF (verificati 2026-10-20)

| File | Byte | Ruolo | Ultima modifica sul server |
|---|---|---|---|
| `spk/planets/de440s.bsp` | 32,726,016 | posizioni (DE440 corto, 1849-12-26 .. 2150-01-22 TDB) | 2020-12-21 |
| `pck/moon_pa_de440_200625.bpc` | 12,863,488 | orientamento della Luna (assi principali) | 2021-06-26 |
| `fk/satellites/moon_de440_250416.tf` | 19,478 | definizione dei frame `MOON_PA_DE440`, `MOON_ME_DE440_ME421` | 2025-04-16 |
| `pck/pck00011.tpc` | 131,226 | costanti IAU (Marte, raggi) | 2022-12-27 |

URL base `https://naif.jpl.nasa.gov/pub/naif/generic_kernels/`. SHA-256 e dimensioni sono fissati in `backend/ephemeris/kernels.lock.json` (fiducia al primo uso: NAIF non pubblica checksum per questi file; due download indipendenti il 2026-10-20 hanno dato lo stesso hash). Il gestore (`kernels.py`) scarica solo via HTTPS dall'host del lock, rifiuta i redirect verso altri host o http, usa timeout, tetto di byte uguale alla dimensione attesa, file temporaneo + `os.replace`, verifica l'hash prima di rendere visibile il file e non esegue mai il contenuto. Il motore ricontrolla dimensione e hash a ogni caricamento.

**Aggiornare i kernel**: scaricare i nuovi file in `build/ephemeris/`, `python -m backend.ephemeris.fetch --write-lock`, rivedere il diff del lock, rieseguire `pytest tests/backend/ephemeris` e **aggiornare la tabella di accuratezza sopra** prima di cambiare le tolleranze. `python -m backend.ephemeris.fetch --check` verifica senza scaricare. Cartella: `EPHEMERIS_DIR` (default `build/ephemeris`, non versionata).

### Riconoscimento (NAIF)

Dati: kernel SPICE di NAIF (Navigation and Ancillary Information Facility, JPL/NASA), in pubblico dominio; efemeridi planetarie DE440 (Park, Folkner, Williams, Boggs, *The Astronomical Journal* 161:105, 2021, doi:10.3847/1538-3881/abd414); orientamento di Marte dal rapporto IAU (Archinal et al., *Celestial Mechanics and Dynamical Astronomy* 130:22, 2018, doi:10.1007/s10569-017-9805-5). NAIF non impone un testo di riconoscimento ma incoraggia la citazione (https://naif.jpl.nasa.gov/naif/credit.html, letta il 2026-10-20): Acton, C.H., "Ancillary data services of NASA's Navigation and Ancillary Information Facility", *Planetary and Space Science* 44(1), 65-70, 1996, doi:10.1016/0032-0633(95)00107-7; Acton, Bachman, Semenov, Wright, "A look toward the future in the handling of space science mission geometry", *Planetary and Space Science* (2017), doi:10.1016/j.pss.2017.02.013. Riferimento di confronto: JPL Horizons (https://ssd.jpl.nasa.gov/horizons/). Software: Skyfield (MIT) e jplephem (MIT) di Brandon Rhodes.

## API

| Rotta | Risposta |
|---|---|
| `GET /api/raven/sky/status` | `available`, `supported_range{start_utc,end_utc}`, `engine{skyfield,jplephem}`, `kernels[]` (dal lock), `convention`, `limits`. Sempre 200, anche senza kernel (`available:false`) |
| `GET /api/raven/sky/subsolar?body=moon\|earth\|mars&t=<ISO UTC Z>` | `{body, t_utc, subsolar{lat_deg,lon_deg_east}, sun_distance_au, sun_direction_body_fixed[3], frame:"viewer", sub_earth{lat_deg,lon_deg_east}}` (`sub_earth` solo per la Luna). `t_utc` e' l'istante arrotondato per la cache (default 1 s) |
| `GET /api/raven/sky/series?body=&t0=&t1=&step_s=` | array paralleli `t_utc[]`, `lat_deg[]`, `lon_deg_east[]`, `sun_distance_au[]`, `sun_direction_body_fixed[][3]` (+ `sub_earth_*` per la Luna) |

Errori: 422 con messaggio generico (mai l'input), 503 senza kernel/extra (`Retry-After: 30`) o oltre il tetto di concorrenza (`Retry-After: 1`), 500 generico. Il calcolo gira in un thread (`asyncio.to_thread`). Le rotte ereditano limite di richieste, tetto del corpo e intestazioni di sicurezza dell'app. Il motore si carica alla prima richiesta (hash di 45 MB + riscaldamento: ~0.1 s misurati con i file in cache di sistema); dopo un caricamento fallito non si riprova prima di 30 s.

Variabili d'ambiente (validate con `backend/envconf`, elencate in `.env.example`):

| Variabile | Default | Significato |
|---|---|---|
| `EPHEMERIS_DIR` | `build/ephemeris` | cartella dei kernel |
| `SKY_MAX_CONCURRENT` | 4 | calcoli concorrenti (oltre: 503) |
| `SKY_MAX_POINTS` | 2000 | punti massimi di una serie |
| `SKY_MIN_STEP_S` | 60 | passo minimo di una serie (s) |
| `SKY_MAX_SPAN_DAYS` | 366 | durata massima di una serie |
| `SKY_CACHE_SIZE` | 512 | voci della cache LRU `(corpo, secondo arrotondato)` |
| `SKY_CACHE_ROUND_S` | 1 | arrotondamento dell'istante per la cache (s) |

## Docker e CI

- `Dockerfile`: stage `ephemeris` (solo libreria standard) scarica i kernel con gli hash fissati e **fa fallire il build** se differiscono; il runtime li copia in `/app/build/ephemeris` (posizione predefinita di `EPHEMERIS_DIR`) e installa `.[fusion,sky]`. Verificato il 2026-10-20: `docker build`, poi `GET /api/raven/sky/subsolar?body=moon&t=2026-12-24T00:00:00Z` risponde 200 nel container (lat -1.19260, lon 0.22505 "ora della Luna").
- CI: installa l'extra `sky`, cache `actions/cache` su `build/ephemeris` con chiave `hashFiles('backend/ephemeris/kernels.lock.json')` e poi `python -m backend.ephemeris.fetch` (verifica hash anche dei file in cache). Non eseguito su GitHub in questa sessione (nessun push).

## Test

`pytest tests/backend/ephemeris`: gestore dei kernel (rete finta), UTC, validazione contro Horizons e NOAA, invarianti (latitudine subsolare entro l'obliquita' 1.54 / 23.44 / 25.19 deg, longitudine subsolare della Luna -12.19 deg/giorno su un mese sinodico, distanza Terra-Luna 356-407 mila km, distanza Sole-Terra/Marte, librazione entro +-7 / +-8 deg, vettorizzato == scalare, Sole allo zenit nel punto subsolare, assi del viewer) e rotte (motore finto + kernel reali). Senza l'extra o senza i kernel i test di validazione si saltano.
