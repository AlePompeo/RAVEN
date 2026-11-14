---
id: page-model
title: Pagina Modello e validazione
kind: page
summary: >-
  La pagina Modello e validazione (/model, alias /validation) mostra la catena RAVEN di otto stadi (S0-S7) costruita
  dal server: per ogni stadio lo stato di validazione (verificato, solo plausibilita', non validato, ignoto) con colore,
  testo e icona, cosa si controlla, contro cosa, lo scarto, cosa NON e' coperto, le prove (test e documenti) e la
  frase ammessa. In Avanzato aggiunge la tabella filtrabile dei parametri (tag V, D, I) e l'esportazione JSON della
  matrice; in Learning un riassunto in parole semplici e un semaforo. Contiene i comandi per riprodurre e i punti
  aperti. Senza server (503) non mostra nulla di inventato.
tags: [pagina, modello, validazione, RAVEN, stadi, S0-S7, semaforo, matrice di validazione, parametri, tag V D I, riprodurre, punti aperti, 503, esportazione JSON]
applies_to: [model]
related: [model-validation, page-compare]
level: intermedio
lang: it
last_verified: 2026-11-10
sources:
  - {ref: frontend/src/pages/model/Model.svelte, supports: "stadi espandibili, chip di stato, prove, tabella dei parametri con filtri, comandi, punti aperti, stati di caricamento e 503"}
  - {ref: frontend/src/pages/planner/reportFormulas.ts, supports: "registro unico delle formule e delle variabili, usato dalla parte 3 del report e dalla sezione Le formule"}
  - {ref: frontend/src/pages/model/model.ts, supports: "stato peggiore per stadio, filtri dei parametri, esportazione JSON"}
  - {ref: backend/api/raven_routes.py, supports: "GET /api/raven/model, /api/raven/validation e /api/raven/parameters, sorgente di tutti i dati di stato"}
  - {ref: backend/domain/raven/validation.py, supports: "voci di validazione per stadio con fonte, scarto, evidenza, cio' che non e' coperto e frase ammessa"}
---
## Cosa fa

La pagina legge `GET /api/raven/model` (stadi, ingressi di ogni stadio, limiti dichiarati e matrice di validazione) e,
in modalita' Avanzato, `GET /api/raven/parameters`. Gli stati e le prove non sono scritti nel frontend: se il
server non risponde mostra un avviso (503 o altro errore) e nient'altro, mai una tabella inventata.

## Come leggerla

Ogni stadio ha un chip: **Verificato** (spunta, verde), **Solo plausibilita'** (tilde, ambra), **Non validato**
(croce, rosso), **Ignoto** (punto interrogativo, grigio tratteggiato). Lo stato dello stadio e' il peggiore tra i suoi
controlli. Aprendo uno stadio si vedono la frase ammessa per descrivere il risultato e, in Avanzato, cosa si
controlla, contro cosa, lo scarto, cosa non e' coperto e i percorsi di test e documenti. Nessuna riga e' una misura
radio o di potenza sulla Luna.

## Learning e Avanzato

In **Learning** ogni stadio ha un riassunto in parole semplici e il semaforo con il conteggio dei controlli per stato.
In **Avanzato** compaiono le prove complete, la tabella dei parametri (filtri per stadio, tag e testo; fonte, unita' e
intervallo) e il pulsante che scarica la matrice di validazione in JSON. I numeri sono gli stessi nelle due modalita'.

## Le formule

La sezione "Le formule" elenca le undici formule del motore (tempo utile, passo utile, propagazione dell'ignoto, quote
Sole/Terra/RF, disco solare, potenza, batteria, perdita in spazio libero, margine di link, diffrazione, affidabilita')
con le variabili, i significati e le unita'. Viene dallo stesso registro (`frontend/src/pages/planner/reportFormulas.ts`)
che alimenta la parte 3 del report di missione: il testo e' identico e in inglese in entrambe le lingue del sito. Il chip
di ogni formula e' lo stato di validazione piu' debole degli stadi che usa.

## Riproduzione e punti aperti

Il blocco "Come riprodurre" elenca i comandi (installazione, test, golden, arbitro
dell'orizzonte, misura del terreno lontano). I punti aperti: validazione assoluta RF, politica della cresta
arrotondata, carichi energetici illustrativi, soglia di 30 dB del terreno lontano (D4), copertura DEM.
