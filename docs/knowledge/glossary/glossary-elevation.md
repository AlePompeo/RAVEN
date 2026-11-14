---
id: glossary-elevation
title: "Elevazione"
kind: glossary
summary: "Angolo verticale di una direzione sopra l'orizzonte, in gradi: 0 = orizzonte, 90 = zenit, valori negativi = sotto l'orizzonte. Nel contratto di telemetria il campo e' el_deg."
tags: ["elevazione", "elevation", "el_deg", "orizzonte", "zenit", "gradi"]
applies_to: [telemetry, viewer]
related: [glossary-azimuth, az-el-convention]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: "frontend/src/viewports/scene.ts", supports: "azElToVector: la componente verticale e' sin(elevazione); describeScene segnala el_deg < 0 come sotto l'orizzonte"}
---
## Convenzione del sito

L'elevazione `el_deg` e' in gradi; un valore negativo significa che l'astro e' sotto l'orizzonte (la descrizione testuale della scena lo segnala). Vedi [convenzione az/el](kb:az-el-convention).
