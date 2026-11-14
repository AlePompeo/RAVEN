---
id: glossary-terminator
title: "Terminatore"
kind: glossary
summary: "Linea che separa la parte illuminata dalla parte in ombra di un corpo celeste (per esempio la Luna). Vicino al terminatore le ombre sono lunghe e i rilievi risaltano."
tags: ["terminatore", "terminator", "giorno notte", "ombra", "Luna", "illuminazione"]
applies_to: [viewer, home]
related: [az-el-convention]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: "conoscenza generale di dominio (non verificata dal repository)", supports: "definizione di terminatore"}
  - {ref: "frontend/src/viewports/canvas2dViewport.ts", supports: "il viewport 2D disegna un terminatore morbido"}
---
## Definizione (conoscenza generale)

Il terminatore e' il confine giorno/notte su un corpo illuminato dal Sole.

## Nel sito

Il viewport 2D (`canvas2dViewport.ts`) disegna un terminatore morbido con una luce ambiente minima; la posizione del Sole nella scena segue [azimut ed elevazione](kb:az-el-convention).
