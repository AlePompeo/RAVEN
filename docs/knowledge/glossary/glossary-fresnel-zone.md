---
id: glossary-fresnel-zone
title: "Zona di Fresnel"
kind: glossary
summary: "Il tubo attorno alla linea di vista che il segnale usa davvero: raggio r1 = sqrt(lambda d1 d2 / (d1 + d2)), circa 8,4 m a 2 km in banda X. Se il crinale lo tocca il segnale si indebolisce."
tags: ["zona di Fresnel", "Fresnel", "tubo", "r1", "linea di vista", "ostruzione"]
applies_to: [simula, lander, grazinglink]
related: [glossary-diffraction, glossary-link-margin, page-simula]
level: principiante
lang: it
last_verified: 2026-10-27
sources:
  - {ref: "backend/domain/grazing/diffraction.py", supports: "fresnel_zone_radius_m: sqrt(n lambda d1 d2 / (d1 + d2)), CB79 sez. 2.3 eq. (2) p. 43"}
  - {ref: "docs/domain/grazinglink-model.md", supports: "valori T6: r1 = 8,449 m a d1 = 2000 m, lambda = 0,035690 m, d2 = 384 400 km"}
---
## In una riga

Zona di Fresnel: il "tubo" attorno alla linea retta tra antenna e Terra in cui viaggia quasi tutta l'energia del
segnale. Ancora piu' semplice: il segnale non e' un filo sottile ma un tubo; se il crinale ne morde un pezzo, arriva
meno segnale.

## Formula ed esempio

r1 = sqrt(lambda d1 d2 / (d1 + d2)) [m], con lambda lunghezza d'onda [m], d1 distanza dell'ostacolo [m], d2 distanza
dalla Terra [m]. Esempio: banda X (lambda = 0,03569 m), crinale a d1 = 2000 m, Terra a d2 = 384 400 km:
r1 = sqrt(0,03569 x 2000) = 8,45 m. In Simula il tubo e' disegnato con raggio x20 (solo nel disegno; i numeri usano
il valore vero).
