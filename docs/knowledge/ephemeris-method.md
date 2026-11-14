---
id: ephemeris-method
title: Come si calcolano posizione e illuminazione di Sole, Terra, Luna e Marte
kind: method
summary: >-
  Le posizioni dei corpi vengono da un'efemeride pubblica del JPL (DE440s, kernel NAIF) letta con
  Skyfield; l'orientamento di Luna e Marte da kernel NAIF e dal modello IAU. Il motore da' il punto
  subsolare, la librazione e azimut/elevazione di Sole e Terra da un sito, e coincide con JPL Horizons
  entro circa un milionesimo di grado per la Luna e qualche decimillesimo di grado per Marte e Terra.
tags: [efemeridi, ephemeris, DE440, NAIF, SPICE, Skyfield, JPL Horizons, punto subsolare, sub-solar, librazione, libration, UTC, Marte, Luna, Terra, azimut, elevazione, kernel]
applies_to: [viewer]
related: [az-el-convention, page-viewer]
level: tecnico
lang: it
last_verified: 2026-10-20
sources:
  - {ref: docs/ephemeris.md, supports: "convenzioni, modello, accuratezza misurata, limiti, kernel e riconoscimento NAIF"}
  - {ref: backend/ephemeris/engine.py, supports: "calcolo del punto subsolare, della librazione, di azimut/elevazione e del modello IAU di Marte"}
  - {ref: backend/ephemeris/kernels.lock.json, supports: "kernel NAIF usati con dimensione, SHA-256 e data di recupero"}
  - {ref: tests/backend/ephemeris/test_validation.py, supports: "confronto con JPL Horizons e con NOAA e tolleranze misurate"}
  - {ref: tests/backend/ephemeris/fixtures/horizons_subpoints.json, supports: "valori JPL Horizons di riferimento per Luna, Marte e Terra con metadati di recupero"}
  - {ref: https://naif.jpl.nasa.gov/naif/credit.html, supports: "NAIF incoraggia la citazione dei kernel e del lavoro di Acton (1996, 2017); nessun testo obbligatorio"}
  - {ref: https://ssd-api.jpl.nasa.gov/doc/horizons.html, supports: "API di JPL Horizons usata per i valori di riferimento"}
---
## Che cosa calcola

Dato un istante UTC (formato `AAAA-MM-GGThh:mm:ss Z`), il motore restituisce: il **punto subsolare** di Luna, Terra e Marte (latitudine e longitudine Est del punto in cui il Sole e' allo zenit), il **punto sub-Terra** della Luna (la librazione: quale punto della Luna e' al centro del disco visto dalla Terra), la distanza dal Sole, e azimut/elevazione di Sole e Terra da un sito sulla superficie. La direzione del Sole nel sistema di assi del visualizzatore 3D si usa direttamente come direzione della luce.

## Da dove vengono i numeri

- **Posizioni**: efemeride DE440 del JPL, nella versione breve `de440s.bsp` (1849-2150), da NAIF. E' una fonte pubblica verificabile; non sono formule approssimate.
- **Orientamento della Luna**: kernel NAIF dell'orientamento (assi principali, libration DE440) con la rotazione fissa verso il sistema Mean Earth / Polar Axis, lo stesso sistema delle coordinate dei siti.
- **Orientamento di Marte**: modello IAU 2015 (costanti nel file `pck00011.tpc`) implementato nel motore, perche' Skyfield non legge questo tipo di file.
- **Direzione del Sole**: apparente, cioe' con tempo di luce, aberrazione dovuta al moto del corpo (circa 0.006 gradi) e deflessione relativistica, come fa JPL Horizons.

## Quanto e' accurato (misurato, non stimato)

Confrontato con JPL Horizons il 2026-10-20 su 8 epoche tra 2026 e 2030: Luna entro 1e-6 gradi (punto subsolare e librazione) e azimut/elevazione da 3 siti entro 1e-6 gradi con distanze entro 7 m; Marte entro 5e-5 gradi in longitudine; Terra entro 1e-3 gradi in longitudine (differenza di circa 0.2 s nella rotazione terrestre predetta, non un errore di frame). Un algoritmo NOAA indipendente concorda con il motore per la Terra entro 0.003 gradi in latitudine e 0.012 gradi in longitudine. I valori esatti e le spiegazioni sono in [docs/ephemeris.md](docs/ephemeris.md).

## Cosa NON fa

- Nessun orizzonte topografico: l'elevazione e' rispetto al piano locale liscio. Ai poli lunari l'illuminazione reale dipende dal terreno.
- Nessuna rifrazione atmosferica (la Luna non ha atmosfera), nessuna dimensione finita di Sole e Terra.
- Intervallo supportato dal 1972-01-01 al 2150-01-20 UTC; l'accuratezza e' misurata solo per il 2026-2030. I secondi intercalari futuri non sono noti.
- La longitudine e' Est positiva e la latitudine dei punti subsolari e' planetocentrica; JPL Horizons stampa Marte con longitudine Ovest positiva e latitudine planetografica, convertite nei test.

## Riconoscimento

Kernel di NAIF (Navigation and Ancillary Information Facility, JPL/NASA), pubblico dominio; efemeridi DE440 di Park, Folkner, Williams e Boggs (2021); software Skyfield e jplephem (licenza MIT). Valori di riferimento: JPL Horizons.
