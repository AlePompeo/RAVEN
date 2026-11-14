---
id: glossary-azimuth
title: "Azimut"
kind: glossary
summary: "Angolo orizzontale di una direzione, in gradi, misurato dal nord in senso orario (0 = nord, 90 = est, 180 = sud, 270 = ovest). Nel contratto di telemetria il campo e' az_deg."
tags: ["azimut", "azimuth", "az_deg", "direzione", "nord", "gradi"]
applies_to: [telemetry, viewer]
related: [glossary-elevation, az-el-convention]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: "frontend/src/viewports/scene.ts", supports: "azElToVector: azimut 0 = nord, orario"}
  - {ref: "contracts/telemetry.schema.json", supports: "az_deg dentro sun e earth"}
---
## Convenzione del sito

L'azimut `az_deg` e' in gradi con 0 = nord, crescente in senso orario; la conversione in vettore 3D e' in `azElToVector` (vedi [convenzione az/el](kb:az-el-convention)).
