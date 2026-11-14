---
id: glossary-soc
title: "Stato di carica (SOC)"
kind: glossary
summary: "Frazione della capacita' della batteria che e' ancora carica, da 0 (vuota) a 1 (piena). Nell'analisi lunare il SOC minimo raggiunto indica se la batteria regge la notte."
tags: ["SOC", "state of charge", "stato di carica", "batteria", "notte lunare", "riserva"]
applies_to: [home, chat]
related: [lunar-energy-model]
level: principiante
lang: it
last_verified: 2026-10-20
sources:
  - {ref: "backend/domain/lunar/energy.py", supports: "il SOC e' energia immagazzinata divisa per la capacita'"}
  - {ref: "conoscenza generale di dominio (non verificata dal repository)", supports: "definizione di stato di carica"}
---
## Definizione (conoscenza generale)

SOC = energia immagazzinata / capacita' della batteria.

## Nell'analisi lunare

Sotto la riserva `min_soc` (default 0.2, illustrativo) il sito passa al carico di sopravvivenza; se
la batteria arriva a 0 il carico non e' servito. Vedi il [modello energetico](kb:lunar-energy-model).
