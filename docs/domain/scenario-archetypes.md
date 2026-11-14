# Archetipi di classe di missione per il cursore di scenari (ricerca fonti)

Ricerca del 9 nov 2026 per la richiesta "cursore di scenari predefiniti" (`docs/process/BACKLOG.md`, sezione del 10 nov).
Tutti i valori sono letti in fonti pubbliche secondarie (per lo più Wikipedia, che a sua volta cita NASA e aziende) e NON sono
stati confrontati con i documenti NASA primari: "non verificato sul primario". Tag **D** = derivato da una fonte letta;
**I** = illustrativo (motivo dichiarato). Dove non c'è fonte adeguata: "nessuna fonte pubblica adeguata: resta ignoto".
Scenario illustrativo di classe, non una stima della TUA missione né un preventivo.

## 0. Fonti usate (tutte lette il 9 nov 2026)
- [W1] Wikipedia, "Commercial Lunar Payload Services", https://en.wikipedia.org/wiki/Commercial_Lunar_Payload_Services (valori di assegnazione e date; letti i primi 100000 caratteri).
- [W2] Wikipedia, "Intuitive Machines Nova-C", https://en.wikipedia.org/wiki/Intuitive_Machines_Nova-C
- [W3] Wikipedia, "Peregrine Mission One", https://en.wikipedia.org/wiki/Peregrine_Mission_One
- [W4] Wikipedia, "Blue Ghost Mission 1", https://en.wikipedia.org/wiki/Blue_Ghost_Mission_1
- [W5] Wikipedia, "Griffin Mission One", https://en.wikipedia.org/wiki/Griffin_Mission_One
- [W6] Wikipedia, "Blue Moon (spacecraft)", https://en.wikipedia.org/wiki/Blue_Moon_(spacecraft)
- [W7] Wikipedia, "VIPER (rover)", https://en.wikipedia.org/wiki/VIPER_(rover)
- [W8] Wikipedia, "Falcon 9" (statistiche al 7 nov 2026), "New Glenn", "Vulcan Centaur".
- [N1] newspaceeconomy.ca, "Moon landing attempts 2023 to 2025", 14 lug 2025, https://newspaceeconomy.ca/2025/07/14/moon-landing-attempts-2023-to-2025/
- [S1] Aerospace Corp., "Development of the Small Satellite Cost Model 2019 (SSCM19)", paper 2019/2020, https://aerospace.org/sites/default/files/2020-05/SSCM19%20paper.pdf (storia, classi di massa, validità; **nessuna formula CER pubblicata nel testo letto**).
- [L1] Dominguez Calabuig et al., Acta Astronautica 221 (2024) 1-11, DOI 10.1016/j.actaastro.2024.05.009, Table 5.
- [L2] Kukreja, Oughton, Linares, arXiv:2504.15291 (8 apr 2025), preprint non peer-reviewed.

## 1. Classe 1 - rover / payload piccolo
| Grandezza | Valore | Fonte | Tag | Limiti |
|---|---|---|---|---|
| Costo di un rover (esempio VIPER, 430 kg a secco, NON piccolo) | stima ott 2019 250 M USD; ciclo di vita NASA 3 mar 2021 433,5 M USD; speso alla cancellazione ~450 M USD | [W7] | D | un solo rover, più grande della classe |
| Massa rover (VIPER) | 430 kg a secco | [W7] | D | idem |
| Costo di consegna sulla Luna (CLPS) | vedi classe 2 | [W1] | D | |
| Costo/massa/durata di un payload o rover piccolo (< 100 kg) | nessuna fonte pubblica adeguata: resta ignoto | - | - | CADRE: pagina Wikipedia non raggiunta (404), non letta |
| Lancio | come passeggero di un lander (classe 2) | [W2][W4] | D | |

VIPER: lancio e atterraggio pianificati 2027, 100 giorni terrestri [W7]; la data di inizio progetto non è stata letta.

