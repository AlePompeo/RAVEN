---
id: page-home
title: Home di RAVEN (Il problema)
kind: page
summary: >-
  La home, voce "Il problema" della barra, pone una domanda: al polo Sud della Luna la Terra sta a circa un grado sopra
  l'orizzonte, un lander riesce ancora a parlarle? Un pulsante "Prova tu" apre Simula, "Come funziona" porta alla storia
  in quattro passi: la Terra quasi sull'orizzonte, perche' un crinale conta (linea di vista contro diffrazione), cosa
  calcola RAVEN (margine di link, ore utili, dati al secondo) con un mini-simulatore a due cursori, e cosa
  significa per una missione (finestre di contatto in un mese illustrativo).
tags: [home, il problema, RAVEN, polo sud, orizzonte, diffrazione, linea di vista, zona di Fresnel, margine di link, mini-simulatore, Prova tu, Simula, finestre, ore utili, Learning, Avanzato, modalita', limiti, stack]
applies_to: [home]
related: [page-simula, page-analizza, page-siti, page-laboratorio, run-demo]
level: principiante
lang: it
last_verified: 2026-10-27
sources:
  - {ref: frontend/src/pages/home/Home.svelte, supports: "palco con la domanda, pulsanti Prova tu e Come funziona, interruttore di modalita', quattro passi con la riga tecnica solo in Avanzato, stack solo in Avanzato, riga d'onesta' con il link Chi siamo"}
  - {ref: frontend/src/pages/home/MiniSim.svelte, supports: "mini-simulatore pigro: due cursori, vista di lato in Canvas 2D, indicatore del margine e frase di Simula, pulsante Apri nel simulatore completo con ?el= e ?rh="}
  - {ref: frontend/src/pages/home/missionStrip.ts, supports: "mese illustrativo: elevazione sintetica 0,95 +- 0,55 gradi, crinale di 40 m a 2 km, 1 Mbps; ore della sola geometria contro ore in cui il link chiude"}
  - {ref: frontend/src/shell/mode.ts, supports: "modalita' Learning (predefinita) o Avanzato: ?mode= nell'URL, poi la scelta salvata in localStorage (hb.mode), poi Learning"}
  - {ref: frontend/src/shell/spatialNav.ts, supports: "in TV la freccia giu' dalla barra porta al primo controllo della pagina (Prova tu)"}
---
## Cosa mostra

Il palco con la Luna, il titolo RAVEN e una domanda: al polo Sud della Luna la Terra sta a circa un grado sopra
l'orizzonte, un lander riesce ancora a parlarle? Sotto, il pulsante principale "Prova tu" (apre [Simula](kb:page-simula))
e "Come funziona" (scende alla storia), poi l'interruttore "Learning | Avanzato".

## I quattro passi

1. La Terra resta quasi sull'orizzonte: dal polo Sud oscilla tra mezzo grado e un grado e mezzo; basta una collina
   lontana per coprirla (foto Earthrise di Apollo 8).
2. Perche' un crinale conta: se la Terra sta sopra la cima il segnale va diritto; se la cima la copre di poco il segnale
   si piega attorno allo spigolo (diffrazione) e arriva piu' debole.
3. Cosa calcola RAVEN: il margine di link in dB, da cui le ore utili e i dati al secondo. Qui c'e' il
   mini-simulatore: "Quanto e' alta la Terra nel cielo" e "Quanto e' alto il crinale" muovono la vista di lato (lander,
   crinale, linea di vista, zona di Fresnel, Terra), l'indicatore verde/ambra/rosso e la frase del risultato. Usa lo
   stesso modello del browser di Simula; "Apri nel simulatore completo" porta i due valori in Simula.
4. Cosa significa per una missione: un mese di esempio con due strisce, le ore in cui la sola geometria vede la Terra e
   le ore in cui il link chiude davvero contando il segnale piegato. E' un esempio illustrativo; per i siti veri ci sono
   [Siti](kb:page-siti) e [Analizza](kb:page-analizza).

## Learning e Avanzato

Learning e' la modalita' predefinita: solo testo semplice e una riga "Cosa stai guardando". Avanzato aggiunge a ogni
passo la riga tecnica (diffrazione a lama con il parametro nu, correzione della cresta da tabella split-step, formula
del margine, tag V/D/I delle fonti) e lo stack della ricerca. La scelta vale per tutto il sito, si ricorda nel browser
(chiave hb.mode, mai cookie) e si puo' forzare con ?mode=learning o ?mode=avanzato. I numeri non cambiano tra le modalita'.

## Limiti

In fondo una riga dice cosa non e' modellato: un solo ostacolo, nessuna misura radio reale al polo Sud, regolite da
letteratura, parametri radio illustrativi, cresta arrotondata da ITU-R P.526-9 (formula verificata, non misurata) con lo split-step come banda. Il link "Chi siamo" porta alla pagina
del team. Dettagli in [Pagina RAVEN](kb:page-grazinglink).
