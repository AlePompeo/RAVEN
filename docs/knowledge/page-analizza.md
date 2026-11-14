---
id: page-analizza
title: Pagina Analizza
kind: page
summary: >-
  Analizza ospita l'analisi RAVEN di un sito reale del polo Sud nel tempo: margine di link, finestra geometrica
  contro finestra reale, diffrazione, antenna, compensatore. In Learning si vedono sito, inizio UTC, durata, antenna sulla
  Terra e velocita', un riepilogo e due grafici; in Avanzato tutti i campi e le sei schede. I numeri sono
  gli stessi nelle due modalita'. La vecchia rotta /grazinglink porta qui con la stessa query.
tags: [pagina, analizza, RAVEN, analisi, sito, finestre, margine di link, diffrazione, antenna, compensatore, Learning, Avanzato, modalita']
applies_to: [analizza, grazinglink]
related: [page-grazinglink, page-siti, link-budget]
level: principiante
lang: it
last_verified: 2026-10-29
sources:
  - {ref: frontend/src/pages/analizza/index.ts, supports: "rotta /analizza con il componente di RAVEN e alias /grazinglink"}
  - {ref: frontend/src/pages/grazinglink/GrazingLink.svelte, supports: "campi e schede mostrati in Learning e in Avanzato, avviso se un campo nascosto non e' valido, esportazione JSON solo in Avanzato"}
  - {ref: docs/design/grazinglink-ux.md, supports: "vista semplice per default e dettagli tecnici dietro Avanzato"}
---
## A cosa serve

Scegli un sito vero, l'inizio in UTC e per quanti giorni: la pagina stima quando il segnale verso la Terra arriva e con
quanto margine. Il riepilogo mostra le ore di visibilita' geometrica, di collegamento stimato e di transizione fuori
linea di vista. Il calcolo e' quello descritto in [page-grazinglink](kb:page-grazinglink).

## Learning

Campi: "Dove (sito al polo Sud)", "Quando iniziare (UTC)", "Per quanti giorni", "Antenna sulla Terra", "Quanti dati al
secondo". Gli altri (passo, profilo del terreno, guadagno, potenza, k del compensatore, diametri, parametri illustrativi)
mantengono i valori impostati; se uno di questi non e' valido la pagina lo dice e invita a passare ad Avanzato. Il
riepilogo e' seguito dal margine nel tempo alla velocita' scelta e dal confronto delle finestre.

## Avanzato

Tutti i campi con unita' e tag, le sei schede (Margine nel tempo, Finestre, Diffrazione, Antenna, Compensatore,
Parametri e limiti) e l'esportazione JSON della richiesta completa. Tornando a Learning con una scheda tecnica aperta
si vedono i grafici semplici; il risultato non viene ricalcolato.
