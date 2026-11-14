---
id: estimator-imu-ahrs
title: Stimatore d'assetto IMU (AHRS, fusione giroscopio-accelerometro-magnetometro)
kind: method
summary: >-
  Il plugin estimator-imu fonde giroscopio (obbligatorio), accelerometro e magnetometro (opzionali)
  con la libreria imufusion (filtro AHRS, Madgwick modificato) e restituisce quaternione e angoli
  roll, pitch, yaw in gradi. Richiede l'extra opzionale [fusion].
tags: [IMU, AHRS, sensor fusion, fusione sensori, assetto, quaternione, roll, pitch, yaw, giroscopio, accelerometro, magnetometro, imufusion]
applies_to: [estimator-imu]
related: [telemetry-contract]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: backend/plugins/estimator_imu/plugin.py, supports: "chiavi di ingresso e unita', convenzione NWU, uscite, regole di validazione"}
  - {ref: backend/plugins/estimator_imu/manifest.toml, supports: "dipendenza opzionale imufusion==1.3.3 dall'extra [fusion]"}
  - {ref: backend/api/routes.py, supports: "endpoint POST /api/estimators/{est_id}/update e /reset, sessioni per client"}
---
## Ingressi (misura) e unita'

- Giroscopio (obbligatorio): `gyro_x_dps`, `gyro_y_dps`, `gyro_z_dps` in gradi al secondo.
- Accelerometro (opzionale): `accel_x_g`, `accel_y_g`, `accel_z_g` in g.
- Magnetometro (opzionale, solo insieme all'accelerometro): `mag_x_ut`, `mag_y_ut`, `mag_z_ut` in microtesla.
- Il passo `dt_s` (secondi, finito e > 0) si imposta con `predict(dt_s)` o nella richiesta `update`.

Convenzione degli assi: NWU (x nord, y ovest, z alto).

## Uscite

`qw`, `qx`, `qy`, `qz` (quaternione, ordine w, x, y, z) e `roll_deg`, `pitch_deg`, `yaw_deg`
(gradi). Il filtro non produce covarianza.

## Comportamento

Senza accelerometro si integra solo il giroscopio (deriva nel tempo, nessuna correzione); con
l'accelerometro si corregge roll e pitch rispetto alla gravita'; con il magnetometro si corregge
anche lo yaw (comportamento tipico di un AHRS, conoscenza generale: non verificato dai test del repository). Una misura non valida (chiavi mancanti, valori non finiti, magnetometro senza
accelerometro) viene rifiutata senza alterare lo stato del filtro.

## Disponibilita'

Senza l'extra `pip install -e ".[fusion]"` il plugin non si carica e le rotte
`/api/estimators/estimator-imu/*` rispondono 404.
