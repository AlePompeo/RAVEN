<!-- SPDX-License-Identifier: Apache-2.0 -->
# Gap analysis 2026-11-04: dai documenti di ricerca e pianificazione al codice (RAVEN, ex GrazingLink)

Analisi di sola lettura del branch `hackathon/nasa-lunar` (HEAD `8ed6be7`, worktree `spec-design`). Per ogni requisito o
funzione promessa nei documenti della cartella `research papers, scripts and planning/` si indica lo stato nel
repository, l'evidenza e cosa manca. Regola: se lo stato non si può verificare dal repository si scrive
**non verificato**. Nessun test è stato eseguito per questa analisi: gli stati "Fatto" si basano sulla presenza di
codice, test e documenti di validazione, non su un'esecuzione odierna.

Legenda. **Stato**: Fatto / Parziale / Non fatto / Da decidere (non fattibile senza una decisione o un dato esterno).
**Sforzo**: S (≤ 1 giorno), M (2-5 giorni), L (> 1 settimana). **Dipende da**: U = decisione dell'utente, X = dati o
testi esterni (dataset della sfida, NASA, fonti), V = validazione che oggi non esiste, — = nessuna dipendenza.

## Documenti letti e cosa non è stato estratto

| Sigla | File | Note di lettura |
|---|---|---|
| DT | `GRAZINGLINK-descrizione-tecnica.md` ("GrazingLink v3") | letto per intero |
| BP | `Business_Plan_Revenue_Plan.md` (ottobre 2026) | letto per intero |
| TUT | `Tutorial dati NASA reali in GrazingLink.md` (backend v0.1) | letto per intero |
| BOZ | `BozzaDescrizioneProgettoNASA.md` | letto; i marcatori `[cite: n]` rimandano a fonti non incluse |
| DA | `DESCRIZIONE AGGIORNATA PROGETTO.pdf` (34 pagine) | testo estratto con `pdftotext -layout`; **non estratte** 7 immagini (pp. 7, 8, 12, 14, 17, 21, 23): formula della potenza solare (p. 13-14, solo le variabili sono nel testo), formula dell'energia (p. 14), schema dell'architettura software (p. 15-17), schema hardware ESP32 (p. 21-23), grafica della timeline (p. 11) |
| MP | `MissionPlanning + Didattica_IdeaFiga.pdf` (20 pagine) | testo estratto; **non estratte** 13 immagini (pp. 3-5, 7-8, 17-18): illustrazioni delle lezioni, slider, schema della modalità Education e **l'esempio di quiz finale (§6, p. 17-18), che è solo immagine** |
| RO | `RiorganizzazioneSitoIdeeElaborate_v6.pdf` (25 pagine) | testo estratto; **non estratte** 12 immagini (pp. 1, 3, 4, 6, 7, 12, 13, 14, 18, 20, 21, 23): diagramma della struttura (p. 1), mockup degli step, struttura di Signal Propagation, diagramma "Explore why", schermata di confronto, esempio di Explainable Results, percorso Education |
| NOMI | `ListaProvvisoriaNomi.txt` | letto |
| ZIP | `grazinglink_backend.zip` | elencati i 32 file; letti solo `README.md` e `requirements.txt` estratti in una cartella temporanea fuori dal repository; nessun codice eseguito |
| OLD | `antenna_directivity.py`, `compensation_demo.py`, `onda_3d_bozza.py`, `Bibliografia_GrazingLink.xlsx`, `42-226D.pdf`, `ManualeEquazioniRiferimentoNASA.pdf` | già esaminati nella fase 1 (`docs/domain/grazinglink-model.md`, righe 7-9 e §7 Bibliografia); qui non riletti |

Stato del repository usato come evidenza: `docs/domain/{grazinglink-model,method,validation}.md`,
`docs/design/grazinglink-ux.md`, `docs/process/*`, `README.md`, `frontend/src/pages/*/index.ts`,
`frontend/src/shell/router.ts`, `backend/api/*routes*.py`, `backend/domain/**`, `git log -80`, l'inventario dei test
(126 file `test_*.py` in `tests/`, 67 `*.test.ts` in `frontend/src`, 42 spec in `e2e/tests`) e `gh run list`.

---

## 1. Tracciabilità requisito per requisito

