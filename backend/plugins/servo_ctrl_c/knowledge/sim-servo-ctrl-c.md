---
id: sim-servo-ctrl-c
title: Simulazione servo-ctrl-c (controllo PI di un servo, HAL host)
kind: simulation
summary: >-
  Plugin C che esegue il controllore PI contro un servo simulato del primo ordine con limite di
  velocita' e rumore del sensore, e restituisce angolo finale, errore a regime, overshoot, tempo di
  assestamento e passi saturati.
tags: [servo-ctrl-c, servo, simulazione, PI, HAL, setpoint_deg, overshoot, settle_time_s, rumore]
applies_to: [servo-ctrl-c, sims]
related: [servo-pi-law]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/hal.md, supports: "protocollo key=value, intervalli degli ingressi, uscite e codici di uscita"}
  - {ref: backend/plugins/servo_ctrl_c/servo_ctrl.c, supports: "parsing, validazione e calcolo delle uscite"}
  - {ref: backend/plugins/servo_ctrl_c/manifest.toml, supports: "id servo-ctrl-c, timeout 5 s"}
---
## Ingressi

| Chiave | Unita' | Intervallo |
|---|---|---|
| `setpoint_deg` | gradi | [-720, 720] |
| `kp` | deg/deg | [0, 1000] |
| `ki` | deg/(deg*s) | [0, 1000] |
| `steps` | passi (intero) | [1, 100000] |
| `dt_s` | s | [1e-4, 1] |
| `plant_tau_s` | s | [dt_s, 100] (con tau < dt l'Eulero esplicito e' instabile) |
| `sensor_noise_v` | V (deviazione standard) | [0, 0.1] |
| `seed` | intero | [0, 2^32-1] |
| `anti_windup` (opzionale) | 0 o 1, default 1 | |
| `plant_rate_dps` (opzionale) | deg/s, default 90 | (0, 1000] |

## Uscite

`final_angle_deg`, `steady_error_deg` (media dell'angolo vero sull'ultimo 10 % dei passi),
`max_overshoot_deg`, `settle_time_s` (ultimo istante con errore > 1 grado), `saturated_steps`.

Un ingresso non valido (chiave mancante, sconosciuta o duplicata, NaN/inf, fuori intervallo) da'
codice di uscita 2 e nessun output. La legge di controllo e' descritta in [PI con anti-windup](kb:servo-pi-law).
Il controllo e' validato solo contro il modello host (L0), non su hardware.
