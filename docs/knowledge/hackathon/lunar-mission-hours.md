---
id: lunar-mission-hours
title: Ore di missione utili (potenziale nelle ipotesi dichiarate)
kind: formula
summary: >-
  Un passo temporale e' utile se ci sono insieme energia disponibile, Terra visibile dal sito, Luna visibile da almeno una stazione DSN e margine di collegamento sufficiente. Ore utili = passi utili per la durata del passo; si riportano anche la frazione, il buco piu' lungo e il numero di finestre.
tags: [ore di missione, ore utili, finestre, visibilita', DSN, margine, Sole, Terra, Luna, siti]
applies_to: [home, chat]
related: [nasa-lunar-problem, lunar-link-budget, lunar-energy-model, lunar-ranking-score, glossary-link-margin]
level: intermedio
lang: it
last_verified: 2026-10-20
sources:
  - {ref: backend/domain/lunar/mission.py, supports: "definizione di passo utile e metriche per sito"}
  - {ref: backend/domain/lunar/runs.py, supports: "lunghezza delle sequenze (finestre e buchi)"}
  - {ref: tests/backend/domain/test_lunar_mission.py, supports: "confronto esatto con una reimplementazione scalare indipendente"}
  - {ref: tests/backend/domain/test_lunar_knowledge.py, supports: "l'esempio svolto qui sotto e' confrontato con l'uscita reale del codice"}
  - {ref: docs/domain/method.md, supports: "definizione, ipotesi e limiti"}
expression: "useful_i = power_i AND earth_i AND dsn_i AND (margin_i >= required);  useful_hours = dt_h * sum_i useful_i;  useful_fraction = useful_hours / (N * dt_h)"
variables:
  - {symbol: power_i, name: energia disponibile al passo i, unit: "-", range: "0 o 1"}
  - {symbol: earth_i, name: Terra sopra la maschera del sito, unit: "-", range: "0 o 1"}
  - {symbol: dsn_i, name: Luna sopra 6 gradi ad almeno uno dei tre complessi DSN, unit: "-", range: "0 o 1"}
  - {symbol: margin_i, name: margine di collegamento al passo i, unit: dB, range: "qualsiasi"}
  - {symbol: required, name: margine richiesto, unit: dB, range: "0 .. 20 (default 3)"}
  - {symbol: dt_h, name: durata del passo, unit: h, range: "0.1667 .. 24"}
  - {symbol: N, name: numero di passi della finestra, unit: "-", range: ">= 1"}
assumptions:
  - ogni passo vale per l'intervallo che parte dall'istante campionato
  - la Terra e' visibile se il suo centro e' sopra la maschera (il disco di circa 1 grado non e' aggiunto)
  - una stazione DSN basta; la disponibilita' di tracking (programmazione) non e' modellata
limits:
  - nessun terreno, perche' l'orizzonte locale e' piatto con maschera
  - la definizione di "ora utile" e' una proposta (vedi docs/domain/assumptions.md), da concordare con il team
  - risultati come potenziale, non come previsione
worked_example:
  inputs: {power: "111111000111", earth: "111100001111", dsn: "111111111110", margin_ok: "110111111111", dt_h: 1.0}
  outputs: {useful_hours: 5, useful_fraction: 0.4167, n_windows: 3, longest_gap_h: 5}
  note: "AND passo per passo: utili ai passi 0, 1, 3, 9, 10 (5 ore su 12); finestre {0-1}, {3}, {9-10}; il buco piu' lungo e' 4-8, cinque ore"
---
## Come leggere i risultati

Le ore utili sono un potenziale: dicono quante ore la geometria, l'energia e il collegamento
permetterebbero con i parametri scelti. Nessuna di queste e' una misura. Il confronto tra siti e'
piu' affidabile del valore assoluto.

## Perche' tante ore sono perse ai poli

Dai poli la Terra sta attorno all'orizzonte (librazione di circa 7 gradi): e' sopra una maschera
piatta solo per una frazione del ciclo di 27.2 giorni. In piu' il Sole radente da' poca potenza a un
pannello orizzontale.
