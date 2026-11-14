# RAVEN: backlog e passaggio di consegne

**Questo è il documento da leggere per riprendere il lavoro** (sessione nuova, altro agente, Copilot). Aggiornarlo a ogni
blocco concluso. Ultimo aggiornamento: 9 novembre 2026. Il resto della pianificazione sta nei documenti indicati in fondo.

## Che cosa è il progetto
RAVEN (nome definitivo; "GrazingLink" è il nome storico della ricerca) pianifica il collegamento radio tra un lander lunare
al polo Sud e la Terra, quando la Terra sta a circa 1 grado dall'orizzonte: Sole e Terra visti dal sito, terreno LOLA,
diffrazione sul crinale (ITU-R P.526-9), multipath, antenna, batteria, visibilità DSN, ore utili. Un solo modello per tutto
il sito (RAVEN engine, stadi S0-S7), spiegabile alla giuria. Branch di lavoro: `hackathon/nasa-lunar`
(remoto `AlePompeo/space-hackathon-base`). Il branch `template-base` è la base generica e riceve anche documenti dell'utente.

## Regole che l'utente ha imposto (valgono sempre)
- **Onestà scientifica:** mai inventare dati; l'ignoto resta ignoto (un terreno sconosciuto non diventa un orizzonte piatto);
  ogni parametro ha tag V (da fonte) / D (derivato) / I (ipotesi illustrativa); non dichiarare validato ciò che non lo è.
- **Un solo modello:** nessun motore parallelo; le pagine usano `/api/raven/*`. Il modello nel browser per gli slider è una
  copia dichiarata dello stadio S5, verificata con fixture (0,01 dB).
- **Lingue: solo inglese (default) e italiano.** Cataloghi `frontend/src/i18n/{en,en.pages,it}.json` con parità di chiavi.
- **Solo Linux** (Windows scartato, macOS mai provato).
- **Nessuna banda di link in testa alle pagine; nessun orologio UTC nella barra; niente domande dei giudici sul sito.**
- **Piani:** esattamente tre (Free, Premium, Enterprise) con tabella di confronto; acquisti disattivati finché non c'è un
  fornitore; prezzi ipotesi; funzioni non realizzate etichettate "Prevista".
- **Risparmio di token:** un agente alla volta; niente Monitor/sleep/polling; test in primo piano con `tail -n 30`; durante
  il lavoro solo gli spec dei file toccati, giro e2e completo a fine blocco o in CI (qui va a circa 1 test al minuto).
- **Download dati minimo:** nulla all'installazione per siti personalizzati; stima e conferma; tetti 10 MB per sito, 40 MB per
  richiesta, cache 300 MB (portata da 200 il 12 nov: i 51 siti del catalogo occupano circa 250 MB, per decisione dell'utente di scaricarli all'installazione).
- **Limite del bundle iniziale:** 70.000 B (`npm run check:bundle`); codice pesante in blocchi caricati a richiesta.
- **Segreti:** nessun token nel repository. Il token GitHub usato in sessione non va salvato né scritto nei file.
- **Git:** commit piccoli, solo i propri percorsi; non forzare i push; non toccare processi altrui; `docs/process/ledger.md`
  è storico (fino alla fase iniziale), non aggiornarlo.

## Esito della sessione dell'11 nov ("continua il lavoro")
1. **Web Worker: non serve.** Il profilo CPU di una simulazione a 365 giorni mostra meno di 100 ms di JavaScript: il blocco è
   l'avvio di WebGL (scena 3D). Fatto: sonda WebGL in cache per tutta la pagina (un contesto in meno per montaggio), scena 3D montata
   400 ms dopo i risultati, barra di avanzamento per scenario. Blocco più lungo 1,97 s -> 1,2 s in WebGL software (headless).
2. **Etichette in inglese** del disegno della sezione laterale per il report (flag `language: 'en'`), con test.
3. **Verifica completa** (11 nov, sera): pytest 2336 passati più i 2 test aggiornati; vitest 1019/1019 (timeout portato a 20 s: sotto
   carico due test pesanti superavano i 5 s); ruff, mypy, lint-imports e svelte-check puliti; e2e completa con 2 worker = 26 falliti, di
   cui 13 solo per carico; i 12 veri sistemati (dashboard, library 8 -> catalogo, i18n smoke, mode /chat, TV: bottone nascosto, compare:
   marcatori a un bersaglio di distanza) e rilanciati in serie: 124/124. **Restano rossi 3 test di `telemetry.spec.ts`**
   (contesto di RAVEN SI): i parametri si vedono solo dopo aver spuntato "Includi i parametri tecnici visibili", che sta in un
   riquadro chiuso; il test va riscritto sul flusso attuale. Chiave duplicata `journey.progress` trovata e protetta da un test
   (`i18n/duplicateKeys.test.ts`).
   Prima nota: chiave duplicata `journey.progress` trovata e protetta da un test
   (`i18n/duplicateKeys.test.ts`).
4. **Scena 3D e orizzonte** anche per i siti del catalogo fuori dal prodotto a 20 m (terreno globale a 237 m dopo il consenso).
   **Più di due siti insieme**: decisione: il planner e il report restano A contro B (54 punti del codice assumono due scenari);
   il confronto di N siti si fa nel Compare (classifica) e nella dashboard. Aperto se si vuole un planner a N scenari.
