---
id: fspl
title: Perdita nello spazio libero (FSPL, Free-Space Path Loss)
kind: formula
summary: >-
  L'FSPL e' l'attenuazione in dB di un segnale radio che si propaga nello spazio libero tra due
  antenne isotrope; cresce con 20 log10 della distanza e della frequenza. Il simulatore fspl-c
  calcola esattamente FSPL(dB) = 92.45 + 20 log10(d_km) + 20 log10(f_GHz).
tags: [FSPL, free-space path loss, perdita di propagazione, attenuazione, link budget, dB, distanza, frequenza, Luna]
applies_to: [fspl-c, sims]
related: [link-budget, glossary-db, sim-fspl-c]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: backend/plugins/fspl_c/fspl.c, supports: "implementazione della formula con costante 92.45 e log10"}
  - {ref: tests/backend/adapters/test_subprocess_sim.py, supports: "il plugin da' ~210.99 dB per 384400 km a 2.2 GHz"}
  - {ref: tests/backend/assistant/test_knowledge_lint.py, supports: "l'esempio svolto qui sotto e' confrontato con l'uscita reale del plugin"}
expression: "FSPL_dB = 92.45 + 20*log10(d_km) + 20*log10(f_GHz)"
variables:
  - {symbol: FSPL, name: perdita nello spazio libero, unit: dB, range: "determinata da d e f"}
  - {symbol: d_km, name: distanza tra trasmettitore e ricevitore, unit: km, range: "> 0 (il plugin rifiuta d <= 0)"}
  - {symbol: f_GHz, name: frequenza del segnale, unit: GHz, range: "> 0 (il plugin rifiuta f <= 0)"}
  - {symbol: "92.45", name: costante che racchiude 20*log10(4*pi/c) con d in km e f in GHz, unit: dB, range: "costante"}
assumptions:
  - propagazione nello spazio libero, senza ostacoli ne' riflessioni
  - antenne isotrope (guadagno 0 dBi alle due estremita')
  - nessuna perdita atmosferica, di pioggia, di puntamento o di polarizzazione
limits:
  - non include le altre perdite di un link budget reale (atmosfera, pioggia, puntamento, cavi)
  - il plugin fspl-c restituisce errore per distanza o frequenza <= 0
  - "e' un modello a campo lontano: non vale a distanze paragonabili alla lunghezza d'onda"
worked_example:
  inputs: {distance_km: 384400, freq_ghz: 2.2}
  outputs: {fspl_db: 210.994}
  note: "distanza media Terra-Luna usata nel test del repository; 20*log10(384400) = 111.695 dB, 20*log10(2.2) = 6.848 dB, somma con 92.45 = 210.994 dB"
derivation:
  - "Con antenne isotrope la potenza ricevuta e' Pr = Pt * (lambda / (4*pi*d))^2, con lambda = c / f."
  - "La perdita in dB e' FSPL = 10*log10(Pt/Pr) = 20*log10(4*pi*d*f / c)."
  - "Esprimendo d in km e f in GHz, 20*log10(4*pi*1000*1e9 / c) = 92.45 dB (c circa 299792458 m/s): da qui la costante."
---
## Come si usa

Raddoppiare la distanza aggiunge circa 6.02 dB di perdita (20*log10(2)); lo stesso vale per
raddoppiare la frequenza. L'FSPL e' il primo termine di un [link budget](kb:link-budget): al valore
si sommano guadagni e si sottraggono le altre perdite per ottenere il margine di collegamento.

## Dove lo calcola il sito

Il plugin `fspl-c` ([simulazione](kb:sim-fspl-c)) legge `distance_km` e `freq_ghz` e restituisce
`fspl_db` con 6 decimali.
