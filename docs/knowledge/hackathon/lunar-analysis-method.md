---
id: lunar-analysis-method
title: Metodo dell'analisi lunare e come leggere i risultati
kind: method
summary: >-
  Il motore di efemeridi validato (JPL DE440, confronto con Horizons) da' Sole e Terra visti dal sito e la Luna vista dai tre complessi DSN; su questi si calcolano visibilita' con maschera, energia solare con batteria, margine di collegamento e ore utili. Tutto e' un potenziale nelle ipotesi dichiarate con orizzonte piatto, senza atmosfera e con link budget semplificato.
tags: [metodo, analisi, siti, date, Sole, Terra, DSN, orizzonte piatto, limiti, ipotesi, illustrativo, librazione]
applies_to: [home, chat]
related: [nasa-lunar-problem, lunar-link-budget, lunar-energy-model, lunar-mission-hours, lunar-ranking-score, ephemeris-method, glossary-libration]
level: intermedio
lang: it
last_verified: 2026-10-20
sources:
  - {ref: docs/domain/method.md, supports: "formule, unita', ipotesi con fonte, limiti, esempio svolto"}
  - {ref: docs/domain/validation.md, supports: "che cosa e' stato validato e come, errori misurati, che cosa NON e' validato"}
  - {ref: docs/domain/assumptions.md, supports: "tabella delle ipotesi con fonti"}
  - {ref: scripts/raven_reference/lunar_routes.py, supports: "oracolo storico delle API /api/lunar, disponibile solo nei test"}
  - {ref: backend/api/retired_routes.py, supports: "ritiro delle API storiche con HTTP 410"}
---
## Stato del documento

Questo e' il metodo storico con orizzonte piatto, conservato come oracolo dei test, non il motore
del sito attuale. Le API `/api/lunar/*` sono ritirate (410). Per la valutazione di missione usare
`/api/raven/evaluate` e [Modello RAVEN e validazione](kb:model-validation).

## Passi

1. Geometria: azimut, elevazione e distanza di Sole e Terra da ogni sito (un calcolo vettoriale per sito) e elevazione della Luna dai complessi DSN di Goldstone, Canberra e Madrid.
2. Visibilita': Sole su se il bordo superiore del disco (centro + 0.27 gradi) supera la maschera; Terra visibile se il centro supera la maschera; Luna visibile dalla Terra se supera 6 gradi ad almeno uno dei tre complessi.
3. Energia: potenza del pannello e simulazione della batteria ([modello energetico](kb:lunar-energy-model)).
4. Collegamento: [link budget](kb:lunar-link-budget) con la distanza reale a ogni passo.
5. [Ore utili](kb:lunar-mission-hours) e [classifica](kb:lunar-ranking-score).

## Limiti da dire sempre

- Orizzonte locale piatto con maschera di elevazione, senza terreno. Ai poli l'illuminazione reale dipende dalla topografia.
- Nessuna atmosfera ne' rifrazione.
- Link budget semplificato: spazio libero, G/T costante, nessun guadagno di codifica verificato.
- I parametri etichettati "illustrative" non hanno fonte e vanno sostituiti con i dati del cliente.
- I risultati sono "potenziale nelle ipotesi dichiarate", non una previsione.
