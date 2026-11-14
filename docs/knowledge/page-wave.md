---
id: page-wave
title: Pagina Onda 3D
kind: page
summary: >-
  Onda 3D mostra in una superficie 3D interattiva l'intensita' |E|^2 di un'onda piana che sfiora un
  crinale (bordo a lama o cresta arrotondata), calcolata con uno split-step di Fresnel. Un cursore di
  distanza sposta un piano di sezione e il grafico 2D sotto confronta la simulazione con la curva
  esatta del bordo a lama. Modello scalare parassiale: un solo crinale, onda piana, niente regolite.
tags: [pagina, onda 3D, diffrazione, frange di Fresnel, bordo a lama, nu, split-step, FFT, cresta arrotondata, banda X, sezione, WebGL, Canvas 2D, CSV, scalare, parassiale]
applies_to: [wave, simula]
related: [page-simula, page-grazinglink, page-viewer]
level: intermedio
lang: it
last_verified: 2026-10-26
sources:
  - {ref: frontend/src/pages/wave/Wave.svelte, supports: "controlli (frequenza o lunghezza d'onda, raggio, distanza, finestra verticale, preset), cursore e animazione senza avvio automatico, schede, esportazione, stati di errore"}
  - {ref: frontend/src/pages/wave/wave.ts, supports: "costruzione e validazione della richiesta, debounce e annullamento, sezione al cursore, avvisi, esportazioni CSV e JSON"}
  - {ref: frontend/src/pages/wave/surface.ts, supports: "colormap viridis, da griglia a mesh, camera orbitale con limiti, proiezione"}
  - {ref: backend/domain/grazing/wave.py, supports: "split-step di Fresnel, assi e convenzione di nu, avvisi di campionamento, limiti del modello"}
  - {ref: backend/api/raven_experiments.py, supports: "endpoint GET e POST /api/raven/wave, limiti dei parametri e ambito didattico, non previsione di missione"}
---
## Cosa mostra

La superficie riporta, per ogni distanza dal crinale (asse lungo) e quota sopra la linea di vista
(asse in profondita'), l'intensita' relativa |E|^2, cioe' divisa per quella dell'onda libera. Altezza
e colore (viridis, adatta ai daltonici) indicano lo stesso valore; la legenda e' sotto la figura.
Sopra la linea di vista l'intensita' oscilla (frange di Fresnel), nell'ombra cala senza oscillare.

## Perche' l'intensita' oscilla

Dietro lo spigolo arrivano l'onda diretta e quella diffratta dal bordo con cammini diversi: si
sommano ora in fase, ora in opposizione. Le frange si allargano con la distanza e con la lunghezza
d'onda (scala radice di lambda per x). Sulla linea di vista, per il bordo a lama, l'intensita' vale 0,25.

## Il parametro nu e il segno

nu = -y * radice(2 / (lambda x)), con y la quota sopra la linea di vista (la cima del crinale e' a
y = 0) e x la distanza. nu > 0 e' l'ombra (y < 0), nu < 0 la zona illuminata. La curva tratteggiata
del grafico e' il bordo a lama esatto, |F(nu)|^2 con gli integrali di Fresnel.

## Comandi

Controlli: frequenza o lunghezza d'onda (preset banda S 2,2 GHz, X 8,4 GHz = 0,0357 m, Ka 32 GHz),
raggio della cresta (0 = lama, fino a 400 m), distanza massima (100-5000 m), finestra verticale
(+-h, fino a 200 m) e tre preset: lama, cresta 100 m, cresta 400 m. Le modifiche partono dopo una
breve pausa (le richieste superate sono annullate); in caso di errore 422, 503 o di rete resta
visibile l'ultima superficie valida. Vista: trascinamento o frecce per ruotare e inclinare, piu' e
meno per ingrandire, 0 per ripristinare; parentesi quadre o il cursore spostano il piano della sezione.
Il pulsante "Avanza lungo la distanza" anima il cursore e non parte mai da solo; con "riduci
movimento" e' disattivato.

## La sezione al cursore

Alla distanza finale la sezione e' quella calcolata dal simulatore. Spostando il cursore, un'anteprima
interpolata dalla griglia lascia subito il posto alla sezione calcolata proprio a quella distanza.
Il grafico affianca la simulazione e la lama esatta; la tabella e i file CSV e JSON (sezione e
griglia intera) contengono gli stessi valori.

## Senza WebGL

Il visualizzatore sceglie WebGL (three.js) e, se manca, ripiega su Canvas 2D con la stessa camera,
gli stessi colori e la stessa luce (quadrilateri pieni dal fondo al primo piano). Un'etichetta indica
la modalita' ("Modalita' compatibile (senza WebGL)").

## Limiti dichiarati

Modello scalare e parassiale 2D (split-step di Fresnel con FFT); un solo crinale, onda piana
incidente, nessun regolite, nessun suolo, nessuna curvatura lunare. La cresta arrotondata (parabola
assorbente) e' simulata e non validata. La finestra FFT e' periodica: valgono quote molto minori di
meta' finestra (limite 200 m). Se la griglia e' troppo grossolana per la lunghezza d'onda compaiono
avvisi di campionamento (kernel_aliasing, dy_coarse, paraxial, step_raised) spiegati in italiano.
