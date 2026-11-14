<!-- SPDX-License-Identifier: Apache-2.0 -->
# Registro dei siti lunari candidati (Fase A)

Dati in `backend/domain/data/sites.json`. Accesso a tutte le fonti: 2026-10-20.

**Riferimento**: Luna, sistema Mean Earth / Polar Axis (ME/PA), latitudine planetocentrica (sfera R = 1737.4 km, come in JPL Horizons), longitudine Est positiva. Altitudine non specificata (0 sulla sfera).

**Cosa NASA pubblica**: NASA elenca le regioni candidate Artemis III solo per nome, senza coordinate (comunicato RELEASE24-136, 2024-10-28, https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ ; abstract LPSC https://ntrs.nasa.gov/citations/20250011660 ; SVS https://svs.gsfc.nasa.gov/5013). Le regioni del 2022 erano di circa 15 x 15 km (da un risultato di ricerca sul comunicato 2022, non riverificato sul testo originale). I dati USGS con le griglie dei siti (DOI 10.5066/P13FD9ZD) non erano scaricabili (Cloudflare 403). Quindi per i siti polari si usa il **centro della feature IAU** (Gazetteer USGS), NON il centro della regione: la regione puo' distare decine di km. Le coordinate sono `verified: true` nel senso "copiate da fonte primaria", con `coordinate_basis: feature_centre`.

| id | lat (deg) | lon E (deg) | tipo | base | fonte |
|---|---|---|---|---|---|
| apollo11 | 0.67416 | 23.47314 | riferimento equatoriale | punto (Wagner 2017) | NSSDCA |
| apollo17 | 20.1911 | 30.7723 | riferimento valle Taurus-Littrow | punto (Wagner 2017) | NSSDCA |
| malapert-massif | -85.98 | -1.67 | massiccio polare | centro feature | Gazetteer 16338; LROC "86S, 0E" |
| haworth | -87.45 | -5.17 | cratere polare | centro feature | Gazetteer 14502 |
| mons-mouton | -84.60 | 31.00 | massiccio polare | centro feature | Gazetteer 16070; IM-2 -84.78, 29.13 |
| nobile-rim | -85.28 | 53.27 | bordo cratere | centro feature | Gazetteer 4321 |
| de-gerlache | -88.48 | -88.34 | bordo cratere | centro feature | Gazetteer 1439 |
| shackleton | -89.67 | 129.78 | cratere vicino al polo | centro feature | Gazetteer 5450 (lista 2022) |

Non inclusi: Peak near Cabeus B, Mons Mouton Plateau, Slater Plain (nessuna coordinata di regione verificata; non si assume che "Slater Plain" coincida col cratere Slater).

## Confronto con il viewer

`frontend/src/viewports/bodies/registry.ts` usa Apollo 11 (0.67416, 23.47314) e Apollo 17 (20.1911, 30.7723): **identici** a NSSDCA/Wagner 2017. Nessuna discrepanza. Il viewer non ha siti polari.

## Avvertenze

- Il campo "Coordinate System" del Gazetteer dice "Planetographic, +East, -180 - 180"; si assume ME/PA (convenzione IAU), non dichiarato esplicitamente nella riga.
- Apollo: le quote reali (es. Apollo 11 a -1926 m nella lista LROC) non sono usate; la posizione e' sulla sfera di riferimento.
- Per i siti polari l'illuminazione dipende dalla topografia locale (orizzonte): un'effemeride Sole/Terra da sfera liscia da' solo l'elevazione geometrica.
