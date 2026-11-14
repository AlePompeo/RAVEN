---
id: glossary-link-margin
title: "Margine di collegamento (link margin)"
kind: glossary
summary: "Differenza in dB tra il livello di segnale (o il rapporto segnale/rumore) ottenuto e quello minimo richiesto; positivo = il collegamento regge con scorta."
tags: ["link margin", "margine", "scorta", "soglia", "link_margin_db"]
applies_to: [telemetry]
related: [link-budget, glossary-db, telemetry-contract]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: "contracts/telemetry.schema.json", supports: "campo opzionale link_margin_db di tipo number"}
  - {ref: "conoscenza generale di dominio (non verificata dal repository)", supports: "significato fisico del margine"}
---
## Definizione (conoscenza generale)

Margine = disponibile - richiesto, in dB. Se e' negativo il collegamento non e' garantito.

## Nel sito

Il campo `link_margin_db` della telemetria porta questo valore in dB come lo fornisce la sorgente; il sito lo mostra nel grafico della pagina Telemetria ma non lo calcola.
