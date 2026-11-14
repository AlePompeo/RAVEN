---
id: glossary-libration
title: "Librazione"
kind: glossary
summary: "Lieve oscillazione apparente della Luna vista dalla Terra (fino a circa 7 gradi in longitudine e in latitudine) che fa vedere un po' del lato nascosto e muove la Terra attorno all'orizzonte dei siti polari."
tags: ["librazione", "libration", "Terra", "orizzonte", "siti polari", "sub-Earth point"]
applies_to: [home, chat]
related: [lunar-mission-hours, lunar-analysis-method]
level: intermedio
lang: it
last_verified: 2026-10-20
sources:
  - {ref: "docs/domain/phase-a-report.md", supports: "librazione massima della scansione 2026-2028: +6.83 gradi in latitudine, +7.63 gradi in longitudine"}
  - {ref: "tests/backend/domain/test_lunar_behaviour.py", supports: "elevazione della Terra dai siti in funzione della librazione, derivata dalla geometria"}
  - {ref: "conoscenza generale di dominio (non verificata dal repository)", supports: "cause della librazione"}
---
## Definizione (conoscenza generale)

La Luna mostra sempre lo stesso lato, ma orbita ellittica e asse inclinato fanno oscillare il punto della
Luna sotto la Terra (punto sub-Terra).

## Nel sito

Da un sito vicino al polo la Terra e' vicina all'orizzonte e, con la librazione in latitudine di ciclo
27.2 giorni, sale e scende rispetto a un orizzonte piatto: e' visibile solo per una parte del tempo.
Da Apollo 11 l'elevazione della Terra resta tra circa 58 e 73 gradi.
