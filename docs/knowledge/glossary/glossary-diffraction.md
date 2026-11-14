---
id: glossary-diffraction
title: "Diffrazione (bordo a lama)"
kind: glossary
summary: "Il segnale radio si piega attorno allo spigolo di un ostacolo: dietro un crinale arriva comunque, indebolito. La perdita J(nu) cresce con nu, l'altezza della cima sopra la linea di vista in unita' di zona di Fresnel."
tags: ["diffrazione", "bordo a lama", "knife edge", "nu", "crinale", "si piega", "J(nu)"]
applies_to: [simula, grazinglink, wave]
related: [glossary-fresnel-zone, glossary-link-margin, page-simula]
level: principiante
lang: it
last_verified: 2026-10-27
sources:
  - {ref: "backend/domain/grazing/diffraction.py", supports: "perdita esatta del bordo a lama con gli integrali di Fresnel (JPL 42-226 eq. 38) e nu > 0 se la cima sta sopra la linea di vista (eq. 39)"}
  - {ref: "frontend/src/pages/simula/linkModel.ts", supports: "stessa formula nel browser, parita' con il motore entro 0,01 dB"}
  - {ref: "docs/domain/grazinglink-model.md", supports: "valori di controllo T1: J(0) = 6,02 dB, J(1) = 13,86 dB, J(2,4) = 20,62 dB"}
---
## In una riga

Diffrazione: il segnale si piega attorno allo spigolo. Ancora piu' semplice: come il suono che senti da dietro un
muro, la radio arriva anche se il crinale copre la Terra, ma piu' debole.

## Nel sito

Il parametro nu misura quanto la cima sta sopra (nu > 0) o sotto (nu < 0) la linea di vista. Esempi del modello:
nu = -1 da' -1,0 dB (un piccolo guadagno, oscillazioni di Fresnel), nu = 0 (cima sulla linea di vista) 6,02 dB,
nu = 1 13,86 dB, nu = 2,4 20,62 dB. In Simula lo stato "Transizione" (ambra) vuol dire proprio questo: il crinale
copre la Terra ma il link chiude per diffrazione. La cresta arrotondata aggiunge il termine T(m,n) di ITU-R P.526-9
(formula verificata sul testo, non misurata); la tabella split-step simulata e' il confronto e da' l'incertezza.
