---
id: page-telemetry
title: Pagina Telemetria
kind: page
summary: >-
  La pagina Telemetria mostra l'ultimo campione ricevuto, un grafico di potenza e margine di link
  nel tempo e la tabella degli ultimi campioni, alimentati dallo stream SSE /api/telemetry/stream.
  Permette anche di importare campioni del link e confrontarli con una previsione RAVEN.
tags: [pagina, telemetria, telemetry, grafico, potenza, margine di link, campioni, SSE]
applies_to: [telemetry, laboratorio]
related: [telemetry-contract, glossary-link-margin, link-budget]
level: principiante
lang: it
last_verified: 2026-10-29
sources:
  - {ref: frontend/src/pages/telemetry/Telemetry.svelte, supports: "sezioni Ultimo campione, Andamento, Ultimi campioni"}
  - {ref: frontend/src/pages/telemetry/LinkCsv.svelte, supports: "importazione e confronto dei campioni del link"}
  - {ref: frontend/src/pages/telemetry/linkComparison.ts, supports: "interpolazione delle previsioni, residui e statistiche"}
  - {ref: backend/api/routes.py, supports: "GET /api/telemetry/stream (SSE) e replay da CSV"}
---
## Cosa si vede

- **Ultimo campione**: i valori piu' recenti (potenza in W, margine di link in dB, azimut ed elevazione di Sole e Terra in gradi se presenti).
- **Andamento**: grafico di potenza e margine di link nel tempo.
- **Ultimi campioni**: tabella dei campioni recenti.

I dati arrivano da `GET /api/telemetry/stream` (SSE). Con `TELEMETRY_CSV` il backend rilancia un CSV;
i campi sono descritti nel [contratto di telemetria](kb:telemetry-contract). Il flusso non specifica la provenienza:
i campioni non vanno presentati come misure reali senza conferma della sorgente. "Spiega questa pagina" riceve lo stato
del flusso e l'ultimo campione visibile, con provenienza non specificata.

## Confronto del link

Il CSV caricato nel browser richiede le colonne `t_utc`, `link_margin_db`, `earth_el_deg`, `rate_bps`:
gli istanti sono UTC con `Z` e strettamente crescenti. Limiti: 1 MB e 2000 campioni. Il sito è scelto
dall'utente; la stazione, il guadagno e k vengono dallo scenario condiviso, gli altri parametri radio dai
valori illustrativi predefiniti. Il file e i valori non vengono inviati al server; la richiesta di previsione
invia il sito e l'intervallo temporale. Se si interroga l'assistente, il riepilogo visibile include anche
l'istante e il margine dell'ultimo campione e alcune statistiche del confronto.

La previsione è calcolata per le velocità supportate dal modello e interpolata linearmente fra punti: può
non cogliere variazioni rapide. I campioni senza previsione o con velocità non supportate sono esclusi.
Il residuo è margine del campione meno margine previsto; bias e RMSE sono calcolati sui campioni confrontati.
La copertura entro ±k·sigma usa il sigma ipotizzato dal modello, non un'incertezza misurata. Le sequenze
di margine negativo contano i campioni consecutivi sotto zero, non la durata delle interruzioni.

L'esempio dimostrativo è generato dal modello con rumore: **non è una misura** e il confronto con lo stesso
modello non ne costituisce una validazione. Anche per un CSV importato la provenienza non è verificata.