5. **Dashboard mission control**: gestore sessioni a sinistra, navigatore al centro (mappa polare con sovramappe, Luna 3D, scena del
   rover), numeri chiave A/B a destra con conto alla rovescia, risultati completi sotto, sessioni che seguono le altre schede.
   Sovramappe: quota LOLA e pendenza regionale (rasterizzate in `backend/assets/overlays/`, `scripts/build_overlays.py`), copertura
   dei dati, ore utili della sessione; ignoto tratteggiato, mai colorato. Aperte: frazione di Sole e di Terra per cella (maschere
   d'orizzonte su griglia), composizione a falsi colori, sovramappe sul globo 3D.

## ROADMAP (12 nov 2026, approvata dall'utente) - da qui si continua
Regole: token ottimizzati (nessun agente, righe mirate con grep/sed, uno script per modifica, un commit per fase, test solo dei file toccati e un giro completo
alla fine), onesta' scientifica, solo occidentali per i modelli (niente Cina/Russia), licenze: MIT/BSD/Apache richiedono comunque gli avvisi (file di avvisi, non README).
**A. Ricerca automatica dei siti** (piano: `docs/design/site-discovery-plan.md` e `-implementation.md`; tutte le decisioni approvate)
- A0 Misura del costo del core: **fatto** (0,3 s per sito del catalogo con maschere in cache; 1,1 s per una cella nuova; 3 celle su 6 vicine a Shackleton chiedevano un
  download: il vincolo vero sono le tessere, non il calcolo). Conseguenza: candidati valutati dal core tutti allo stesso prodotto di terreno (240 m) e per questo si
  scarica l'intero prodotto 75S 240 m (58 MB) all'installazione; a nord di -75 gradi solo siti del catalogo o con tessere in cache, il resto "stima delle sovramappe, non
  verificata dal core" (tag I).
- A1 Brief: `MissionBrief` (pydantic) + parser a regole IT/EN + rotta `POST /api/raven/brief/parse` (**in corso**); scheda editabile nella chat di RAVEN SI e come pulsante "Trova siti".
- A2 Strati nuovi nelle sovramappe globali e polari: coincidenza Sole e Terra, durata massima senza Sole, durata massima senza Terra; matrice delle caratteristiche per cella.
- A3 Surrogato: fisica dalle sovramappe + correzione appresa (GP, alberi con quantili), pre-addestramento offline, conformal, apprendimento attivo, blocchi spaziali.
- A4 Probabilita': propagazione dei parametri di tag I (Sobol), P(obiettivi) con intervalli, nuvola (strato "idoneita'") + K siti, ordine lessicografico, fronte di Pareto.
- A5 Rotta a lavori `POST /api/raven/discover`, interfaccia "Trova siti", "Usa come A/B", sezione del report, pagine di conoscenza di RAVEN SI e riconoscimento dell'intento.
- A6 Agenti: parser LLM (online se configurato, altrimenti Granite 4.0 Nano locale con controllo RAM), elenco di esclusione dei modelli non occidentali, spiegatore e critico deterministici.
**Stato A (12 nov, sera):** A0 fatto. A1 backend fatto (`api/raven_brief.py`, `POST /api/raven/brief/parse`). A2 fatto: strati `both`, `sun_gap`, `earth_gap` nelle sovramappe
globali e polari, in dashboard e sulla Luna 3D. A3 fatto (numpy/scipy, senza scikit-learn che e' nell'extra `ml` non installato): `discovery/surrogate.py` (media fisica
lineare + correzione gaussiana, intervalli conformal con il piu' severo fra blocchi spaziali e k-fold casuale, copertura 88,8 % su 90 % nominale), `discovery/features.py`.
A4 parziale: `discovery/search.py` (apprendimento attivo, celle non confrontabili, obiettivi, probabilita' per cella, nuvola `suitability`); manca la propagazione degli
intervalli di tag I (Sobol). A5 backend fatto: `POST /api/raven/discover` + `GET /api/raven/discover/{id}` (lavoro asincrono, uno alla volta, valutatore = RAVEN core su 240 m dalle
tessere in cache, modalita' `coarse` in `dem_select`). Prova reale: 54 valutazioni in 46 s, 5 proposte; intervalli ancora larghi con cosi' poche valutazioni.
**A5 interfaccia (12 nov, notte):** pannello "Find the best sites" nella pagina Siti (`shell/finder/SiteFinder.svelte`): prompt letto dalle regole, scheda editabile del brief, avanzamento,
tabella dei siti con valori del core e intervallo del surrogato (ignoto se non lo sa dire), strato "Search result (suitability)" nel pannello delle sovramappe; e2e `site-finder.spec.ts` (2 test, ricerca simulata).
**A3b fatto (12 nov, notte):** caratteristiche Sole/Terra/insieme/notte/blackout **della finestra del brief** (`features.window_features`: orizzonti dalla griglia delle quote spedita
`polar-heights.npy`, effemeridi della finestra) al posto delle medie del 2027. Esperimento su 74 valutazioni reali del core (finestra 14 giorni, errore di validazione incrociata sulla quota
di ore utili): media 0,23; tutte le 10 caratteristiche 0,108; solo distanza dal polo + variabili di finestra 0,07-0,09 (scelte: `SURROGATE_FEATURES`); un peso di rilevanza nel kernel non
ha aiutato (radio peggiorata) ed e' stato tolto. Radio e Sole: errore 0,15-0,2 contro 0,32-0,4 della media. Intervalli al 90 % di circa +-0,23 sulle ore utili (due regimi di calibrazione, il piu'
severo): onesti ma larghi con 50 valutazioni. Le prime tre proposte sono stabili fra esecuzioni.
**A4b fatto (12 nov, notte):** `discovery/uncertainty.py` (scrambled Sobol in base 2 su 6 parametri di tag I con intervalli ASSUNTI: area pannello, batteria, carico attivo, duty radio
+-30 %, guadagno d'antenna +-2 dB, perdite +-1 dB; stessi insiemi per ogni sito; probabilita' = quota di insiemi che rispettano gli obiettivi con intervallo di Wilson al 90 %; parametri piu'
correlati al margine). Nel job: `uncertainty_samples` (default 12), proposte riordinate per probabilita' e poi ore utili, colonna "Probability of meeting them" e intervalli assunti nel pannello.
Prova reale: 5 siti con Sole >= 60 % e radio >= 80 %: P = 1,0 con Wilson 0,82-1,0 su 12 insiemi, perche' Sole e radio dei primi siti sono ben sopra le soglie e questi parametri non
spostano la quota di Sole (nota: le soglie del brief riguardano Sole e radio, non le ore utili). Giro completo: pytest 2415 passati, vitest 1025, bundle ok.
**A6 e A5 (12 nov, notte, seconda meta'):** politica "solo modelli occidentali" nel codice (`assistant/cloud.py`: `MODEL_RE` e' un sostituto che rifiuta i nomi di Qwen, DeepSeek, GLM/Zhipu, Kimi,
Yi, InternLM, Baichuan, MiniMax, Ernie, Hunyuan, Doubao, GigaChat, Yandex, Sber e simili in config, discovery, cloud e nella rotta della chat; la preferenza predefinita non ha piu' Qwen:
`ollama:granite4*,ollama:phi4*`; `.env.example` aggiornato). Livello modello del brief (`api/raven_llm.py`, `POST /api/raven/brief/parse` con `use_model`/`allow_external`): chiamato solo se le regole
lasciano campi obbligatori vuoti, locale (loopback) o online configurato **solo con consenso**; ogni valore proposto deve essere scritto nel testo (grounding), validato dallo schema, le regole
vincono; errori con codice generico. Pannello: caselle per il modello e per il consenso esterno, "Use in the planner" (il sito proposto diventa sito personalizzato dello scenario e apre il planner).
Pagina di conoscenza `docs/knowledge/site-finder.md` (RAVEN SI la recupera: 3 domande di prova). Giro completo: pytest 2460, vitest 1025, bundle ok; e2e del pannello 3/3.
Fatti dopo: intento nella chat di RAVEN SI (`pages/chat/intent.ts`, regole IT/EN, una domanda resta domanda) con la stessa scheda dentro la chat, sezione del report con il sito migliore (Pareto e terreno), Pareto/ordine/catalogo.
**Misura del modello locale (2026-11-11, llama.cpp b12110, 12 core, 12 prompt IT/EN, temperatura 0, JSON):** Granite 4.0-h 350M Q4_K_M: 50 % dei campi, inventa campi, 1,9 s, 0,56 GB;
Granite 4.0-h 1B Q4_K_M: 79 % dei campi (con date inventate dal solo mese e priorita' "balanced" non richiesta), 8,7 s mediana, 1,6 GB. Nessuno dei due raggiunge il criterio (>= 95 %): NON si
installa un modello incluso e il gestore/passo `--with-llm` e' sospeso. Il livello modello resta un riempitivo opzionale, sempre dietro le regole e dietro il controllo "il valore e' nel testo"
(`raven_llm.grounded`); chi ha Ollama o una API configurata lo usa gia'. Da rifare con prompt a pochi esempi o un modello piu' grande (3B+) se serve.
**Confronto a 3B (stessa prova, 12 core, solo licenze permissive e produttori occidentali; Gemma e Llama esclusi per licenza con condizioni):** Granite 4.0-h micro 88 %, 22 s, 2,4-2,8 GB;
Ministral 3 3B (Apache-2.0) 91 %, 13 s, 2,6-3,1 GB; Phi-4-mini (MIT) 85 %, 13 s, 2,6-2,9 GB; SmolLM3 3B (Apache-2.0) 82 % e una risposta non JSON, 12 s, 2,7-3,0 GB.
La differenza di accuratezza e' piccola (12 prompt, 34 campi: un campo vale 3 punti), quella di latenza no. **Regola dell'utente:** Granite 3B come predefinito solo se nessun altro modello va meglio; Ministral va
meglio (accuratezza e tempo, RAM simile), quindi **predefinito: Ministral 3 3B Instruct 2512 Q4_K_M** (Apache-2.0, Mistral AI, Francia; file 2,15 GB, sha256
`fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`, da `unsloth/Ministral-3-3B-Instruct-2512-GGUF`); alternative: Granite 4.0-h micro 3B (sha256 `bcc78b9b…f023`), Granite 1B (0,9 GB)
per poca RAM. RAM libera minima da richiedere all'avvio: 4 GB. Da riprovare con 50 prompt. Resta valido: regole prima, il modello riempie solo i campi presenti nel testo.
**Catena chiusa (2026-11-11):** messaggio in chat -> scheda con brief da confermare ("Confirm and find sites", nessuna ricerca parte prima) -> job -> **resoconto finale** sopra la tabella
(`POST /api/raven/discover/{id}/summary`, `domain/raven/discovery/summary.py`: il motore sceglie il migliore, il modello spiega, testo accettato solo se nomina quel sito e usa solo numeri dei fatti,
altrimenti testo del motore; IT/EN) -> "Use in the planner" -> report con la sezione del verdetto. **Modello locale collegato:** `backend/assistant/local_llm.py` (llama-server su 127.0.0.1, avvio alla
prima richiesta, scarico dopo 5 min, soglia di RAM libera dal manifest, `GET /api/raven/llm/status`), `raven_llm.pick` lo usa quando non c'e' un servizio dell'utente, timeout 120 s; installer
`./install.sh --with-llm` (Ministral 3B, 2,15 GB) o `--with-llm-small` (Granite 1B, 0,9 GB, soglia 2,5 GB), sha256 e dimensione fissati, `THIRD_PARTY_NOTICES.md`. Provato davvero: installer (download
verificato), brief con modello (11,6 s), resoconto con modello (15 s), nessun processo rimasto dopo lo stop del server. Trovato e corretto: il controllo "il valore e' nel testo" accettava qualsiasi
stringa per `priority` e `mission_class` (il modello aveva inventato balanced e medium_lander): ora serve una parola del testo (`ENUM_WORDS`); le regole capiscono anche "privilegiando/favouring/preferisco".
**Punti aperti trovati:** (1) questa macchina ha 6,9 GB di RAM e circa 2,4 GB disponibili con le applicazioni aperte: il 3B (2,6-3,1 GB) non parte (il controllo lo rifiuta e il testo del motore resta),
serve `--with-llm-small` o chiudere altro; (2) FATTO il 2026-11-12: il Q&A di RAVEN SI usa il modello locale come candidato `raven-local` (dopo i modelli dell'utente, prima dell'estrattivo; `LazyProvider` avvia il server alla prima domanda,
errore `unavailable` e ripiego sull'estrattivo se non parte; provato con domanda reale: recupero della pagina FSPL, risposta in streaming, 30 s con l'1B; la guardia ha segnalato `no_citation`: l'1B
non cita sempre il materiale); (3) 50 prompt di misura invece di 12 per confermare Ministral; (4) latenza 12-15 s con il 1B su 12 core carichi: su 4 core sara' piu' alta (la
interfaccia mostra "in scrittura"), prompt cache da misurare; (5) macOS non supportato per il modello (solo Linux, regola); (6) flake di vitest sotto carico (1 volta su 3, riga home.test).
**Report finale: ignoto e traccia NASA (2026-11-12).** Fatto: (1) le nove sovramappe come immagini nella parte 2 (`ReportOverlays.svelte`, A e B marcati, scala nell'immagine, PDF 3x3 in una pagina);
(2) intervallo delle ore utili e delle quote Sole/Terra/radio quando ci sono passi ignoti ("Confirmed X h, at most Y h"; "Between X % and Y %"); (3) grafici con ignoto: bande tratteggiate sul grafico oltre alla
striscia, grafico delle ore cumulate con fascia tra confermate e massimo possibile (`usefulBounds`); (4) BUG trovato: il motore PDF NON disegna i `pattern` SVG, quindi le strisce "ignoto" uscivano BIANCHE come un
"no" noto; ora il tratteggio e' fatto di linee (`hatchLines`, test `overlayChartHatch.test.ts`); (5) nuova figura "Sole e Terra rispetto all'orizzonte" (`ReportSky.svelte`: azimut/elevazione per passo, orizzonte del
terreno all'azimut di ciascun corpo, asse tagliato nel vuoto piu' grande perche' al polo il Sole attraversa il nord). Il PDF aspetta mappe e verdetto prima di abilitare il download. Perche' "0 h utili": e' il minimo
CONFERMATO; le ore `outside_model` (diffrazione sotto 30 dB, ostacoli multipli non modellati) sono ignote e non contano; vicino al polo e' frequente (es. Shackleton 168 h su 168 ignote). Limite del Learn: 9 pagine (era 8).
Confronto con la traccia: coperti scelta/confronto siti, coordinate libere, data e durata, Sole/Terra sull'orizzonte (ora anche azimut), tempo a tramonto e Earthset all'inizio della finestra, elevazione solare max/media,
durata della luce, finestre di visibilita' della Terra (come striscia e come piu' lunga continua), giorni lunari, mappe 2D, accessibilita' Learn/Expert. NON coperti nel report: (a) elenco delle finestre con inizio e fine
in UTC (ora solo strisce e durate massime); (b) vista 3D e animazione (ci sono nell'app, non nel report); (c) confronto di due date sullo stesso sito nel report non verificato qui; (d) tempo a tramonto alla data/ora di
atterraggio scelta (ora all'inizio della finestra). E2E: il test lungo del planner era instabile con mappe grandi (canvas a 720 px): con 324 px passa (31/31 due volte); causa esatta non isolata.
**Da fare in A:** terreno a 237 m fuori dal polo per la ricerca a celle.
**B. Dati e validazione:** misure di fading (cercare dati con profondita' e geometria), confronto delle sovramappe con prodotti NASA, ICE/DESNZ e MIL-HDBK-217F dalle fonti
primarie, statistiche di lancio, tabella atterraggi sui rapporti primari, coordinate primarie di Luna 25, SLIM, Odysseus, Blue Ghost e regioni Artemis.
**C. Prodotto:** lezioni e modalita' demo di Learn, dati ufficiali della sfida (se esistono), verifica del testo italiano/inglese di tutto il nuovo, THIRD_PARTY_NOTICES generato.
**D. Qualita':** giro e2e completo, causa vera del test `home` instabile, prova di installazione su macOS, accessibilita' del nuovo, bundle entro 70.000 B, CI (budget dell'utente).
**Ordine:** A0 -> A1 -> A2 -> A3 -> A4 -> A5 -> A6 (B, C, D in parallelo quando c'e' attesa o dopo ogni fase di A).

## (completata) PROSSIMA SESSIONE (richiesta dell'utente dell'11 nov, "proseguiamo dopo")
Regole di sempre: token ottimizzati, lavoro in chat senza agenti, test in background, un solo giro completo alla fine.
1. **Sovramappe sul globo 3D** (oggi solo sulla mappa polare): quota, pendenza, quota di Sole e di Terra, falsi colori, copertura.
2. **Validazione assoluta della radio**: cresta arrotondata, multipath, energia; confronto con fonti e misure pubbliche, stato di ogni
   stadio nella pagina Modello.
3. **Parametri mancanti di Fresnel** (zona di Fresnel, raggio al crinale, lunghezza d'onda, valori ancora ignoti o illustrativi) stimati
   dal motore interno con intervallo, fonte e tag.
4. **Stima approssimata della CO2e di produzione** (oggi ignota nel report), **affidabilità** (per classe di componente, probabilità di
   trasferimento) e le altre quantità oggi "ignote" o "senza fonte": tutte stimate dal motore RAVEN interno, con intervallo, ipotesi,
   fonte e tag, mai presentate come preventivo o LCA; il testo resta compito dell'assistente RAVEN SI. Fonti da leggere prima di
   produrre numeri (ICE/DESNZ per i materiali, MIL-HDBK-217F, statistiche di lancio e atterraggio primarie).

### Esito (12 nov): punti 1–4 e dashboard rifatta
- 1 fatto: sovramappe sul globo 3D, ora **sulla Luna 3D della pagina Siti** (`Viewer.svelte`, shader `threeViewport.ts`, prop `overlay`), con lo
  stesso pannello (`shell/overlay/OverlayPanel.svelte`, `overlayController.svelte.ts`) usato in `/siti` (a destra del globo) e nella dashboard.
- Dashboard ripensata come sala di controllo del piano del Mission Planner: testo di scopo, striscia con numeri A/B e conti alla rovescia,
  navigatore a tutta larghezza (stage >= 74 % dell'altezza dello schermo, legenda e sovramappe a lato), grafici sotto, sessioni in un
  riquadro richiudibile. Il 3D del navigatore segue sito e istante dello scenario (store dello scenario).
- 2 parziale, per mancanza di dati: il report JPL IPN 42-243 non pubblica valori di fading (solo "oltre 20 dB in alcuni casi" e grafici).
  Confronto d'ordine di grandezza in `test_multipath.py`: il modello raggiunge -21,5 dB su terreno liscio e circa -10 dB con rugosita' 0,25 m
  (profondita' dipendente dalla rugosita' ignota). `s5.multipath` resta `not_validated` (guardia in `test_validation.py`).
- 3 fatto nei limiti delle fonti: `GET /api/raven/report/fresnel-estimate` (permittivita' 2,2–3,8, perdita <= 0,019, tag I; fonti NTRS
  19780005009 e Carrier 1991 da snippet, non lette); rugosita' e raggio al crinale restano ignoti. Mostrate in Model > "Engine estimates".
- 4 fatto nei limiti delle fonti: `GET /api/raven/report/landing-estimate` (13 tentativi 2019–2025; **verificata il 12 nov su pagine
  secondarie**: SLIM e IM-2 Athena sono "ambigui" (atterrati ma ribaltati), non successo/fallimento; Luna 25 e Chang'e 6 non confermati dalla
  ricerca; risultato 5 riusciti, 3 ambigui, 5 falliti, intervallo 18–82 %). Fattore dell'alluminio per la CO2e di produzione **non confermato**
  sulle tabelle ICE (una verifica ha trovato solo 2,176 kg/kg di un'altra voce): scritto tra i limiti. Tassi di guasto per classe
  (MIL-HDBK-217F) e statistiche di lancio: ignoti, nessuna fonte letta (mostrati come "Unknown").
- Roadmap: pagina rimossa da decisione precedente; non e' piu' un compito. Restano: valori di fading misurati, ICE/DESNZ e MIL-HDBK-217F
  dalle fonti primarie, N scenari nel planner (non pianificato), codice HTTP dell'errore a 365 giorni e budget GitHub Actions (utente).

### Terreno dei siti fuori dal prodotto a 20 m (12 nov, sera)
- Il Viewer 3D diceva "fuori copertura DEM" per i 41 siti a nord di -85 gradi perche' `views.snapshot` li escludeva. Ora li legge come siti
  utente: terreno globale a 237 m se le tessere sono in cache, `needs_download` se mancano, `unknown` se l'orizzonte non e' ancora calcolato
  (mai calcolato nello snapshot: `MaskStore.get(compute=False)`). Le tessere dei 51 siti pesano circa 250 MB.
- `install.sh`: nuovo passo opzionale "terrain of ALL catalogue sites" (`python -m backend.domain.raven.prefetch_global`): scarica le tessere
  e calcola le maschere d'orizzonte. Tetto cache portato da 200 a 300 MB.
- Piani di terreno spediti in `backend/assets/terrain_plans.json` (`scripts/build_terrain_plans.py`, test di uguaglianza): il primo snapshot
  passa da 15 a 2,5 s. Il pannello delle sovramappe sta sotto la scena (slot `below` del Viewer), non accanto: a lato il Viewer scendeva sotto
  833 px e nascondeva l'elenco dei luoghi.

### Installer in parallelo e dati obbligatori (12 nov, notte)
- `install.sh` ora ha 4 passi. Passo 2: frontend (Node, `npm ci`, build) e plugin C partono subito in background; in primo piano uv,
  Python, numpy+scipy; appena ci sono, partono in background i dati (kernel NAIF, tile LOLA dei siti predefiniti, terreno di tutti i 51
  siti con 24 richieste alla volta, maschere d'orizzonte su tutti i core) mentre si installa il resto dei pacchetti. Poi attende tutto.
  Una sola domanda iniziale (salvo `--yes` o tutto gia' installato); i dati sono obbligatori (`--skip-data` e' l'unica uscita); un
  download fallito ferma l'installer con il comando da rilanciare, tenendo i file gia' scaricati. Stamp scritti con un lock (`mkdir`).
- Bug trovato dalla prova da zero: `_opener()` di `dem.py` non aveva `HTTPDefaultErrorHandler`, quindi uno stato HTTP di errore (server
  che limita le richieste) faceva restituire `None` a `opener.open` e il download andava in `TypeError`; ora e' un `HTTPError` con
  retry (test `test_dem_opener.py`).
- Prova da zero: copia pulita del progetto, `PATH=/usr/bin:/bin`, nessun `.tools`, `.venv`, `build`, `node_modules`
  (`run_clean.sh` nella cartella tmp del job). Tempi misurati il 12 nov: da zero con Node e Python gia' nel PATH 319 s; su PATH senza node, npm, python e uv (scarica uv, CPython 3.14 e Node 22 da solo) 432 s. Collo di bottiglia trovato e tolto: `enforce_limit` dopo ogni tessera elencava la cartella (quadratico su 2862 tessere) e la memoria teneva tutte le tessere; il download di massa ora applica il tetto una volta sola.

### Sovramappe su tutta la Luna 3D (12 nov, notte)
- Prima le sovramappe coprivano solo il disco polare sud (da -75 gradi). Ora la Luna 3D (pagina Siti e dashboard) le mostra su **tutta la
  superficie**: rasters equirettangolari 720 x 360 (celle di 0,5 gradi, circa 15 km) in `backend/assets/overlays/global-*.json`
  (`scripts/build_overlays_global.py`, modulo `backend/domain/raven/overlays_global.py`, `GET /api/raven/overlay?scope=global`).
- Fonte: LOLA LDEM globale a 237 m letta **a un punto per cella** con richieste HTTP range (259.200 punti in circa 2.000 richieste, niente
  tessere): quota (da -8,6 a +10,2 km) e pendenza regionale; copertura per prodotto (20 m / 240 m / globale); frazione del 2027 con Sole e
  con Terra sopra l'orizzonte (orizzonti su 30 celle, 24 azimut; DE440 ogni 6 h). Controllo: Sole circa 50 % ovunque, Terra circa 97 % sul lato
  vicino e 2-6 % sul lato nascosto (librazione). Limiti dichiarati nella legenda: celle da 15 km (rilievo piu' piccolo invisibile, la luce dei
  terreni scabri e' sovrastimata), non validata contro i prodotti di illuminazione NASA; il disco polare (celle da 2 km) resta piu' preciso
  vicino al polo sud e si usa nella mappa polare.
- Shader: la sovramappa e' un dato e non luce: resta leggibile sul lato notturno (minimo 55 % di luminosita') e mantiene l'ombreggiatura del
  rilievo. Il test dell'elenco dei marcatori ha trovato un difetto: senza istantanea un sito a nord di -85 gradi risultava "fuori copertura DEM";
  ora e' "in calcolo" finche' il servizio non risponde.
- `home.test.ts` instabile sotto carico: attesa del chunk pigro portata a 15 s.

### Ricerca automatica dei siti: piano (12 nov, notte)
- Piano scritto in `docs/design/site-discovery-plan.md` (nessun codice): brief da prompt o modulo, candidati dalle sovramappe, surrogato con
  campionamento attivo sul core, probabilita' con propagazione degli intervalli di tag I, nuvola di idoneita' + K siti, agenti LLM a lista bianca,
  6 fasi testabili. In attesa delle 6 decisioni elencate al punto 8 del documento.
- Fatto prima del piano: tabella degli atterraggi verificata missione per missione (campo `checked`; Luna 25 e Chang'e 6 confermati) e stime del
  motore (permittivita', atterraggio) anche nel report e nel PDF. Trovata e corretta una regressione della dashboard: il riquadro delle sessioni
  chiuso nascondeva i comandi (2 test di `mission-planner.spec.ts` rossi, ora verdi).

## Esito del secondo giro dell'11 nov (telemetria, sovramappe, installer)
- **Telemetria:** i 3 test e2e riscritti sul contesto opt-in dell'assistente (impostazioni, "Includi i parametri tecnici visibili", etichetta
  "Riduci RAVEN SI"): 5/5.
- **Sovramappe:** aggiunte quota di Sole e di Terra (quota del 2027 con il corpo sopra l'orizzonte regionale, ~2,4 km per cella,
  orizzonti da 24 azimut su 30 celle, direzioni da DE440 ogni 6 h con librazione) e il composito a falsi colori (rosso Sole, verde Terra,
  blu pendenza). Calcolate offline da `scripts/build_overlays.py` e spedite in `backend/assets/overlays/`; valide solo per la calotta
  entro circa 77,3 S (la corona esterna e le celle illeggibili sono "nessun dato"). **Non validate** contro i prodotti di illuminazione
  NASA: confronto qualitativo con il motore (Haworth, Shackleton, de Gerlache bui in entrambi; Malapert molto illuminato dalla
  sovramappa, mentre il motore conta 34 % perché molti passi sono ignoti). Aperte: sovramappe sul globo 3D, validazione.
- **install.sh:** il passo 7 era lento perché scaricava le tessere una alla volta (e dopo l'aggiunta dei siti scaricava anche le tessere
  dei nuovi siti polari). Ora: download in parallelo (12 tessere, 4 kernel), prefetch predefinito limitato ai 6 siti polari
  originali (gli altri scaricano le loro tessere al primo uso, con consenso, oppure con `--all-sites`), barra di avanzamento per i
  download, barra generale dei passi e battito ("... 1m23s") per i passi lunghi senza output. Test: `test_prefetch.py`.

## DA FARE quando l'utente dice "continua il lavoro" (lista dell'11 nov, in quest'ordine)
Regole: **ottimizzare i token il più possibile** (risposte brevi, nessun polling, leggere solo i file necessari, un solo giro di
test completi alla fine, test in background), lavoro fatto in chat, nessun agente, test in background mentre si continua; commit piccoli e push su
`hackathon/nasa-lunar`; la CI di GitHub non parte (budget Actions) quindi contano i test locali.
1. **Web Worker e blocco della pagina**: il rendering dei risultati blocca il thread principale per circa 1,4 s e
   `long-period.spec.ts` può risultare rosso a 2 s; spostare il calcolo pesante in un Web Worker e mostrare una barra di avanzamento.
2. **Traduzione delle etichette** dentro il disegno della sezione laterale usato nel PDF in inglese ("scala verticale",
   "fascio HPBW", "antenna 2,0 m", "quota (m)", "Calcolo della scena…" in `pages/lander/canvasLander.ts`): il report è solo in inglese.
3. **1 e2e fallito su 59 da sistemare** (non identificato con certezza dopo l'ultima correzione) e **verifica completa di backend e
   frontend** in una sola esecuzione sull'ultimo codice: pytest intero, ruff, mypy, lint-imports, vitest, svelte-check, e2e intera.
4. **Più di due siti insieme** (confronto di N scenari in planner e report) e **scena 3D e orizzonte anche per i siti fuori dal
   prodotto a 20 m** (terreno globale a 237 m, dopo il consenso al download).
5. **Dashboard come mission control** (il compito più importante e completo):
   - La sezione Dashboard mantiene il **gestore di file** che salva le sessioni del Mission Planner.
   - L'interfaccia principale diventa una **dashboard interattiva in tempo reale stile mission control**: ogni grafico e ogni
     statistica nel proprio riquadro, aggiornati con i dati delle sessioni/risultati.
   - **Al centro** il vero e proprio **Lunar Landing Sites Navigator**: la scena 3D dei siti oppure la simulazione del rover, con
     un interruttore tra le due.
   - Sul navigator vanno aggiunte **sovramappe sulla Luna** per mostrare ciò che oggi è ignoto: da progettare. Proposta di partenza:
     copertura del terreno per sito (20 m / 237 m / assente), stato ignoto per fase (luce, terreno, radio, DSN) con tratteggio e
     legenda, visibilità della Terra, ore utili per sito come colore del marcatore, regione senza dati; ogni sovramappa con la
     fonte e lo stato (noto / stimato / ignoto) e accendibile da un pannello.
   - Precisazione dell'utente: le sovramappe possono essere **heat map con colori diversi, come nel remote sensing per i dati SAR
     elaborati**. Livelli: quota e pendenza LOLA; frazione di tempo con Sole sopra l'orizzonte e con Terra visibile (maschere
     d'orizzonte del motore, precalcolate su una griglia grossolana della regione polare per una finestra di date); copertura dei dati
     (20 m / 237 m / assente) come mappa a classi; valore per sito come colore del marcatore (mai interpolato tra siti); composizione a
     falsi colori (rosso = Sole, verde = Terra, blu = pendenza). Regole: celle senza dato trasparenti o tratteggiate con voce di legenda,
     mai colorate come zero; niente interpolazione tra i siti; fonte e stato (misurato / derivato / stimato) per ogni livello; scale
     sequenziale (quantità), divergente (differenza A-B) e categorica (classi), non basate solo sul colore; trasparenza regolabile.
   - Riferimenti grafici dell'utente (solo per capire il tipo di interfaccia, "ai slop"): immagine di una sala di controllo con più
     schermi (ftcdn 19/84/31/11), un'altra sala di controllo (futurecdn 265SWqz…), una HUD di telemetria futuristica con radar circolare
     centrale, pannelli dati laterali, grafici e bussola su fondo scuro con griglia ciano (magnific 85267-10286).
   - Vincoli di sempre: solo inglese e italiano, solo Linux, ignoto resta ignoto, accessibilità (bersagli di tocco, axe), bundle entro
     il budget.

## Decisione del 10 nov (sera): sezione Sostenibilità e costi
Il report ha la parte 3 "Sustainability and cost" calcolata dal core (`backend/domain/raven/economics.py`,
`GET /api/raven/report/estimate`); il Dossier non ha più i gruppi economia, CO2e e piano (stime solo dall'engine).
L'utente accetta che Learn sia di 5 pagine (il limite di 4 non vale più). Aperti: codice HTTP dell'errore a 365 giorni
(il messaggio ora mostra lo stato), blocco di ~1,4 s del thread principale (`long-period.spec.ts` rosso a 2 s), CI.

## Stato (12 nov): feedback sul report scaricato, punti 1-5 (parte legale, rischi, stime automatiche, grafici, verifica visiva)
- **Parte legale rimossa** (sezione, i campi `jurisdiction`/`authority`, `LEGAL_ITEMS`, chiave `legal` del JSON, voce dell'indice e
  dell'ESG, casella delle sezioni, chiavi dei cataloghi). Restano UNA frase di limiti in parte 4 (`disclaimer`) e la voce di costo
  "assicurazione e regolatori". Le bozze salvate con chiavi legali si caricano (chiavi ignorate): test in `reportMode.test.ts`.
- **Rischi:** `estimates/risks.ts` produce al massimo 5 righe unite fra A e B (lontano terreno, ore fuori dal modello, sopravvivenza/buio,
  blackout, terreno definito dall'utente), ordinate per gravita' (alta da 25 % della finestra), in parole semplici con conseguenza e
  prossima azione. Nessuna sezione a parte: Learn = 3 punti in parte 1, Expert = una tabella compatta in parte 1. Spariti i 29 righe,
  le righe di stato per stadio, i percorsi interni e il blocco "Inputs used" (restano nel JSON). Le stime `risk_register` e
  `contingencies` non esistono piu'; le bozze salvate le scartano.
- **Stime automatiche e cursore di classe** (`estimates/missionClass.ts`, `totals.ts`, `MissionClassSlider.svelte`): 4 posizioni
  nominate (default lander commerciale piccolo), tastiera nativa (input range). Producono fascia del costo totale e durata di sviluppo
  (solo classi con fonte: costo lander piccolo 47-118 M USD, medio 199,5 M USD (un solo valore), grande 2,89-3,4 mld USD (fonte
  secondaria, un'altra riporta 7 mld non risolto); sviluppo piccolo 3,9-4,7 anni, medio almeno 6,5), massa al lancio e classe di
  lancio, CO2 del lancio = propellante bruciato x fattore di combustione (Falcon 9: RP-1 155,8 t da capacita' dei serbatoi; Falcon
  Heavy 402,8 t; New Glenn: metano da volume 710 m3 x 0,40-0,43 t/m3 (densita' NON letta da fonte, tag I); stechiometria
  44,01/12,011 e 44,01/16,04; quota bruciata 0,85-1 e frazione di carbonio 0,85-0,87 tag I; solo CO2 di combustione = limite
  inferiore della CO2e), statistiche di lancio (Falcon 9 698/701, Block 5 644/645, New Glenn 2/3) e di atterraggio (8 tentativi
  2023-2025: 3 pieni, 2 parziali). Le stime compaiono AUTOMATICAMENTE nel report (non scartate = incluse; il valore dell'utente
  prevale; nel Dossier si puo' scartare ogni stima). Totali su due righe "Declared by you" / "Including RAVEN estimates (range)"
  in parte 1 (Learn ed Expert). La stima della massa con le densita' dichiarate (tag I) ora e' automatica (casella per spegnerla).
  **Non fatto perche' senza fonte letta:** CO2e di produzione (nessun fattore dei materiali DESNZ/ICE letto: la ricerca web non ha
  restituito la tabella; il foglio gov.uk non e' stato aperto), affidabilita' per classe di componente, probabilita' di trasferimento,
  costo di rover e per voce, Vulcan (massa di propellente non cercata). Stanno nella checklist unica "Owner only, or no public
  source (5)" in parte 4. Fonti secondarie (Wikipedia): non verificate sui primari.
- **Grafici:** audit in `docs/design/design-system.md` (sezione "Audit dei grafici"). Aggiunto un grafico (ore utili cumulate + striscia
  utile/non utile/ignoto); asse x ora in giorni dall'inizio di ciascun periodo. Non aggiunti: finestre DSN a parte, bande impilate.
- **Appendici:** l'appendice delle stime accettate e la sezione E (costi/ESG) sono ora un'unica appendice D "Cost, schedule and
  sustainability" (cost, devtime, vehicle, launch CO2, statistics, massa, potenza); tolte dal documento (restano nel Dossier e nel
  JSON) matrice dei requisiti, piano di verifica, AIT, calendario, tabella di potenza (percorsi interni); tolte le righe "Not provided:"
  per fase; le stime nel report sono "compact" (metodo, fonte, ipotesi, limiti in un paragrafo, senza percorsi interni).
- **Verifica visiva (PDF reali Malapert-Haworth 7 d, 60 min):** Learn 4 pagine (era 6), Expert 13 (era 16/32). Guardate tutte e 4 le
  pagine Learn e le pagine 1, 2, 3 (grafici), 10, 11, 12 dell'Expert; corretti: chip accanto al valore (pagina 1 ora contiene tutta la
  parte 1), nota dei totali, "Proposed" nel report, dump degli ingressi, massa A = B mostrata una volta. Resta: pagina 10 dell'Expert
  a meta' vuota (l'intestazione dell'appendice C precede schede alte); il PDF Learn/Expert non e' stato guardato in scala di grigi.

## Stato (10 nov, sera): esito dei punti aperti del report
- **E2E in CI (34345c4):** causa dei test `/chat` e `/sims#explain` su tutti i dispositivi touch: `Chat.svelte` fissava le caselle a
  1rem e sovrascriveva la regola globale a 44 px del puntatore grossolano (difetto del prodotto, corretto; la matrice dispositivi e'
  la guardia). `basepath` e `contacts`/`keyboard` erano test vecchi: il footer non ha piu' "Roadmap" e Explore non porta piu' a
  Laboratorio (decisione gia' presa, v. `journey.spec.ts`); aggiornati, non indeboliti.
- **Report Learn a 4 pagine:** le formule principali (frazione utile, passo utile, quote Sole/Terra/RF, batteria, perdita in spazio
  libero, margine di link) in versione compatta (`FormulaDef.learn`); l'insieme completo resta in Expert. PDF Malapert-Haworth
  7 giorni, 60 min: Learn 6 -> 4 pagine, Expert 9 (invariato).
- **Termini di diffrazione:** `/api/raven/evaluate` restituisce per passo `diffraction_nu`, `knife_edge_loss_db`,
  `ridge_correction_db`, `diffraction_loss_db`, `multipath_gain_db` (None = ignoto, mai zero); la tabella del report li mostra.
- **135 h contro 140 h (Malapert 2027-04-07, 7 d, 60 min): non e' una regressione.** I default del motore (carichi, riserva, duty
  delle comunicazioni, capacita') sono identici dal 5 nov (verificato eseguendo il motore ai commit 4ccd2c9 e 399d4b2: 140 h).
  135 h (80,36 %) = stessa corsa con il **carico termico continuo di 2 W del profilo di affidabilita' illustrativo**
  (`thermal_load_w`, applicato a carico attivo e di sopravvivenza: 52 W e 12 W invece di 50 W e 10 W; verificato: 135 h). Il report
  ora elenca le ipotesi di carico (carico attivo, sopravvivenza, comunicazioni medie, batteria e riserva) nella parte 4 e,
  quando c'e', dichiara il carico termico aggiunto.

- **Debito tecnico (10 nov):** (a) k del compensatore: era gia' in `rf_overrides` nel percorso del viaggio; ora anche in
  `missionEvaluateIn`/`evaluateRequests` (`Radio.k`), test backend che k=0 e k=6 cambiano il rate scelto. (b)(e) gia' fatti
  prima: telemetria su `evaluate`, `noLegacyCalls` senza eccezioni, `/api/lunar|grazing|sky` rispondono 410 (README corretto).
  (c) eliminati `Planner.svelte` (irraggiungibile, solo un test lo importava) e i moduli usati solo da esso. (d) il default del
  registro `lunar.days` era 29,53 d (4252 passi a 10 min): ora 7 d (1008 passi, tag I), golden dei default aggiornati.
  (f) `s5.browser_mirror`: "verificato entro 0,01 dB contro il motore Python su 32 casi" (+61 punti del bordo a lama a 1e-6 dB),
  conteggi bloccati da `linkModel.test.ts`. (g) tutti i 24 test di `mission-planner.spec.ts` passano (alcuni a volte vanno in
  timeout se due worker caricano la macchina; da soli passano).
- **Periodo lungo (365 giorni):** la UI bloccava gia' con messaggio i passi sopra 1500 campioni; il tempo andava nel
  raffinamento dei bordi delle finestre (400 valutazioni a istante, ~5 s su 6,5 s). Ora: budget di 200 istanti per richiesta
  (bordi oltre il budget restano al passo e `*_resolved` falso, dichiarato in `windows_rule`), predicati lit/link separati
  (365 d: 6,5 -> 3,3 s) e passo compatibile scelto e spiegato dalla UI (`compatibleStep`; 365 d -> 360 min). Prova:
  `long-period.spec.ts` (< 20 s, nessun blocco del thread principale > 2 s; misurato un blocco di circa 1,4 s al rendering
  del risultato, non eliminato: resta aperto spostare il rendering pesante fuori dal thread principale). Non c'e' un indicatore
  di avanzamento percentuale (il motore e' una sola richiesta); resta il pulsante Annulla.
- **Aperto:** PDF Expert 9 pagine (non toccato); i termini di diffrazione compaiono nel report solo con motore aggiornato.

## Stato (10 nov)
**Report riscritto attorno al confronto A vs B, solo in inglese (10 nov).** Decisione utente: il REPORT (anteprima, stampa, PDF,
testi del JSON) e' solo in inglese qualunque sia la lingua del sito; il sito resta en+it. I testi stanno in
`reportText.ts` (fuori dai cataloghi, la parita' en/it non li vede); `reportLocalize.ts` eliminato; PDF con lang en e piede
"Page X of Y"; le proposte SI del report si chiedono con lang en. Struttura: 1 verdetto (frase unica deterministica con i numeri,
schede A|B con barre noto-si/noto-no/ignoto, max 3 punti, legenda una volta), 2 quattro grafici sovrapposti con striscia
noto/ignoto, 3 "How it was computed" (registro unico `reportFormulas.ts`: formule con variabili nominate, legenda con tag V/D/I
e stato di validazione, valori della run nelle ultime colonne), 4 limiti e validazione. Learn = parti 1-4; Expert = parti 1-4 +
appendici A-F presenti solo se hanno contenuto, indice breve con numeri di pagina. Passo Report: un pulsante Download PDF, menu
"More" (stampa, JSON, modifica dossier), interruttore Learn|Expert, "Customise sections" solo in Expert, riga "The report is
generated in English"; il campo decisione sta nel Dossier. Test: `reportLint.test.ts` (anti-slop e solo inglese),
`reportFormulas.test.ts` (ogni variabile definita e legata ai campi dell'engine), `reportCompare.test.ts`. Limite noto: il PDF
Learn Malapert-Haworth 7 giorni e' di 6 pagine (obiettivo 3-4: la parte 3 occupa circa 3 pagine); lo stato di validazione di
una formula e' il piu' debole fra gli stadi coinvolti.

## Stato (9 nov)
**Rifinitura grafica del PDF del report (9 nov, notte).** Fatto: copertina (scenari A/B, periodo, ora del calcolo, modello e
impronta, avviso), indice con puntini, sintesi esecutiva per scenario (ore utili, Sole/Terra/RF noti, batteria minima,
affidabilita' non validata) con chip stato colore+icona+parola, fasce di fase 0-F e tinte per tipo, tabelle con intestazione
ripetuta, grafici A/B affiancati senza grid (render del report reale 27 pagine circa 7-9 s), grafici SVG non piu' neri (stile
calcolato copiato negli attributi), titoli h1-h4 reali, test di contrasto sulla palette. Limiti: anelli in scala di grigi
leggibili solo dalla legenda; PDF/UA non validato; stampa del browser piu' lunga (limiti e2e 20 pagine, sintetico 4).

**Passaggio Affidabilita' dedicato e rifinitura del report (9 nov, sera).**
Il Mission Planner ha nove passaggi: Missione, Siti, Periodo, Energia, **Affidabilita'** (`mp_step=reliability`), Comunicazioni,
Simulazione, Dossier, Report. Ingressi, grafici A/B, margini termici/radiativi e statistiche dell'affidabilita' stanno solo
li' (i risultati appaiono dopo il calcolo del confronto); Energia, Simulazione e Dossier hanno solo un pulsante
"Apri affidabilita'". Sezione del report invariata. Stampa: `@page` con margine 0 (nessuna testatina/pie' di pagina del
browser), riempimento 10/10/15 mm ripetuto a ogni pagina. Formati: segno meno e intervalli ("da -5,3 a -1,5 °"), un solo
formato data UTC `YYYY-MM-DD HH:mm UTC`, 8,425 GHz, "3 Mbit/s". Limiti del motore e fonte "illustrative" tradotti dal
catalogo (sconosciuti invariati). Compattazione: una tabella degli elaborati mancanti per fase, parametri del server una
volta sola (righe diverse per scenario), una serie/tabella "A = B" se i numeri coincidono, frasi al posto di grafici a 0
costante, ore note/ignote affiancate con la differenza fra RF ignota e stato missione ignoto, certificato DEMO e nota
carta/CO2e in Appendice finale. Nessuna modifica di fisica o motore. Passaggio Learn (`mp_step` dei collegamenti) invariato:
il quiz non ha una lezione sull'affidabilita'.

**Confronti grafici reliability e statistiche generali della missione.**
Verificata una lacuna: i sei grafici precedenti erano tre curve duplicate
per scenario, senza grafici termici/radiativi. Ora dieci grafici comparativi:
tre curve A/B sovrapposte su ore dall'atterraggio, piu' barre per catena
cumulativa, guasti, durata media del recupero, degrado per componente,
margine termico firmato, dose rispetto alla propria tolleranza TID e ore
disponibili/non disponibili/utili. Scale comuni, A continua e B tratteggiata,
valori esatti, zeri distinti dagli ignoti; nessun ponte sulle lacune.
Ipotesi condivise esplicite: curve coincidenti non validano ambienti uguali.
Nessuna storia termica o nuova probabilita' dedotta dall'ambiente.

Audit generale: le curve esistenti di Sole/Terra, potenza, carica, margine RF
e bitrate restano. Aggiunti due anelli per la partizione effettiva del tempo
campionato S7, utile/noto non utile/ignoto, e un confronto energetico A/B
in Wh. Barre per costi dichiarati e CO2e delle fasi in Dossier e report,
solo quando esistono stime, anche parziali ma mai normalizzate in un totale
completo. Nessuna torta per probabilita' sovrapposte o per costi/CO2 ignoti.
Totali nulli/incoerenti non disegnano proporzioni al 100%.
Spunte esistenti Grafici/Economia/Sostenibilita' rispettate, nessuno schema
JSON o calcolo fisico modificato.

Verifiche: 63 test frontend, Svelte 0 errori/0 warning, bundle root/app
68.139/68.147 B. 26 E2E del Planner e reliability tutti superati, inclusi
mobile, axe, salvataggi, grafici EN/IT, selezioni e digest del report.
PDF verificati senza testo fuori margine, pagine vuote o URL del browser:
15/14 pagine completi root IT/app EN con statistiche generali e costi/CO2;
20/19 con lo studio reliability nei rispettivi esempi; sintetici 2/2.
Grafici reali ispezionati; corretto il testo centrale degli anelli per
ereditare il colore leggibile della carta bianca anziche' il token scuro.

**Affidabilita', degradazione e protezione della missione.**
Studio opzionale `raven-reliability-1` nel RAVEN engine, endpoint rigoroso
`POST /api/raven/report/reliability`, input EN/IT nelle schede Energia e Dossier.
Cinque sottosistemi critici in serie: alimentazione, batteria, radio/antenna,
avionica e controllo termico. Catena lancio-trasferimento-atterraggio-superficie,
shock e perdite prestazionali distinti, hazard permanente e upset recuperabile,
probabilita' di recupero, durata media, ore disponibili/non disponibili e utili
attese. Integrali analitici, finestre ignote come limiti, tre grafici per scenario.
Il superamento della soglia di prestazione interrompe l'operativita'
condizionata, non la sopravvivenza fisica; coperto anche il caso di componente
gia' sotto soglia all'inizio della superficie.

Temperature protette del componente/giunzione confrontate con i limiti
dichiarati; TID lineare schermata in krad(Si), margini e avvisi espliciti.
Indicazioni progettuali per isolamento/MLI, schermi, radiatori, riscaldatori,
regolazione, ECC/watchdog e componenti radiation-tolerant. Il carico termico
incrementale si applica ai due carichi energetici reali solo con consenso
esplicito e invalida la simulazione fisica. Cambiare solo i tassi di guasto
ricalcola lo studio statistico senza rifare S0-S7.

Nessun tasso precompilato per default: dati ignoti, fonte/ipotesi obbligatoria,
preset sintetico solo su azione utente. Non e' una qualifica hardware, FMECA,
simulazione di volo, calcolo dei flussi termici o trasporto delle particelle.
Non dimensiona schermi e non deduce probabilita' da margini negativi; i numeri
operativi sono condizionati all'inviluppo ambientale. Degrado aggregato,
non ricalcolo dinamico di capacita' batteria, efficienza solare e guadagno RF.
Limiti e fonti di metodo NIST/NASA espliciti nel report e nella documentazione.

Sezione selezionabile con tabelle, grafici e input completi; JSON schema 4
esteso in modo additivo e digest DEMO comprensivo dei risultati. Migrazione
dei piani e delle precedenti venti spunte, salvataggi e richieste obsolete
gestiti; errori/riprova visibili e nessun report mentre il calcolo e' pendente.
RAVEN SI mantiene limite del contesto e whitelist tecnica cloud esistenti.

Verifiche: 60 test backend, 52 frontend, Svelte 0 errori/0 warning, Ruff,
formato, mypy e otto contratti import-linter. 26 E2E Chromium del Planner,
inclusi affidabilita' reale, carichi 12/52 W con esempio termico da 2 W,
avvisi ambientali, dati mancanti, errore/riprova, digest, persistenza,
mobile e axe. Sei PDF root IT e /app/ EN: 13/2 pagine completo/sintetico
precedenti; 17 pagine con lo studio completo. Contatori, dati pronti,
nessun URL del browser, pagina bianca o testo fuori margine; rendering
ispezionati. Bundle iniziale 68.139/68.147 B, sotto 70.000 B.
Entrambe le demo locali aggiornate e backend di questa sessione riavviati,
proxy intatto; ulteriori tre E2E sui servizi pubblicati tutti superati.

**Nuova impaginazione editoriale del report.**
Anteprima su carta bianca e PDF A4 con masthead, nome missione e metadati
ordinati, palette petrolio/grigio, gerarchie tipografiche, tabelle con righe
alternate e riquadri distinti per avvisi e promemoria ambientale. Timbro
conclusivo affiancato alla provenienza, nessun logo nei footer. Contenuti,
calcoli, selezione sezioni e schema JSON invariati.

Testatine CSS RAVEN / MISSION PLANNER e footer testuale con numero pagina:
nei quattro PDF Chromium verificati anche con intestazioni automatiche
abilitate non compaiono URL localhost, indirizzo della pagina o data del browser.
Nota EN/IT per disattivare "Intestazioni e pie' di pagina" nei browser che
continuano ad aggiungerli: non si dichiara controllo universale del dialogo
di stampa. La data del calcolo resta fra i metadati utili della missione.

Corretto un problema emerso verificando i PDF reali: il ResizeObserver durante
la stampa poteva ricalcolare le pagine e invalidare temporaneamente budget,
CO2e e certificato. La misura resta congelata in media print e riprende a
schermo; test unitario dedicato e E2E confrontano i valori prima/dopo il PDF.
Verifiche: 30 test frontend, Svelte 0 errori/0 warning, bundle root/app
68.139/68.147 B. Percorso E2E completo root IT e /app/ EN con quattro PDF:
13 pagine completi e 2 sintetici, tutti i contenuti pronti, testatine e contatori,
nessuna pagina bianca o testo fuori margine; controllati anche i rendering.
Build isolate e porte temporanee, nessun processo preesistente fermato.
Entrambe le demo locali aggiornate con gli stessi asset verificati.

**RAVEN SI, chat persistente e generazione online facoltativa.**
Branding pubblico: RAVEN prodotto, RAVEN engine motore di calcolo, RAVEN SI
marchio ombrello per Learning Assistant, assistente web general-purpose e
assistenza alla compilazione dei report del Mission Planner. Non significa
navigazione o ricerca autonoma su Internet: questi strumenti non sono implementati.
Identificativi `raven-core-*`, API e compatibilita' dei report salvati preservati.

Pulsante RAVEN SI sempre accessibile in basso a destra, chat moderna adattiva
e stessa conversazione su /chat e nel pannello. Storico solo in memoria fra
minimizzazione e navigazione SPA, mai nello storage del browser; reload e nuova
conversazione lo cancellano. Streaming, interruzione, copia, fonti con pannello
annidato, scorciatoie, focus, scrim e stampa verificati. Parametri aggiuntivi
facoltativi con anteprima dei soli valori trasmessi. Controlli e messaggi EN/IT.

Groq predisposto con flag server disabilitato di default, chiave esclusivamente
nell'ambiente server e consenso esplicito distinto per chat e dossier.
Cambiare modalita' cancella lo storico prima di condividerlo. La chat remota
recupera solo la guida pubblica approvata per ID e percorso, mai il resto della
conoscenza interna; parametri testuali esclusi. Il report remoto invia solo
campi numerici noti del modello: niente nomi, note, costi, finanziamenti o dati
legali. Proposte non revisionate con provenienza, digest e ambito dati; nessuna
sostituzione dei calcoli, autorizzazioni o qualifiche. Consenso non salvato
nella missione. Errori/quote e fallback locale sono dichiarati.

Verifiche: 199 test backend assistente/report, 124 frontend mirati inclusa
parita' dei cataloghi, Svelte 0 errori/0 warning, Ruff/formato, mypy e otto
contratti import-linter. 21 E2E Chromium verificati: streaming/fonti, tastiera,
mobile e bersagli 44 px, axe chiaro/scuro, persistenza root/app, stampa/PDF,
consenso/provenienza cloud simulati e regressioni dei risultati fisici.
Bundle iniziale root/app 68.139/68.147 B, sotto 70.000 B. Entrambe le demo locali
aggiornate e rispondenti; proxy esistente non modificato.

**Limite operativo:** nessuna chiave Groq configurata e nessuna generazione
esterna reale eseguita. La demo usa risposte estrattive locali, non una SI
generativa simulata come attiva. Per attivare Groq servono account, chiave
server, flag, verifica dei controlli dati/quote e consenso utente. Test online
eseguiti solo con trasporti e risposte simulati; nessuna valutazione della
qualita' di un modello generativo reale.

**Audit dell'autocompletamento del report, campo per campo.**
Tutti i 35 elaborati delle fasi 0–F espongono nel JSON dipendenze dei dati e stato
di compilazione: dichiarazione utente, studio parziale, proposta oppure input/
evidenze esterne mancanti. Una sintesi visibile distingue campi popolati da
elaborati ingegneristici approvati: questi ultimi restano zero. Non viene
scambiato il testo generato con una verifica o con una missione qualificata.

Collegati ai dati già disponibili: soglie Sole/RF (zero incluso), finestra
campionata, batteria/carichi/energia e relativo ambito noto, configurazione
radio/pannello e baseline versione/hash del Core. I riepiloghi usano i parametri
effettivamente restituiti dal server, non una ricostruzione dalla bozza.
Massa del veicolo, hardware qualificato, disegni di volo, traiettorie e prove
eseguite non vengono inventati; il piano di verifica è una proposta esplicita.
Senza valutazioni non compaiono falsi risultati engine; un budget senza importi
noti non viene presentato come fattibilità economica calcolata.

Il report mostra ora anche subtotale/copertura dei costi, differenza dal
finanziamento, contingenza percentuale/importo e confronto aritmetico del
finanziamento. Core e formule numeriche invariati. Dati dichiarati di
operatore/giurisdizione/autorità sono tracciati nelle corrispondenti voci legali,
senza attribuire autorizzazioni. Piani E/S/G e indicatore ambientale stimato
sono collegati ai rispettivi pilastri. Il confine CO₂e resta distinto dai confini
complessivi ESG, non forniti; misure verificate e assurance restano assenti.

Corretto anche un caso di SI obsoleta: soglie/obiettivi e limiti del modello
entrano nella chiave di validità; cambiare solo le spunte continua a non
invalidarla. Il contesto SI contiene i parametri effettivi del Core.
La SI generativa locale è tuttora indisponibile (verificato stato/discovery):
funziona l'autocompletamento deterministico, non una generazione reale.
Su richiesta dell'utente valutata GroqCloud Free come opzione online; nessuna
API esterna abilitata e nessun dato di missione inviato. Servono account/chiave
server e scelta esplicita dei soli dati tecnici non riservati da inviare.
Gemini non è proposto come opzione automaticamente gratuita per il sito UE:
i termini richiedono Paid Services per API client messi a disposizione in SEE.

Verifiche: 41 test frontend mirati, 19 test API report del Core, Svelte
0 errori/0 warning, bundle root/app 68.258/68.266 B. Tre E2E Chromium:
JSON/dipendenze, nuovi valori e metadati, digest, selezione, ripristino e
regressioni buio/ignoti su root e /app/. Quattro PDF controllati direttamente:
completi IT/EN 13/13 pagine, sintetici 2/2; nessuna pagina vuota, controllo
stampato o testo fuori margine. Entrambe le demo locali aggiornate.

**Sezioni del report selezionabili e preset sintetico.**
Nel passo Report sono disponibili 20 spunte: singole fasi ECSS 0–F, elaborati
delle fasi selezionate, sintesi/decisione, grafici, finestre, configurazione,
provenienza completa, economia, ESG/CO₂e, prospetto legale, proposte SI/informativa,
bibliografia, timbro/certificato e promemoria carta. Preset «Report completo» e
«Report sintetico»; il secondo conserva la sintesi degli scenari senza appendici.
I dettagli tecnici sono indipendenti dai testi delle fasi: per esempio si possono
includere i parametri anche senza la narrazione della fase C.

Le spunte controllano anteprima e PDF, non ricalcolano la fisica e non cancellano
i risultati. Persistono nel dossier/sessione e nella libreria; vecchie bozze
senza selezione aprono il report completo, selezioni danneggiate sono rifiutate.
Il JSON resta esplicitamente un archivio completo di calcolo e dossier:
`lifecycle.presentation` registra spunte, sezioni omesse e questa distinzione,
con estensione additiva dello schema 4. Non è un sistema di redazione/oscuramento
di fatti eventualmente ripetuti in sezioni mantenute.

Identificazione del modello, limiti essenziali e clausola di responsabilità sono
sempre inclusi; le esclusioni sono elencate e il documento non viene presentato
come dossier completo. Anche senza timbro il report può essere esportato,
senza obbligare la generazione del certificato. Se il timbro è selezionato,
il digest include le scelte; cambiare solo impaginazione non invalida le proposte
SI della stessa missione. Stima pagine e CO₂e si aggiornano sul contenuto incluso.
Controlli esclusi dal flusso di stampa: nessuna pagina vuota introduttiva.

Verifiche: 40 test frontend mirati, Svelte 0 errori/0 warning, bundle root/app
68.258/68.266 B. Tre E2E Chromium distinti: percorso IT/EN con quattro PDF,
persistenza delle spunte, reinserimento indipendente della provenienza,
aggiornamento CO₂e, JSON completo, digest e nessuna nuova simulazione; due
regressioni settimana buia. Verifica diretta dei quattro PDF: completi 13/12
pagine, sintetici 2/2; sezioni escluse assenti, avvisi preservati, nessuna pagina
bianca, nessun controllo UI stampato e nessun testo fuori margine.
Entrambe le demo locali aggiornate.

**Report compatto, certificato blockchain DEMO e indicatori CO₂e.**
Impaginazione A4 ottimizzata senza sopprimere sezioni, grafici o parametri:
corpo 9,5 pt, titoli e spaziature ridotti, grafici su due colonne, tabelle/fonti
compatti e margini 10/10/15 mm. Le note identiche dei parametri non registrati
sono raccolte in una legenda †; ogni riga conserva valore e attribuzione.
Nei PDF di prova: IT da 29 a 13 pagine, EN da 27 a 12, non un limite garantito per
qualunque missione. Testate tutte le righe dei parametri, fasi 0–F e testo entro
i bordi pagina. Footer solo testuale; timbro grafico conclusivo conservato.

Il timbro è accompagnato da un certificato blockchain **esplicitamente simulato**:
digest SHA-256 reale delle evidenze strutturate, JSON con chiavi ordinate,
identificativo transazione prefissato DEMO. Nessuna rete, broadcast, firma wallet,
autorità temporale, certificazione legale o firma dei byte PDF. Il digest è
riproducibile dall'export; cambiare contenuto lo cambia. JSON schema 4.

Nel Dossier si possono dichiarare emissioni per ciascuna fase 0–F (kg CO₂e),
fonte/metodo e perimetro del ciclo di vita, evitando doppio conteggio.
`/api/raven/report/carbon` somma con Decimal: subtotale delle sole fasi note,
totale soltanto se tutte sono dichiarate, zero solo esplicito. Non è una LCA
indipendente, né l'impronta di lancio/veicolo dedotta dall'energia solare.
Indicatore, dati e limiti compaiono nella fase F/ESG e nell'export.

Chiusura con foglia SVG e promemoria digitale: stima browser delle pagine a pari
contenuto, compatte contro spaziatura standard; conversione in CO₂e nel Core.
Scenario dichiarato: una copia A4, solo fronte, carta primaria 80 g/m².
Verificato nel file ufficiale UK DESNZ 2025, Material use / Paper:
fattore `19_506_5164_15_1`, 1345,0779 kg CO₂e/t, circa 6,7114 g CO₂e/foglio.
Fonte primaria nella bibliografia. Sono potenziali emissioni della produzione
della carta, non risparmi misurati o compensazioni: esclusi toner, stampante,
trasporto, smaltimento ed energia digitale/server; nessun vantaggio netto
digitale/stampa dichiarato. Il conteggio dell'anteprima di stampa prevale
sulla stima del browser; fronte-retro e carta riciclata cambiano i risultati.

Verifiche: 19 test API report, 37 frontend mirati, Svelte 0 errori/0 warning,
Ruff e mypy puliti; build root/app 68.258/68.266 B sotto 70.000 B.
Tre E2E Chromium distinti, con percorso completo IT/EN, ricostruzione indipendente
del digest dal JSON, somma CO₂e di prova, persistenza e regressioni settimana buia.
PDF finali 13/12 pagine: tutti i footer/numeri, certificato e reminder presenti,
nessun testo oltre i bordi pagina, una sola immagine del timbro e nessun logo
nei footer. Entrambe le demo locali aggiornate e responsive.

**Report autocompilato e nuovo passo Dossier di missione (8 passi).**
Le fasi 0–F vengono completate con riepiloghi dei risultati effettivi del Core,
configurazione e ipotesi dichiarate dall'utente, distinguendo origine, proposte e
prove mancanti. Il nuovo Dossier raccoglie obiettivi e criteri di successo,
architettura, responsabili/giurisdizione/autorità, lancio, fine vita, piani ESG e
fonti. Non modifica né ripete il calcolo scientifico. Bozze precedenti senza
dossier restano leggibili; libreria e sessione conservano i nuovi input.

Economia: nove voci inseribili, valuta/anno base/fonte o metodo, contingenza e
finanziamento; il Core Python calcola subtotale noto, totale completo e scarto dal
finanziamento. Una voce o contingenza assente impedisce un totale completo,
mentre zero esplicito è ammesso. La compatibilità aritmetica con il budget non
costituisce fattibilità economica; prezzi di mercato e costi non vengono inventati.
Approvazioni, qualifiche, impronta/punteggi ESG e conclusioni legali restano non
valutati senza evidenze.

SI opzionale: endpoint dedicato esclusivamente a modelli locali loopback, nessun
invio a provider remoto. Le proposte narrative sono separate, attribuite e da
revisionare; cambiare scenario, risultati, dossier o lingua le rende obsolete.
Nell'ambiente corrente non è installato un modello locale raggiungibile:
il pulsante segnala esplicitamente l'indisponibilità, senza fingere una generazione.
Il completamento deterministico e il budget funzionano senza modello.
JSON schema 3. Rimosso il logo dai piè di pagina PDF; rimangono testo/numerazione e
il solo timbro grafico conclusivo.

Verifiche: 41 test backend, 35 frontend mirati, Svelte 0 errori/0 warning,
Ruff e mypy puliti; build root/app sotto 70.000 B. Tre E2E Chromium live:
percorso con dossier IT/EN, budget 900 + 20% = 1.080 e scarto 80, indisponibilità SI,
export/ripristino/invalidazione e due regressioni settimana buia root/app.
PDF IT/EN di 29/27 pagine: una sola immagine, il timbro nell'ultima pagina,
nessuna immagine nei piè di pagina; testo e numerazione su tutte le pagine.
Le prove di generazione SI riuscita usano un provider simulato, non un modello
reale installato. Demo locali root e /app aggiornate.

**Report di missione strutturato per fasi ECSS 0–F, economia, ESG e aspetti legali.**
Blocco precedente: il dossier e lo schema 3 sopra sostituiscono le limitazioni
di input e lo schema 2 descritti in questo paragrafo.
Indice sequenziale riferito a ECSS-M-ST-10C Rev.1 §§4.4.1–4.4.3, verificati nel PDF
ufficiale: ECSS usa review gate e modello a V, consente sovrapposizioni e richiede
tailoring; non equivale a un waterfall rigido o a una certificazione del report.
Fase 0: obiettivi scientifici/tecnologici/altri, con priorità e soglie effettive del
Planner. A: studio tecnico esistente, decisione e prospetto economico predisposto.
B: configurazione di studio; C: parametri effettivi, provenienza e limiti.
D: sviluppo/AIT/qualifica; E: lancio, trasferimento, eventuale inserzione/discesa,
commissioning e operazioni; F: smaltimento, passivazione, archiviazione e sostenibilità.
Le review MDR–MCR restano non eseguite; elaborati, autorizzazioni, progetto di volo
e fattibilità dell'intera missione non vengono inventati.

Economia: voci sull'intero ciclo di vita, valuta/anno base/metodo/fonti, incertezze,
contingenza, imposte/inflazione, totale, finanziamento e flussi di cassa; importi
e conclusione di fattibilità restano null/non valutati, mai zero. Nessun nuovo input
economico nel Planner, in attesa delle specifiche dell'utente.
ESG trasversale 0–F: E ambiente/emissioni/materiali/rifiuti/protezione lunare,
S sicurezza/diritti/filiera/comunità/accessibilità, G responsabilità/etica/costi/fonti/
conformità/supervisione SI. Predisposti confini, materialità, indicatori, baseline,
obiettivi, valori/unità, fonti, responsabili e verifica; nessun punteggio o claim ESG.
Quadro legale: giurisdizione/operatore, autorizzazione, registrazione/responsabilità,
spettro, contratti/export control, licenze/privacy e obblighi ambientali da valutare.
Riferimenti primari ECSS, UNOOSA, ITU e GRI inclusi.

Esplicita la generazione deterministica del report e l'assistenza Copilot allo
sviluppo, senza contenuti SI di progetto/budget/diritto generati automaticamente.
Clausola finale di limitazione di responsabilità nei limiti di legge, con eccezioni
inderogabili e necessità di revisione legale: nessuna promessa di esonero assoluto.
Timbro visivo RAVEN con logo esistente, versione del modello e SHA del registro,
non firma digitale o approvazione della missione. Piè di pagina PDF con marchio
RAVEN e numerazione su ogni pagina, tramite pagine CSS nominate per questa rotta.
JSON schema 2 conserva tutti i dati precedenti e aggiunge il blocco `lifecycle`;
anteprima e stampa/PDF mostrano la stessa struttura bilingue.

Verifiche: 25 test frontend mirati, Svelte check senza errori/avvisi, build root/app
sotto 70.000 B; E2E live del percorso completo su entrambe le demo in IT/EN,
con export, ripristino, invalidazione e viewport mobile. Verifica diretta dei due
PDF Chromium di 22 pagine ciascuno: fasi, ESG, clausola e timbro finale presenti,
marchio e numero pagina verificati su tutte le pagine.

**Explore, Learn e informativa riorganizzati.**
Rimosse la sezione About «Da GrazingLink a RAVEN» e la pagina/rotta Roadmap,
insieme ai collegamenti visibili. Explore conserva quattro schede: modello 3D del
collegamento, onda 3D, Link budget e analisi 3D dei siti; eliminata la quinta
scheda Estensioni/Laboratorio. Le rotte tecniche legacy restano compatibili.
Nel passo Siti del Mission Planner compare una libreria didattica delle otto
posizioni di catalogo, con descrizioni generiche e fonti, senza metriche della
missione o giudizi di idoneità. La guida alle antenne compare soltanto nella pagina
dedicata 03 Link budget, non in Explore o Comunicazioni:
copertura/guadagno/puntamento, lander distinto dal
ricevitore DSN, nessuna qualificazione hardware implicita.
Correzione del posizionamento verificata con 2 test Explore, Svelte check senza
errori/avvisi, build root/app sotto il budget e 2 E2E live: guida assente in Explore
e nel passo Comunicazioni, presente nella pagina Link budget in IT/EN.

Learn è ora un percorso di 15 schede: sette passi del Planner e stadi S0–S7,
ciascuno con spiegazione, esempio, quiz, feedback e avanzamento condizionato.
I collegamenti di pratica aprono una nuova scheda senza perdere la lezione.
Enterprise mostra «Chiedi un preventivo», senza intervalli di prezzi cumulati;
checkout e servizi commerciali restano nello stato precedente.

About include dichiarazione di indipendenza/non-affiliazione a NASA e governi o
agenzie spaziali di Russia/Cina, contributi reali dello sviluppo assistito da
GitHub Copilot e legenda di 14 riferimenti (dati/metodi/confronti distinti).
Terminologia SI adottata volontariamente: verificati
[EO 14434, 29 settembre 2026](https://www.whitehouse.gov/presidential-actions/2026/09/inaugurating-the-era-of-super-intelligence/)
e [attuazione NIST](https://www.nist.gov/super-intelligence).
L'ordine riguarda l'esecutivo federale USA, non costituisce obbligo per RAVEN né
certificazione di capacità superumane. Titoli storici e identificatori tecnici
mantengono i nomi originali. Nessun nuovo claim di validazione fisica S2/S3.

Verifiche: 834 test frontend nel giro completo; dopo il completamento della
bibliografia, 33 test mirati e Svelte 0 errori/0 warning. Chromium: 14 casi
superati nel primo giro; due attese del vecchio titolo «Analizza» corrette,
con 5 casi di modo/alias superati nel giro mirato (19 casi distinti complessivi).
Build finali root/app: 68.307/68.315 B iniziali, sotto 70.000 B.
Demo root e /app aggiornate con pubblicazione atomica dell'index e conservazione
degli asset già in uso; entrambi i test live di libreria, guida antenne, informativa
con 14 fonti e prezzo Enterprise superati dopo il deployment.

**Mission Planner: intervallo delle effemeridi vincolato dai kernel.**
Il motore locale supporta UTC dal 1972-01-01 al 2150-01-20
23:58:50.815539; Sole, Terra e un calcolo completo nel 2001 sono disponibili.
`/api/raven/sites` espone `ephemeris.supported_range` derivato dal motore, non una data
arbitraria. Entrambi i planner impostano min/max sui calendari UTC, riducono l'ultimo
inizio consentito in base alla durata e validano entrambi gli scenari; anteprime e
calcoli non partono con date fuori intervallo. Evaluate/compare rispondono 422 anche
quando la partenza è coperta ma la durata completa supera il limite. Test:
24 API backend, 31 frontend mirati, Svelte 0 errori/0 warning, Ruff e mypy puliti,
3 Chromium E2E (limiti su root e /app, regressione report a sette passi).
Build root/app: 68.509/68.517 B iniziali, sotto il limite di 70.000 B.

**Report annuale del 7 aprile: zeri riprodotti e controllati, nessuna correzione numerica.**
Le cifre riportate corrispondono a 365 giorni, passo 24 h e pannello orizzontale.
Malapert ha davvero SOC minimo zero: 49.750,697 Wh generati contro almeno 87.600 Wh
di sola sopravvivenza annuale, 46.729,035 Wh di carico non soddisfatto e 5.040 h
campionate nello stato dark. Haworth ha SOC minimo 87,368% solo nel primo intervallo
di 24 h; 8.736 h successive di batteria ignota sono distinte dalle 1.200 h RF ignote.
Audit separato S1/S3 con gli stessi kernel e orizzonti, 8.760 campioni orari per sito:
Haworth ha ancora zero illuminazione e generazione; Malapert Sole 34,292% e
49.542,689 Wh generati (contro 34,247% e 49.750,697 Wh al passo giornaliero).
Questa verifica non certifica oscurità continua tra i campioni, convergenza della
batteria annuale o qualificazione fisica di S2/S3; non riavviare la batteria per
segmenti indipendenti per ricostruire un anno.

**Ricontrollo engine e Mission Planner: anteprime ora reattive.**
Riprodotto esattamente il report 16-19 aprile 2027, pannello tracking
1 m² e radio 10 kbit/s, 10 dBi. I valori estremi sono coerenti:
Malapert genera 22.414,168 Wh e resta carico; Haworth in ombra scende
al 62,105% e ha RF chiuso per `blocked_far_terrain`, senza margine finito.
Verificati indipendentemente integrale della potenza, scarica della
batteria e visibilita' contro orizzonte LOLA, non contro zero gradi.
Con 0,01 m² Malapert genera circa 3,11 W e scende al 61,048%;
con -10 dBi e 3 Mbit/s il margine varia tra -17,881 e -16,517 dB,
RF chiuso e tempo utile zero. Non introdotte oscillazioni artificiali.
**Bug reale corretto:** la firma dei parametri era letta dentro `untrack`:
gli edit nella stessa scheda nascondevano i grafici senza ricalcolare.
Ora debounce 300 ms, un solo
preview in corso, ultimo input accorpato e nessun retry automatico
dopo errore per lo stesso input. Gli errori restano espliciti.
Report: spiegati SOC saturo e curve RF non fornite per link chiusi;
fonti dei parametri risolte nel registro completo, non nel sottoinsieme
dei controlli. Export schema 1 conserva `parameters` e aggiunge
`source_parameters` completo. Valori runtime senza voce registrata
non vengono piu' descritti come calcoli ignoti.
Simboli Unicode corretti nel DOM del report: la corruzione del testo
incollato non e' stata riprodotta. Modello scientifico ancora 1.4.
**833 test frontend (4 worker), 8 E2E Chromium mirati superati**,
inclusi edit energetici, errore senza retry, report su entrambe le basi,
replay/camera WebGL e storia. Svelte senza errori/avvisi; build iniziali
68.509/68.517 B, sotto 70.000 B. Nessun nuovo giro backend o E2E completo.

**Mission Planner: grafici, risultati energetici e regressioni CI.**
Scale percentuali fisse 0-100%: una batteria piena non appare piu' vuota,
ne' un calo 90-80% come una scarica completa. Assi con unita', UTC o indice
del campione, descrizioni EN/IT di potenza W, carica %, elevazione gradi,
margine dB e velocita' bit/s. Gli ignoti conservano buchi, tempi e selezione;
nessuna sostituzione con zero. Carica datata a fine passo, potenza a inizio.
Risolta anche l'etichetta del valore SOC istantaneo, prima chiamato minimo.
Il confronto 7-14 aprile 2027 e' realmente in ombra: generazione 0 Wh,
Malapert utile 140 h sulla batteria iniziale, minimo 16,7%.
Haworth ha 22 h di energia nota e 146 h successive ignote; l'RF e' ignoto
solo in 63 h non consecutive. Il report distingue questi intervalli e
spiega il blocco dell'integrazione energetica al primo carico RF ignoto.
Nessun dato inventato e nessuna modifica al modello scientifico 1.4.
Snapshot serializzati e accorpati sull'ultimo input: non si annullano
calcoli che il server deve comunque finire. Cache con chiave catturata,
risposte/errori obsoleti scartati; limiti backend invariati.
La CI `42520591921` ha concluso con backend/frontend/installer superati,
771 E2E superati e 11 falliti. Tutti gli 11 casi falliti superano ora
il giro locale mirato: corretti sovrapposizione snapshot, aspettative
obsolete su siti RF ignoti, dizionario degli stati e ordine dei parametri URL.
**832 test frontend e 22 scenari Chromium E2E verificati**, compreso
il report buio alla radice e sotto `/app/`; Svelte senza errori/avvisi.
Build iniziali 68.509/68.517 B, entrambe sotto 70.000 B.
Non dichiarato un nuovo giro completo locale o una nuova CI tutta verde:
il push avvia un nuovo controllo remoto.

**Tentativo di chiusura S2/S3: correzioni numeriche, modello 1.4.**
Raggi polari corretti con rotazione cartesiana condivisa per maschere, profili
e impronte di download; otto regressioni prima fallivano. Cache maschere v2.
Il fit respinge apici extrapolati: terreno lineare non produce creste risolte.
S3 integra l'area esatta sopra la maschera lineare a tratti, senza orizzonti
costanti ai punti medi; controlla tutti i bin attraversati e conserva l'ignoto
per proiezioni parziali prossime allo zenit fuori dominio.
Matrice **22 verificate, 4 plausibilita', 6 non validate, 1 ignota**.
**S2 resta non validato e S3 solo plausibilita': la richiesta di Verified
complessivo non e' soddisfatta.** Mancano qualificazione indipendente del
terreno/curvatura/vertice proiettato e un confronto di illuminazione equivalente.
Il prodotto NASA LROC originale e' stato recuperato dall'archivio migrato:
SHA-256 identico, ma criterio radiometrico e supporto di 100 m restano diversi
dal modello geometrico puntuale. Gli errori di mappe regionali LOLA a 5 m
non sono trasferiti alle mappe bloccate a 20/240 m.
**273 test backend mirati finali, 826 frontend e 17 Chromium E2E superati**;
Svelte senza errori/avvisi, lint/formato/tipi/contratti superati, entrambe
le build entro il limite iniziale di 70.000 B. Il primo giro backend completo
aveva 2257 superati, 49 saltati e due fallimenti: parita' di margini tutti
ignoti e dipendenze S2 correnti negli archivi legacy. Corretti e rieseguiti
nel giro mirato; nessun numero golden rigenerato. Le dipendenze storiche
sono isolate solo nella fixture degli endpoint legacy, mai nella produzione
o nelle prove scientifiche correnti. Non dichiarato un nuovo giro E2E completo.
Dettagli: `docs/domain/validation.md`, «S2/S3 closure attempt and numerical corrections».

**Validazione degli stadi restanti: correzioni S2/S4/S5/S7, modello 1.3.**
Riprodotti e corretti minimo SOC che ignorava lo stato iniziale, attribuzione
di RF/DSN ignoti come cause false certe, raggio enorme inventato dal fit di
terreno piatto a quote negative e omissione implicita della correzione RF
quando mancava la curvatura di un ostacolo. Con nu positivo e raggio non finito,
il modello completo ora da' `outside_model`; lama senza correzione solo se
scelta esplicitamente. Nessun parametro fisico inventato o promozione osservativa.
Le prove aritmetiche S2/S7 portano la matrice a **21 voci verificate**, 4 solo
plausibilita', 6 non validate e 1 ignota. S2/S4/S5 restano non validati, S3
solo plausibilita'; le porte fisiche restano bloccate dai dati equivalenti mancanti.
Il risultato ignoto attraversa API, scene, puntamento, testo ed export senza
diventare un margine legacy o zero; terreno, renderer e camera restano disponibili.
Simula reale non presenta gauge/tabelle/export didattici come un risultato corrente.
Model/Validation EN/IT mostra **Verified** quando tutte le voci dello stadio
sono chiuse, rilegge con pulsante/focus, respinge stati non supportati e invalida
i parametri quando cambia l'identita'. Archivi 1.2 storici, hash registro invariato.
**2201 backend superati / 49 saltati**, **826 frontend**, **48 controlli frontend
finali mirati** e **73 E2E selezionati superati**, inclusi tutte le prove Model,
WebGL/2D, ignoto RF senza fallback didattico, export, camera e Planner.
Svelte zero errori/avvisi; Ruff, mypy, contratti generati e import superati.
Build `/` e `/app/`: bundle iniziale **68.509 / 68.517 B**. Non e' un giro E2E
completo ne' una garanzia a freddo: il 503 del Planner gia' noto e il fallimento
CI precedente non vengono dichiarati risolti da questo giro verde selezionato.
dettagli in `docs/domain/validation.md`, sezione «Remaining-stage arithmetic and applicability corrections».

**Validazione incrementale S2-S5 richiesta dal proprietario: correzione S3, modello 1.2.**
Separati geometria RF campionata S2, aritmetica S4 e formule TE/TM/rugosita' S5 dalla
qualificazione fisica non dimostrata. Nuove prove indipendenti cartesiane e integrale
della fase su altezze gaussiane; parametri V/D/I invariati. La matrice passa da
16 a **19 voci verificate**, con 4 solo plausibilita', 6 non validate e 1 ignota:
sono conteggi di evidenze, non promozioni degli stadi fisici.
Trovato e corretto un errore reale S3: i rettangoli delle 48 strisce perdevano una
falce solare a -0,26999 gradi con raggio 0,27, dando frazione zero e buio.
Ora si integra l'area circolare esatta in ogni striscia, conservando l'orizzonte
al suo punto medio; il calcolo energetico S4 riceve la frazione corretta.
Errore massimo precedente su orizzonte piatto 0,000773109883; nuovo confronto
analitico entro 2e-15. Semidiametri invalidi e falce con terreno incompleto
restano esplicitamente ignoti. Versione **raven-core-1.2**, stesso hash del registro:
gli archivi 1.1 restano storici, non ricalcolati come correnti.
Confronto piu' impegnativo su cinque maschere reali a 200 km, anno 2027, 1460 istanti
per sito (passo 6 h), contro integratore indipendente a 1024/2048 colonne:
massimo residuo 1,2726e-5 di frazione, raffinamento 4,472e-6, nessun passo lit diverso.
Maschera condivisa: non e' una validazione indipendente del terreno o osservativa.
Due siti illuminati aggiunti ai test riproducibili, senza download e con batch RAM limitati.
Model/Validation EN/IT mostra conteggi per stadio e prove ancora necessarie.
S2/S4/S5 restano non validati, S3 solo plausibilita': le quattro porte fisiche
del closure audit restano bloccate dai dati equivalenti mancanti, non da unit test mancanti.
**2179 backend superati / 49 saltati** nel giro completo; **204 test scientifici/API
finali superati**, incluse le due nuove regressioni su dati reali. **823 frontend**,
Svelte zero errori/avvisi; Ruff, mypy (161 file), contratti generati e 8 contratti
di import superati. Build `/` e `/app/`, bundle iniziale 68.509 / 68.517 B.
E2E su server nuovi: prima 27/28 a due worker, poi **28/29 a un worker come CI**,
incluso nuovo caso Model in inglese e tutti i casi Model/lingua. In entrambi fallisce
il primo wizard per **503 "troppe analisi in corso"** durante preview/scene a freddo,
non per un risultato numerico: scena non disponibile e messaggio esplicito.
La concorrenza/client non sono stati alterati per nascondere il fallimento.
Questo giro non viene dichiarato completamente verde; resta il limite di avvio
scientifico a freddo gia' osservato nei precedenti fallimenti CI.
Evidenze, condizioni di sblocco e limiti in `docs/domain/validation.md`,
sezione «Incremental S2-S5 validation and S3 correction».

**Correzioni Home, Contatti e continuita' delle scene richieste dal proprietario.**
Storia della Home, foto/credito, mini-simulatore, frasi, stati, validita', tooltip,
numeri e riepilogo mensile nei cataloghi EN/IT lazy, reattivi al cambio lingua.
Rimosso il blocco finale Home sui limiti/Chi siamo e, da Contatti, la sezione di
assistenza e il callout dei dati team da completare; schede del team conservate,
nessun contatto inventato. Evidenze e limiti scientifici restano in Model/Validation.
La descrizione della cresta ora rispecchia il modello corrente: ITU-R P.526-9,
con split-step come confronto, non come correzione primaria.
Il Planner mantiene dati, renderer e camera dell'ultima scena durante gli aggiornamenti
di tempo, radio e sito: niente copertura nera o reset della vista dal rover a ogni
ricalcolo. Scena precedente ed eventuale luce precedente sono dichiarate, non
spacciate per un risultato corrente; luce aggiornata solo quando le efemeridi e la
scena coincidono alla risoluzione di un secondo delle API, anche con clock frazionario.
Tutti e tre i renderer WebGL evitano setSize a dimensioni invariate e ridisegnano
sincronicamente dopo ResizeObserver, prima che il buffer azzerato venga compositato.
**823 test frontend superati**, Svelte senza errori/avvisi, parita' EN/IT, build
`/` e `/app/`; bundle iniziale **68.509 B / 68.517 B**, sotto 70.000 B.
**10 E2E specifici e 47 E2E del codice finale superati**, inclusi lettura reale
del buffer WebGL dopo resize su Viewer/Onda/Lander/Simula, camera e frame conservati
con API lenta/503, clock frazionario, ripiego 2D, Planner, export e accessibilita'.
Giro E2E completo su server nuovi e asset isolati: **776/777 superati in 24,3 minuti**;
unica asserzione obsoleta sui link di assistenza rimossi da Contatti aggiornata e
ricollaudata: **15/15 Contatti e pagine legali superati**. Il piccolo affinamento
finale della precisione del clock e' stato ricollaudato nei 47 casi pertinenti,
inclusa una nuova regressione (la suite ora contiene 778 casi). Nessun retry o
test disattivato; non si spaccia il primo giro con l'asserzione obsoleta per verde.
Demo locali `/` (8014) e `/app/` (8001) aggiornate con gli asset finali e verificate
in Chromium, senza riavviare i server o cancellare i dati del browser. Nessuna
modifica numerica al modello scientifico.

**Verifica dell'installer e regressioni frontend/backend/CI/E2E richiesta dal proprietario.**
`install.sh` collaudato in una copia isolata, con Node/uv e dipendenze installati da zero:
build, plugin C, kernel/tessere in cache, avvio, secondo avvio idempotente, aggiornamento
del codice con cambio PID sulla stessa porta e arresto riusciti. Il fingerprint include
backend/contratti, dipendenze e configurazione di build frontend; `--reinstall` ferma
prima il proprio server. Collaudati porta occupata, zeri iniziali e reinstallazione
a server acceso; il probe usa SO_REUSEADDR per non confondere TIME_WAIT con un listener.
Validazione porte senza overflow/ottale e controllo del comando
completo prima di riutilizzare/fermare un PID; nessun processo della demo esistente toccato.
Tre variabili di sicurezza documentate anche in `.env.example`. Assistente: nomi citati
devono essere presenti nel passaggio recuperato e domande generiche sulla pagina danno
precedenza al documento della pagina, senza abbassare le soglie del golden set.
Import scientifici serializzati anche in defaults, pipeline e tabella di compensazione:
corretto il deadlock SciPy osservato nei log CI. Contatti con bersagli touch da 44 px;
Esc/clic fuori annullano il caricamento lazy del menu lingua senza riapertura tardiva.
CI aggiunge la regressione di riavvio dell'installer: upload artefatti non bloccanti
con avvisi/summary espliciti, conservazione un giorno; nessun test, build, controllo
licenze o generazione SBOM ignorato. La quota GitHub gia' esaurita non e' stata cancellata
o aumentata: vecchi artefatti conservati e download eventualmente indisponibili.
**2162 test backend superati (49 saltati), 821 frontend e 70 E2E mirati**, inclusi
i casi falliti della CI precedente; Ruff/mypy, otto contratti, schemi, licenze runtime/CI
e generazione SBOM verificati. Bundle iniziale 68.480 B. **Giro E2E completo: 771
superati in 21,9 minuti**, da server nuovi con tutti gli import protetti; nessun retry
o test disattivato. Server/asset di collaudo isolati, demo locale preservata.
Nessuna modifica al modello scientifico.
Esito successivo della CI GitHub `42504240860`: backend, frontend e install-smoke
superati; E2E **766/771**, quattro risposte 503 e un'asserzione URL sensibile
all'ordine/arricchimento dei parametri. Non si dichiara quella CI verde sulla base
dei test locali; resta da verificare il prossimo giro sul runner GitHub.

**Correzioni dei sette rilievi dell'audit di sicurezza richieste dal proprietario.**
Certifi 2026.10.19, runtime Debian aggiornato e pip/librerie vendorizzate rimossi dopo
l'installazione; proxy derivato dalla base bloccata con aggiornamenti Alpine e Brotli
almeno 1.2.1-r0. Compose/runbook ora costruiscono anche il proxy. Esclusioni Docker/Git
estese ai segreti annidati, configurazioni private e chiavi SSH/PEM; canary con soli
file fittizi verifica esclusione e conservazione degli esempi.
Estimatori isolati per proprietario con capability HMAC emessa dal server tramite
`X-Estimator-Owner`: nessun cookie, nessun cambio al contratto StateEstimate; i client
devono reinviare l'header per mantenere lo stato (handshake GET documentato). Il Planner
non usa questi endpoint. Horizon condivide il limite delle analisi, 503 oltre il tetto
e 504 dopo 120 s; il lease resta occupato fino alla fine reale del worker anche se
la risposta viene cancellata. Cache maschere entro 128 file/8 MB per il catalogo,
quota custom complessiva 200 MB applicata a ogni inserimento; niente nuove scritture
se non si puo' liberare quota, errori nei log e pulizia dei parziali. Telemetria:
tre stream per IP normalizzato, 429 oltre il tetto e lease assoluto di 300 s.
**192 test mirati, 10 test stack AMD64/ARM64, 1 anti-spoofing e 3 browser superati**;
Ruff, mypy (161 file), otto contratti d'import, Compose e licenza Certifi OK.
Build complete native/ARM e ricollaudo delle immagini finali senza pip riusciti.
Scansioni finali: **zero CRITICAL in app/proxy, zero advisory Python e proxy**;
restano **11 advisory HIGH distinti Debian (47 occorrenze per pacchetto), senza
versione corretta indicata dal database**: non equivalgono a exploit pubblici dimostrati,
ma non vengono nascosti o dichiarati risolti. Il connector upstream resta invariato
e richiede il monitoraggio dei propri advisory. Il controllo licenze dell'intero venv
locale segnala ancora Torch opzionale preesistente; non e' nel runtime distribuito.
Container, reti, volume e tag delle sole prove rimossi; server di anteprima e
`test-results/` preesistenti preservati. Nessun sito pubblicato, token cloud creato
o promessa di sicurezza assoluta; controlli VM/account, backup e updater ancora aperti.

**Piano di aggiornamento continuo del sito richiesto dal proprietario.** Esteso
`docs/process/pilot-runbook.md`: promozione di commit verificati su `deploy/production`
(branch non ancora creato), lettura outbound con deploy key read-only, updater/timer
systemd, build ARM, collaudo, sostituzione controllata e rollback esplicito. Versione
dell'app distinta dal modello scientifico, cache HTML/versione non persistente, asset
hashati con vecchie release conservate e avviso EN/IT senza reload forzato delle bozze.
Nessun nuovo servizio a pagamento, webhook pubblico o SSH aperto ai runner GitHub.
**Solo piano:** updater, metadati/version endpoint, regole cache e avviso non implementati.
Restano autorizzazione della key, promozione delle release, account/VM/dominio e collaudi
reali. Non promette zero downtime e non aggira la CI o la qualificazione scientifica.

**Preparazione deployment Oracle Always Free + Cloudflare Tunnel, scelta del proprietario.**
Nuovo `compose.oracle.yaml` separato dal Compose di sviluppo: frontend/backend nella stessa
immagine, dati LOLA su volume persistente scrivibile dall'utente non root, root read-only,
limiti CPU/RAM/processi e log bounded, assistente estrattivo senza API a pagamento.
Nginx normalizza l'IP prima dei rate limiter e non espone direttamente il backend:
solo loopback per il collaudo; cloudflared legge il token da file montato soltanto al
connettore. Token/.env esclusi da Git e build. Training/job del template bloccati con
403 dal proxy pubblico; pipeline opzionale non attivata, strumenti RAVEN preservati.
Runbook operativo in `docs/process/pilot-runbook.md`: quote correnti Oracle 2 OCPU/12 GB,
200 GB di storage complessivo, configurazione VM/DNS/Tunnel, dati, collaudo e aggiornamenti.
**Build complete AMD64 e ARM64 riuscite**, incluso C statico e librerie scientifiche.
ARM verificato in emulazione con kernel bloccati, bootstrap, calcolo reale S0-S7,
orizzonte completo, matrice corrente, frontend/asset e SSE: **4 test deployment superati**.
**1 test proxy/rate limit** prova che XFF falsificato non aggira il limite e che utenti
distinti non condividono la quota; **38 API/hardening, 10 knowledge e 2 browser superati**.
Prefetch esplicito di 624 tessere del catalogo (~41 MB), volume conservato attraverso
ricreazione dei container e passaggio AMD64/ARM64. SELinux mantenuto attivo: etichetta
applicata al solo file Nginx. Solo nell'override di test emulato il timeout dell'healthcheck
e' 15 s anziche' 3 s; la produzione resta invariata, non si dichiarano prestazioni Oracle.
**Non pubblicato online:** mancano dominio, account/VM Oracle e accesso Cloudflare del
proprietario. Nessuna risorsa cloud creata, DNS modificato o servizio a pagamento attivato.
Restano collaudo hardware reale, TLS/DNS/Tunnel, reboot/ripristino/carico e dati legali/
contatti effettivi prima del lancio pubblico. I server di anteprima condivisi non modificati.

**Trasparenza e preparazione del pilota (punto 5 commerciale).** Privacy e Cookie aggiornate
in EN/IT: flussi server/browser, cronologia locale, archivi di compatibilita', limiti di
conservazione/export, consenso e log senza false garanzie di anonimizzazione. Nuova
`/terms` nel footer e nei Piani: condizioni tecniche del prototipo, non contratto commerciale.
Contatti offre aiuto self-service verso Learn, Model e gestione dei dati; nessun indirizzo,
ticket, SLA o contatto privacy inventato. Il repository privato non e' proposto come supporto
pubblico. Le preferenze di consenso e gli errori di persistenza seguono la lingua scelta.
`docs/process/pilot-runbook.md` distingue UI da operazioni: copie manuali dei report,
ricostruzione del deployment, logging/retention e gate di collaudo/pilota. Nessun backup cloud,
pagamento, iscrizione al pilota o consenso contrattuale implementato. Restano necessari
dati reali del gestore, canale verificato, revisione legale e configurazione operativa.
Verifica: **131 test frontend mirati, 15 knowledge e 19 E2E superati**; Svelte senza
errori/avvisi, parita' EN/IT, build `/` e `/app/`, bundle **68.480 B**. Browser verifica
assenza cookie/Set-Cookie, storage bloccato, persistenza consenso, help e focus, axe,
mobile senza overflow, footer/Piani e prefisso `/app/`. Un test precedente che vietava
qualsiasi focus nel main Contatti ora verifica correttamente i link di aiuto, mantenendo
le schede segnaposto non focalizzabili. Build/server isolati, nessun processo altrui toccato.

**Confronti scientifici con fonti primarie.** Sei nuove prove: budget lunare Surveyor
NASA CR-69102 (telemetria/TV), anche sullo stadio S5 corrente, e potenza circolare lossless
NASA CR-119032. Residuo massimo del margine nominale: 0,0471 dB. La perdita di spazio
pubblicata e' un input: il rapporto non specifica l'unita' delle "miles", non si dichiara
validata quella distanza. Confrontato realmente il testo ITU P.526-16: J e T mantengono le
espressioni -9 implementate; nessuna modifica numerica necessaria. Matrice con tre evidenze
separate (budget assoluto aritmetico, base circolare lossless, formula del crinale).
**105 test scientifici e 3 test API pertinenti superati**, Ruff/mypy/8 contratti d'import
e contratti generati OK. Nessuna promozione della validazione fisica:
misure RF, multipath/cresta con condizioni equivalenti, hardware energetico e Sole/terreno
restano bloccati dalle evidenze mancanti. Fonti, hash, riproduzione e criteri di sblocco
in `docs/domain/validation.md`, sezione "Primary-reference closure audit".

**Vendita reale: piano, non attivazione.** `docs/design/commercial-launch-plan.md` distingue
le funzioni locali/browser gia' consegnate da storico cloud/PDF server, conserva esattamente
Free/Premium/Enterprise e identifica decisioni del proprietario, account/database, checkout
ospitato, webhook verificati/idempotenti, enforcement/quote, ciclo abbonamento, legale/privacy,
operazioni e pilota. Ogni fase ha dipendenze e criteri di uscita. Nessun prezzo approvato,
pagamento, account o licenza commerciale implementato. La knowledge Pricing ora documenta
le due etichette "Prevista" da riallineare prima del lancio. **15 test di knowledge/documentazione
superati.** Nessun frontend o acquisto modificato.

**Audit precedente e Learn/cronologia (vecchi punti 2 e 4).** Modello `raven-core-1.1`: corretto il
punto speculare sotto il limite numerico di 0,05 gradi; Python e browser usano la geometria reale
per escludere riflessioni oltre il crinale. Parita' con 32 vettori, sei nuovi casi analitici S4,
totali energetici nulli preservati e prefisso noto dichiarato nei riepiloghi. La versione del
modello, oltre all'hash dei parametri, vincola il recupero come risultato corrente.
Il primo audit non aveva reperito la fonte circolare ne' un budget lunare assoluto completo
e aveva controllato solo il catalogo ITU. Il successivo confronto primario sopra chiude
quelle lacune documentali/aritmetiche, non la validazione fisica di multipath, crinale,
energia reale e discrepanze Sole/terreno.

Learn offre quattro lezioni EN/IT (orizzonte, energia, radio, evidenze), risposte con spiegazioni,
progressione controllata e collegamenti agli strumenti esistenti che mantengono lo scenario.
La Dashboard archivia automaticamente solo i calcoli definitivi: fino a 8 istantanee e
2 milioni di caratteri in localStorage. Definizioni custom ricostruite dai parametri originali,
non dai siti correnti; nessun cambio silenzioso della bozza. Selettore, cursori sincronizzati,
JSON, eliminazione selettiva e svuotamento con conferma. Quota, corruzione e incompatibilita'
sono errori espliciti; nessuna espulsione automatica. Vecchie versioni compatibili col registro
sono consultabili in sola lettura con avviso. Una cronologia svuotata resta esplicitamente vuota,
senza reinserire automaticamente l'ultimo calcolo al reload.

Verifica del nuovo blocco: **2139 backend superati, 49 saltati; 815 frontend superati**;
tipi Svelte (zero errori/avvisi), Ruff, mypy, 8 contratti d'import e contratti generati OK.
Build `/` e `/app/` isolate per non modificare gli artefatti dei server gia' attivi:
bundle iniziale **68.208 B**. I 22 E2E pertinenti sono verificati sulla build finale:
21 superati nell'ultimo giro; il confronto tra date e' stato riverificato con altri due
test di navigazione/parametri (3/3), dopo aver atteso le anteprime prima di invalidarle.
Nessun retry o aumento del limite backend. Verificati export JSON/PDF, due calcoli storici,
persistenza senza ultimo run di sessione, cursori, sola lettura, corruzione/svuotamento,
lezioni EN/IT, mobile, axe e base `/app/`. I server di test isolati sono terminati dalla suite.

**Mission Planner, nuovo percorso guidato.** La rotta `/mission-planner` usa ora
Missione > Siti > Periodo > Energia > Comunicazioni > Simulazione > Report, con riepilogo modificabile, slider/campi
numerici, catalogo/globo condiviso, coordinate custom, anteprime da RAVEN, scena lander sincronizzata e onda didattica
incorporata facoltativa. Bozza e ultimo calcolo restano separati: una modifica fisica rende i risultati obsoleti e
blocca l'export fino al ricalcolo. Libreria locale compatibile con le missioni precedenti, incluse le definizioni custom
salvate nelle nuove voci. Rapporto con risultati, finestre, grafici, soglie, fonti e parametri effettivi: JSON oppure
stampa/salvataggio PDF del browser (non un servizio PDF autonomo). Piano: `docs/design/mission-planner-journey.md`.
Verificati il percorso completo nel browser, export, recupero, cronologia, due date, consenso al download, anteprima,
libreria fra sessioni, scena/timeline, onda incorporata, mobile/accessibilita' e coerenza con le altre viste.
Gli E2E del Planner e i selettori dipendenti sono migrati; la vecchia vista resta solo per compatibilita' dei test legacy.
Il percorso guidato non introduce un modello scientifico parallelo; le limitazioni restano aperte.
**Visualizzazioni e dashboard.** Periodo/Energia aprono i grafici temporali in primo piano,
Comunicazioni apre lander e orizzonte, Simulazione apre la scena sincronizzata e il Report
mostra prima i risultati. Anteprime del periodo complete ma separate dal calcolo definitivo:
automatiche solo all'ingresso con DEM disponibile, esplicite dopo modifiche o per siti custom.
Grafici con slider/cursore condiviso, istanti UTC e valori ignoti preservati: Sole, Terra,
potenza, SOC, margine e bitrate scelto. `/dashboard` nella barra globale riusa l'ultimo calcolo
della scheda, segnala la bozza modificata e rifiuta archivi incompatibili; non e' telemetria live.
Onda resta un approfondimento didattico facoltativo. La home non e' stata modificata.

**Debito tecnico risolto.** Telemetria su `/api/raven/evaluate` con margini grezzi per bitrate,
senza extrapolazione dei campioni ignoti; onda e cielo sotto `/api/raven/*`. `/api/lunar`,
`/api/grazing` e `/api/sky` rispondono 410, non redirect o HTML. Le implementazioni storiche
sono conservate solo in `scripts/raven_reference` per gli oracoli scientifici: non sono
esposte in produzione. Rimossi helper inutilizzati e default oltre 1500 campioni. Il
compensatore k modifica il bitrate prudenziale scelto, non il margine fisico a bitrate fisso;
quel bitrate e' ora visibile. Parita' browser S5 registrata come verificata con 32 vettori,
non come validazione fisica indipendente. Overflow mobile della tabella corretto vincolando
gli elementi posizionati al contenitore scorrevole, senza nascondere l'overflow del documento.

Verifiche del blocco precedente: **2132 test backend superati, 49 saltati; 804 test frontend superati**;
check Svelte senza errori/avvisi, lint/format/mypy/import e contratti OK. Build `/` e `/app/`
riuscite; bundle iniziale **68.177 B**, sotto 70.000 B grazie all'import diretto dei moduli
del registro. Gli E2E mirati verificano anche report JSON/PDF, libreria, consenso, timeline,
anteprime e dashboard mobile. Giro completo **751 E2E**, 746 superati al primo passaggio:
i cinque test rimasti (conteggio navbar e misura sub-pixel del pulsante lingua) sono stati
corretti e riverificati. Verifica finale di Planner/lander: 27 casi superati; verifica finale
di menu/navbar/tastiera: 11 casi superati. Corretto anche l'allineamento della navbar a 834 px:
nessun testo su due righe, nessun overflow. Nessuna nuova validazione fisica indipendente.

Ultima revisione pubblicata precedente a questo blocco: `09a1f0d`. Planner e rimozione helper
sono nei commit `86f1eb0` e `09c0312`; migrazione e visualizzazioni sono verificate.
Roadmap, About, coordinate custom, piani a tre livelli, demo e confronto A/B sono implementati.

## Debito tecnico/idee (solo testo, nulla di implementato)
- Batteria e RF come intervalli (caso migliore/peggiore del carico di comunicazione) invece di tutto ignoto dopo il primo
  passo RF ignoto.
- Report generato lato server come PDF (WeasyPrint) invece della stampa del browser: numeri di pagina, intestazioni correnti
  e margini garantiti (oggi `@page` ha margine 0 e il riempimento e' ripetuto con `box-decoration-break: clone`, quindi non ci
  sono piu' testatine CSS ne' numeri di pagina).

## Coda dei lavori, in ordine
1. **Leggere l'esito della nuova CI** e correggere eventuali regressioni. Rimosso il richiamo CI
   a un test PowerShell gia' eliminato (il progetto supporta Linux).
   Test funzionali seriali per non saturare il limite condiviso di due calcoli; i test di
   navigazione attendono la fine delle richieste prima di cambiare pagina. Non ricostruire
   il dist mentre viene servito da una suite. `origin/template-base` gia' incluso dopo il fetch.

## Rinviati da discutere con l'utente
Struttura del sito (barra attuale o 4-5 voci), modalità Demo per la giuria (scenari precalcolati offline), rapporto PDF
(per chi, quanto lungo). Learn non e' piu' rinviato: percorso interattivo implementato su richiesta dell'utente.
Le domande originali sono in `decisions-2026-11-04.md`.

## In attesa dell'utente
Vendita (fornitore di pagamento, prezzi e condizioni, consegna dell'accesso, account e licenze, punto chiave rinviato);
il piano implementativo richiesto e' ora in `docs/design/commercial-launch-plan.md`, senza abilitare acquisti.
Contatti veri e dati legali (privacy, condizioni d'uso); coordinate delle regioni Artemis
(NASA non le pubblica: non inserirne).

## Decisi di NON fare ora
DEM a 5 m (27 file PGDA 78); prodotto a 20 m fino a -80 gradi; Windows; altre lingue; punteggio unico nella classifica.
Motivi in `decisions-2026-11-04.md`. Da riconsiderare se i dati della sfida lo richiedono.

## Punti scientifici aperti (tenuti aperti dall'utente)
Validazione radio fisica/operativa (budget Surveyor completo ora verificato aritmeticamente, non misurato),
cresta arrotondata (formule ITU -9/-16 confrontate, ma nessun arbitro elettromagnetico convergente equivalente),
multipath (fonte circolare lossless verificata, non fase lossy o accoppiamento hardware) ed energia reale non validati.
Soglia 30 dB del terreno lontano illustrativa, valore storico di Nobile rim dell'arbitro non riproducibile,
validazione Sole-terreno solo parziale e scarto polare non spiegato. Non chiudere questi punti con etichette
o misure inventate: il protocollo e le evidenze richieste sono nella sezione finale di `docs/domain/validation.md`.

## Verifiche mai fatte
Firefox, WebKit, telefono e TV reali, GPU reale, lettori di schermo veri, installatore su macOS e caso offline, prestazioni
di Onda 3D e Scena lander.

## Come lavorare
- Avvio: `./install.sh` (Linux). Test server: `.venv/bin/python -m pytest -q`; frontend: `cd frontend && npx svelte-check &&
  npx vitest run && npm run check:bundle`; browser: `cd e2e && E2E_PORT=8014 npx playwright test <spec> --workers=1`
  (prima `e2e/scripts/build-app.sh`; porte 8001/8002/8014 libere: server vecchi falsano i risultati).
- Lint: `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `python contracts/gen.py --check`.
- In ambiente condiviso non fermare server di proprieta' incerta e non ricostruire il loro dist.
  La configurazione E2E accetta `E2E_APP_PORT`, `E2E_PROXY_PORT`, `E2E_STATIC_DIR` e
  `E2E_APP_STATIC_DIR`, oltre a `E2E_PORT`, per verificare build isolate con porte libere.
- Un agente alla volta nella stessa cartella; commit prima di cambiare argomento.

## Indice dei documenti
`docs/domain/raven-model.md` (architettura, stato M0-M15, validazione per stadio), `raven-changes.md` (differenze
volute), `validation.md`, `method.md`, `grazinglink-model.md` (ricerca storica), `artemis-regions.md`;
`docs/process/decisions-2026-11-04.md` (decisioni e rinvii), `gap-analysis-2026-11-04.md` (requisiti contro codice);
`docs/design/` (UX, design system), `docs/i18n.md`, `README.md`.

## Coda aggiunta il 9 nov (decisioni dell'utente)
Dopo l'agente in corso (scheda Affidabilità separata + rifinitura del report), in quest'ordine:
1. **FATTO il 9 nov (indice incluso): PDF generato dal server** (dettagli in `docs/knowledge/run-install.md`, sezione "PDF del
   report"). Spike riuscito su Fedora 44 (pango 1.57, WeasyPrint 70.0, extra `pdf`; CI ubuntu: apt `libpango-1.0-0
   libpangoft2-1.0-0 poppler-utils`, da verificare al primo giro CI). Porta `ReportRenderer` (`backend/core/ports.py`), adattatore
   `backend/adapters/report_weasyprint.py`, ripulitore `backend/domain/raven/report_html.py`, rotta `backend/api/report_routes.py`.
   Frontend: pulsante primario "Scarica PDF", indice nel componente del report (`ReportToc.svelte`, `reportToc.ts`),
   serializzatore `reportPdf.ts`. Limiti noti: le griglie CSS diventano blocchi (WeasyPrint 70 le impagina male: grafici in una
   colonna), PDF/UA-1 dichiarato ma non validato, Docker senza Pango (ripiego sulla stampa). Da fare: rifinitura grafica (punto 2).
   Testo originale della decisione: scelta tecnica proposta: WeasyPrint (HTML + CSS
   -> PDF) dietro una porta `ReportRenderer`; il frontend invia l'HTML stampabile del report (grafici come SVG/PNG con
   testo alternativo) a `POST /api/raven/report/pdf`; il server lo converte con un recupero di risorse disattivato (solo
   `data:`), HTML ripulito (niente script/iframe/link esterni), limite di dimensione, di velocità e di concorrenza, font
   libero incorporato, metadati (titolo, lingua, autore), segnalibri dai titoli, numeri di pagina, PDF/UA se supportato,
   uscita deterministica. Se le librerie di sistema (Pango) mancano: 503 chiaro e ripiego sulla stampa del browser;
   `install.sh` lo rileva e dice cosa installare (senza sudo automatico). Prima uno spike: verificare che funzioni su
   questa macchina (Fedora) e in CI (Ubuntu); se non è praticabile, fermarsi e riferire.
2. **Rifinitura grafica e accessibilità del PDF** (stesso CSS per stampa e server): tavolozza sobria con una tinta per fase
   e per tipo di contenuto (risultati RAVEN, lavoro proposto non fornito, avvisi, limiti); stati con colore + icona + testo;
   copertina, indice con numeri di pagina, riquadro dei numeri chiave, tabelle a righe alternate con intestazione ripetuta;
   contrasto almeno AA verificato in automatico; prova in scala di grigi e per daltonismo; intestazione/piè di pagina propri
   ("pagina X di Y"); verifica visiva reale (PDF -> immagini, pagine guardate).
3. Idee di modello per dopo: batteria e RF come intervalli (caso peggiore/migliore del carico di trasmissione) al posto di
   "tutto ignoto" dopo il primo passo ignoto.

### Indice del PDF (richiesta del 9 nov)
Il report deve avere un vero **indice** (table of contents) dopo la copertina: fasi 0-F, ESG, affidabilità, legale, appendice e
le sezioni principali, ciascuna con link interno e **numero di pagina**. Nel PDF generato dal server (WeasyPrint) i numeri si
calcolano con `target-counter(attr(href), page)` e i segnalibri vengono dai titoli. Nella stampa del browser (ripiego)
Chrome non supporta `target-counter`: l'indice resta con i link ma senza numeri di pagina, e lo dice. Test: il testo del PDF
contiene l'indice e ogni numero di pagina punta alla pagina in cui compare il titolo (verifica con estrazione per pagina).

## Decisione del 10 nov: chi completa i campi "non forniti" del report
- **Engine:** produce da solo le STIME dei dati non esattamente certi ma stimabili (cronoprogramma, riepilogo di potenza ed
  energia, registro dei rischi dai propri risultati, fasce di costo, CO2e, affidabilità per classe di componente). Forma
  separata "Stima RAVEN": metodo, fonte, tag D/I, intervallo, ingressi usati; non sovrascrive mai un dato dell'utente; esclusa
  dai totali finché l'utente non la accetta; mai presentata come preventivo, LCA o previsione; ingressi ignoti restano ignoti.
- **Assistente IA (RAVEN SI):** solo testo e contenuti più incerti che l'engine non può calcolare (bozze di obiettivi,
  descrizioni, sintesi, traduzioni, proposte da rivedere). Etichettato come proposta con modello, data e digest del contesto.
  L'IA non è mai la fonte di un numero.
- **Né engine né IA:** dati che ha solo il titolare della missione (obiettivi veri, ente legale, autorizzazioni, preventivi,
  prove, approvazioni): restano "da completare".
- Prossimo passo: dopo l'analisi `docs/domain/report-completion.md`, implementare le stime per ordine di valore/costo.
- **Fatto (10 nov, passi 1-4):** modello `EngineEstimate` (`frontend/src/pages/planner/estimates/*`), registro rischi e
  contingenze, matrice requisiti con piani di verifica e AIT deterministici, calendario operativo, bilancio di potenza e
  massa (solo con default dichiarati tag I). Chip/accetta/scarta nel Dossier, riquadro "Stima RAVEN" nel report e nel PDF.
  Test: `estimates/estimates.test.ts` (vitest) ed `e2e/tests/report-estimates.spec.ts`. Stato dettagliato in
  `docs/domain/report-completion.md` sez. 6.
- **Resta (passi 5-6):** banda di costo SSCM (serve massa o classe dichiarata), CO2e a bande, statistiche storiche di
  lancio/atterraggio con fonte, affidabilita' per classe, ridondanza, cassa e inflazione. Da fare con il lavoro sul layout
  del Dossier: le stime stanno oggi in un riquadro in testa al Dossier (minimo, non ridisegnato). Il PDF del server con il
  riquadro non e' stato verificato in e2e (solo stampa del browser). Decisione 6 (stime accettate nel contesto cloud): per
  ora escluse dal contesto SI.

## Richiesta del 10 nov: cursore di scenari predefiniti per i valori ignoti (costi, CO2e, rischio...)
Dopo i passi 1-4 delle stime, aggiungere al Dossier un **cursore con casistiche predefinite** ("classe di missione") per ottenere
un'analisi approssimativa quando l'utente non ha i dati. Progetto:
- Posizioni nominate (non un numero continuo), proposta: 1 rover/payload piccolo, 2 lander commerciale piccolo (classe CLPS,
  default), 3 lander medio, 4 lander grande/classe equipaggio. Ogni posizione = archetipo con massa, classe di lancio, durata e
  configurazione energia/radio dichiarati (tag I) e riferimenti pubblici citati (es. valori pubblici dei contratti CLPS, statistiche
  pubbliche degli atterraggi lunari tentati). Eventuale modificatore "ottimistico/tipico/prudente" sugli intervalli.
- Il cursore alimenta, come "Stima RAVEN" (stato proposta/accettata/scartata, intervallo min-tipico-max, metodo, fonte, ingressi
  usati, limiti di validità), le fasce di: costo per voce, CO2e per fase, bilancio di massa e potenza, probabilità di
  lancio/atterraggio, calendario di sviluppo indicativo. Un valore senza fonte adeguata (es. CO2e del lancio) resta ignoto.
- Onestà: etichetta ben visibile "scenario illustrativo di classe, non una stima della TUA missione né un preventivo"; mai
  sovrascrive i dati dell'utente; esclusa dai totali finché non accettata; chi inserisce i propri dati li vede prevalere.
- Prerequisito: modello EngineEstimate (agente in corso). Richiede ricerca delle fonti pubbliche per ogni archetipo prima di
  scrivere numeri (nessun numero senza fonte).

## Richiesta del 10 nov: due modalità di report (Learn ed Expert) e ridisegno del Dossier
Problema: il passo Dossier è un muro di campi di testo aperti ("non fornito") che riduce intuitività, usabilità e velocità per
l'utente medio. Requisiti del ridisegno:
- **Modalità Learn** (sostituisce il "report breve"): solo i campi e le sezioni strettamente necessari per provare il prodotto e
  capire come funziona un report; il resto è nascosto, non cancellato; testi di spiegazione brevi per ogni sezione; "genera il
  report adesso" funziona senza compilare nulla (l'engine compila ciò che sa, con le stime "Stima RAVEN" e il cursore di
  scenari); il report Learn è corto e didattico (cosa è una fase, cosa sono ignoto/stimato/fornito).
- **Modalità Full report / Expert** (ricercatore): TUTTI i campi e le sezioni selezionati di default, con tutte le sezioni del
  dossier, delle fasi 0-F, ESG, CO2e, affidabilità, legale e appendici; l'utente può deselezionare. È il report completo.
- Collegamento con l'interruttore globale Learning | Avanzato del sito: per default Learn = Learning, Expert = Avanzato, ma
  nel passo Report l'utente può cambiare modalità senza cambiare quella del sito (la scelta resta nello stato persistito).
- Campi aperti: preferire scelte (liste, chip, valori predefiniti) al testo libero; i campi vuoti raggruppati in sezioni chiuse
  "Facoltativo" con un contatore ("12 campi facoltativi da completare"); indicatore di completezza che conta anche le stime
  accettate; niente muro di caselle di testo nella vista Learn.
- Criteri di accettazione: in Learn compaiono al più ~6 domande essenziali e il report si genera con un clic; in Expert tutti i
  campi sono presenti; stessi numeri in entrambi (cambia solo ciò che si vede/include); test e2e per i due percorsi, axe e 390 px.
- **Fatto (10 nov, Learn/Expert):** modalità del report Learn ed Expert, Dossier ridisegnato (4 domande essenziali + soglie in sola
  lettura, "Genera il report adesso" a un clic, "Accetta tutte le stime e genera", gruppi facoltativi chiusi con contatore, indicatore
  di completezza), stesso interruttore nel passo Report, slot vuoto per il cursore di scenari. e2e: `report-modes.spec.ts` (con
  confronto pdftotext Learn/Expert); `mission-planner.spec.ts` apre i gruppi del Dossier. Non fatto: scelte al posto di testo libero
  per giurisdizione/autorità/piani, e il cursore di scenari. Dettagli in `docs/domain/report-completion.md` sez. 7.

## Decisione dell'11 nov: report COMPLETO, il minimo possibile di "ignoto / non fornito"
Richiesta dell'utente: il report non deve lasciare parametri ignoti o "not provided"; il sistema stima tutto correttamente.
Regola adottata (onestà): ogni valore numerico del report ha SEMPRE uno dei tre stati: **provided** (inserito dall'utente),
**computed** (calcolato dall'engine dai risultati), **estimated** (stima dell'engine con ipotesi, tag D/I, intervallo e
fonte dichiarati). Nessun buco: dove l'utente non ha dato un dato e l'engine può stimarlo, la stima compare AUTOMATICAMENTE
nel report, chiaramente etichettata "estimate", con intervallo; i totali mostrano due righe: "declared" e "including RAVEN
estimates (range)". Questo sostituisce la vecchia regola "le stime restano fuori finché non accettate" SOLO per il report
(nel Dossier l'utente può ancora sovrascrivere o scartare ogni stima, e il suo valore prevale sempre).
Cosa resta "da dichiarare dal titolare" e NON si può stimare onestamente: ente legale e giurisdizione, autorizzazioni,
approvazioni, preventivi reali, prove di qualifica, firme. Non sono sparsi per il documento: compaiono in UNA checklist corta
("Items only the mission owner can declare", con il numero) e basta.
Piano: (1) cursore di classe di missione (4 posizioni) come ingresso delle stime; (2) estendere le stime a costi (classi con
fonte: fasce totali), calendario, massa/potenza, affidabilità per classe di componente, rischi, CO2e DERIVATA (es. CO2 del
lancio = massa di propellente × fattore di emissione chimico; produzione = massa per materiale × fattori pubblicati) con
ricerca di fonti per ogni fattore; (3) tolti i "not provided" sparsi, sostituiti da stime o dalla checklist unica; (4) test:
nessun campo numerico del report vuoto, ogni stima ha metodo, ipotesi, intervallo e fonte. Dipende dalla riscrittura del report
in corso (stessi file).

## Feedback dell'utente sul report scaricato (12 nov), da fare dopo l'agente in corso
Report Expert di 32 pagine: troppo lungo, muro di testo. Decisioni:
1. **Sostenibilità e costi automatici dall'engine** (mancano ancora nel report): stime etichettate (provided/computed/estimated)
   con intervallo e fonte, ingresso = cursore di classe di missione; CO2e derivata (propellente x fattore di combustione;
   materiali x fattori pubblicati); costi con le fasce che hanno una fonte; due righe di totali (dichiarato / con stime).
2. **Togliere definitivamente la parte legale**: sezione 'Valutazione legale e regolatoria', i 7 campi legali del dossier, le
   voci legali dell'indice e dell'ESG. Resta solo UNA riga di limiti/dichiarazione nella parte 4 (assunzione: non è la sezione
   legale; se l'utente intende rimuovere anche quella riga, lo dica).
3. **Registro dei rischi**: da 29 righe a un massimo di 5 rischi UTILI, unificati fra A e B, in parole semplici
   (esempio reale: B, il terreno lontano chiude il link per 105 ore su 168; B, 63 ore fuori dal modello = ignoto; A, 33 ore in
   modalità sopravvivenza). Via le righe di stato di validazione per stadio (stanno già nella parte 4 e nella pagina Modello),
   via i percorsi interni (evaluations[1].inputs_state...) e il blocco 'Inputs used' (vanno solo nel JSON esportato). In Learn
   al massimo 3 punti. Decidere onestamente se la sezione serve: se resta, mezza pagina.
4. **Grafici**: verificare se mancano grafici per contestualizzare il confronto fra i due siti nelle varie fasi del Planner
   (Sole, Terra/DSN, margine radio, batteria, stati della missione nel tempo, affidabilità nel tempo, finestre utili A/B) e
   che tutte le variabili siano rappresentate correttamente (unità, assi, ignoto distinto da zero); aggiungere solo grafici
   nel tempo giustificati, uno per domanda.
5. **Audit generale della lunghezza** dell'Expert (32 pagine): per ogni appendice dire se serve; togliere ogni elenco di dati
   interni; obiettivo: Expert <= ~15 pagine, Learn <= 4.
