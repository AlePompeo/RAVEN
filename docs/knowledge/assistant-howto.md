---
id: assistant-howto
title: Come funziona il Learning Assistant
kind: concept
summary: >-
  Il Learning Assistant risponde SOLO dal materiale del sito (documenti di conoscenza, manifest dei
  plugin, contratti dati), cita ogni fonte come [id] e, se la risposta non c'e', lo dice. Di default
  usa il provider assistant-extractive, che non richiede chiavi ne' rete.
tags: [assistente, learning assistant, RAG, citazioni, assistant-extractive, assistant-openai-compat, Ollama, provider, chat]
applies_to: [chat, assistant-extractive, assistant-openai-compat]
related: [decision-grounded-assistant, run-demo]
level: principiante
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/assistant.md, supports: "architettura, contratto HTTP, configurazione dei provider, limiti"}
  - {ref: backend/assistant/service.py, supports: "flusso recupero -> prompt -> provider -> validazione, fallback estrattivo"}
---
## Come risponde

1. Cerca nel materiale del sito (ricerca BM25, italiano e inglese).
2. Compone la risposta con i passaggi trovati e li cita con `[id]`.
3. Se non trova nulla di pertinente risponde che l'informazione non e' presente nel materiale del sito.

## Chiavi API

Il provider predefinito non richiede alcuna chiave API. Solo `assistant-openai-compat` puo' usarne una
(`ASSISTANT_LLM_API_KEY`), letta unicamente dall'ambiente del server: non e' mai nel client ne' nei log.

## Provider

- `assistant-extractive` (default): deterministico, nessuna rete, nessuna chiave.
- `assistant-openai-compat`: usa un modello linguistico tramite un endpoint compatibile OpenAI
  (per esempio Ollama in locale). Se il provider fallisce, l'assistente ripiega sulla risposta estrattiva e lo segnala.

Si sceglie con la variabile d'ambiente `ASSISTANT_PROVIDER`. Il testo inviato a un provider ospitato lascia la macchina.

## Lingua del sito

Il sito e' disponibile solo in inglese (predefinita) e italiano. Il selettore e' nella barra in alto (nel menu su
schermi stretti); la scelta si ricorda nel browser e si puo' forzare con `?lang=en` o `?lang=it`.

## Aggiungere conoscenza

Basta aggiungere un file markdown con front-matter in `docs/knowledge/` o in
`backend/plugins/<plugin>/knowledge/`: nessuna modifica di codice. Guida in `docs/knowledge/README.md`.
