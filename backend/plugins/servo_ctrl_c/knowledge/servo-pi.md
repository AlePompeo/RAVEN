---
id: servo-pi-law
title: Legge del controllore PI con clamp e anti-windup (servo)
kind: formula
summary: >-
  Il controllore del servo calcola u = kp*e + I con I che accumula ki*e*dt; l'uscita e' limitata
  (clamp) a [out_min, out_max] e, con anti-windup, l'integrale si congela quando continuerebbe a
  spingere nel limite (integrazione condizionale).
tags: [PI, controllore, servo, anti-windup, clamp, kp, ki, saturazione, controllo]
applies_to: [servo-ctrl-c, sims]
related: [sim-servo-ctrl-c]
level: tecnico
lang: it
last_verified: 2026-10-15
sources:
  - {ref: backend/plugins/servo_ctrl_c/control.c, supports: "pi_step: err, integ, u, clamp e integrazione condizionale"}
  - {ref: backend/plugins/servo_ctrl_c/control.h, supports: "unita' (gradi, secondi) e intervalli kp, ki, dt_s"}
  - {ref: docs/hal.md, supports: "controllore PI con clamp d'uscita e anti-windup per integrazione condizionale"}
expression: "e = setpoint - misura; I_nuovo = I + ki*e*dt; u = kp*e + I_nuovo; u limitato a [out_min, out_max]"
variables:
  - {symbol: e, name: errore (setpoint meno misura), unit: deg, range: "|setpoint| e |misura| <= 1000"}
  - {symbol: kp, name: guadagno proporzionale, unit: deg di uscita per deg di errore, range: "[0, 1000]"}
  - {symbol: ki, name: guadagno integrale, unit: deg di uscita per (deg di errore * s), range: "[0, 1000]"}
  - {symbol: dt, name: passo di controllo, unit: s, range: "[1e-4, 1]"}
  - {symbol: I, name: stato integrale, unit: deg, range: "limitato in modulo a 1e9"}
  - {symbol: u, name: comando in uscita, unit: deg, range: "[out_min, out_max]; nell'harness del servo [0, 180]"}
assumptions:
  - ingressi finiti (NaN o infinito vengono rifiutati con CTRL_ERR_VALUE)
  - il passo dt e' costante e uguale a quello passato a pi_init
limits:
  - "anti-windup per sola integrazione condizionale: congela l'integrale solo se l'errore spinge ancora nel limite"
  - dimostrato solo contro il modello host della HAL, non su hardware reale (vedi docs/hal.md)
  - senza anti-windup (anti_windup = 0) l'integrale continua ad accumulare in saturazione
worked_example:
  inputs: {kp: 2, ki: 20, dt_s: 0.01, setpoint_deg: 10, misura_deg: 0, integrale_iniziale_deg: 0}
  outputs: {u_deg: 22}
  note: "e = 10; I_nuovo = 0 + 20*10*0.01 = 2; u = 2*10 + 2 = 22 gradi, dentro [0, 180] quindi nessun clamp"
derivation:
  - "Il termine proporzionale kp*e reagisce all'errore istantaneo."
  - "Il termine integrale ki*e*dt accumulato elimina l'errore a regime."
  - "Se u supera out_max (o scende sotto out_min) il comando e' limitato e il flag saturated vale 1."
  - "Con anti_windup attivo, in saturazione superiore l'integrale non si aggiorna se e > 0 (in inferiore se e < 0): l'accumulo non cresce mentre il comando e' gia' al limite."
---
## Perche' l'anti-windup

Senza protezione, durante una lunga saturazione (per esempio il servo limitato in velocita')
l'integrale cresce e, quando l'errore si inverte, provoca un grosso overshoot. L'integrazione
condizionale evita l'accumulo mentre il comando e' al limite.
