---
id: site-finder
title: Trova i siti migliori (ricerca automatica)
kind: page
summary: >-
  Il pannello "Find the best sites" della pagina Siti cerca da solo, nella regione polare sud, i luoghi che meglio
  soddisfano una missione descritta a parole. Il testo diventa un brief modificabile; il core RAVEN valuta i luoghi
  promettenti scelti da un predittore leggero; per ogni sito proposto mostra i valori del core, la previsione del predittore
  con il suo intervallo e la probabilita' di raggiungere gli obiettivi (tag I, stime).
tags: [ricerca siti, trova siti, brief, predittore, surrogato, probabilita', intervallo, non confrontabile, idoneita', sovramappe, tag I, polo sud]
applies_to: [siti]
related: [page-siti, model-validation]
level: intermedio
lang: it
last_verified: 2026-11-12
sources:
  - {ref: frontend/src/shell/finder/SiteFinder.svelte, supports: "pannello, brief editabile, tabella dei risultati, colonne e testi"}
  - {ref: backend/api/raven_brief.py, supports: "campi del brief e parser a regole in italiano e inglese"}
  - {ref: backend/api/raven_llm.py, supports: "livello opzionale del modello: solo cio' che il testo supporta, consenso per il servizio online"}
  - {ref: backend/api/raven_discover.py, supports: "lavoro asincrono, valutatore = core su terreno 240 m dalle tessere in cache, uno alla volta"}
  - {ref: backend/domain/raven/discovery/search.py, supports: "apprendimento attivo, celle non confrontabili, distanza minima, proposte"}
  - {ref: backend/domain/raven/discovery/surrogate.py, supports: "predittore: media fisica piu' correzione gaussiana, intervalli conformal"}
  - {ref: backend/domain/raven/discovery/uncertainty.py, supports: "parametri di tag I variati, probabilita' con intervallo di Wilson"}
  - {ref: docs/design/site-discovery-plan.md, supports: "regole: il core decide, nessun punteggio unico, ignoto resta ignoto"}
---
## A cosa serve
Invece di scegliere i siti a mano, descrivi la missione ("14 giorni da aprile 2027, almeno il 60 % di Sole, 5 siti vicino al
polo sud") e RAVEN cerca i luoghi migliori. Il risultato non e' una garanzia: e' una classifica sotto ipotesi dichiarate.

## Come si usa
1. Scrivi la richiesta e premi "Read my request". Le regole leggono date, giorni, percentuali di Sole e di radio, bit rate,
   quanti siti e la zona. Cio' che il testo non dice resta vuoto: non viene inventato. Richieste che il motore non sa trattare
   (acqua, ghiaccio) sono elencate come "non supportate" e ignorate.
2. Controlla e correggi il brief: e' la scheda con i valori. Servono almeno la data di inizio e i giorni.
3. Premi "Find sites". La ricerca gira sul server (circa un minuto) con una barra di avanzamento. Una sola ricerca alla volta.
4. Leggi la tabella e, se vuoi, scegli lo strato "Search result (suitability)" nel pannello delle sovramappe per vedere la nuvola
   sulla Luna 3D.

## Come funziona (in breve)
- **Candidati:** le celle della regione polare sud, con caratteristiche ricavate dalle sovramappe (quota, pendenza, Sole,
  Terra, Sole e Terra insieme, notte e blackout piu' lunghi) calcolate **sulla tua finestra di date**.
- **Predittore:** un modello leggero stima le metriche del core. Serve solo a scegliere dove guardare.
- **Core:** ogni sito proposto e' stato valutato dal core RAVEN, tutti sullo stesso terreno (LOLA 240 m) per poterli confrontare.
- **Probabilita':** il core e' deterministico per un insieme di parametri; i parametri illustrativi (area del pannello, batteria,
  carico, guadagno d'antenna, perdite) hanno una incertezza ASSUNTA. Si valutano 12 insiemi di parametri per sito e si conta
  quanti rispettano gli obiettivi. L'intervallo e' di Wilson al 90 %: dice quanto sono pochi i campioni.

## Dal messaggio al resoconto (la catena completa)
1. Scrivi la richiesta nella chat: se chiede di trovare siti si apre questa scheda con il brief gia' compilato.
2. **Conferma:** controlla e correggi il brief. Non parte nessuna ricerca finche' non premi "Confirm and find sites".
3. La ricerca gira come job (circa 90 s) e produce la nuvola: i siti, il fronte di Pareto, la probabilita' con il suo intervallo.
4. **Resoconto finale:** sopra la tabella un breve testo dice qual e' il sito migliore. Lo sceglie il motore (primo della classifica:
   probabilita' di rispettare gli obiettivi, poi tempo utile). Il modello, se disponibile, lo spiega soltanto: il testo si usa solo se
   nomina quel sito e non usa numeri che non siano nei risultati; altrimenti si mostra il testo del motore.
5. Il modello locale (Ministral 3B, installabile con `./install.sh --with-llm`) parte da solo alla prima richiesta, se la memoria
   libera e' almeno 4 GB, e si ferma dopo 5 minuti di inattivita'. Senza modello tutto funziona con regole e testo del motore.

## Dentro il Mission Planner (senza aprire la chat)
Nel passo "Siti" del Mission Planner c'e' il riquadro "Trova i siti automaticamente". Si apre, il periodo del planner (data e giorni)
e' gia' nel brief, e basta premere "Find sites" (oppure descrivere la missione per compilare gli altri campi). Nella tabella ogni sito ha
"Usa come A" e "Usa come B"; "Usa i primi due come A e B" li assegna in un colpo solo. Il periodo della ricerca sostituisce quello del
planner (se rientra nell'intervallo delle effemeridi), cosi' i siti sono valutati nella finestra per cui sono stati scelti. Un sito che
coincide con uno del catalogo (stesse coordinate a 0,01 gradi) e' usato cosi' com'e'; gli altri diventano siti personalizzati.

## Cosa significano i numeri
- "Useful", "Sun", "Radio": valori del core per quel sito e quella finestra.
- "Predicted useful": cio' che il predittore, senza vedere quel sito, avrebbe detto, con il suo intervallo. Se l'intervallo e'
  "Unknown" il predittore non sa dirlo. Intervalli larghi sono normali con poche valutazioni.
- "Probability of meeting them": quota di insiemi di parametri in cui gli obiettivi sono rispettati. Un "Unknown" significa che
  non e' stata calcolata, non che sia zero.
- Un luogo "non confrontabile" non ha un valore (per esempio mancano le tessere di terreno nella cache): non e' in classifica.

## Limiti da ricordare
- Solo la regione polare sud (da 75 gradi sud in giu'); altrove la ricerca non e' verificata dal core.
- Terreno a 240 m: il rilievo piu' piccolo non e' risolto. Radio, energia e batteria sono parametri illustrativi (tag I).
- Gli intervalli dei parametri sono ipotesi, non misure. Le sovramappe non sono validate contro prodotti NASA.
- Il modello linguistico, se lo attivi, compila solo i campi che le regole non hanno capito e solo con valori scritti nel tuo testo;
  il servizio online e' usato solo se lo consenti in modo esplicito. Modelli di organizzazioni cinesi o russe sono rifiutati.
