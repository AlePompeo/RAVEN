---
id: run-install
title: Installazione e avvio con un solo comando
kind: page
summary: >-
  Da un clone nuovo, ./install.sh (solo Linux) installa Python, Node e le
  dipendenze senza permessi di amministratore, compila il sito, scarica i kernel NAIF, avvia il
  server su 127.0.0.1 e apre il browser. Si ferma con ./stop.sh.
tags: [installazione, install.sh, stop.sh, avvio, quick start, uv, node, kernel NAIF, LOLA, offline]
applies_to: [home]
related: [run-demo, assistant-howto]
level: principiante
lang: it
last_verified: 2026-11-09
sources:
  - {ref: README.md, supports: "sezione Quick start"}
  - {ref: install.sh, supports: "passi, opzioni e download dell'installer per Linux/macOS"}
  - {ref: backend/api/report_routes.py, supports: "POST /api/raven/report/pdf: tetto 6 MB, limiti, 503 senza motore"}
  - {ref: backend/adapters/report_weasyprint.py, supports: "WeasyPrint: solo data:, font incorporato, determinismo"}
  - {ref: backend/assets/report-print.css, supports: "foglio di stile del PDF: pagine, segnalibri, indice, layout dei grafici"}
  - {ref: frontend/src/pages/planner/reportPrint.css, supports: "palette di stampa e stili dei componenti del report"}
---
## Comando

- Linux: `./install.sh`

Opzioni: `--yes` (nessuna domanda), `--no-browser`, `--port N` (predefinita 8000, se occupata ne
sceglie una libera), `--skip-data`, `--no-start`, `--reinstall`, `--help`.

## Cosa fa

1. Usa Python 3.12+ e Node 22+ se gia' presenti; altrimenti li scarica in `.tools/` (Node da
   nodejs.org con SHA-256 verificato, `uv` con checksum fissato, CPython circa 35 MB).
2. Crea `.venv/` e installa le dipendenze con `constraints/base.txt` (extra `fusion` e `sky`, piu' `pdf` se le librerie
   Pango del sistema sono presenti: altrimenti avvisa quale pacchetto installare, senza sudo, e prosegue; il PDF del
   report ripiega allora sulla stampa del browser. Vedi la sezione "PDF del report" piu' sotto).
3. Tutto il lavoro lento e indipendente gira **in parallelo**: `npm ci` e `npm run build` (Node scaricato se manca),
   i plugin C (se esistono `gcc` e `make`), i pacchetti Python e i dati. I download dei dati partono appena sono
   installati numpy e scipy (pochi secondi), mentre il resto dei pacchetti si installa.
4. Dati obbligatori (salvo `--skip-data`): kernel NAIF (45 MB, SHA-256 verificato), tile LOLA dei siti predefiniti
   (circa 41 MB) e terreno di tutti i 51 siti del catalogo (circa 250 MB: prodotto globale a 237 m e tile polari,
   24 richieste alla volta), poi le maschere d'orizzonte calcolate su tutti i core. Senza rete l'installer si ferma e dice
   cosa rilanciare, conservando i file gia' scaricati. Una sola domanda iniziale per tutto, salvo `--yes`.
5. Il tetto della cache del terreno e' 300 MB.
6. Avvia il server solo su 127.0.0.1, attende `/health` e apre il browser.

Non modifica nulla fuori dalla cartella del progetto e non cambia il PATH di sistema. Rieseguirlo
rifa' solo cio' che e' cambiato. Il registro e' `install.log`.

## PDF del report generato dal server

Il pulsante "Scarica PDF" del Mission Planner invia al server l'HTML stampabile del report (senza controlli interattivi,
grafici SVG con testo alternativo) a `POST /api/raven/report/pdf` e riceve un PDF uguale in ogni browser: indice con
numeri di pagina (`target-counter`), segnalibri dai titoli, "Pagina X di Y", titolo, lingua e autore "RAVEN", uscita
deterministica. Il motore e' WeasyPrint (extra `pdf`, licenza BSD-3) e richiede le librerie Pango del sistema.
Garanzie: recupero di risorse solo `data:` (un riferimento `file:` o `http:` viene rifiutato), HTML ripulito con lista di
consentiti, font HB Sans (SIL OFL 1.1) incorporato, tetto del corpo 6 MB solo per questa rotta (413 oltre), frequenza
`PDF_RATE_PER_MIN`, concorrenza `PDF_MAX_CONCURRENT`, tempo `PDF_TIMEOUT_S`; errori generici. Il motore non impagina bene
le griglie CSS: il server le trasforma in blocchi e il foglio di stile del PDF (`backend/assets/report-print.css`) affianca i
grafici A/B con inline-block, senza griglie. Il PDF ha copertina, indice con puntini e numeri di pagina, sintesi esecutiva,
fasce colorate per fase 0-F e tinte per tipo di contenuto (stato sempre con colore, icona e parola), tabelle con intestazione
ripetuta; i titoli del PDF salgono di un livello (h1-h4 reali). I colori stanno in `frontend/src/pages/planner/reportPrint.css`
(condiviso con la stampa del browser) e il contrasto WCAG AA e' verificato da `reportPrintContrast.test.ts`. I grafici SVG
ricevono lo stile calcolato come attributi (il motore ignora classi e `var()`). Il tempo di generazione del report reale
(27 pagine, due scenari, affidabilita') e' circa 7-9 s. La conformita' PDF/UA non e' verificata.
Se Pango manca, `install.sh` non installa l'extra e dice quale pacchetto installare (Fedora `pango`; Debian/Ubuntu
`libpango-1.0-0 libpangoft2-1.0-0`; Arch `pango`), senza sudo; il server risponde 503 e la pagina apre la stampa del
browser, dove l'indice ha i collegamenti ma non i numeri di pagina. L'immagine Docker (python:3.14-slim) non include
Pango: li' vale il ripiego. Il codice sta in `backend/api/report_routes.py`, `backend/adapters/report_weasyprint.py` e
`backend/domain/raven/report_html.py`.

## Fermare e disinstallare

`./stop.sh` ferma solo il server avviato dall'installer (PID in
`.server.pid`). Per disinstallare si eliminano `.tools/`, `.venv/` e `build/`.