### 1.1 Modello scientifico

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R1 | Geometria Sole/Terra da effemeridi SPICE, frame lunare coerente (DT §3-4.1; DA p. 4 Mod. 1; BOZ §3A; MP Step 2 p. 12) | Fatto | `backend/ephemeris/engine.py` (frame `MOON_ME_DE440_ME421`), `/api/sky/*`, `docs/domain/validation.md` "Validato": scarto contro JPL Horizons 8,2e-7° (Sole), 1,2e-6° (Terra); fixture `tests/backend/domain/fixtures/horizons_reference.json` | UT1 predetto dopo 2027-01, incertezza non quantificata (validation.md "NON validato") | S | — |
| R2 | Orizzonte reale da DEM LOLA con curvatura e altezza del mast, 360 azimut (DT §4.1; DA p. 5 Mod. 2; MP Step 3 p. 13) | Fatto | `backend/domain/grazing/horizon.py` (maschera per sito, 1440 azimut, LDEM_85S_20M fino a 10 km + LDEM_75S_240M fino a 200 km), `/api/lunar/horizon`, `tests/backend/domain/grazing/test_horizon.py`; arbitro indipendente `scripts/solar_horizon_arbiter.py`; validation.md §"Endpoint con maschera d'orizzonte" | DEM a 5 m (Barker, PGDA 78/104) non integrati; terreno oltre 200 km non modellato; solo stereografica polare sud | M | X |
| R3 | Profilo del terreno verso la Terra, ostacolo dominante (DT §4; BOZ §3A, §7) | Parziale | `grazing/terrain.py`, `grazing/analysis.py`; profilo CSV dell'utente in `pages/grazinglink/grazing.ts` (`parseProfileCsv`) | Diffrazione multipla su più creste: non implementata (limite dichiarato, model.md §4 "Si approssima" 1) | L | V |
| R4 | Diffrazione a bordo a lama esatta e approssimazione ITU-R P.526 (DT §4.2; DA p. 5 Mod. 3) | Fatto | `grazing/diffraction.py`; test `test_exact_knife_edge_equals_p526_eq26_by_quadrature`, `test_itu_approx_is_p526_eq27`; P.526-9 letta sul testo (validation.md §"Fonte ITU-R P.526-9") | Versione P.526 in vigore (-15 o successiva) non letta. Lo scarto dell'approssimazione ITU misurato nel repo è ≤ 0,123 dB, non ≤ 0,11 dB come in DT §4.2 | S | X |
| R5 | Correzione per cresta arrotondata, multi-fidelity (DT §5.3; BOZ §2.4, §3B) | Parziale | Politica implementata: T(m,n) di P.526-9 §4.2 predefinita, tabella split-step come confronto, incertezza = max(tabella, \|ITU − split-step\|) (`grazing/compensation.py`, `simula/linkModel.ts`); studio `scripts/study_splitstep_convergence.py` | Nessuna misura; soluzione esatta del cilindro (Mie/Fock) non calcolata; tabella non convergente in dx (circa 0,5 dB a ν = 3, R = 400 m); ITU e split-step non concordano entro 0,5 dB (validation.md §"Aperti") | L | V |
| R6 | Tabelle di compensazione con processo gaussiano, celle mancanti, anomalie MAD, avviso fuori dominio (DT §5.2-5.3, §8 DoD) | Parziale | GP usato **offline** in `scripts/gen_compensation_table.py` (extra `[ml]`); a runtime interpolazione bilineare con incertezza, flag > 4 MAD e `clamped` (`grazing/compensation.py`, `data/compensation_table.json`), `/api/grazing/compensation`, `TabCompensator`/`ValidityMap.svelte` | GP non a runtime (scelta di progetto, non un difetto); la tabella corregge la differenza fra due modelli, non la realtà (DT §5.3 lo dichiara) | S | V |
| R7 | Multipath a due raggi sul regolite, ε = 3,7 − j0,01, rugosità di Gorham (DT §4.3; DA p. 5 Mod. 4; BOZ §3C) | Fatto (con correzioni) | `grazing/multipath.py`, `test_multipath.py`; model.md §0 n. 5-8: errore dello script originale sul fattore di rugosità (fattore 2 nell'esponente) corretto | Solo polarizzazione orizzontale (JPL226 usa RCP); nessuna parte non coerente, nessuna curvatura; nessuna misura | M | V |
| R8 | Antenna: guadagno, HPBW, perdita di puntamento, preset omni/media/alta, gimbal (DT §4.4, §6; DA p. 6 Mod. 5; BOZ §3E) | Fatto | `grazing/antenna.py`, `grazing/gimbal.py`, `/api/grazing/antenna`, `TabAntenna.svelte`, `test_antenna.py` (costante 12,04 verificata) | HPBW ≈ 70 λ/D non verificato sulla fonte (model.md §0 n. 10); dati Apollo/VIPER/Chang'e-3 da fonti secondarie (DT §6) non confermati | S | X |
| R9 | Link budget: Friis, rumore, Eb/N0, margine 3 dB, stazioni 34/18 m (DT §4.5; DA p. 6 Mod. 6; MP Lezione 5 p. 8-9) | Fatto (parametri illustrativi) | `grazing/analysis.py`, `lunar/link.py`, plugin `fspl_c`; test `test_nasa_lunar_return_rate_scaling_with_ground_gt`, `..._with_lunar_dish`, `test_nasa_cadet_forward_power_budget` | Nessun margine assoluto pubblicato riprodotto (validation.md §"Margine lunare assoluto"); parametri radio con tag I; guadagno di codifica CCSDS, G/T in funzione dell'elevazione non modellati | M | X, V |
| R10 | Compensatore del bit rate con margine k·σ, obiettivo di interruzioni (DT §5.4; BOZ §3D: 10 kbps-3 Mbps) | Fatto | `grazing/bitrate.py`, `/api/grazing/compensator`, `test_bitrate.py`; insieme dei bit rate `shell/scenario.ts` `BITRATES` = 1e4…3e6 | σ supposto noto e gaussiano; estensione "banditi con ACK/NACK" (DT §5.4) non fatta (fuori nucleo) | M | V |
| R11 | Preset Artemis 36 kbps e 60 Mbps (DT §4.6) | Non fatto | nessuna occorrenza di 36 kbps / 60 Mbps in `backend/domain` e `frontend/src/pages`; `BITRATES` arriva a 3 Mbps | aggiungere preset con fonte citata (il requisito NASA non è nel repo) | S | X |
| R12 | Relay what-if 1-3 satelliti, Set Cover ILP (DT §2, §4.7; DA p. 10 Mod. 12; RO p. 10 "Advanced Extensions") | Non fatto | nessun codice "relay"/"LunaNet" in `backend/` e `frontend/src` | tutto; DA e RO lo classificano P3/estensione | L | U |
| R13 | Grafici d'onda 3D, pannello "onda" (DT §2, §7, §9.4) | Fatto | `grazing/wave.py`, `/api/grazing/wave`, `pages/wave/*`, alias `/wave` → `/simula?tab=onda`; e2e `wave.spec.ts`, `wave-no-webgl.spec.ts` | — | — | — |
| R14 | Scena 3D: tubo di Fresnel, cresta, cono d'antenna, frange di multipath al suolo che cambiano col mast (DT §9; BP §2.4; BOZ §6) | Parziale | `pages/simula/SimulaScene.svelte`, `UnifiedScene.svelte`, `pages/lander/*` | frange di multipath disegnate al suolo e "Scena 2" con causa per punto: **non verificato** | M | — |
| R15 | Illuminazione solare con ombre del terreno come funzione centrale (DA p. 7-8 Mod. 8, p. 13 Livello 1; MP Lezione 3) | Parziale | `/api/lunar/solar-terrain` con maschera a 200 km (validation.md: concorda con l'arbitro entro 1 passo su 4380; contro LROC WAC r = 0,95, RMS 4-6 punti) | La timeline base del Planner (`/api/lunar/timeline`) usa ancora l'orizzonte **piatto** (method.md §"Timeline per il Mission Planner"); il terreno entra solo nella missione accoppiata | M | — |
| R16 | Potenza solare su pannello (DA p. 13 Livello 2) e bilancio energetico con batteria (DA p. 14 Livello 3) | Fatto (non validato) | `lunar/energy.py`, `lunar/terrain_energy.py`, `lunar/coupled.py` (`/api/lunar/mission`), `pages/planner/panel.ts` | nessun confronto con un caso reale; parametri di pannello, batteria e carico illustrativi (validation.md "NON validato") | M | V, X |
| R17 | Controlli di coerenza dichiarati in DT: Malapert quota massima Terra 10,7°, tramonto ≈ 8 giorni; relay 77 %/100 %; Miller non riprodotto (DT §4, §11) | Non verificato | nessuna occorrenza di questi numeri in `docs/domain/*` | rieseguire con il motore attuale e documentare | S | — |

### 1.2 Validazione dichiarata

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R18 | Tre verifiche per la giuria: geometrica, topografica, temporale (DA p. 30-31) | Parziale | geometrica: Horizons (R1); topografica: arbitro + LROC WAC + orientamento DEM confermato (validation.md); temporale: nessun raffinamento dei bordi delle finestre (`pages/planner/windows.ts` campiona, nessuna bisezione) | verifica temporale a risoluzione più fine e caso RF "con parametri noti e risultati riproducibili" pubblicato come slide | M | — |
| R19 | Validazione con riferimenti NASA del tutorial: Horizons, Quickmap/Moon Trek, mappe di illuminazione, pytest (TUT §8) | Parziale | Horizons e mappe di illuminazione (AVGVISIB, LROC WAC) fatti; pytest presente | confronto quote/rilievi con Quickmap o Moon Trek: non fatto (manuale) | S | X |
| R20 | "Dichiarare sempre: validazione su dati di volo in sospeso" (DT §10; BP nota di affidabilità; BOZ §7) | Fatto | testi `planner.rfDisclaimer`, README "Limiti dichiarati", `/pricing` disclaimer | — | — | — |
| R21 | Validazione scientifica come costo strategico: specialisti RF, simulazioni indipendenti (BP §8.5) | Non fatto | nessuna revisione esterna documentata | revisione di un esperto RF e confronto con un simulatore indipendente | L | U, V |

### 1.3 Mission Planner, percorso didattico e quiz

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R22 | Mission Planner a 6 passi: Setup, Landing Site, Timeline, Solar, Communication, Results (RO p. 2-5, p. 16) | Parziale | `/mission-planner` (`pages/planner/Planner.svelte`, 1592 righe): setup Guided/Advanced (`setup.ts`), passi Site/Time/Sun/Earth/Radio/Comparison; e2e `mission-planner.spec.ts` | nomi e ordine dei passi diversi da RO (manca lo step "Mission Results" separato; tipo di missione lander/rover non verificato) | S | U |
| R23 | Timeline multi-dominio sincronizzata con cursore e scena 3D: luce, Terra, RF, margine, bit rate (DA p. 8-9 Mod. 9, p. 11; MP Step 7-9; RO p. 19) | Fatto | `MissionTimeline.svelte`, `timeline.ts`, `rfDsnOverlap.ts`, missione accoppiata lazy (commit `6167655`) | motivo di chiusura per finestra e raffinamento dei bordi (MP Step 8) non fatti | M | — |
| R24 | Confronto A/B fra siti e fra date (DA p. 7 Mod. 7, p. 12; MP Step 10; BP P0) | Fatto | modalità `sites`/`dates` nel Planner, `/api/lunar/analyze`, `/api/grazing/compare`, Siti `?tab=classifica`; e2e `compare.spec.ts` | — | — | — |
| R25 | Report esportabile PDF/CSV (BP §2.2 P1; DA p. 9 Mod. 10; MP Step 11) | Parziale | Planner: `window.print()` e JSON (`missione-raven.json`); Analizza: CSV/JSON (`ExportBar.svelte`) | nessun PDF generato con struttura a 10 sezioni di MP Step 11; etichette di `ExportBar` in italiano fisso | M | — |
| R26 | Mission Objectives (DA p. 19 §10A; RO p. 19) | Fatto | `pages/planner/objectives.ts` (+ test); non modificano la simulazione | — | — | — |
| R27 | Confidence & Data Quality, "Model Confidence & Assumptions" (DA §10B; RO p. 22) | Fatto | `pages/planner/quality.ts`, provenance negli endpoint, indicatore di validità (`ValidityMap.svelte`) | — | — | — |
| R28 | What-if e Before/After (DA §10C; RO p. 21) | Fatto | `pages/planner/sensitivity.ts`, `/api/lunar/coupled-sensitivity`, what-if energia del terreno (commit `79203bc`) | — | — | — |
| R29 | Mission Replay (DA §10D) | Fatto | chiavi `planner.replay*`, e2e `mission-planner.spec.ts` | — | — | — |
| R30 | Nessun punteggio unico; eventuale Landing Suitability Index solo dopo criteri chiari (DA §10E; RO p. 17; MP §6 Lezione 6) | Da decidere | esiste un punteggio di classifica `rank_sites` (`lunar/mission.py`, `docs/knowledge/hackathon/lunar-ranking-score.md`), con componenti sempre mostrate | decidere se tenerlo, rinominarlo o toglierlo | S | U |
| R31 | Libreria di 3-4 scenari dimostrativi (Site A-D) (RO p. 21) | Parziale | `library.ts` (salvataggio locale, max 20) e due esempi didattici "sites"/"dates" (`Planner.svelte` `openExample`) | i quattro scenari A-D con spiegazione del fenomeno; gli esempi usano de Gerlache e Shackleton, che con la maschera a 200 km sono **in ombra tutto l'anno** (validation.md, tabella 2027) | S | — |
| R32 | Modalità Demo per la giuria, "Launch Interactive Demo", 2-3 min, funzionante offline con scenari precalcolati (RO p. 23-24) | Non fatto | nessuna stringa o pagina corrispondente | percorso guidato precalcolato | M | — |
| R33 | Explainable Results: cosa, perché, quali parametri (RO p. 20) | Fatto | `pages/planner/explain.ts` (+ test) | — | — | — |
| R34 | "Explore why": dal Planner al laboratorio con stessi sito, istante, frequenza, antenna, mast, terreno (RO p. 13) | Parziale | `analysisLink` in `Planner.svelte` apre `/simula?tab=scena&scene=analysis` con sito, istante, mast, stazione, guadagno, bit rate, k; scenario condiviso in `shell/scenario.ts` | passaggio di frequenza e parametri del terreno e ritorno senza perdita: **non verificato** end-to-end | S | — |
| R35 | Livelli Basic/Advanced/Expert (RO p. 12) | Parziale | due livelli Learning/Avanzato (`shell/mode.ts`), Guided/Advanced nel Planner | livello Expert (coefficienti di Fresnel, rugosità, parametri di compensazione) come livello separato | S | U |
| R36 | Percorso Education in sei lezioni, glossario, quiz, report finale (MP §1, §3, §5; DA p. 18 §9) | Parziale | stepper `lesson` 0-5, esercizi (`planner.exercisesTitle`), tre quiz sì/no (visibilità, Sole su orizzonte piatto, DEM mancante), glossario a scomparsa, decisione motivata | quiz a scelta multipla (l'esempio di MP §6 è un'immagine non estratta), domande per ogni lezione, test prima/dopo | M | X |
| R37 | KPI della didattica: completamento, risposte corrette, confronti (MP §8; BP §14 Education) | Non fatto | nessuna analitica (scelta: nessun cookie non essenziale) | decidere se e come misurare | M | U |

### 1.4 Riorganizzazione del sito (Home / Planner / Explore / Learn)

Registro attuale (`frontend/src/pages/*/index.ts`, ordine): Home `/` (0), Mission Planner `/mission-planner` (5),
Explore `/explore` (10), Simula `/simula` (10, alias `/lander`, `/wave`), Learn `/learn` (20), Analizza `/analizza`
(20, alias `/grazinglink`), Pricing `/pricing` (25), Siti `/siti` (30, alias `/viewer`, `/compare`), Team `/contacts`
(30), Telemetria (36), Simulazioni (37), Laboratorio (40), Assistente `/chat` (50), legali `/licenses` `/privacy`
`/cookies` (90-92), `/404`.

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R38 | Navigazione principale a tre percorsi Plan/Explore/Learn (RO p. 1, p. 15 priorità 1) | Parziale | pagine `/explore` e `/learn` sono hub (`shell/JourneyHub.svelte`) con schede verso le pagine esistenti; commit `d7ec3fc` | le pagine vecchie restano in barra accanto agli hub (Simula, Analizza, Siti, Laboratorio): doppio ingresso | M | U |
| R39 | Home con tre grandi scelte, dati NASA usati, anteprima e confronto (RO p. 15) | Parziale | `Home.svelte` collega `/simula` e `/mission-planner`; mini-simulatore e striscia di missione | nessun ingresso diretto a Explore e Learn dalla home; sezione "dati NASA utilizzati" non verificata | S | — |
| R40 | Explore in 4 schede: Terrain & Geometry, Signal Propagation (Diffraction/Multipath/Wave), Antenna & Link Budget, Model Validation (RO p. 7-10, p. 16) | Parziale | hub Explore: Scena (`/simula?tab=scena`), Onda, Analizza, Siti, Laboratorio | nessuna scheda "Model Validation & Analysis" che raccolga compensazione, incertezza, mappe di validità, casi di verifica; Antenna & Link Budget come scheda propria assente (sta dentro Analizza) | M | — |
| R41 | Learn in 5 voci: Guided Mission, Lunar Geometry, Solar Illumination, Radio Communication, Interactive Exercises (RO p. 17) | Parziale | hub Learn con 3 schede: Mission Planner, la storia in home, Assistente | contenuti per geometria, illuminazione e radio come lezioni autonome | M | — |
| R42 | Sites & Data (libreria siti, fonti NASA/JPL, DEM) e About/Documentation (metodologia, limiti, validazione) (RO p. 17) | Parziale | `/siti`, `/licenses`, documenti in `docs/` e base di conoscenza dell'assistente | pagina About/Metodologia nel sito; pagina fonti e DEM | M | — |
| R43 | Tre zone per scheda (visualizzazione, controlli, risultati) e meno pulsanti visibili (RO p. 11) | Non verificato | commit `ba7f4f0` "collapsible settings drawers", `0357e26` | verifica visiva non eseguita in questa analisi | — | — |

### 1.5 Tutorial dati NASA reali (quali dataset, quali integrati, quali manuali)

| ID | Passo del tutorial (TUT) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R44 | Passo 1: kernel NAIF `naif0012.tls`, `de440s.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_*.tf` (TUT §3) | Fatto (automatico) | `install.sh`/`make ephemeris` scaricano 45 MB con SHA-256 in `build/ephemeris`; `engine.py` apre `moon_pa_de440_200625.bpc` | — | — | — |
| R45 | Passo 2: scelta del DEM: `LDEM_85S_40M/20M/10M`, `LDEM_80S_*`, `LDEM_875S_5M`, DEM dei siti PGDA 90 (TUT §4) | Parziale | integrati e bloccati in `backend/domain/grazing/dem.lock.json`: `ldem_85s_20m_float` e `ldem_75s_240m_float` (PDS `float_img`, SHA-256), scaricati a tile (circa 41 MB) | 40 m, 10 m, 80°S, 5 m e PGDA 90 non integrati | M | X |
| R46 | Passo 3: conversione DN × 0,5, rifiuto dei valori "raggio" (TUT §5) | Fatto per i prodotti usati | i prodotti `float_img` sono già in metri; lo script `prepare_lola_dem.py` dello ZIP non è portato | serve solo se si aggiungono prodotti interi (IMG/JP2) | S | — |
| R47 | Passo 4: `check_dem.py` (unità, proiezione, copertura, sito, caratteristiche) (TUT §6) | Parziale | orientamento verificato con LROC WAC e AVGVISIB (validation.md), test `test_dem.py` | strumento utente per controllare un DEM arbitrario | S | — |
| R48 | Passo 5: DEM propri in una cartella, sovrapposizione fine → grosso, `provenance.dem.layers` (TUT §7) | Parziale | sovrapposizione fissa 20 m (10 km) + 240 m (200 km) in `horizon.py`; `GRAZING_DEM_DIR` è la cartella della cache | caricamento di DEM forniti dall'utente | M | — |
| R49 | Passo 6: validare con Horizons, Quickmap/Moon Trek, mappe di illuminazione, pytest (TUT §8) | Parziale | vedi R19 | Quickmap/Moon Trek manuali | S | X |
| R50 | Catalogo delle 17 regioni candidate Artemis con DEM PGDA 78/104, coordinate da inserire, stato `needs_coordinates`/`no_dem`/`ready` (TUT §9) | Parziale | `backend/domain/data/sites.json`: 8 siti (Apollo 11 e 17; Malapert, Haworth, Mons Mouton, Nobile rim, de Gerlache, Shackleton) con coordinate di **centri di feature IAU**, `kind` "…artemis_candidate" | catalogo delle 17 regioni; NASA non pubblica le coordinate delle regioni (TUT §9 "Perché le coordinate sono vuote") | M | X |
| R51 | Luce continua per una permanenza di 156 h, `/stay-windows` (TUT §9) | Non fatto | nessun endpoint `stay`/`countdown`/`sweep`/`compare/shift` in `backend/api` | portare la logica (non il codice) dallo ZIP | M | — |
| R52 | Testo di attribuzione delle fonti (TUT §11) | Non verificato | `/licenses`, `docs/design/credits.md` (solo immagini SVS/LOLA) | testo "Data and models" visibile nei risultati | S | — |

### 1.6 Pricing e business plan

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R53 | Tre piani: Free, Premium, Enterprise, con tabella di confronto (il BP §6.1 ne elencava cinque; ridotti a tre per decisione dell'utente; prezzi ipotesi) | Fatto (solo vetrina) | `/pricing` (`pages/pricing/Pricing.svelte`), prezzi "Indicativo" in `i18n/en.pages.json` e `it.json`; e2e `pricing.spec.ts` | prezzi validati (BP §6: "ipotesi da validare") | S | U |
| R54 | Pagamenti (BP §6.1-6.2) | Da decidere | link esterni abilitati solo da `VITE_PREMIUM_CHECKOUT_URL` e `VITE_ENTERPRISE_CHECKOUT_URL` (HTTPS) (`checkout.ts`); README "RAVEN non gestisce pagamenti, contratti, fatturazione" | scelta del fornitore, IVA, fatturazione, contratti | M | U |
| R55 | Account, autenticazione, licenze e attivazione degli accessi (BP §6.1 Professional "storico delle simulazioni", Enterprise "multiutente") | Non fatto | nessun login/sessione/chiave d'accesso in `backend/api` (unico riferimento a token: plugin `assistant_openai`) | identità, ruoli, licenze, storico lato server | L | U |
| R56 | Misura dell'uso / prezzo per volume di simulazioni (BP §6.1 Professional) | Non fatto | solo rate limit in memoria (`backend/api/security.py`) | contatori per utente, quote | M | U |
| R57 | API e integrazioni per terzi (BP §6.2 n. 4, Enterprise) | Parziale | API REST pubblica (`/api/lunar/*`, `/api/grazing/*`), OpenAPI di FastAPI | chiavi, quote, versionamento e SLA per clienti | M | U |
| R58 | Report tecnico campione, video 60-90 s, scheda prodotto, listino pilota, matrice di validazione (BP §10.3) | Non verificato | non presenti nel repository (validation.md è la base tecnica della matrice) | materiali commerciali | M | U |
| R59 | Obiettivi di ricavo e break-even (BP §9) | Da decidere | calcoli coerenti: 10 × 199 × 12 = 23 880 €; + 30 000 = 53 880 €; − 36 000 = 17 880 €; Education 7 500 − 3 600 = 3 900 € | nessun legame col codice; obiettivi da fissare dopo interviste (BP §11) | — | U |
| R60 | Go-to-market: 10-15 interviste, 3-5 test, ≥ 3 manifestazioni d'interesse, pilot (BP §4.3, §10) | Non verificato | nessuna evidenza nel repository | attività esterna | L | U |
| R61 | Legale: privacy, cookie, licenze, condizioni d'uso, disclaimer "non qualificato per decisioni operative" (BP nota, §13) | Parziale | `/privacy` (modello "da completare a cura del titolare", `Privacy.svelte` riga 9), `/cookies`, `/licenses`, disclaimer in `/pricing` e nei risultati | titolare e contatti reali; **nessuna pagina di condizioni d'uso**; condizioni contrattuali delle licenze | M | U |
| R62 | Supporto standard/prioritario (BP §6.1) | Non fatto | `/contacts` con segnaposto (`frontend/src/data/team.json`) | canale di supporto e recapito commerciale | S | U |
| R63 | Sicurezza (BP §8.2 "Backend, report e sicurezza"; Enterprise) | Parziale | CSP `default-src 'self'`, header di sicurezza, rate limit, limite del corpo (`security.py`), nessun cookie, CORS chiuso per default, allowlist licenze e SBOM in CI (`docs/process/ci-notes.md`) | autenticazione, audit, test di penetrazione, hosting pubblico protetto | L | U |
| R64 | KPI di prodotto e commerciali (BP §14) | Non fatto | nessuna analitica | decisione su privacy e strumenti | M | U |

### 1.7 Nome del prodotto

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R65 | Scelta del nome fra le proposte (NOMI: LunaLink, MoonReach, LunaBridge, MoonHorizon, LunaSignal, SeleneX, Lunaris, …, top 5 LunaLink/MoonReach/LunaBridge/HorizonX/Lunaris) | Da decidere | **RAVEN non è nella lista** (e nemmeno GrazingLink). Rinomina a RAVEN nel commit `b94c1d8` (2026-11-03); "GrazingLink" resta nei percorsi (`/grazinglink`), nei documenti (`docs/domain/grazinglink-*.md`) e in 8 file di `frontend/src` | decisione definitiva; verifica di disponibilità del marchio e del dominio (non documentata) | S | U |

### 1.8 Backend prototipo nello ZIP contro backend attuale

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R66 | Backend "un solo motore scientifico" con `/simulate`, `/compare`, `/compare/shift`, `/countdown`, `/sweep`, `/horizon`, `/stay-windows`, `/artemis/regions`, `/sites`, `/health` (ZIP README) | Parziale (equivalenti diversi) | il backend attuale ha `/api/lunar/{sites,defaults,analyze,timeline,solar-terrain,horizon,coupled-sensitivity,mission}` e `/api/grazing/{status,defaults,analyze,compare,antenna,snapshot,scene,compensation,compensator,wave}` | `/countdown`, `/sweep`, `/stay-windows`, `/compare/shift`, catalogo Artemis: vedi §3 | M | — |

### 1.9 Integrazioni, hosting, CI, accessibilità, lingue, documentazione, team, estensioni

| ID | Requisito (fonte) | Stato | Evidenza | Cosa manca | Sforzo | Dip. |
|---|---|---|---|---|---|---|
| R67 | Integrazioni dati promesse: SPICE, LOLA, Horizons, Moon Trek, QuickMap, CesiumJS (BP §3.1; DA p. 15 tabella "Dati e tecnologie") | Parziale | SPICE e LOLA integrati; Horizons come fixture di validazione offline; scena con Three.js | Moon Trek e QuickMap non integrati (solo riferimento manuale); CesiumJS non usato (scelta) | M | X |
| R68 | Dataset ufficiali della sfida (DA p. 1; `docs/hackathon/nasa-lunar.md` "Da aggiungere dopo il 28 ottobre") | Non fatto | `nasa-lunar.md` §"Dati e termini d'uso": nessun dato ufficiale incluso né verificato | testo ufficiale della sfida, dataset, licenze | M | X |
| R69 | Motore C++/WebAssembly per orizzonte e profilo (DT §3, §8 ore 0-8; BOZ §6) | Non fatto (sostituito) | motore in Python (`backend/domain`) e modello di link nel browser in TypeScript (`simula/linkModel.ts`, parità con Python entro 0,01 dB, validation.md) | decidere se serve ancora | — | U |
| R70 | Hosting e deploy (BP §8.1 "Hosting, dominio" 0-50 €; RO p. 24 demo offline) | Parziale | `Dockerfile`, `compose.yaml` (non provato, README), `install.sh`/`install.ps1`, devcontainer provato in Codespaces il 2026-10-20 (ledger); server demo su tailnet (ledger) | hosting pubblico, dominio, HTTPS, backup | M | U |
| R71 | CI/CD | Parziale | `.github/workflows/ci.yml` (job backend, frontend, e2e, install-smoke); `gh run list`: ultime esecuzioni completate sul branch **fallite** (2026-11-04 12:05 merge; 2026-11-02), una in corso alle 17:31 | CI verde; nessun deploy automatico | M | — |
| R72 | Accessibilità (DA §5 interfaccia intuitiva; `grazinglink-ux.md` interruttore accessibile) | Fatto (test) | e2e `a11y.spec.ts` (axe), `keyboard.spec.ts`, `tv.spec.ts`, `devices.spec.ts`, `shell/a11y.ts` | esito sull'ultimo commit: non verificato (CI sopra) | S | — |
| R73 | Lingue: solo inglese e italiano (decisione) | Parziale, in corso | `frontend/src/i18n/locales.ts`: `LANGS = ['en','it']`, commit `8ed6be7` toglie hi/zh/ar/ko; un altro agente sta modificando `frontend/src/i18n`, `e2e/tests/i18n*`, `docs/i18n*` | `docs/i18n.md` dice ancora "sei lingue" al momento della lettura; testo italiano fisso nei componenti (`t(` = 0 in `Wave.svelte`, `Privacy.svelte`, `Cookies.svelte`; `ExportBar.svelte` "Scarica CSV"); titoli "Mission Planner", "Explore", "Learn" fissi in inglese | M | — |
| R74 | Documentazione: metodologia, modelli, limiti, validazione (RO p. 17; BP §10.3) | Fatto (repo), Parziale (sito) | `docs/domain/*`, `docs/knowledge/*` (pagine e assistente), `docs/traceability.md` | README non aggiornato (vedi §5 B); pagina About nel sito (R42) | S | — |
| R75 | Team e contatti, ruoli (DT §8 "Alessio: motore; tu: dati, modelli, validazione, pitch"; `nasa-lunar.md` divisione dei compiti) | Non fatto | `team.json`: due membri "Nome Cognome" con bio segnaposto | nomi, foto, ruoli, contatti reali | S | U |
| R76 | Demo hardware ESP32 con LED e OLED (DA p. 21-29 §11) | Non fatto | `docs/hal.md` riga 53: nessuna build o esecuzione su ESP32 | opzionale (DA lo mette in P3) | M | U |
| R77 | Pathfinding A* per rover consapevole dell'RF (DA p. 9 Mod. 11) | Non fatto | nessun codice | P3 | L | U |
| R78 | Verificare il testo ufficiale della sfida prima di adeguare i requisiti (DA p. 1) | Non verificato | nome della sfida diverso fra i documenti (vedi §5 A1) | lettura del testo ufficiale NASA 2026 | S | X |

---

## 2. Cosa manca: i 15 punti aperti principali (in ordine di priorità dentro ogni gruppo)

### Bloccati da una decisione dell'utente
1. **Nome del prodotto** (R65): RAVEN non è nella lista dei nomi; GrazingLink resta in URL e documenti. Decidere e,
   dopo, uniformare (S) e verificare marchio/dominio.
2. **Titolare, privacy, condizioni d'uso, contatti e team** (R61, R62, R75): privacy è un modello da completare,
   non esiste una pagina di condizioni d'uso, `team.json` contiene segnaposto. Servono dati reali dell'utente (S-M).
3. **Modello commerciale operativo** (R54, R55, R56): fornitore di pagamento, account/licenze, misura dell'uso.
   Oggi solo vetrina. Grande lavoro (L) e da non iniziare prima delle interviste (BP §4.3).
4. **Hosting pubblico** (R70): dove e con quale dominio pubblicare la demo per la giuria (M).
5. **Punteggio di classifica** (R30): tenerlo o toglierlo, visto che DA e RO chiedono di non avere un punteggio unico (S).

### Bloccati da dati esterni
6. **Testo e dataset ufficiali della sfida** (R68, R78): non inclusi; il nome della sfida stesso differisce fra i
   documenti (M).
7. **Coordinate delle regioni Artemis e DEM a 5 m** (R50, R45, R2): NASA non pubblica le coordinate delle regioni;
   i siti attuali sono centri di feature IAU, tre dei quali fondi di cratere in ombra tutto l'anno (M).
8. **Parametri radio di un lander e di una stazione reali** (R9, R11): oggi tag I; preset Artemis 36 kbps/60 Mbps
   senza fonte nel repo (S-M).

### Realizzabili subito
9. **CI verde** (R71): le ultime esecuzioni completate sul branch sono fallite (M).
10. **Lingue solo en/it complete** (R73): togliere il testo italiano fisso da Simula, Onda, Export, Privacy, Cookie;
    allineare `docs/i18n.md` (lavoro dell'altro agente in corso) (M).
11. **Struttura Explore/Learn e home a tre ingressi** (R38-R42): oggi gli hub convivono con le vecchie pagine;
    mancano la scheda Model Validation, le lezioni di Learn e la pagina About (M).
12. **Modalità Demo per la giuria con scenari precalcolati offline** (R32) e **esempi didattici con siti illuminati**
    (R31) (M).
13. **Report PDF strutturato** (R25) e **finestre con motivo di chiusura e bordi raffinati** (R23, R18) (M).

### Lacune di validazione
14. **Margine RF assoluto e cresta arrotondata non validati** (R5, R7, R9, R21): nessuna misura, nessun bilancio
    lunare completo pubblicato, ITU e split-step distanti fino a 2,4 dB; serve un riferimento indipendente (cilindro
    esatto) e una revisione di un esperto RF (L).
15. **Energia e illuminazione nel Planner** (R15, R16): la timeline base usa ancora l'orizzonte piatto; energia e
    batteria senza confronto reale; controlli di DT §4 (Malapert 10,7°, 8 giorni) non rieseguiti (R17) (M).

---

## 3. Backend prototipo (ZIP) contro backend attuale

Contenuto dello ZIP (32 file, 150 485 byte): pacchetto `grazinglink/` (`api.py`, `artemis.py`, `compare.py`,
`config.py`, `ephemeris.py`, `horizon.py`, `mission.py`, `models.py`, `rf.py`, `terrain.py`, `visibility.py`,
`windows.py`), `data/artemis_regions.json`, `data/sites.json`, `scripts/{fetch_kernels,prepare_lola_dem,check_dem,
add_artemis_site}.py`, `examples/demo.py`, 6 file di test (il README dichiara 53 test: **non verificato**, non
eseguiti), `requirements.txt` (numpy, pydantic, fastapi, uvicorn, spiceypy, astropy, rasterio, pytest, httpx).

| Aspetto | ZIP (dal README) | Backend attuale |
|---|---|---|
| Effemeridi | spiceypy + fallback analitico astropy (dichiarato) | `backend/ephemeris`, kernel NAIF con SHA-256, validato contro Horizons |
| Frame lunare | `MOON_ME_DE440_ME421`, **non provato** con i PCK reali (README "Cosa NON è stato verificato") | stesso frame, usato con i kernel reali |
| DEM | GeoTIFF in `data/dem/`, sovrapposizione fine → grosso; **nessun DEM LOLA reale letto** | tile PDS `float_img` bloccati (20 m + 240 m), orientamento confermato con LROC |
| Orizzonte | campionamento fino a 60 km, oltre il bordo sfera | maschera a 200 km, 1440 azimut, validata con arbitro e LROC |
| RF | knife-edge P.526, oltre ν = 2,4 "unavailable" (soglia euristica); **niente multipath, niente cresta arrotondata** | knife-edge esatto, T(m,n) P.526-9, multipath, antenna, gimbal, compensatore |
| Contratto | JSON camelCase del documento (`startTime`, `durationHours`, …) | `site_ids`, `start_utc`, `days`, `step_min` (contratti in `contracts/`) |
| Validazione | sub-solare, librazione, orizzonte su casi chiusi; nessuna contro Horizons/Quickmap | vedi `docs/domain/validation.md` |

**Da riusare (come idee e specifiche, riscritte e testate nel repository, non copiando il codice):**
- `/stay-windows`: luce continua per una permanenza di N ore con vincoli sul blackout della Terra (R51);
- `/countdown` (prossimo tramonto/alba, Earthset/Earthrise), `/compare/shift` (stessa data spostata di N giorni),
  `/sweep` (percentuali giorno per giorno per heatmap);
- finestre con motivo di chiusura e raffinamento dei bordi per bisezione (R23, R18);
- `path_condition` (`los_clear`, `fresnel_zone_obstructed`, `diffracted`, `shadowed_beyond_model`) e
  `rf_relying_on_diffraction_percent`: utili per la distinzione visibilità/diffrazione/RF di MP e RO;
- catalogo `artemis_regions.json` (17 regioni, puntatori PGDA 78/104, coordinate volutamente null) e controlli di
  `check_dem.py` (unità, proiezione, bordo) come strumento per DEM forniti dall'utente (R47, R48, R50).

**Da non integrare e perché:**
- il motore dello ZIP duplicherebbe effemeridi, orizzonte e RF già presenti e validati; due motori contraddicono la
  regola "un solo motore scientifico" (MP §9, RO p. 13) e la regola del branch di non toccare il core
  (`docs/hackathon/nasa-lunar.md`);
- il fallback analitico astropy e la sfera oltre 60 km danno risultati ottimistici; il frame lunare e i DEM non sono
  mai stati provati su dati reali (lo dice lo ZIP stesso);
- la soglia euristica ν = 2,4 e l'assenza di multipath/cresta arrotondata sono un passo indietro rispetto al modello
  attuale;
- il contratto camelCase non coincide con quello versionato in `contracts/`;
- l'archivio è materiale non fidato: il codice non è stato rivisto né eseguito, e `rasterio`/`astropy` non sono
  nell'allowlist delle licenze verificata in CI (**non verificato**);
- `data/sites.json` dello ZIP ha coordinate dichiarate "NON verificate".

---

## 4. Integrazioni dati: integrate, manuali, mancanti

| Fonte | Stato | Dove |
|---|---|---|
| NAIF SPICE (DE440, PCK/FK lunari, LSK) | integrata, automatica | `backend/ephemeris`, `make ephemeris` |
| LOLA `ldem_85s_20m_float`, `ldem_75s_240m_float` (PDS) | integrata, automatica a tile | `grazing/dem.py`, `dem.lock.json`, `prefetch.py` |
| JPL Horizons | fixture offline di validazione | `tests/backend/domain/fixtures/` |
| LROC WAC `WAC_POLE_ILL_TWI_SOUTH_100M`, LOLA AVGVISIB | confronto manuale di validazione (script) | validation.md §"Validazione Sole-terreno" |
| NASA SVS (immagini) | asset grafici | `docs/design/credits.md` |
| DSN 810-005 (coordinate, G/T) | valori citati | `docs/domain/assumptions.md` |
| NASA/TM-2019-220203, TM-2020-220472 | controlli differenziali nei test | validation.md |
| LOLA 40 m/10 m/80°S/5 m, PGDA 78/90/104 (Barker, Bertone) | non integrati | — |
| Moon Trek, QuickMap | non integrati; solo riferimento manuale | — |
| Dataset ufficiali della sfida | non inclusi | `docs/hackathon/nasa-lunar.md` |

---

## 5. Contraddizioni

### A. Fra documenti
1. **Nome della sfida**: DT, BP e BOZ parlano di "CLPS Lunar Mission Browser"; DA p. 1 dice di aver individuato la
   challenge ufficiale "Lunar Landing Site Navigator". Nessuno dei due è verificato nel repository (R78).
2. **Nome del prodotto**: GrazingLink in tutti i documenti; NOMI propone altri nomi (top 5: LunaLink, MoonReach,
   LunaBridge, HorizonX, Lunaris); il codice usa RAVEN, che non compare in nessun documento.
3. **Posizionamento**: DT e BOZ mettono al centro l'RF (diffrazione, multipath, compensazione); DA p. 1-2 e p. 29-30
   mettono al centro luce, Terra e confronto, e spostano diffrazione e multipath in P2, GPR in P3; BP P1 mette la
   diffrazione fra le priorità. RO mette Link Budget e Diffraction in P1, Multipath e GPR in P2.
4. **Bit rate**: BOZ §3D "da 10 kbps a 3 Mbps"; DT §6 fino a 100 Mbps; DT §4.6 preset 36 kbps e 60 Mbps.
5. **Librazione**: BOZ §3A ±6,7° in latitudine e ±7,9° in longitudine; DT §6 "circa ±7°"; ZIP README ±6,6° lat e ±6°
   lon su 30 giorni.
6. **Elevazione della Terra al polo**: BOZ §1 "tra 0,5° e 1,5°" dall'orizzonte; DT §4 Malapert fino a 10,7°.
7. **Motore**: DT §3 e BOZ §6 prevedono C++/WebAssembly; DA p. 15 e ZIP usano Python/FastAPI.
8. **Didattica**: BP §7 la tratta come linea complementare da limitare a tour e spiegazioni per l'hackathon; MP
   propone sei lezioni, quiz e report; RO p. 23 vuole "un vero strumento didattico".
9. **Pannello solare**: DA p. 17 esempio con inclinazione 15°; ZIP README: pannello verticale che segue il Sole,
   perché "con il Sole a pochi gradi un pannello inclinato di 15° produrrebbe quasi nulla".
10. **Stato di Artemis**: TUT §9 e ZIP: Artemis III ora test in orbita terrestre, primo allunaggio Artemis IV (fonte
    del 23 ottobre 2026); gli altri documenti parlano di Artemis III. Non verificato qui.

### B. Fra documenti e codice
1. **Cresta arrotondata**: DT §5.3 dice che il bordo a lama sottostima "fino a circa 2,4 dB" (R = 400 m) e
   BOZ §3B usa il GPR sullo split-step; il codice usa ora T(m,n) di P.526-9 come correzione predefinita, che vale
   4,22 dB a ν = 3 e 10,34 dB a ν = 8 per R = 400 m (validation.md, tabella "tre fonti"): margini più bassi di quelli
   dei documenti. JPL226 eq. (35)-(38) darebbe 0 ed è stata scartata.
2. **Rugosità del multipath**: lo script di DT (`compensation_demo.py`) applica `exp(-(4πσ sinψ/λ)²)` all'ampiezza;
   il codice usa `exp(-(q_z s)²/2)` (model.md §0 n. 7). Le profondità delle frange di DT §4.3 ("fino a −20 dB") non
   sono più riprodotte da quel calcolo (numero non riverificato qui).
3. **Accuratezza ITU J(ν)**: DT §4.2 "entro 0,11 dB"; repository ≤ 0,123 dB per −0,78 < ν ≤ 5.
4. **Un solo motore**: MP §9 e RO p. 13 chiedono un solo motore; nel codice coesistono il modello "lunar"
   (orizzonte piatto, link semplificato: `backend/domain/lunar`, `/api/lunar/timeline`) e il modello "grazing"
   (DEM, diffrazione: `backend/domain/grazing`), collegati solo nella missione accoppiata `/api/lunar/mission`.
   method.md lo dichiara ("Non rappresenta la diffrazione di GrazingLink").
5. **Punteggio unico**: DA §10E e RO p. 17 chiedono di evitarlo; il codice ha `rank_sites` (media pesata
   normalizzata, `lunar-ranking-score.md`).
6. **Livelli**: RO p. 12 Basic/Advanced/Expert; codice Learning/Avanzato (`grazinglink-ux.md` lo ha deciso così).
7. **Siti**: RO p. 4 propone Malapert, Shackleton; ZIP e TUT puntano alle 17 regioni Artemis; il codice ha 6 centri
   di feature IAU e 2 siti Apollo; gli esempi didattici usano de Gerlache e Shackleton, entrambi in ombra tutto
   l'anno con la maschera a 200 km.
8. **README** contraddice lo stato: dice "Pagina principale: `/grazinglink`" (oggi alias di `/analizza`; l'ingresso
   è `/mission-planner`) e "La CI di GitHub non è mai stata eseguita; nessun repository remoto configurato", mentre
   `origin` è `github.com/AlePompeo/space-hackathon-base` e la CI gira (ledger, `gh run list`).
9. **Lingue**: decisione solo en/it e `locales.ts` coerente; `docs/i18n.md` riporta ancora sei lingue (in modifica
   da un altro agente al momento della lettura).
10. **Contratto dello scenario**: DA p. 17 e MP Step 1 p. 11 definiscono `MissionScenario` camelCase con
    `solarPanel`, `antenna.frequencyHz`, `rfThresholdDb`; l'API attuale usa `site_ids`, `start_utc`, `days`,
    `step_min`, `overrides`.

---

## 6. Rischi

| Rischio | Impatto | Nota |
|---|---|---|
| Aderenza alla traccia non verificata | Alto | nome della sfida incerto e dataset ufficiali assenti (R68, R78): i requisiti P0 potrebbero non coincidere con quelli NASA |
| Esempi e siti in ombra permanente | Alto per la demo | gli esempi didattici confrontano due fondi di cratere con 0 % di luce sotto la maschera completa (validation.md): rischio di demo poco leggibile o fraintesa |
| Due modelli con risultati diversi nella stessa pagina | Medio-alto | timeline a orizzonte piatto accanto a illuminazione con terreno (R15, §5 B4): numeri diversi per lo stesso sito |
| Margini RF più bassi dei documenti | Medio | la politica ITU è più conservativa: pitch e slide basati su DT/BOZ andrebbero aggiornati |
| CI rossa | Medio | ultime esecuzioni completate fallite: non si può dichiarare il branch verificato |
| Vetrina prezzi senza base legale | Medio | `/pricing` mostra prezzi indicativi senza condizioni d'uso, titolare né contatti reali (R61) |
| Nome RAVEN non vagliato | Medio | assente dalla lista dei nomi, nessuna verifica di marchio documentata; doppio nome nei percorsi |
| Ridistribuzione di documenti di terzi | Medio | `42-226D.pdf` e `ManualeEquazioniRiferimentoNASA.pdf` sono versionati in git (repository privato); diritti di ridistribuzione **non verificati** (la copia ITU è invece esclusa da git, validation.md) |
| Uso del codice dello ZIP | Medio | archivio non fidato, non provato su dati reali; integrarlo duplicherebbe il motore |
| Risultati letti come garanzia operativa | Alto | mitigato da disclaimer (R20); resta finché mancano misure e revisione RF (R21) |
| Lavoro i18n in corso in parallelo | Basso-medio | file condivisi (`frontend/src/i18n`, `docs/i18n*`) modificati da un altro agente: rischio di conflitti nei prossimi commit |
| Scope | Medio | DA conta 12 moduli più ESP32; molti P2/P3 già fatti (energia, replay) mentre P0 di RO (struttura del sito, demo per la giuria) è parziale |
