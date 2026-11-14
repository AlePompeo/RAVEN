---
id: sim-fspl-c
title: Simulazione fspl-c (perdita nello spazio libero)
kind: simulation
summary: >-
  Plugin C (kind simulation) che calcola la perdita nello spazio libero in dB dati la distanza in
  km e la frequenza in GHz. Si usa dalla pagina Simulazioni o con POST /api/simulations/fspl-c/run.
tags: [fspl-c, simulazione, plugin C, distance_km, freq_ghz, fspl_db]
applies_to: [fspl-c, sims]
related: [fspl, link-budget]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: backend/plugins/fspl_c/fspl.c, supports: "ingressi distance_km e freq_ghz, uscita fspl_db, codice di uscita 2 se <= 0"}
  - {ref: backend/plugins/fspl_c/manifest.toml, supports: "id fspl-c, kind simulation, timeout 5 s, licenza Apache-2.0"}
  - {ref: backend/api/routes.py, supports: "endpoint POST /api/simulations/{sim_id}/run con corpo {inputs: {nome: numero}}"}
---
## Ingressi e uscite

| Nome | Direzione | Unita' | Significato |
|---|---|---|---|
| `distance_km` | ingresso | km | distanza tra le antenne, deve essere > 0 |
| `freq_ghz` | ingresso | GHz | frequenza, deve essere > 0 |
| `fspl_db` | uscita | dB | perdita nello spazio libero, vedi [formula](kb:fspl) |

Con `distance_km <= 0` o `freq_ghz <= 0` il programma termina con codice 2 e l'API risponde con un
errore di simulazione (nessun valore viene inventato).

## Come si esegue

Il programma legge righe `chiave=valore` da stdin e scrive `fspl_db=<valore>` su stdout. Dall'API:
`POST /api/simulations/fspl-c/run` con `{"inputs": {"distance_km": 384400, "freq_ghz": 2.2}}`; la
risposta contiene `outputs.fspl_db`. Il tempo massimo e' 5 secondi (campo `timeout_s` del manifest).
Il binario va compilato con `make build-c`.
