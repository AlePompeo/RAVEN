---
id: lunar-energy-model
title: Modello energetico del sito lunare (pannello solare e batteria)
kind: formula
summary: >-
  La potenza del pannello e' P = S A eta k (1 - degradazione) cos(incidenza), con S = 1360.8 W/m2 / r_AU^2 e il Sole che deve avere il bordo superiore sopra la maschera. Una simulazione passo-passo della batteria (rendimenti di carica e scarica, riserva, carico di sopravvivenza o operativo) da' energia raccolta, SOC minimo e sopravvivenza alla notte lunare.
tags: [energia, pannello solare, batteria, SOC, notte lunare, irradianza, 1360.8, sopravvivenza, Luna]
applies_to: [home, chat]
related: [nasa-lunar-problem, lunar-link-budget, lunar-mission-hours, glossary-soc, glossary-terminator]
level: tecnico
lang: it
last_verified: 2026-10-20
sources:
  - {ref: backend/domain/lunar/energy.py, supports: "implementazione di irradianza, angolo di incidenza, potenza e simulazione della batteria"}
  - {ref: tests/backend/domain/test_lunar_energy.py, supports: "Sole allo zenit, SOC lineare di notte, rendimento di andata e ritorno, conservazione dell'energia"}
  - {ref: tests/backend/domain/test_lunar_knowledge.py, supports: "l'esempio svolto qui sotto e' confrontato con l'uscita reale del codice"}
  - {ref: docs/domain/assumptions.md, supports: "1360.8 W/m2 (Kopp e Lean 2011), efficienza celle 29.5 % (SoA 2022) e valori illustrativi"}
  - {ref: docs/domain/method.md, supports: "formule, ipotesi e limiti dell'intera analisi"}
expression: "P_W = S_Wm2 * A_m2 * eta * k * (1 - deg) * cos(incidenza),  S_Wm2 = 1360.8 / r_AU^2"
variables:
  - {symbol: S_Wm2, name: irradianza solare totale alla distanza Sole-Luna, unit: W/m2, range: "1316 .. 1408"}
  - {symbol: r_AU, name: distanza Sole-Luna dalle efemeridi, unit: AU, range: "0.983 .. 1.017"}
  - {symbol: A_m2, name: area del pannello, unit: m2, range: "0.01 .. 100 (default 1, illustrativo)"}
  - {symbol: eta, name: efficienza delle celle, unit: "-", range: "0.05 .. 0.5 (default 0.295, SoA 2022)"}
  - {symbol: k, name: fattore di sistema (packing, temperatura, cablaggio), unit: "-", range: "0.1 .. 1 (default 0.80, illustrativo)"}
  - {symbol: deg, name: degradazione dei pannelli, unit: "-", range: "0 .. 0.9 (default 0.02, illustrativo)"}
  - {symbol: incidenza, name: angolo tra la normale del pannello e la direzione del Sole, unit: deg, range: "0 .. 90 (oltre 90 la potenza e' 0)"}
assumptions:
  - Sole sopra la maschera quando il bordo superiore del disco (elevazione del centro + 0.27 gradi) supera la maschera
  - orizzonte locale piatto (sfera liscia di 1737.4 km), nessun terreno
  - pannello orizzontale, inclinato o ad inseguimento; nessun effetto della temperatura
  - la batteria carica con rendimento eta_c e scarica con eta_d; sotto la riserva min_soc si passa al carico di sopravvivenza
limits:
  - la polvere lunare, le ombre del terreno e la termica non sono modellate
  - ai poli l'illuminazione reale dipende dalla topografia, quindi una sfera liscia puo' essere ottimistica o pessimistica secondo il punto
  - area del pannello, batteria, carichi, rendimenti e degradazione sono illustrativi
worked_example:
  inputs: {sun_distance_au: 1.0, sun_elevation_deg: 30, orientation: horizontal, array_area_m2: 1.0, cell_efficiency: 0.295, packing_factor: 0.8, degradation_fraction: 0.02}
  outputs: {irradiance_w_m2: 1360.8, cos_incidence: 0.5, array_power_w: 157.363}
  note: "pannello orizzontale: cos(incidenza) = sin(30 gradi) = 0.5; P = 1360.8 * 1 * 0.295 * 0.8 * 0.98 * 0.5 = 157.363 W"
derivation:
  - "L'irradianza segue la legge dell'inverso del quadrato rispetto al valore a 1 AU."
  - "Per un pannello orizzontale cos(incidenza) = sin(elevazione del Sole)."
  - "Bilancio: energia raccolta = carico servito + variazione immagazzinata + energia scartata + perdite di carica e scarica (verificato dai test)."
---
## Come si legge

Il SOC minimo raggiunto nella finestra e' il margine energetico: 0 significa che la batteria si e'
esaurita (il carico non e' stato servito). Il "buio piu' lungo" e' l'intervallo continuo con il
Sole sotto la maschera; ai siti equatoriali e' circa meta' mese sinodico (14.77 giorni).

## Modalita'

Carico operativo (default 50 W piu' la comunicazione solo quando il link e' disponibile) finche'
il pannello copre il carico o la batteria e' sopra la riserva; altrimenti carico di sopravvivenza
(10 W, illustrativo, riscaldatori inclusi).
