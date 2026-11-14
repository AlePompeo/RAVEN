---
id: pipeline-guarantees
title: Garanzie della pipeline dati (at-least-once e idempotenza)
kind: concept
summary: >-
  La pipeline consegna at-least-once (un messaggio non confermato torna in coda) e l'elaborazione
  e' idempotente con chiave (source_id, site_id, t_utc): il livello clean e' effectively-once, ma
  NON si promette exactly-once end-to-end perche' raw puo' contenere duplicati.
tags: [pipeline, at-least-once, idempotenza, dedup, effectively-once, coda, dead-letter, backpressure, Parquet, DuckDB]
applies_to: [ingest-csv, pipeline]
related: [telemetry-contract]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/pipeline.md, supports: "garanzie, layout dei dati, validazione, interrogazione"}
  - {ref: backend/plugins/ingest_csv/plugin.py, supports: "sorgente CSV che mappa le colonne sul contratto telemetry"}
---
## Garanzie

- **At-least-once**: un messaggio ritirato (`get`) e non confermato (`ack`) torna in coda dopo
  `visibility_timeout_s`, anche dopo un crash con la coda durevole; dopo `max_attempts` consegne va
  in dead-letter con un motivo.
- **Idempotenza**: la chiave di dedup e' `(source_id, site_id, t_utc)`. Lo stesso record ripetuto
  produce una sola riga nel livello `clean` (effectively-once su `clean`).
- **Non** exactly-once end-to-end: `raw` e' il registro di cio' che e' arrivato e puo' contenere
  un record piu' volte.
- **Ordine** garantito solo per partizione (sorgente + giorno UTC); l'arrivo fuori ordine e'
  accettato e contato in `out_of_order`.
- **Backpressure**: coda con limite; politica `block` oppure `drop_with_counter`.
- **Scritture atomiche**: file temporaneo, `fsync`, `os.replace`; i lettori vedono solo i file `part-*.parquet` completi.

## Livelli

`raw` (come arrivato), `clean` (validato sul contratto telemetry, UTC, dedup), `curated` (aggregati
orari per sito). Percorso: `<PIPELINE_DIR>/{raw,clean,curated}/source=<id>/date=YYYY-MM-DD/`.

## Abilitazione

La pipeline e' attiva solo se `PIPELINE_DIR` e' impostata e l'extra `[data]` e' installato;
altrimenti `GET /api/pipeline/metrics` risponde `{"enabled": false}`.