## 2. Classe 2 - lander commerciale piccolo CLPS (default)
| Grandezza | Valore | Fonte | Tag | Limiti |
|---|---|---|---|---|
| Valore contratto Peregrine (Astrobotic) | 79,5 M USD (31 mag 2019); 108 M USD riportati a gen 2024 | [W1] | D | valore di aggiudicazione NASA, non costo totale del fornitore |
| IM-1 (Intuitive Machines) | 77 M USD (31 mag 2019), poi 118 M USD (gen 2024) | [W1][W2] | D | idem |
| IM-2 | ~47 M USD (16 ott 2020) | [W1] | D | idem |
| Blue Ghost 1 (Firefly) | 93,3 M USD (4 feb 2021) | [W1][W4] | D | idem |
| IM-3 / Blue Ghost 2 | 77,5 M USD (17 nov 2021) / 112 M USD (14 mar 2023), voli pianificati inizio 2027 | [W1] | D | non ancora volati |
| Massa Nova-C | secca 675 kg; al lancio 1900 kg; payload 100 kg (infobox) o >130 kg (testo) | [W2] | D | fonte discordante al suo interno |
| Massa Blue Ghost 1 | secca 469 kg; al lancio 1517 kg; payload ~94 kg | [W4] | D | |
| Massa Peregrine | al lancio 1283 kg; secca non indicata; payload max 90 kg | [W3] | D | |
| Classe di lancio | Falcon 9 Block 5 (Nova-C, Blue Ghost); Vulcan VC2S (Peregrine) | [W2][W3][W4] | D | |
| Energia | Nova-C: 200 W massimi in superficie, batteria 25 Ah a 28 V (=0,7 kWh, mio calcolo); Blue Ghost: pannelli 400 W | [W2][W4] | D | **molto sotto al default Planner (1 m2 / 10 kWh)** |
| Radio | Peregrine: banda X; Blue Ghost: banda S e X | [W3][W4] | D | guadagno antenna e bit rate non letti |
| Durata sviluppo (assegnazione -> lancio) | Peregrine 4 a 7 m (mag 2019 -> 8 gen 2024); IM-1 4 a 8,5 m (-> 15 feb 2024); Blue Ghost 1 3 a 11 m (4 feb 2021 -> 15 gen 2025); IM-2 4 a 4 m (16 ott 2020 -> 27 feb 2025) | [W1][W4] | D (differenze di date, mio calcolo) | 4 casi |
| Durata sviluppo Griffin | assegnato 11 giu 2020, lancio pianificato non prima di gen 2027 (>6 anni) | [W1][W5] | D | non ancora volato |
| Costo per voce / fase (struttura, propulsione, avionica, operazioni) | nessuna fonte pubblica adeguata: resta ignoto | - | - | i contratti CLPS sono prezzi a corpo |

Contratti annullati (rischio di programma) [W1]: Masten 75,9 M USD (apr 2020), annullato per fallimento; OrbitBeyond 97 M USD ritirato 29 lug 2019; Draper/ispace CLPS-12 73 M USD (21 lug 2022), annullato a luglio 2026.

## 3. Classe 3 - lander medio
| Grandezza | Valore | Fonte | Tag | Limiti |
|---|---|---|---|---|
| Griffin Mission One: massa lander | 1265 kg (secca o umida non indicato); payload >445 kg incl. rover FLIP da 500 kg | [W5] | D | |
| Lancio Griffin | Falcon Heavy | [W5] | D | |
| Valore contratto Griffin | 199,5 M USD (11 giu 2020) | [W1] | D | valore di aggiudicazione |
| Blue Moon Mark 1 | massa al lancio 21 350 kg (umida); payload a superficie 3000 kg; secca non indicata; lanciatore non specificato | [W6] | D | di fatto sopra la classe: estremo superiore |
| Costo Mark 1 | valore del task order CLPS non indicato | [W1] | - | resta ignoto |

Altre voci (costo per voce, CO2e): nessuna fonte pubblica adeguata: resta ignoto.

