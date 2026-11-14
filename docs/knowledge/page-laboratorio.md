---
id: page-laboratorio
title: Pagina Laboratorio
kind: page
summary: >-
  Laboratorio e' la pagina degli strumenti per chi vuole andare a fondo: una scheda porta alla Telemetria (i dati del
  collegamento in diretta) e una alle Simulazioni (i plugin del backend da eseguire con i propri valori). Le due
  pagine restano rotte vere (/telemetry e /sims) e nella barra di navigazione evidenziano la voce Laboratorio.
tags: [pagina, laboratorio, strumenti, telemetria, simulazioni, plugin, ricerca, Learning, Avanzato]
applies_to: [laboratorio]
related: [page-telemetry, page-sims]
level: principiante
lang: it
last_verified: 2026-10-27
sources:
  - {ref: frontend/src/pages/laboratorio/Laboratorio.svelte, supports: "schede Telemetria e Simulazioni con una riga di spiegazione; dettagli tecnici solo in Avanzato"}
  - {ref: frontend/src/pages/telemetry/index.ts, supports: "rotta /telemetry fuori dalla barra, sezione Laboratorio"}
  - {ref: frontend/src/pages/sims/index.ts, supports: "rotta /sims fuori dalla barra, sezione Laboratorio"}
---
## Cosa contiene

- **Telemetria**: potenza, margine di link e posizione di Sole e Terra che arrivano in diretta, con grafico e tabella.
  Dettagli in [page-telemetry](kb:page-telemetry).
- **Simulazioni**: scegli una simulazione, scrivi i valori degli ingressi e premi Esegui. Dettagli in [page-sims](kb:page-sims).

In Learning ogni scheda ha una riga semplice; in Avanzato anche cosa c'e' sotto (flusso SSE dal backend con il
contratto telemetry, plugin descritti da un manifest con ingressi validati).
