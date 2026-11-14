---
id: rl-negative-result
title: Esito onesto dell'RL sul servo - nessun vantaggio su un PD ben tarato
kind: decision
summary: >-
  Sull'impianto servo di esempio un controllore PD ben sintonizzato e' quasi ottimo: l'addestramento
  RL (ARS lineare, PPO) lo eguaglia ma non lo supera, quindi il candidato non passa il gate e non e'
  promuovibile. L'esempio dimostra pipeline e gate, non la superiorita' dell'RL.
tags: [RL, apprendimento per rinforzo, ha battuto, superare il PD, reinforcement learning, ARS, PPO, servo, PD, gate, risultato negativo, env-servo, trainer-rl]
applies_to: [trainer-rl, env-servo]
related: [ml-promotion-gate, servo-pi-law]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/ml.md, supports: "ambiente SimulationEnv, gate di promozione, risultati misurati ARS e PPO"}
---
## Ambiente (`env-servo`)

Azione: 1 componente in [-1, 1]. Osservazione: 3 valori in [-1, 1] (errore misurato/180 deg,
velocita'/rate, setpoint/90 deg). Ricompensa `r = -|errore_vero_deg|/90 - 0.05 * [azione fuori
limite]`, sempre <= 0. `terminated` quando assestato (errore <= 1 deg e velocita' <= 5 deg/s),
`truncated` a 100 passi.

## Gate

Il guadagno e' (R_politica - R_baseline)/|R_baseline| su 300 episodi appaiati con IC 95% bootstrap.
Soglie: `gain_ci_low >= max(0.15, valore del promosso)` e `gain_ci_low_perturbed >= 0.15`.
Il baseline e' la migliore griglia P/PD sintonizzata sui semi di training (kp 45, kd -2).

## Risultato misurato

ARS (politica lineare avviata a caldo dal PD, 3 semi 0/1/2): `gain_mean` circa -0.003/-0.002/-0.003
sul profilo nominale; nessun insieme di non linearita' provato supera 0.15 (il migliore e' circa 0).
PPO (Stable-Baselines3, 1 seme, 200 000 passi): guadagno -0.0014, `gain_ci_low` -0.0020: raggiunge il PD ma non
lo supera. Contro un P non sintonizzato il guadagno e' 0.46-0.49 (informativo, fuori dal gate).
Conclusione dichiarata in `docs/ml.md`: con questi parametri illustrativi un PD ben tarato resta praticamente ottimo.
