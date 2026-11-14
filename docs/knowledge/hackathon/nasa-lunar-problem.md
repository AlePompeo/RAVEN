---
id: nasa-lunar-problem
title: Confronto di siti e date lunari per un asset di superficie (NASA Space Apps)
kind: problem
summary: >-
  La sfida NASA Space Apps sulla Luna chiede di confrontare siti e date per un asset di superficie, in base a quando Sole e Terra sono visibili, all'energia solare disponibile, al margine del collegamento radio diretto verso la Terra e alle "ore di missione" utili. La soluzione in preparazione calcola Sole e Terra visti dal sito (validati con JPL Horizons), l'energia e il margine di collegamento, ma i risultati sono ancora da calcolare.
tags: [problema, soluzione, hackathon, metodologia, Luna, siti, link budget, energia, Horizons]
applies_to: [home, chat]
related: [link-budget, fspl, az-el-convention]
level: intermedio
lang: it
last_verified: 2026-10-20
sources:
  - {ref: docs/domain/phase-a-report.md, supports: "cosa e' stato verificato e cosa no nella Fase A, discrepanze e domande aperte"}
  - {ref: docs/domain/sites.md, supports: "elenco dei siti candidati con coordinate, sistema di riferimento e fonte"}
  - {ref: backend/domain/data/sites.json, supports: "registro dei siti in formato dati (id, lat, lon Est, tipo, fonte, verified)"}
  - {ref: docs/domain/assumptions.md, supports: "parametri di collegamento radio, energia e profilo di carico con intervallo, default e stato (V verificato, D derivato, I illustrativo)"}
  - {ref: tests/backend/domain/fixtures/horizons_reference.json, supports: "azimut/elevazione/distanza di Sole e Terra da JPL Horizons per 3 siti e 4 epoche, con parametri di richiesta"}
  - {ref: "https://ntrs.nasa.gov/citations/20250011660", supports: "NASA elenca nove regioni candidate Artemis III per nome, senza coordinate; illuminazione e visibilita' della Terra tra i criteri"}
  - {ref: "https://ssd-api.jpl.nasa.gov/doc/horizons.html", supports: "documentazione dell'API JPL Horizons usata per i dati di riferimento"}
---
## Problema

La sfida NASA Space Apps in tema lunare chiede di **confrontare siti e date** per un asset sulla superficie lunare. Per ogni coppia sito/data servono: quando Sole e Terra sono visibili dal sito, quanta energia solare e' disponibile, il margine del collegamento radio diretto verso la Terra (Direct-to-Earth, DTE) e le "ore di missione" utili che ne risultano. Il testo ufficiale del bando non e' stato recuperato in questa fase: l'enunciato qui sopra e' la descrizione ricevuta dal team (da confrontare con il bando).

## Vincoli

- Le assunzioni del team non sono ancora scelte: siti, date e parametri di collegamento/energia sono proposte in `docs/domain/`.
- Ogni numero ha una fonte e una data di accesso (2026-10-20) oppure e' etichettato "illustrativo, non verificato".
- La NASA pubblica le regioni Artemis III solo per nome: per i siti polari si usa il centro della feature IAU (USGS Gazetteer), che non coincide con il centro della regione.
- Nessuna quota/topografia: le posizioni sono su una sfera di 1737.4 km.

## Ipotesi

- Sistema di riferimento Mean Earth / Polar Axis, latitudine planetocentrica, longitudine Est positiva.
- Il collegamento DTE usa una stazione DSN da 34 m in banda X (8.4 GHz) o S (2.2 GHz); i valori di guadagno e temperatura di sistema sono quelli del manuale DSN 810-005, mentre potenza e antenna del lander sono illustrative.
- Il codice di canale e il suo Eb/N0 richiesto non sono verificati (si parte dal caso BPSK non codificato).
- Profilo di carico e degrado dei pannelli illustrativi.

## Metodologia

1. Per ogni sito ed epoca, calcolare azimut/elevazione e distanza di Sole e Terra visti dal sito (vedi [convenzione az/el](kb:az-el-convention)); la propria implementazione si valida contro le fixture JPL Horizons (CENTER `coord@301`, nessuna rifrazione).
2. Energia: flusso solare = costante solare x (1 UA / distanza)^2 x seno dell'elevazione, per efficienza e fattori di sistema; ai poli serve una maschera d'orizzonte da topografia, non una sfera liscia.
3. Collegamento: [link budget](kb:link-budget) con perdita nello spazio libero ([FSPL](kb:fspl)), guadagni e G/T del DSN, margine >= 3 dB.
4. Ore di missione utili: ore in cui Sole, energia, Terra e margine soddisfano le condizioni di `docs/domain/assumptions.md` (definizione proposta, da concordare).

## Perche' questa soluzione

Usa solo dati e formule tracciabili (Horizons, manuale DSN, NASA SoA) e separa in modo esplicito il verificato dall'illustrativo, cosi' il confronto tra siti non dipende da numeri non controllati.

## Alternative considerate

Da compilare dal team. In Fase A non e' stata valutata nessuna alternativa di modello (per esempio effemeridi a bassa precisione contro Horizons, o modelli di orizzonte da DEM).

## Risultati

da calcolare

## Limiti

- Coordinate dei siti polari: centro della feature, non della regione Artemis III.
- Nessuna topografia: l'elevazione e' geometrica sulla sfera.
- Guadagno antenna lander, potenza di trasmissione, profilo di carico, degrado, rendimento: illustrativi.
- Eb/N0 richiesto con codifica CCSDS non verificato (PDF non scaricabile).
- Banda X per lander lunare: la fonte NASA del lander usa 8450-8500 MHz, il DSN indica 8400-8450 MHz per deep-space: da chiarire.
