<!-- SPDX-License-Identifier: Apache-2.0 -->
# Base di conoscenza del Learning Assistant

L'assistente risponde solo da questi documenti. Aggiungere un file qui (o in
`backend/plugins/<plugin>/knowledge/`) basta: all'avvio viene indicizzato, senza modifiche di codice
(con `ASSISTANT_DEV_RELOAD=1` si ricostruisce da solo quando i file cambiano).

## Regole d'autore

1. Un file = un documento, con front-matter YAML (vedi `_template.md`) e corpo markdown. I file che
   iniziano con `_` e i `README.md` sono ignorati.
2. `id` unico, minuscolo (`a-z0-9._-`). Gli id `plugin-<id>` e `contract-<nome>` sono riservati alle voci
   generate automaticamente da `manifest.toml` e da `contracts/*.schema.json` (un documento scritto a mano
   con lo stesso id le sostituisce).
3. `kind`: `concept`, `formula`, `method`, `simulation`, `page`, `glossary`, `problem`, `decision`.
4. Ogni affermazione specifica del sito (numeri, unita', nomi) deve essere verificabile: metti il file, il
   test o l'URL in `sources` con cosa sostiene. I percorsi del repository vengono controllati.
5. Le **formule** richiedono `expression`, `variables` (con `unit` per ogni variabile), `assumptions`,
   `limits` e un `worked_example` con `inputs` e `outputs`. Se la formula e' calcolata da un plugin, aggiungi un
   test che confronta l'esempio con l'uscita reale (vedi `tests/backend/assistant/test_knowledge_lint.py`).
6. Conoscenza generale di dominio ammessa, ma dichiarala ("conoscenza generale") nel testo e nella fonte.
7. `applies_to`: id dei plugin e delle pagine (nome della cartella in `frontend/src/pages/`) a cui il documento si
   riferisce: serve al contesto di pagina e ai suggerimenti.
8. Link interni: `[testo](kb:altro-id)` e `related: [id]` devono puntare a id esistenti.
9. Scrivi in italiano (termini tecnici in inglese se standard) oppure imposta `lang: en`.

## Controlli

`pytest tests/backend/assistant` valida tutti i documenti (id unici, campi richiesti, unita' presenti,
link e fonti esistenti, ogni plugin con almeno un documento o in lista di esenzione) e il set di
domande d'oro. Gli errori di un documento non fermano l'app: compaiono come `knowledge_errors` in
`GET /api/assistant/status`.

## Hackathon

Copiare `hackathon/_problem_template.md` in `docs/knowledge/hackathon/problem.md` e compilarlo: descrive il
problema, la metodologia e le scelte, cosi' l'assistente puo' spiegare la soluzione.
