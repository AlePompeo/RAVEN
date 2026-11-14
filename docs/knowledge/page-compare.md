---
id: page-compare
title: Pagina Confronto siti
kind: page
summary: >-
  Confronto siti classifica i siti con il modello unico RAVEN Core (POST /api/raven/compare): ordine lessicografico
  sulle componenti scelte (ore utili, ore ignote, margine minimo e mediano, carica minima), tutte sempre visibili,
  nessun punteggio. I siti con componenti ignote (senza terreno LOLA, dati mancanti) stanno a parte, come "non
  confrontabili", con il motivo. La pagina dichiara versione e registro del modello.
tags: [pagina, confronto siti, RAVEN, Luna, classifica, componenti, ore utili, ore ignote, margine, non confrontabile, DEM, LOLA, fuori copertura, modello unico, scenario condiviso]
applies_to: [compare, siti]
related: [page-siti, page-model, ephemeris-method, link-budget, page-viewer]
level: intermedio
lang: it
last_verified: 2026-11-05
sources:
  - {ref: frontend/src/pages/compare/RavenCompare.svelte, supports: "modulo Scenario, tabella delle componenti, elenco dei non confrontabili con il motivo, riga che dichiara la regola, versione del modello, pulsanti di riga"}
  - {ref: frontend/src/pages/compare/ravenRanking.ts, supports: "ordine richiesto (criterio scelto per primo, poi i predefiniti), lettura delle righe senza punteggio"}
  - {ref: frontend/src/shell/ravenApi.ts, supports: "client di /api/raven/compare con i tetti D9, cache delle richieste identiche, annullamento, errori 422/503"}
  - {ref: backend/api/raven_routes.py, supports: "POST /api/raven/compare: limiti, cache, 422 generico, 503 senza efemeridi"}
  - {ref: backend/domain/raven/ranking.py, supports: "classifica lessicografica, pareggio per id dichiarato, gruppo not_comparable con i motivi"}
  - {ref: docs/domain/raven-model.md, supports: "decisione D5 (classifica unica) e tetti D9"}
  - {ref: docs/domain/sites.md, supports: "gli otto siti con coordinate e fonte; per i siti polari il centro della feature IAU, non della regione"}
---
## Cosa fa

La pagina confronta i siti con lo **stesso modello** usato da Pianificatore, scena Lander, Visualizzatore e
Simula (RAVEN Core, versione e registro mostrati sopra la tabella). Ogni sito riceve le sue componenti:
**ore utili** (stato operativo e collegamento utilizzabile), **ore ignote** (dipendono da ingressi ignoti,
mai contate come utili), **margine RF minimo e mediano** sui passi con margine noto e **carica minima** della
batteria; in Avanzato anche il tempo al primo blackout. E' un potenziale nelle ipotesi dichiarate, non una
previsione di missione.

Si scelgono inizio (UTC), durata, passo, stazione di terra, bit-rate, guadagno e siti, e si preme "Confronta con
RAVEN". I valori predefiniti sono quelli del modello: 7 giorni a 10 minuti. Limiti (D9): 1500 passi per sito e
6000 in totale; la pagina li controlla prima di chiamare il server e spiega come rientrare (la finestra lunare
da 29,53 giorni a 10 minuti, 4252 passi, e' fuori tetto).

## Classifica

L'ordine e' **lessicografico** sulle componenti: il criterio scelto in "Ordina prima per" conta per primo, poi
valgono ore utili, ore ignote (meno e' meglio) e margine minimo. A parita' decide l'id del sito, che e' una
scelta dichiarata e non un criterio fisico. **Non esiste un punteggio**: nessuna media pesata. Un sito del tutto
bloccato da terreno lontano noto (nessun numero di margine) e' ultimo e mostrato come "bloccato (noto)": e' un
no, non un ignoto.

## Non confrontabili

I siti con componenti ignote per il confronto scelto (per esempio fuori dalla copertura LOLA, latitudine > -85
gradi: Apollo 11, Apollo 17, Mons Mouton) non stanno ne' sopra ne' sotto gli altri: sono elencati in "Non
confrontabili" con il motivo (per esempio "margin_min_db unknown"). Nessun numero viene inventato.

## Errori

Parametri fuori tetto: messaggio prima della chiamata. 422 dal modello: parametri rifiutati. 503: efemeridi non
disponibili o server occupato. Nessun risultato viene mostrato in caso di errore. Dal [Visualizzatore 3D](kb:page-viewer)
ogni sito si mostra sul globo e si apre nel Pianificatore con sito, istante, stazione e bit-rate nell'URL.
