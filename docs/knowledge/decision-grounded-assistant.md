---
id: decision-grounded-assistant
title: Decisione - assistente ancorato al materiale (RAG) con provider senza chiave
kind: decision
summary: >-
  L'assistente e' un RAG ancorato: le risposte sul sito vengono solo da documenti con fonte, con
  citazioni verificate dopo la generazione; il provider predefinito e' estrattivo cosi' la demo
  funziona su qualunque computer senza chiave API.
tags: [decisione, RAG, grounding, allucinazioni, citazioni, estrattivo, nessuna chiave, demo]
applies_to: [chat, assistant-extractive]
related: [assistant-howto]
level: intermedio
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/assistant.md, supports: "motivazioni, alternative, limiti e cosa non e' verificato"}
---
## Perche'

- **Correttezza**: un modello libero puo' inventare numeri e fonti; qui i fatti specifici del sito
  si leggono solo dal contesto recuperato e ogni citazione `[id]` fuori dal contesto viene rimossa.
- **Demo ovunque**: il provider estrattivo non usa rete ne' chiavi, quindi funziona offline.
- **Aggiornabilita'**: nuovi plugin e documenti vengono indicizzati senza modifiche di codice.

## Alternative considerate

Un LLM senza recupero (rischio di allucinazioni), embeddings neurali (dipendenze pesanti, non necessarie in questa versione), chiamate a strumenti/funzioni (superficie d'attacco maggiore: rimandate).

## Limiti

Una risposta estrattiva e' meno fluida di quella di un LLM. La qualita' dei modelli gratuiti non e' stata misurata.