## 4. Classe 4 - lander grande / classe equipaggio
| Grandezza | Valore | Fonte | Tag | Limiti |
|---|---|---|---|---|
| Blue Moon Mark 2 | secca 16 000 kg; al lancio >45 000 kg; payload 20 000 kg (riutilizzabile) o 30 000 kg (sola andata) | [W6] | D | non ha mai volato |
| Lanciatore | New Glenn, carenatura da 7 m | [W6] | D | |
| Contratto HLS Blue Origin | circa 3,4 mld USD (maggio 2023) | [W6]; ricerca web (Futurism, SpacePolicyOnline: risultati non aperti) | D | un'altra fonte parla di 7 mld: non risolto |
| Contratto HLS SpaceX (Starship) | 2,89 mld USD | ricerca web, sintesi di Wikipedia "Human Landing System" (pagina non aperta) | D, debole | da verificare sul comunicato NASA |
| Date | Artemis V: 2030 nel testo, 2028 nella lista della stessa pagina | [W6] | D | incoerenza della fonte |
| Massa di Starship HLS, durata di sviluppo, costo per voce | nessuna fonte pubblica adeguata: resta ignoto | - | - | |

## 5. Modelli di costo parametrici
- SSCM (Aerospace Corp., non NASA; NASA finanziò la prima fase nel 1995) [S1]: satelliti sotto i 1000 kg; da SSCM05 due insiemi di CER, micro (<=100 kg) e piccoli (>100 e <=1000 kg); base dollari FY19; fuori dall'intervallo di validità l'errore cresce. **Le formule non sono nel paper letto**; il manuale SSCM14 è a distribuzione ristretta (ricerca web). Calibrato su satelliti in orbita terrestre e vicino-Terra, non su lander lunari. Uso in RAVEN: nessuno finché non si ottengono formule pubbliche.
- USCM (Aerospace/Tecolote) e modelli NASA per strumenti/missioni: non cercati né letti in questa sessione: "non verificato", resta ignoto.

## 6. Statistiche di atterraggio e di lancio
| Grandezza | Valore | Fonte | Tag | Limiti |
|---|---|---|---|---|
| Tentativi di allunaggio 2023-2025 | 8 tentativi. Successo pieno 3: Chandrayaan-3 (23 ago 2023), SLIM (19 gen 2024, capovolto), Blue Ghost 1 (2 mar 2025). Parziale 2: IM-1 (22 feb 2024), IM-2 (6 mar 2025), entrambi capovolti. Fallimento 3: Hakuto-R M1 (25 apr 2023), Luna-25 (19 ago 2023), Hakuto-R M2 (5 giu 2025). Peregrine (lancio 8 gen 2024) non tentò l'atterraggio | [N1] (conteggio derivato dalla tabella) | D | il sito non riporta i totali; la classificazione è della fonte |
| Altri | Chang'e 4 (3 gen 2019) e Chang'e 6 (1 giu 2024): successi CNSA | Wikipedia "List of missions to the Moon" (solo introduzione) | D | elenco incompleto |
| Beresheet 2019 | fallimento (data non verificata) | ricerca web | D, debole | |
| Vikram (Chandrayaan-2) 2019; eventi dopo giu 2025 | non verificati | - | - | resta ignoto |
| Lander commerciali USA volati (IM-1, Blue Ghost 1, IM-2) | 1 pieno, 2 parziali (Peregrine: 0 tentativi) | [W1][N1] | D | campione di 3-4: probabilità non stimabile con significato statistico |
| Falcon 9 | 698 successi su 701 lanci (99,6%) al 7 nov 2026; Block 5 644 su 645 (99,8%); 2 fallimenti totali (CRS-7; Starlink 9-3, lug 2024); 1 parziale (CRS-1, ott 2012) | [W8] | D | |
| New Glenn | 3 lanci: 2 successi, 1 fallimento (NG-3, 19 apr 2026, stadio superiore) | [W8] | D | n=3 |
| Vulcan Centaur | 4 lanci, 4 successi nominali, 2 anomalie dei booster solidi (4 ott 2024, 12 feb 2026) | [W8] | D | n=4 |
| Probabilità di trasferimento translunare | nessuna fonte pubblica adeguata: resta ignoto | - | - | |

