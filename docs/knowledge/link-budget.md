---
id: link-budget
title: Link budget e margine di collegamento
kind: concept
summary: >-
  Il link budget somma guadagni e sottrae perdite lungo un collegamento radio per stimare il
  segnale che arriva al ricevitore; il margine di collegamento e' lo scarto in dB rispetto al
  minimo necessario. CONOSCENZA GENERALE di dominio, non una funzione implementata dal sito.
tags: [link budget, margine, link margin, EIRP, G/T, Eb/N0, dB, collegamento, general knowledge]
applies_to: [telemetry, fspl-c]
related: [fspl, glossary-eirp, glossary-gt, glossary-link-margin, glossary-ebn0, glossary-db]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: backend/plugins/fspl_c/fspl.c, supports: "unico termine del link budget calcolato dal sito: la perdita nello spazio libero"}
  - {ref: contracts/telemetry.schema.json, supports: "il campo opzionale link_margin_db (dB) nella telemetria"}
  - {ref: docs/ml.md, supports: "il dataset sintetico del predittore usa 40 + 10 log10(power_w) - 20 log10(distance_km/1000) + rumore come link_margin_db"}
---
## Idea (conoscenza generale, non dal sito)

Un link budget e' un bilancio in dB: potenza irradiata (EIRP) piu' guadagno in ricezione,
meno le perdite (la principale e' l'[FSPL](kb:fspl), poi atmosfera, pioggia, puntamento), da
confrontare con la soglia richiesta dal ricevitore. Il **margine** e' la differenza: positivo
significa che il collegamento regge con scorta. Questa descrizione e' standard di dominio; il sito
non implementa un link budget completo.

## Cosa c'e' davvero nel sito

- La simulazione `fspl-c` calcola solo il termine di perdita nello spazio libero.
- La telemetria puo' portare `link_margin_db` (dB), un numero fornito dalla sorgente: il sito non lo calcola.
- Il dataset sintetico di `predictor-baseline` genera `link_margin_db` con una formula illustrativa
  (vedi `docs/ml.md`), non con un link budget fisico reale.
