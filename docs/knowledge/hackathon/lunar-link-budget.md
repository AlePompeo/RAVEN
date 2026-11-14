---
id: lunar-link-budget
title: Link budget diretto verso la Terra dal sito lunare (modello semplificato)
kind: formula
summary: >-
  Il margine di collegamento DTE e' Eb/N0 ottenuto meno Eb/N0 richiesto, con Eb/N0 = EIRP - FSPL - perdite + G/T + 228.6 - 10 log10(R) - perdita di implementazione. Il sito usa la distanza Terra-sito vera (efemeridi) a ogni passo; il risultato e' un potenziale nelle ipotesi dichiarate, con parametri illustrativi dove non esiste una fonte.
tags: [link budget, margine, EIRP, G/T, Eb/N0, FSPL, DSN, banda X, DTE, Luna, Boltzmann]
applies_to: [home, chat]
related: [fspl, link-budget, nasa-lunar-problem, glossary-eirp, glossary-gt, glossary-ebn0, glossary-link-margin]
level: tecnico
lang: it
last_verified: 2026-10-20
sources:
  - {ref: backend/domain/lunar/link.py, supports: "implementazione delle funzioni pure (fspl_db, eirp_dbw, cn0_dbhz, ebn0_db, link_margin_db)"}
  - {ref: tests/backend/domain/test_lunar_link.py, supports: "identita' con la formula di fspl-c (offset costante 0.0022 dB), proprieta' 6.02 e 3.01 dB, calcolo indipendente in unita' lineari"}
  - {ref: tests/backend/domain/test_lunar_knowledge.py, supports: "l'esempio svolto qui sotto e' confrontato con l'uscita reale del codice"}
  - {ref: docs/domain/assumptions.md, supports: "G/T DSN 54.1 dB/K (X), frequenza 8.425 GHz, margine 3 dB, 4 kbps, Eb/N0 9.6 dB, maschera 6 gradi e valori illustrativi"}
  - {ref: docs/domain/method.md, supports: "formule, ipotesi e limiti dell'intera analisi"}
expression: "margin_dB = [10 log10(P_W) + G_dBi - FSPL_dB - L_dB + GT_dBK + 228.6 - 10 log10(R_bps) - Limp_dB] - EbN0req_dB,  FSPL_dB = 20 log10(4 pi d / lambda)"
variables:
  - {symbol: P_W, name: potenza RF di trasmissione, unit: W, range: "0.01 .. 200 (default 20, illustrativo)"}
  - {symbol: G_dBi, name: guadagno dell'antenna del lander, unit: dBi, range: "-10 .. 70 (default 20, illustrativo)"}
  - {symbol: d, name: distanza sito-Terra dalle efemeridi, unit: km, range: "355000 .. 407000 circa"}
  - {symbol: f_GHz, name: frequenza, unit: GHz, range: "0.1 .. 40 (default 8.425, DSN 810-005/104)"}
  - {symbol: L_dB, name: perdite di puntamento piu' altre perdite, unit: dB, range: "0 .. 40 (default 1 + 1, illustrativo)"}
  - {symbol: GT_dBK, name: figura di merito della stazione di terra, unit: dB/K, range: "20 .. 70 (default 54.1, derivato da DSN 810-005/104)"}
  - {symbol: R_bps, name: velocita' dati, unit: bit/s, range: "10 .. 1e8 (default 4000, TP-2019-220391)"}
  - {symbol: Limp_dB, name: perdita di implementazione, unit: dB, range: "0 .. 10 (default 2, illustrativo)"}
  - {symbol: EbN0req_dB, name: Eb/N0 richiesto (BPSK non codificato, BER 1e-5), unit: dB, range: "0 .. 30 (default 9.6)"}
  - {symbol: "228.6", name: -10 log10 della costante di Boltzmann, unit: dBW/K/Hz, range: costante}
assumptions:
  - "spazio libero, quindi nessuna atmosfera, pioggia o ionosfera"
  - G/T costante (cielo sereno, zenit); a bassa elevazione peggiora ma qui non e' modellato
  - guadagno d'antenna indipendente dall'angolo di puntamento (il puntamento e' una perdita fissa)
  - nessun guadagno di codifica verificato (CCSDS non recuperato), quindi soglia non codificata
limits:
  - il default per potenza, guadagno antenna e perdite e' ILLUSTRATIVO, non e' un dato di missione
  - con i default a 4 kbps il margine e' circa 43 dB, quindi il collegamento non e' il fattore limitante; lo diventano la geometria e l'energia
  - non c'e' un esempio numerico pubblicato riprodotto, perche' TP-2019-220391 non riporta i guadagni d'antenna e il suo margine non e' ricalcolabile
worked_example:
  inputs: {distance_km: 384400, frequency_ghz: 8.425, tx_power_w: 20, tx_antenna_gain_dbi: 20, pointing_loss_db: 1, other_losses_db: 1, ground_gt_dbk: 54.1, data_rate_bps: 4000, implementation_loss_db: 2, required_ebn0_db: 9.6}
  outputs: {fspl_db: 222.655, eirp_dbw: 33.010, cn0_dbhz: 91.055, ebn0_db: 53.035, margin_db: 43.435}
  note: "FSPL = 20 log10(4 pi 384400e3 / 0.035582) = 222.655 dB; EIRP = 13.010 + 20 = 33.010 dBW; C/N0 = 33.010 - 222.655 - 2 + 54.1 + 228.6 = 91.055 dBHz; Eb/N0 = 91.055 - 36.021 - 2 = 53.035 dB; margine = 53.035 - 9.6 = 43.435 dB"
derivation:
  - "Potenza ricevuta isotropica Pr = Pt Gt (lambda / (4 pi d))^2 (vedi fspl)."
  - "C/N0 = Pr G/T / (k L) con k = 1.380649e-23 J/K: in dB -228.6 dBW/K/Hz."
  - "Eb/N0 = C/N0 / R, con R in bit/s; il margine e' la differenza con la soglia richiesta."
---
## Come si usa

Il sito calcola questa catena a ogni passo temporale con la distanza reale Terra-sito: raddoppiare la
distanza costa 6.02 dB, raddoppiare la potenza ne guadagna 3.01. Il passo e' "utile" per le ore di
missione solo se il margine e' almeno il margine richiesto (default 3 dB, TP-2019-220391).

## Differenza con il plugin fspl-c

La formula esatta usa la costante 92.4478 dB; il plugin usa 92.45, quindi differisce di una costante
+0.0022 dB (210.994 contro 210.992 dB a 384400 km e 2.2 GHz). L'analisi usa la forma esatta.
