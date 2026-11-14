---
# Copia questo file, rinominalo (NON iniziare il nome con "_") e compila. I file con "_" sono ignorati.
id: esempio-id-unico            # minuscolo, cifre, - . _ ; unico in tutto il repository
title: Titolo leggibile
kind: concept                   # concept | formula | method | simulation | page | glossary | problem | decision
summary: >-
  Una o due frasi autosufficienti: e' il testo che l'assistente usa per primo.
tags: [parole, chiave, anche in inglese]
applies_to: [id-plugin, id-pagina]   # id di plugin (manifest) e cartelle di frontend/src/pages/<id>
related: [altro-id]                  # ogni id deve esistere
level: intermedio               # principiante | intermedio | tecnico
lang: it                        # it | en
last_verified: 2026-01-01       # data in cui hai riverificato ogni affermazione
sources:                        # almeno una; i percorsi del repository devono esistere
  - {ref: docs/esempio.md, supports: "che cosa sostiene questa fonte"}
# --- solo per kind: formula (tutti obbligatori) ---
# expression: "y = a*x + b"
# variables:
#   - {symbol: x, name: ingresso, unit: m, range: "[0, 10]"}   # unit obbligatoria ("-" se adimensionale)
# assumptions: [ipotesi 1]
# limits: [limite 1]
# worked_example:
#   inputs: {x: 2}
#   outputs: {y: 5}
#   note: "calcolo passo per passo"
# derivation: ["passo 1", "passo 2"]
---
## Sezione

Ogni intestazione `##` diventa un passaggio citabile. Scrivi solo fatti verificabili e cita
il file o il test che li sostiene in `sources`. Collega altri documenti con
[testo](kb:altro-id). Marca esplicitamente la "conoscenza generale" non verificabile nel repository.
