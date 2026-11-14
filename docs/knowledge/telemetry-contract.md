---
id: telemetry-contract
title: Contratto di telemetria (campi e unita')
kind: concept
summary: >-
  Un campione di telemetria ha schema_version, t_utc, site_id e power_w obbligatori; sono
  opzionali link_margin_db (dB) e gli oggetti sun ed earth con az_deg ed el_deg (gradi). Le unita'
  sono nel nome del campo.
tags: [telemetria, telemetry, contratto, schema, power_w, link_margin_db, az_deg, el_deg, t_utc, site_id, unita]
applies_to: [telemetry, ingest-csv]
related: [glossary-link-margin, glossary-azimuth, glossary-elevation, pipeline-guarantees, contract-telemetry]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: contracts/telemetry.schema.json, supports: "campi, obbligatorieta' e tipi"}
  - {ref: backend/api/routes.py, supports: "mappatura delle colonne CSV del replay sul contratto (csv_replay, _row_to_sample)"}
  - {ref: docs/pipeline.md, supports: "normalizzazioni del processor (power_kw -> power_w, rad -> deg) e chiave di dedup"}
---
## Campi

| Campo | Obbligatorio | Unita' | Note |
|---|---|---|---|
| `schema_version` | si | - | stringa semver `MAJOR.MINOR.PATCH` |
| `t_utc` | si | UTC | stringa ISO-8601 con fuso orario |
| `site_id` | si | - | stringa non vuota |
| `power_w` | si | watt (W) | numero |
| `link_margin_db` | no | decibel (dB) | numero, vedi [margine di collegamento](kb:glossary-link-margin) |
| `sun`, `earth` | no | - | oggetti con `az_deg` ed `el_deg`, entrambi obbligatori dentro l'oggetto |
| `sun.az_deg`, `earth.az_deg` | - | gradi | azimut, vedi [convenzione](kb:az-el-convention) |
| `sun.el_deg`, `earth.el_deg` | - | gradi | elevazione |

Non sono ammessi campi extra (`additionalProperties: false`).

## Replay da CSV

Con `TELEMETRY_CSV` impostato, il backend rilancia il CSV riga per riga (una al secondo di
default) come telemetria. Le colonne ammesse sono `t_utc`, `site_id`, `schema_version`, `power_w`,
`link_margin_db`, `sun_az_deg`, `sun_el_deg`, `earth_az_deg`, `earth_el_deg`; una colonna fuori
contratto o una cella vuota scarta la riga (conteggiata in `invalid_rows`).