## 7. CO2e
- Lancio: [L1] Tabella 5 dà impatti per lancio (GWP100 da 4,71 a 29,60 "CO2,eq."; unità non estratta dal testo letto) ma per lanciatori **riutilizzabili europei ipotetici di fascia L/XXL**, non per Falcon 9, New Glenn o Vulcan. [L2] è un preprint e non riporta CO2e per lancio né per kg (solo quote percentuali: produzione e combustione 72,6% del ciclo di vita). **Per il lancio dei veicoli di queste classi: nessuna fonte pubblica adeguata: resta ignoto.**
- Costruzione (carbonio incorporato) di lander/rover: nessuna fonte pubblica adeguata: resta ignoto.
- Fattore di emissione per kg di payload: nessuna fonte adeguata letta: resta ignoto.

## 8. Quantità senza fonte pubblica adeguata (restano ignote)
Costo per voce/fase di ogni classe; costo e massa di rover/payload piccoli; formule SSCM/USCM; CO2e di lancio e di costruzione; probabilità di trasferimento e di sopravvivenza alla notte lunare; affidabilità dei singoli componenti (solo puntatori: MIL-HDBK-217F, DoD, 1995; database di parti NASA/ESA: non aperti, nessun numero letto); massa di Starship HLS; potenza, batteria e guadagno d'antenna di Peregrine e Blue Ghost.

## 9. Mappatura alle 4 posizioni del cursore (PROPOSTE, tag I)
Tutti i valori sono proposte da validare: non sono dati misurati. Motivo del tag I: la posizione è una scelta di progetto; i numeri citati sono solo riferimenti di ordine di grandezza.

| Pos. | Archetipo | Massa (proposta) | Lancio | Durata sviluppo | Energia/radio | Riferimenti D |
|---|---|---|---|---|---|---|
| 1 | rover/payload piccolo | 50-150 kg (I: nessuna fonte) | passeggero di un lander | ignota | default Planner: 1 m2, 10 kWh, 15 dBi, 100 kbit/s | VIPER come estremo alto (430 kg, 433,5 M USD) |
| 2 (default) | lander CLPS piccolo | secca 470-680 kg, al lancio 1300-1900 kg | Falcon 9 / Vulcan | 3,9-4,7 anni | default Planner; **i lander reali hanno 200-400 W e 0,7 kWh: il default non li rappresenta** | [W1][W2][W3][W4] |
| 3 | lander medio | ~1300 kg (Griffin) fino a 21 350 kg (Mark 1) | Falcon Heavy / New Glenn | >6,5 anni (Griffin, in corso) | proposta I: scalare dal default | [W5][W6] |
| 4 | lander grande/equipaggio | secca 16 000 kg | New Glenn / classe Starship | ignota | proposta I | [W6] |

Modificatore ottimistico/tipico/prudente: se applicato, usare solo gli estremi osservati (durata 3,9-4,7 anni; Falcon 9 99,6% contro New Glenn 2/3), non coefficienti inventati.

## 10. Cautele
- Fonti secondarie (Wikipedia) non allineate ai documenti NASA primari; i valori CLPS sono assegnazioni con modifiche, non il costo reale del fornitore.
- Calibrazione: SSCM è su satelliti, non su lander; pochi voli per la classe 2.
- Intervalli ampi; date di lettura: 7 nov 2026 per Falcon 9; atterraggi dopo giu 2025 non verificati.
- Mai sovrascrivere i dati dell'utente; esclusa dai totali finché non accettata; etichetta "scenario illustrativo di classe, non una stima della TUA missione né un preventivo".
