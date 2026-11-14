<!-- SPDX-License-Identifier: Apache-2.0 -->
# Rapporto Fase A: ingressi verificati

Data: 2026-10-20. Branch `hackathon/nasa-lunar`. Nessun valore e' stato preso dalla memoria: ogni cifra ha fonte e data in `sites.md`, `assumptions.md` o nella fixture.

## Verificato

- **Apollo 11 e 17**: coordinate NSSDCA (Wagner et al. 2017) = quelle del viewer (`frontend/src/viewports/bodies/registry.ts`). Nessuna discrepanza.
- **Siti polari**: centri delle feature IAU dal Gazetteer USGS (Malapert/Mons Malapert, Haworth, Mons Mouton, Nobile, de Gerlache, Shackleton). Controllo incrociato: LROC indica "86S, 0E" per Malapert (feature: -85.98, -1.67); LROC IM-2 -84.78, 29.13E dentro una regione Artemis III (Mons Mouton feature: -84.60, 31.00).
- **Fixture Horizons** (`tests/backend/domain/fixtures/horizons_reference.json` + `horizons_raw/`): 3 siti x 4 epoche x (Sole, Terra), az/el apparenti senza rifrazione ("Atmos refraction: NO (AIRLESS)"), distanza e velocita' radiale, distanza centro Luna-centro Terra. Efemeridi DE441, frame Luna MEAN_ME (high precision), API v1.2. Epoche 2026-12-24 (quasi piena), 2027-04-07 (quasi nuova), 2027-08-09 (circa quarto, massima librazione in latitudine +6.83 e longitudine +7.63 deg della scansione giornaliera 2026-12..2028-12), 2028-01-19 (circa quarto, librazione vicina al massimo). Esempio di controllo di coerenza: da Malapert la Terra e' a -3.1 deg (sotto l'orizzonte) il 2027-08-09, mentre da Apollo 11 e' a 73 deg.
- **DSN 34 m**: guadagno (X 68.21-68.29 dBi a 8425 MHz; S 56.74 dBi a 2295 MHz) e temperature di sistema da 810-005 Module 104 Rev. Q (2026-08-03); limite meccanico di elevazione ~6 deg da Module 301 Rev. P.
- **Energia**: 1360.8 +/- 0.5 W/m2 (Kopp & Lean 2011, SORCE/TIM); efficienza celle 28-32% e Li-ion 182-264 Wh/kg (NASA SoA Power 2022); mese sinodico 29.53 d (NASA Moon Fact Sheet).
- **Margine del lander**: >= 3 dB, TWTA 61 W RF / 110 W DC, 4 kbps in superficie (NASA/TP-2019-220391).

## Non verificato o illustrativo

- Centri delle **regioni** Artemis III: la NASA pubblica solo i nomi (comunicato RELEASE24-136; abstract LPSC; SVS 5013). Il dataset USGS con le griglie (DOI 10.5066/P13FD9ZD) e' dietro Cloudflare (403), non recuperato. Le regioni del 2022 erano ~15 x 15 km (da risultato di ricerca, non riverificato sul testo originale).
- Peak near Cabeus B, Mons Mouton Plateau, Slater Plain: nessuna coordinata di regione verificata, quindi esclusi.
- Valore TSIS-1 diretto della costante solare (si usa SORCE/TIM).
- Eb/N0 richiesto per i codici CCSDS (turbo/LDPC): CCSDS 130.1-G-3 non scaricabile (404). Solo il caso ideale BPSK (9.59 dB a 1e-5, calcolato) e' disponibile.
- Guadagno antenna del lander, potenza di trasmissione di default (20 W), perdite di implementazione, fattori di sistema dei pannelli, degrado, pacco batteria (120 Wh/kg), DoD, profilo di carico.
- Tolleranze consigliate per confrontare il codice proprio con la fixture (0.1 deg e' un punto di partenza illustrativo).
- Il testo originale del bando Space Apps non e' stato aperto: la descrizione della sfida e' quella data dal team.

## Discrepanze e avvertenze

1. Nessuna discrepanza viewer/fonte per Apollo 11 e 17. Il viewer non contiene siti polari.
2. Banda X lander: TP2019 usa 8450-8500 MHz in discesa; Module 101 indica 8400-8450 MHz come allocazione deep-space. Probabile differenza di categoria (vicino-Terra contro deep-space) ma non verificata.
3. L'intestazione di Horizons riporta "Solar constant 1367.6 W/m2" (valore storico): non usarla come fonte; il valore adottato e' 1360.8.
4. Il Gazetteer riporta "Planetographic, +East"; si assume ME/PA, coincidente con la sfera usata da Horizons (header: raggio 1737.4 km, alt ~0).
5. Il valore 1737.4 km come raggio di riferimento significa che le quote reali (es. Apollo 11 a -1926 m nella lista LROC) sono ignorate.
6. Gli epoch 2027-2028 usano UTC predetto (EOP "PREDICTS" fino al 2027-01-13 e oltre) e leap second costante: incertezza non quantificata.
7. Azimut mal condizionato oltre ~89 deg di elevazione e vicino ai poli: confrontare vettori.
8. Il conteggio 9 regioni (2024) vs 13 (2022): "Peak near Shackleton" e' solo nel 2022; incluso come caso estremo vicino al polo.

## Domande aperte per l'ingegnere RF / energia

- Quale banda e quale categoria di assegnazione si usano per il lander (8400-8450 o 8450-8500 MHz; S-band)?
- Antenna del lander: gimbal con MGA/HGA o fissa? Guadagno e puntamento sull'elevazione della Terra (da Malapert la Terra e' a pochi gradi dall'orizzonte).
- Potenza RF disponibile e budget DC; codice di canale (CCSDS LDPC/turbo/conv.) e Eb/N0 richiesto da cartella tecnica.
- Margine di progetto (3 dB come TP2019) e perdite meteo/elevazione della stazione (maschera 6 o 10 deg).
- Quale stazione/complesso DSN e quanto tempo di tracking e' ammesso; considerare piu' stazioni per coprire la rotazione della Terra?
- Efficienza, fattori di sistema, degrado nel tempo e polvere per i pannelli; energia specifica del pacco, DoD, riserva minima, riscaldamento in notte lunare.
- Profilo di carico reale e definizione di "ora di missione utile".
- Come trattare l'illuminazione ai poli: DEM LOLA e profili di orizzonte (Mazarico et al. 2011) o prodotti LRO esistenti?
- Siti: confermare con il team quali regioni usare e se servono i centri di regione ufficiali (da LROC/USGS) al posto dei centri feature.
