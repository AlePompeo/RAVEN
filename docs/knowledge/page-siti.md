---
id: page-siti
title: Pagina Siti
kind: page
summary: >-
  Siti mostra insieme il globo e il confronto: sito e ora UTC sono condivisi. Le schede "Globo" e "Classifica"
  restano disponibili separatamente con ?tab=globo oppure
  ?tab=classifica; le vecchie rotte /viewer e /compare portano qui. In Learning la classifica mostra solo sito, ore
  utili e margine tipico; in Avanzato tutte le colonne, i flag del terreno, le esportazioni e i parametri V/D/I.
tags: [pagina, siti, globo, classifica, visualizzatore, confronto siti, ore utili, margine, Learning, Avanzato, modalita', polo sud]
applies_to: [siti, viewer, compare]
related: [page-viewer, page-compare, page-analizza]
level: principiante
lang: it
last_verified: 2026-10-29
sources:
  - {ref: frontend/src/pages/siti/Siti.svelte, supports: "vista unificata e schede Globo e Classifica"}
  - {ref: frontend/src/pages/siti/index.ts, supports: "alias /viewer (tab=globo) e /compare (tab=classifica)"}
  - {ref: frontend/src/pages/compare/RavenCompare.svelte, supports: "colonne e campi mostrati in Learning e in Avanzato, stessi valori"}
  - {ref: frontend/src/pages/viewer/Viewer.svelte, supports: "titolo del corpo come h2 dentro Siti; differenza di perdita in spazio libero solo in Avanzato"}
  - {ref: frontend/src/shell/CustomSitePanel.svelte, supports: "campi, errori, globo, stima del terreno e terreno sconosciuto"}
  - {ref: docs/domain/raven-model.md, supports: "prodotti per sito, tetti di download e misure"}
---
## Globo

La Luna e la Terra nell'istante scelto, con i luoghi e i siti polari; toccando un sito del polo Sud si vede quanto e'
alta la Terra da li'. Dettagli in [page-viewer](kb:page-viewer).

## Classifica

Ogni sito e' calcolato con lo stesso modello di Analizza; in cima c'e' il sito con piu' ore utili. In Learning:
"Ore utili (h)" (la finestra reale, anche con il segnale piegato dal crinale) e "Margine tipico (dB)" (il margine
mediano: sopra 0 dB il collegamento funziona). La data e ora UTC iniziale si possono scegliere in entrambe le modalita'.
In Avanzato anche finestra geometrica, transizione, margine minimo,
bit-rate sostenibile, interruzioni, dati consegnati, elevazione della Terra, flag del terreno, esportazioni CSV e JSON
e il confronto energetico semplificato. Dettagli in [page-compare](kb:page-compare).

Da ogni riga "Mostra sul globo" seleziona il sito con data, stazione, bit-rate, guadagno e k del confronto
eseguito, anche se il modulo e' stato modificato dopo il calcolo. Nella vista unificata non lascia la pagina;
se lo scenario cambia, un avviso invita a ricalcolare la classifica, che resta riferita al calcolo precedente.
Il margine sul globo usa lo stesso guadagno dello scenario; il parametro k riguarda il compensatore e non cambia
il margine istantaneo al bit-rate scelto.

## Sito personalizzato

Il pulsante "Sito personalizzato" (sotto l'elenco dei luoghi del globo) aggiunge un punto qualsiasi della Luna da latitudine e
longitudine est, oppure con un clic sul globo (le coordinate scelte compaiono accanto). Al massimo 8 siti; compaiono come i siti del
catalogo nel globo, nella classifica, in Simula, nella Scena lander e nel Pianificatore, e restano nell'indirizzo (parametro `cs`) e in
sessionStorage. Il terreno viene dal miglior prodotto LOLA che copre il punto (20 m al polo sud, 240 m altrove); i dati si scaricano solo
vicino al sito e solo dopo la tua conferma ("questo sito richiede circa X MB", al massimo 10 MB per sito). Dove nessun prodotto sta nei
tetti il terreno e' SCONOSCIUTO: orizzonte e profilo radio sono ignoti (mai terreno piatto), mentre geometria, DSN e perdita in spazio
libero restano validi. La risoluzione usata e la portata dell'orizzonte sono nel risultato.
