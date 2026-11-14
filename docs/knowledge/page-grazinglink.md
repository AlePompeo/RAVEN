---
id: page-grazinglink
title: Pagina RAVEN
kind: page
summary: >-
  RAVEN calcola il margine del collegamento radio tra un rover al polo Sud lunare e la Terra,
  quando la Terra sta a 0,5-1,5 gradi dall'orizzonte e un crinale la nasconde o la sfiora. La pagina
  confronta la finestra solo geometrica con quella reale (con diffrazione, multipath e antenna) in
  sei schede, con grafici, tabelle alternative ed esportazione CSV e JSON. I parametri radio sono
  ipotesi illustrative (tag I).
tags: [pagina, RAVEN, diffrazione, bordo a lama, nu, finestra geometrica, finestra reale, zona di transizione, crinale, LOLA, DEM, profilo del terreno, CSV, antenna, HPBW, gimbal, compensatore, bit rate, margine di link, multipath, polo sud, illustrativo, make grazing-dem, ITU-R P.526]
applies_to: [grazinglink, analizza]
related: [page-analizza, link-budget, page-compare, page-viewer]
level: intermedio
lang: it
last_verified: 2026-10-26
sources:
  - {ref: frontend/src/pages/grazinglink/GrazingLink.svelte, supports: "modulo Scenario (sito coperto dal DEM, profilo CSV facoltativo, spazzolamento della Terra, inizio UTC, durata, passo, stazione, guadagno, potenza, velocita', k), schede ARIA, stati di errore"}
  - {ref: frontend/src/pages/grazinglink/grazing.ts, supports: "validazione del profilo CSV (come l'API), costruzione della richiesta, ore delle due finestre e zona di transizione, integrali di Fresnel, mappa di calore, esportazioni"}
  - {ref: backend/api/raven_experiments.py, supports: "esperimenti RF didattici /api/raven/experiments, non previsioni di missione; parametri radio unificati, nessun download implicito, 503 senza DEM o efemeridi, 422 generico"}
  - {ref: backend/domain/grazing/analysis.py, supports: "finestre geometrica e reale, segnalazioni (terreno, raggio risolto, multipath, correzione, geometria estrapolata) e limiti dichiarati"}
  - {ref: docs/domain/grazinglink-model.md, supports: "equazioni, parametri V/D/I e limiti del modello"}
---
## Cosa fa

Dal polo Sud lunare la Terra resta a 0,5-1,5 gradi sopra l'orizzonte: un crinale puo' nasconderla o
sfiorarla. Gli strumenti solo geometrici dicono "visibile" o "bloccato". RAVEN aggiunge la
**diffrazione** sul crinale (bordo a lama esatto e correzione per cresta arrotondata), il
**multipath** sul regolite e l'**antenna** (guadagno, larghezza di fascio, puntamento), e ne ricava
il margine di link in dB nel tempo per ogni velocita' di trasmissione. Il risultato e' un
**potenziale nelle ipotesi dichiarate**, non una previsione di missione.

## Il modulo

Si sceglie un sito (solo quelli coperti dal DEM LOLA, latitudine <= -85 gradi; gli altri sono
disabilitati con "fuori copertura DEM"), l'inizio UTC, la durata, il passo, la stazione di terra
(DSN 34 m o 18 m), guadagno dell'antenna del rover, potenza, velocita' per la finestra e il margine
k del compensatore. Facoltativo: un **profilo del terreno in CSV** (distanza in m da 0 e crescente,
quota in m; al massimo 1500 punti e circa 60 kB), validato nel browser come fa l'API; con un profilo
si puo' scegliere anche uno **spazzolamento dell'elevazione della Terra** al posto delle efemeridi.
Un profilo di prova e' marcato "profilo sintetico di prova": non e' un dato lunare.

## Le sei schede

1. **Margine nel tempo**: elevazione della Terra contro quella del crinale e margine di link per
   velocita'; sopra 0 dB il link chiude.
2. **Finestre**: la doppia barra con la finestra geometrica (Terra sopra il crinale) e quella reale
   (margine >= 0 dB), con ore e percentuali. La **zona di transizione** sono le ore in cui la
   geometria dice "bloccato" ma il link chiude, per effetto della diffrazione.
3. **Diffrazione**: la perdita J(nu) esatta (integrali di Fresnel) contro l'approssimazione ITU-R P.526-9,
   eq. (27), valida per nu > -0,78; sotto tale soglia lo zero e' una scelta del codice. Sono mostrati i
   punti di funzionamento e la mappa di calore della correzione per
   cresta arrotondata (nu per raggio), con le celle anomale e l'incertezza. Tabella alternativa inclusa.
4. **Antenna**: guadagno e HPBW contro il diametro, perdita di puntamento con la formula dello script
   (12 (x/HPBW)^2) e la variante corretta (12,04), con la differenza in dB, e la necessita' del gimbal
   rispetto alla librazione.
5. **Compensatore**: interruzioni e dati consegnati contro k, e la velocita' scelta nel tempo. E' un
   controllo in avanti con margine statistico, non apprendimento per rinforzo.
6. **Parametri e limiti**: ogni parametro con etichetta V, D o I e fonte, le segnalazioni
   dell'analisi (prodotto del terreno, raggio risolto, multipath, incoerenza "aperta", passi con
   geometria estrapolata) e i limiti dichiarati.

Ogni grafico ha una tabella alternativa e i pulsanti "Scarica CSV" e "Scarica JSON".

## Limiti da ricordare

Ostacolo singolo dominante; nessuna misura radio reale al polo Sud; parametri del regolite da
letteratura; la correzione della cresta arrotondata e' T(m,n) di ITU-R P.526-9 par. 4.2 (testo letto il
2026-11-04), non misurata; la tabella split-step resta come confronto e lo scarto e' l'incertezza. JPL 42-226
dice che la correzione svanisce per Terra lontana, ma con un parametro senza raggio: non usato. Nessuna di
queste e' una validazione sperimentale. **I parametri radio sono
ipotesi illustrative (tag I).**

## Messaggi di errore

Senza i dati LOLA il server risponde 503 e la pagina lo dice: si scaricano con `make grazing-dem`
(tile in build/lola), oppure si carica un proprio profilo. Un sito fuori copertura DEM o parametri non
validi danno 422; senza efemeridi 503. Nessun risultato viene inventato.
