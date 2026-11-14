---
id: page-sims
title: Pagina Simulazioni
kind: page
summary: >-
  La pagina Simulazioni (percorso /sims) permette di scegliere una simulazione, inserire coppie
  nome/valore come ingressi e premere Esegui per vedere i risultati restituiti dal backend.
tags: [pagina, simulazioni, sims, ingressi, esegui, risultato]
applies_to: [sims, laboratorio]
related: [sim-fspl-c, sim-servo-ctrl-c, sim-grazinglink-link, fspl, servo-pi-law]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: frontend/src/pages/sims/Sims.svelte, supports: "campi Simulazione, Nome ingresso, Valore, pulsanti Aggiungi ingresso ed Esegui, pannello Risultato"}
  - {ref: frontend/src/pages/sims/index.ts, supports: "percorso /sims"}
  - {ref: backend/api/routes.py, supports: "POST /api/simulations/{sim_id}/run, errori 404/502/504/503"}
---
## Uso

1. Scegliere la simulazione (per esempio `fspl-c` o `servo-ctrl-c`).
2. Aggiungere un ingresso per ogni parametro: nome (es. `distance_km`) e valore numerico finito.
3. Premere **Esegui**: il risultato compare nel pannello Risultato.

Gli ingressi validi per ogni simulazione sono descritti in [fspl-c](kb:sim-fspl-c) e
[servo-ctrl-c](kb:sim-servo-ctrl-c) e [grazinglink-link](kb:sim-grazinglink-link). Il plugin RAVEN
usa un profilo sintetico di prova e mostra anche il confronto della perdita in spazio libero col plugin C,
se disponibile. Se la simulazione supera il suo timeout l'API risponde 504;
con troppe simulazioni in corso 503.
