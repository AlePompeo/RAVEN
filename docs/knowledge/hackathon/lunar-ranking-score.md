---
id: lunar-ranking-score
title: Regola di punteggio per confrontare i siti
kind: formula
summary: >-
  Ogni sito riceve due componenti, la frazione di ore utili e il SOC minimo della batteria, ciascuna divisa per il massimo tra i siti confrontati; il punteggio e' la media pesata (pesi di default uguali). Le componenti sono sempre mostrate: il punteggio da solo non va letto.
tags: [punteggio, classifica, ranking, pesi, siti, confronto, normalizzazione]
applies_to: [home, chat]
related: [nasa-lunar-problem, lunar-mission-hours, lunar-energy-model]
level: intermedio
lang: it
last_verified: 2026-10-20
sources:
  - {ref: backend/domain/lunar/mission.py, supports: "funzione rank_sites e componenti"}
  - {ref: tests/backend/domain/test_lunar_mission.py, supports: "test della regola, dei pesi e dei casi limite"}
  - {ref: tests/backend/domain/test_lunar_knowledge.py, supports: "l'esempio svolto qui sotto e' confrontato con l'uscita reale del codice"}
  - {ref: docs/domain/method.md, supports: "scelta della regola e suoi limiti"}
expression: "score_s = sum_k w_k * (c_ks / max_s' c_ks') / sum_k w_k,  c_1 = useful_fraction, c_2 = min_soc"
variables:
  - {symbol: c_1s, name: frazione di ore utili del sito s, unit: "-", range: "0 .. 1"}
  - {symbol: c_2s, name: SOC minimo della batteria del sito s, unit: "-", range: "0 .. 1"}
  - {symbol: w_k, name: peso della componente k, unit: "-", range: ">= 0, somma > 0 (default 1 e 1)"}
  - {symbol: score_s, name: punteggio del sito, unit: "-", range: "0 .. 1"}
assumptions:
  - la normalizzazione e' rispetto al migliore dei siti confrontati, quindi cambiare l'insieme dei siti cambia i punteggi
  - le due componenti hanno lo stesso peso salvo indicazione diversa
limits:
  - e' una scelta di progetto (illustrativa), non uno standard, e due siti con punteggio vicino non sono distinguibili
  - se il massimo di una componente e' 0 la componente vale 0 per tutti
  - il SOC minimo dipende da batteria e carichi illustrativi
worked_example:
  inputs: {a: {useful_fraction: 0.8, min_soc: 0.2}, b: {useful_fraction: 0.4, min_soc: 0.8}, c: {useful_fraction: 0.0, min_soc: 0.0}}
  outputs: {score_a: 0.625, score_b: 0.75, score_c: 0.0, ranking: "b, a, c"}
  note: "massimi 0.8 e 0.8; a = (1 + 0.25)/2 = 0.625; b = (0.5 + 1)/2 = 0.75; c = 0"
---
## Perche' non un solo numero

Il punteggio sintetizza due aspetti diversi (comunicazione ed energia utili, robustezza della batteria).
L'API restituisce per ogni sito valore, valore normalizzato e peso di ciascuna componente.
