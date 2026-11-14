<!-- SPDX-License-Identifier: Apache-2.0 -->
# NASA Space Apps: confronto di siti lunari (branch `hackathon/nasa-lunar`)

Caso specifico costruito sulla base generica. Regola di flusso: il core (`backend/core`) NON si modifica in questo branch; si aggiungono solo `backend/domain/` e `backend/plugins/` specifici. I miglioramenti generici vanno nel branch base e poi si fa merge qui. Controllo: `python scripts/check_core_unchanged.py <riferimento-base>`.

## Obiettivo (da dimostrare in 30 secondi ai giudici)

Aiutare a **confrontare siti lunari e date** per una stazione/missione: quando il Sole e la Terra sono visibili dal sito, quanta energia si ha, che margine di collegamento radio con la Terra, quante "ore di missione" utili si ottengono. Output: classifica dei siti e delle date, con ipotesi dichiarate.

## Divisione dei compiti (dal blueprint)

- **Elettronica/TLC**: link budget RF, bilancio energetico, calcolo delle ore di missione, firmware ESP32/servo/alimentazione, validazione della plausibilità dei numeri e delle ipotesi.
- **Informatica/robotica/AI**: effemeridi e orizzonte, backend e topic, scena 3D e UX, controllore di puntamento, eventuale ottimizzatore "miglior sito/data".
- **Insieme**: contratto dati (formato e unità), pitch di 3 minuti (problema, demo dal vivo, risultato).

## Contratto dati (bozza da chiudere nelle prime 2 ore)

Base già pronta in `contracts/telemetry.schema.json` (versione 1.0.0): `schema_version`, `t_utc` (UTC), `site_id`, `power_w`, `link_margin_db`, `sun{az_deg, el_deg}`, `earth{az_deg, el_deg}`; `additionalProperties: false`. Per il dominio servono probabilmente altri campi (potenza generata/consumata, stato batteria, distanza Terra-sito, visibilità, ore di missione cumulate). **Decisione aperta**: o si estende lo schema con una nuova `schema_version` (e si rigenerano i tipi con `contracts/gen.py`), o si definisce un secondo schema di dominio. Ogni unità sta nel nome del campo.

## Piano 48 ore

1. Giorno 1 mattina: scelta di 3-4 siti e chiusura del contratto dati.
2. Giorno 1 pomeriggio-sera: in parallelo effemeridi + 3D e modelli energia/RF + firmware; integrazione minima a fine giorno con dati finti (il replay CSV e la pagina Telemetria già esistono).
3. Giorno 2 mattina: integrazione completa, ore di missione, confronto tra siti, collegamento con la demo hardware.
4. Giorno 2 pomeriggio: congelare le funzioni, rifinire la UI, provare la demo, registrare un video di backup, preparare il pitch.

## Cosa la base offre già e cosa va scritto

| Esigenza | Già nella base | Da scrivere nel dominio |
|---|---|---|
| Link budget | plugin `fspl-c` (perdita di spazio libero, formula verificata su 384400 km a 2,2 GHz = 210,994 dB) | guadagni d'antenna, potenza TX, rumore, margine: ipotesi dichiarate |
| Energia | -- | bilancio solare/batteria per sito e data |
| Effemeridi e orizzonte | -- | posizione di Sole e Terra visti dal sito (libreria da scegliere e di cui verificare la licenza) |
| 3D e telemetria | pagine Viewer e Telemetria, `ViewportPort` | scena lunare, sito, direzioni Sole/Terra |
| Puntamento | stimatore IMU, controllore servo in C su host | legge di puntamento verso la Terra |
| Confronto e ottimizzazione | pipeline dati, registro modelli | classifica siti/date; eventuale ottimizzatore con soglia e approvazione umana |

Per i calcoli di dominio le competenze di riferimento sono quelle di link budget, sistemi di potenza e meccanica orbitale; ogni formula va scritta con le sue ipotesi e verificata da chi ha le competenze RF/energia.

## Rischi (dal blueprint)

- Hardware che non parte: video di backup, demo opzionale.
- Modelli RF troppo complessi: formule semplici con ipotesi dichiarate.
- Troppa ambizione: congelare le funzioni a metà del secondo giorno.
- Perdere il focus: in 30 secondi i giudici devono capire come si confrontano siti e date.

## Dati e termini d'uso

Nessun dato ufficiale è stato incluso né verificato. **Da aggiungere dopo il 28 ottobre**: i dettagli dei dataset ufficiali della sfida (fonte, licenza, `terms_url`, formato, limiti di richiesta). Ogni sorgente dichiara licenza e attribuzione nel manifest del plugin.

## Cose NON verificate

Tutte le grandezze fisiche di dominio sono ancora da scrivere e validare. Nessuna ipotesi su siti, orbite, antenne o consumi è stata assunta in questo branch.
