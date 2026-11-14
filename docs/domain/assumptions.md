<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tabella delle ipotesi (Fase A)

Accesso a tutte le fonti: 2026-10-20. Legenda colonna "Stato": **V** = valore letto in una fonte primaria recuperata; **D** = derivato con calcolo ripetibile da valori V (formula indicata); **I** = illustrativo, NON verificato (scelta di progetto da validare). Nessun valore I va presentato come dato.

Abbreviazioni fonti: **DSN104Q** = DSN 810-005 Module 104 Rev. Q, "34-m BWG Stations Telecommunications Interfaces", 2026-08-03, https://deepspace.jpl.nasa.gov/dsndocs/810-005/104/104Q.pdf. **DSN101I** = 810-005 Module 101 Rev. I, https://deepspace.jpl.nasa.gov/dsndocs/810-005/101/101I.pdf. **DSN301P** = 810-005 Module 301 Rev. P (2026-05-22), https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf. **TP2019** = NASA/TP-2019-220391 "NASA Lunar Lander Reference Design", https://www.lpi.usra.edu/lunar/strategies/NASA-TP-2019-220391.pdf. **SOA22** = NASA Small Spacecraft Technology State-of-the-Art, cap. 3 Power (2022), https://www.nasa.gov/wp-content/uploads/2023/05/3.-soa-power-2022.pdf. **MOONFACT** = https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html (agg. 11 gen 2024). **EARTHFACT** = https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html (agg. 15 nov 2024).

## (a) Collegamento radio diretto verso la Terra (DTE)

