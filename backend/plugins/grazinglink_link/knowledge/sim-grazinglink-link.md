---
id: sim-grazinglink-link
title: Simulazione RAVEN su profilo di prova
kind: simulation
summary: >-
  Il plugin grazinglink-link calcola il margine per una elevazione e un crinale sintetico, con lo
  stesso motore RAVEN. Non rappresenta il terreno LOLA né un sito o una misura reale.
tags: [grazinglink-link, simulazione, diffrazione, profilo sintetico, margine]
applies_to: [grazinglink-link, sims, laboratorio]
related: [sim-fspl-c, glossary-link-margin]
level: principiante
lang: it
last_verified: 2026-10-29
sources:
  - {ref: backend/plugins/grazinglink_link/plugin.py, supports: "ingressi, profilo sintetico e uscite del plugin"}
  - {ref: backend/domain/grazing/analysis.py, supports: "motore di calcolo e ipotesi del margine"}
  - {ref: frontend/src/pages/sims/Sims.svelte, supports: "confronto della perdita con il plugin fspl-c"}
---
## Uso e limiti

Seleziona RAVEN in Simulazioni (identificatore tecnico `grazinglink-link`). Sono obbligatori `earth_el_deg` (gradi, da -30 a 60) e
`ridge_radius_m` (metri, da 10 a 5000). Sono facoltativi `ridge_height_m` (metri, da 1 a 100;
predefinito 33), `frequency_ghz` e `rate_bps` (tra quelli supportati dal modello). Il crinale
parabolico è a 2000 m, su un profilo **sintetico di prova** con passo 5 m; l'elevazione è impostata,
non calcolata dalle effemeridi. I parametri radio predefiniti sono illustrativi.

L'uscita `margin_db` è il margine al bit-rate scelto; `nu`, `knife_edge_loss_db` e
`ridge_correction_db` descrivono la diffrazione. `profile_synthetic = 1` segnala che il terreno non
è reale; `radius_resolved` segnala se il raggio è risolto dal profilo. La pagina confronta
`fspl_db` con il risultato del plugin C `fspl-c`: lievi differenze sono dovute a costanti e
arrotondamenti. Se il plugin C non è disponibile il controllo è segnalato come non disponibile.
`earth_below_horizon` segnala che l'elevazione è ≤ 0 e il modello è fuori dal suo dominio;
`correction_clamped` segnala la saturazione ai bordi della tabella di correzione.
