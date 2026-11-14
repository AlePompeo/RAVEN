---
id: page-simula
title: Pagina Simula
kind: page
summary: >-
  Simula e' la pagina per giocare con il problema. La scheda "Scena" e' il simulatore: scena 3D del lander guidata dai
  controlli (elevazione della Terra, quota e raggio del crinale, antenna, dati al secondo), indicatore grande del
  margine con una frase, indicatore di validita', grafico del margine contro l'elevazione e mappa di validita', tutto
  calcolato nel browser. "L'onda" mostra la diffrazione dopo il crinale con gli stessi valori; "Sito nel tempo" e' la
  Scena lander con il terreno LOLA. Learning e Avanzato cambiano cosa si vede, non i numeri.
tags: [pagina, simula, simulatore, scena, onda, scena lander, margine di link, diffrazione, zona di Fresnel, mappa di validita', preset, missione guidata, sito reale, Learning, Avanzato]
applies_to: [simula, lander, wave]
related: [page-lander, page-wave, page-analizza, glossary-link-margin, glossary-diffraction, glossary-fresnel-zone]
level: principiante
lang: it
last_verified: 2026-10-27
sources:
  - {ref: frontend/src/pages/simula/Simula.svelte, supports: "schede Scena (simulatore), L'onda (Onda 3D) e Sito nel tempo (Scena lander), caricate in modo lazy"}
  - {ref: frontend/src/pages/simula/SimulaScene.svelte, supports: "controlli, preset, missione, indicatore, grafico, mappa, sito reale, Avanzato con tag ed esportazione"}
  - {ref: frontend/src/pages/simula/linkModel.ts, supports: "modello nel browser: nu, bordo a lama esatto, correzione della cresta dalla tabella, spazio libero, antenna, multipath, margine, indicatori di validita'"}
  - {ref: frontend/src/pages/simula/linkModel.test.ts, supports: "parita' con il motore Python entro 0,01 dB su 30 casi (scripts/dump_link_parity.py)"}
  - {ref: frontend/src/pages/simula/index.ts, supports: "alias delle vecchie rotte /lander (tab=sito) e /wave (tab=onda)"}
  - {ref: docs/design/grazinglink-ux.md, supports: "ruolo di Simula, due modalita', indicatore e mappa di validita', riga d'onesta'"}
  - {ref: frontend/src/pages/simula/SimulaScene.svelte, supports: "siti personalizzati in modalita' sito reale"}
---
## Cosa contiene

Tre schede sotto il titolo "Simula" e l'interruttore di modalita':

- **Scena** (il simulatore, `?tab=scena`, predefinita). A sinistra la scena 3D: lander, crinale, tubo della prima
  zona di Fresnel, Terra alla sua elevazione; senza WebGL la stessa scena diventa una sezione laterale 2D. A destra
  l'indicatore del margine (verde / ambra / rosso con parola e simbolo), una frase ("Il segnale arriva con 18 dB di
  margine: puoi inviare 100 kbps") e l'indicatore di validita' con il perche'. Sotto: il grafico del margine contro
  l'elevazione della Terra (punto corrente, soglia 0 dB, orizzonte geometrico del crinale) e la mappa di validita'.
- **L'onda** (Onda 3D): parte da frequenza, raggio e distanza del crinale della Scena. Aperta da sola usa i suoi
  predefiniti. Dettagli in [page-wave](kb:page-wave).
- **Sito nel tempo** (Scena lander, `?tab=sito`): un sito reale nel tempo con il terreno LOLA. Dettagli in
  [page-lander](kb:page-lander).

## Scenario didattico e sito reale

Per default la Scena usa un crinale sintetico su terreno piano, con l'etichetta "Scenario didattico (non e' un sito
reale)": tutti i numeri sono calcolati nel browser mentre si muovono i controlli (nessun pulsante Calcola). Il
pulsante "Usa un sito reale" carica la scena di un sito coperto dal DEM LOLA da /api/raven/scene: il margine
mostrato e' quello del modello unico RAVEN Core (stesso numero di Pianificatore, Lander e Visualizzatore; la pagina ne dichiara la versione), e i controlli regolano solo antenna, dati al secondo e tempo (piu' palo e stazione in
Avanzato). Il grafico, con un sito reale, usa il crinale dominante di quell'istante come ostacolo singolo: e'
un'approssimazione dichiarata.

## Learning e Avanzato

Learning: cinque controlli con nomi quotidiani (quanto e' alta la Terra, quanto e' alto il crinale, quanto e'
arrotondata la cima, quanto e' grande l'antenna, quanti dati al secondo), definizioni di una riga, i preset "Terra
alta", "Terra radente", "Crinale che blocca", "Antenna piccola" e una missione guidata a 5 passi che si spuntano da
soli quando l'utente fa la cosa richiesta. Avanzato: tutti i parametri con unita', etichetta V/D/I e fonte (dal
registro RAVEN, /api/raven/parameters), i controlli di validita', il confronto tra varianti (bordo a lama, cresta
arrotondata, multipath, antenna dello script contro corretta), le incertezze, la tabella dei numeri, l'esportazione
JSON e CSV e lo stato completo nell'URL (link riproducibile). In Learning l'URL resta pulito. I numeri sono identici
nelle due modalita'.

## Quando la risposta smette di valere

L'indicatore di validita' e la mappa (elevazione della Terra contro quota del crinale, 60 x 40 celle; colore = stato,
trama = validita') segnalano: Terra all'orizzonte o sotto (fuori modello), angolo cima-linea di vista oltre 10 gradi
(parassiale incerta) o 20 gradi (fuori), correzione della cresta saturata fuori dalla tabella (nu fuori da -1,5...3)
o estrapolata per un crinale fuori da 500-8000 m, punto di riflessione oltre il crinale (multipath non applicato),
tabella non disponibile (correzione omessa), raggio non risolto dal DEM (solo sito reale). Una riga fissa ricorda
cosa non e' modellato: un solo ostacolo, nessuna misura radio reale al polo Sud, regolite da letteratura, parametri
radio illustrativi, cresta arrotondata da ITU-R P.526-9 (formula verificata, non misurata) con lo split-step come
banda. Nel pannello Avanzato il confronto tra varianti mostra la cresta ITU (con incertezza) e la cresta con la
tabella split-step.

## Link

`/simula?tab=scena&mode=avanzato&el=0.7&rr=200` apre il simulatore con quei valori; `/lander?...` porta alla scheda
Sito nel tempo e `/wave?...` all'onda. Per un sito reale su un mese intero si passa ad [page-analizza](kb:page-analizza).

## Sito personalizzato

In modalita' sito reale l'elenco dei siti include quelli personalizzati; la scena usa il prodotto LOLA che copre il punto (risoluzione
nel risultato).
