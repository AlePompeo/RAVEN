---
id: run-demo
title: Come avviare la demo in locale
kind: page
summary: >-
  Demo locale senza Docker: make venv, make build-c, build del frontend, poi
  STATIC_DIR=frontend/dist make dev su http://127.0.0.1:8000. Per la telemetria di esempio si
  imposta TELEMETRY_CSV. L'assistente funziona senza alcuna chiave API.
tags: [demo, avvio, installazione, make dev, quick start, STATIC_DIR, TELEMETRY_CSV, build, Docker]
applies_to: [home]
related: [assistant-howto, telemetry-contract]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: README.md, supports: "sezione Avvio rapido (locale, senza Docker)"}
  - {ref: Makefile, supports: "target venv, build-c, dev"}
  - {ref: .env.example, supports: "variabili STATIC_DIR e TELEMETRY_CSV"}
---
## Passi

1. `make venv` crea il virtualenv e installa le dipendenze di sviluppo.
2. `make build-c` compila i plugin C (`fspl`, `servo_ctrl`); serve `gcc`.
3. `cd frontend && npm ci && npm run build && cd ..` compila il frontend.
4. `STATIC_DIR=frontend/dist make dev` avvia il server su http://127.0.0.1:8000.

Per lo sviluppo del frontend con ricarica a caldo: `cd frontend && npm run dev` (proxy `/api`
verso 127.0.0.1:8000).

## Telemetria di esempio

Impostare `TELEMETRY_CSV` al percorso di un CSV con colonne del [contratto di telemetria](kb:telemetry-contract):
il backend lo rilancia riga per riga. Senza, la pagina Telemetria non riceve campioni.

## Assistente

Il Learning Assistant risponde dal materiale del sito senza chiavi ne' rete (provider
`assistant-extractive`); vedi [come funziona l'assistente](kb:assistant-howto).

## Con Docker

`make docker` poi `docker run --rm -p 127.0.0.1:8000:8000 hackathon-base:dev`. Il README segnala che
`docker compose` non e' stato provato su quella macchina.
