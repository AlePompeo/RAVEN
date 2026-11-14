---
id: glossary-db
title: "Decibel (dB)"
kind: glossary
summary: "Unita' logaritmica per rapporti di potenza: x_dB = 10*log10(P1/P2). Rapporti di ampiezza usano 20*log10."
tags: ["dB", "decibel", "logaritmo", "rapporto di potenza"]
applies_to: [telemetry, fspl-c]
related: [fspl, glossary-link-margin]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: "contracts/telemetry.schema.json", supports: "il suffisso _db dei campi (es. link_margin_db) indica decibel"}
  - {ref: "backend/plugins/fspl_c/fspl.c", supports: "fspl_db e' in dB"}
---
## Definizione (conoscenza generale)

Il decibel esprime un rapporto in scala logaritmica: 10 dB = fattore 10 in potenza, 3 dB circa un fattore 2 (10*log10(2) = 3.01 dB). Somme e sottrazioni in dB corrispondono a prodotti e rapporti lineari, per questo i link budget si fanno in dB.

## Nel sito

I nomi dei campi portano l'unita': `link_margin_db` e `fspl_db` sono in dB.