| Parametro | Intervallo | Default consigliato | Stato | Fonte / nota |
|---|---|---|---|---|
| Banda S, ricezione DSN | LNA 2200-2300 MHz; guadagno riferito a 2295 MHz | 2295 MHz | V | DSN101I Tab. 2 (2200-2300 MHz; nota: la modifica "2270-2300 -> 2200-2300" e' nel registro revisioni); DSN104Q Tab. 5 |
| Banda X, ricezione DSN | LNA 8200-8600 MHz; assegnazione telemetria deep-space 8400-8450 MHz | 8425 MHz | V | DSN101I Tab. 2 (nota "Deep space downlink telemetry allocation is 8400 to 8450 MHz"); DSN104Q Tab. 7 (8425 MHz) |
| Banda X per lander lunare | TP2019 usa 8450-8500 MHz in discesa e 7190-7235 MHz in salita | 8.4 GHz (X) come portante di riferimento; S ~2.2 GHz come alternativa | V (documento) / dubbio | TP2019 sez. 11 (downlink 8450-8500 MHz). Differisce dalla banda 8400-8450 del DSN deep-space: domanda aperta per l'ingegnere RF (categoria vicino-Terra vs deep-space nell'allocazione ITU/SFCG; non verificata qui) |
| Guadagno antenna DSN 34 m BWG, X | 68.21-68.29 dBi a 8425 MHz (a seconda della modalita'), +0.1/-0.2 dB | 68.2 dBi | V | DSN104Q Tab. 7, picco in elevazione, senza atmosfera |
| Guadagno antenna DSN 34 m BWG, S | 56.74 dBi a 2295 MHz | 56.7 dBi | V | DSN104Q Tab. 5, stessa nota |
| Temperatura di sistema Top, X | 19.74-42.1 K (cielo sereno CD=25%, zenit, secondo stazione/configurazione); 26.2 K per DSS-24 X-only non diplexed | 26.2 K | V | DSN104Q Tab. 9 |
| Temperatura di sistema Top, S | 22.3-43.88 K (stesse condizioni) ; 27.79 K per DSS-34 non diplexed | 27.8 K | V | DSN104Q Tab. 9 |
| G/T DSN | X: ~54.1 dB/K; S: ~42.3 dB/K | usare i due valori | D | G/T = G(dBi) - 10 log10(Top). X: 68.29 - 10 log10(26.2). S: 56.74 - 10 log10(27.79) (guadagno Tab. 5 con Top di DSS-34: accoppiamento approssimato). Valori in cielo sereno allo zenit; elevazione bassa e pioggia peggiorano |
| Maschera di elevazione stazione | 6 deg limite meccanico ricezione; 10 deg / 13.5 deg trasmissione bassa/alta potenza | 6 deg (ricezione); 10 deg se si vuole margine meteo | V (6, 10, 13.5) / I (10 come scelta prudente) | DSN301P sez. 2.2.2 (limite meccanico ~6 deg) e 2.2.3 ("generic elevation limits ... 6.0 degrees for receive, 10.0 ... low-power transmit, 13.5 ... high-power transmit") |
| Potenza RF di trasmissione lander | esempio documentato: TWTA 61 W RF out, 110 W DC in (102 W + 8 W EPC); lander piccoli: 5-20 W | 20 W RF | 61 W: V (esempio); 5-20 W e default: I | TP2019 sez. 11.6.7. Il default 20 W e' illustrativo |
| Guadagno antenna lander | TP2019 usa 2 antenne emisferiche + antenna a medio guadagno su gimbal a terra; il guadagno in dBi NON e' riportato nel testo estratto | emisferica 0-5 dBi; MGA 15-25 dBi; HGA >30 dBi | I | Nessun valore verificato. Sostituire con scheda tecnica reale |
| Velocita' dati | superficie 4 kbps (TBR), transito/discesa 20 kbps (TBR) | 4 kbps | V (TBR) | TP2019 sez. 11 |
| Margine di collegamento richiesto | >= 3 dB in tutte le fasi | 3 dB | V | TP2019 sez. 11 |
| Modulazione / Eb/N0 richiesto, ideale | BPSK/QPSK coerente: 9.59 dB per BER 1e-5; 10.53 dB per BER 1e-6; limite di Shannon -1.59 dB | 9.6 dB + perdite di implementazione | D | BER = 0.5 erfc(sqrt(Eb/N0)), formula da testo (Proakis, Digital Communications); calcolo in Python con bisezione, controllabile |
| Perdite di implementazione | 1-3 dB | 2 dB | I | Non verificato |
| Codifica canale CCSDS (LDPC, turbo, conv+RS) | guadagno di codifica rispetto a BPSK non codificato: NON verificato | decisione al progetto: partire dal caso non codificato (conservativo) | I | Riferimenti da leggere: CCSDS 131.0-B (TM Synchronization and Channel Coding, Blue Book) e CCSDS 130.1-G-3 (Green Book, giugno 2020, riferimento da MathWorks). Il PDF non e' scaricabile da public.ccsds.org (404): Eb/N0 richiesto per codice NON recuperato |
| Perdita in spazio libero (FSPL) | S: 210.5-211.5 dB; X: 222.1-223.1 dB per 363 300-405 500 km | calcolare con la distanza di Horizons | D | FSPL = 20 log10(4 pi d f / c); distanze perigeo/apogeo da MOONFACT (0.3633e6 e 0.4055e6 km, centro-centro). Intervallo sito-Terra osservato nelle fixture Horizons: 355 200-387 349 km |

## (b) Energia

| Parametro | Intervallo | Default | Stato | Fonte / nota |
|---|---|---|---|---|
| Irradianza solare totale a 1 UA | 1360.8 +/- 0.5 W/m2 (minimo solare 2008) | 1360.8 W/m2 | V | Kopp & Lean 2011, GRL 38 L01706 (SORCE/TIM, NASA/LASP), https://espo.nasa.gov/node/30086. Non recuperato un valore TSIS-1 diretto (https://lasp.colorado.edu/tsis/ solo come missione successore). Il valore 1367.6 nell'intestazione di Horizons NON e' una fonte primaria TSI |
| Distanza Terra-Sole (Luna alla stessa distanza) | perielio 147.095e6 km, afelio 152.100e6 km, semiasse 149.598e6 km | usare la distanza Horizons (campo delta del Sole) | V | EARTHFACT; fixture Horizons: 147.17e6-151.67e6 km sui 4 epoch |
| Variazione di flusso per distanza | x1.034 (perielio) .. x0.967 (afelio) -> 1407.5 .. 1316.4 W/m2 | flusso = 1360.8 (149.598e6 / r)^2 | D | Legge dell'inverso del quadrato; calcolo ripetibile |
| Efficienza celle multi-giunzione (BOL) | 28.0-32.0 % in tabella; "over 32%" miglior stato dell'arte | 29.5 % | V | SOA22 Tab. 3-1 (es. SolAero ZTJ 29.5, IMMa 32.0, Azur 3G28C 28) e sez. 3.2.1 |
| Fattori di sistema array (packing, temperatura, angolo, cablaggio) | non verificati | 0.80 complessivo | I | Da ricavare da scheda del pannello; SOA22 elenca solo le cause di degrado |
| Degrado pannelli (radiazione, polvere, vetro) | cause citate, tassi NON quantificati | 1-3 % per anno equivalente | I | SOA22 sez. 3.2.1 cita radiazione, scurimento del coverglass, contaminazione, guasti. Il tasso e' illustrativo; la polvere lunare non e' trattata |
| Energia specifica celle Li-ion | 182-264 Wh/kg (18650/21700; es. Panasonic NCR18650B 243, LG MJ1 260, Samsung 50E 262); "latest cells exceeded 240 Wh/kg" | 200 Wh/kg a livello cella | V | SOA22 Tab. 3-4 e sez. 3.4 |
| Energia specifica del pacco batteria | non verificata (include struttura, BMS, termica) | 120 Wh/kg | I | Rapporto cella->pacco non citato |
| Profondita' di scarica ammessa | non verificata | 80 % | I | |
| Rendimento carica/scarica | non verificato | 0.90 round-trip | I | |
| Mese sinodico (giorno lunare per sito equatoriale) | 29.53 giorni | 29.53 d | V | MOONFACT |
| Durata notte lunare, siti equatoriali | circa meta' del ciclo sinodico | ~14.77 d | D | 29.53 / 2, approssimazione: dipende da latitudine e librazione |
| Obliquita' dell'asse lunare rispetto all'orbita | 6.68 deg | 6.68 deg | V | MOONFACT |
| Illuminazione ai poli | dipende dalla topografia locale (orizzonti); varia di 2-3 settimane/anno | calcolo con modello di orizzonte da DEM LOLA, non con sfera liscia | V (affermazione) | NASA LPSC "Artemis III Site Selection Update", https://ntrs.nasa.gov/citations/20250011660 ("south polar illumination ... shifting approximately 2-3 weeks per year"). Metodo: Mazarico et al. 2011, Icarus, https://ntrs.nasa.gov/citations/20120010094 (profili di orizzonte da DEM LOLA 240 m); dati: https://pgda.gsfc.nasa.gov/products/69 |
| Altitudine / DEM dei siti | non incluso | 0 sulla sfera 1737.4 km | I | Limite della Fase A |

## (c) Profilo di carico (ILLUSTRATIVO, non verificato)

Tutti i valori sono ipotesi da sostituire con i dati del cliente. L'unica cifra documentata e' la potenza del TWTA (110 W DC per 61 W RF, TP2019).

| Modo | Potenza (W) | Condizione di ingresso | Stato |
|---|---|---|---|
| Sopravvivenza / notte lunare | 10 (inclusi riscaldatori) | Sole sotto maschera | I |
| Standby attivo | 25 | Sole sopra maschera, batteria sopra riserva | I |
| Scienza / operativita' | 50 | idem | I |
| Comunicazione DTE | 110 (TWTA documentato) + 20 base | Terra sopra maschera e margine >= 3 dB | 110 W: V (TP2019); resto I |

Proposta di definizione di "ora di missione utile" (da concordare, I): ora in cui Sole sopra la maschera locale di illuminazione, energia disponibile (generazione piu' batteria sopra la riserva) e, per le ore di comunicazione, Terra sopra la maschera della stazione con margine di collegamento >= 3 dB.

## (d) Efemeridi (Fase B, aggiunta 2026-10-20)

Il motore `backend/ephemeris` (docs/ephemeris.md) riproduce le fixture Horizons di Fase A (Sole e Terra da 3 siti, 4 epoche) con errore massimo 8.2e-7 deg in elevazione, 7e-8 deg in azimut (x cos el) e 7 m in distanza (Sole); 1.2e-6 deg e 0.16 m (Terra). La tolleranza "0.1 deg" suggerita in Fase A era solo un punto di partenza: i test usano le tolleranze misurate (1e-5 deg). Il riferimento resta sfera liscia di raggio 1737.4 km senza orizzonte topografico; azimut/elevazione sono apparenti (tempo di luce, aberrazione, deflessione) senza rifrazione. Per i siti polari l'elevazione geometrica non basta (vedi la riga "Illuminazione ai poli").
