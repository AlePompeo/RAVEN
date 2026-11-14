---
id: ml-promotion-gate
title: Cancello di promozione dei modelli ML (con approvazione umana)
kind: method
summary: >-
  Un modello addestrato resta "candidato" finche' le sue metriche non superano la soglia scritta
  nella model card E una persona lo approva esplicitamente; l'API HTTP non espone la promozione. Il
  predittore di esempio ha skill 0.80 contro soglia 0.25 su dati sintetici.
tags: [ML, promozione, gate, model card, soglia, skill, candidato, rollback, predictor-baseline, ONNX, approvazione umana]
applies_to: [predictor-baseline, trainer-baseline, predictor-nn, trainer-rl]
related: [rl-negative-result]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/ml.md, supports: "ciclo chiuso con promozione umana, soglie, esempio predictor_baseline e predictor_nn"}
---
## Il ciclo

dataset sintetico (seme, sha256) -> addestramento in subprocess (`POST /api/train`) -> candidato
ONNX + `model_card.json` (`status = candidate`) -> valutazione sul test set FISSO contro baseline ->
promozione solo se le metriche rispettano la soglia **e** c'e' approvazione umana esplicita ->
rollback alla versione promossa precedente.

`promote(version, approver=..., approved=True)` richiede il flag e il nome dell'approvatore, e
rifiuta se una metrica della soglia manca o e' sotto soglia. La promozione e' nell'API Python del
registro: l'API HTTP non la espone, per scelta di sicurezza.

## Numeri dell'esempio `predictor_baseline` (dati sintetici, seed 1, 2000 campioni)

- Metrica: `skill = 1 - MSE_modello / MSE_baseline`, soglia dichiarata >= 0.25.
- RMSE del modello 0.574 dB, baseline lineare 1.289 dB, media 4.554 dB: skill 0.80.
- Il test set e' fisso (500 campioni, seme 20261012). Il risultato vale solo per questa
  distribuzione sintetica: su telemetria reale servono un test set reale e una nuova soglia.

L'esempio `predictor_nn` (extra `[dl]`) ottiene skill 0.83 contro soglia 0.25 (RMSE 0.529-0.531 dB, seed 1-3).
