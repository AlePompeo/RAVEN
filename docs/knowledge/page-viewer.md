---
id: page-viewer
title: Pagina Visualizzatore 3D
kind: page
summary: >-
  Il Visualizzatore 3D mostra la Luna (lato sito) e la Terra (lato stazione) come i due lati del collegamento
  RAVEN. Scelto un sito polare disegna la linea verso la Terra con l'angolo sull'orizzonte; sulla Terra
  evidenzia la stazione DSN che vede la Luna. Un selettore di data e ora UTC muove Terra e librazione; i
  marcatori dei siti sono colorati per stato del link, sempre con il testo.
tags: [pagina, viewer, visualizzatore 3D, Luna, Terra, RAVEN, scena, descrizione, azimut, elevazione, accessibilita, data, ora, UTC, luce solare, terminatore, riproduzione, stato del link, aperto, transizione, bloccato, fuori copertura DEM, stazione DSN, Goldstone, Madrid, Canberra, scenario condiviso, distanza Terra-Luna, perdita in spazio libero]
applies_to: [viewer, siti]
related: [page-siti, az-el-convention, ephemeris-method, glossary-azimuth, glossary-elevation, glossary-terminator]
level: principiante
lang: it
last_verified: 2026-10-26
sources:
  - {ref: frontend/src/pages/viewer/Viewer.svelte, supports: "scena 3D di Luna e Terra, rotazione con trascinamento o frecce, linea sito-Terra e stazione-Luna con l'angolo scritto, marcatori per stato del link, pulsanti Apri scena lander e Analisi completa, pannello Perche' RAVEN e riga dei limiti"}
  - {ref: frontend/src/pages/viewer/SkyTime.svelte, supports: "selettore di data e ora UTC: campi data e ora, Adesso, passi di un giorno o un'ora, riproduzione a tre velocita', messaggi di errore, punto subsolare"}
  - {ref: frontend/src/pages/viewer/skyLight.ts, supports: "richiesta a /api/raven/sky/subsolar con al massimo circa 4 richieste al secondo, richieste superate annullate, ultima luce valida conservata"}
  - {ref: frontend/src/pages/viewer/snapshot.ts, supports: "richiesta a /api/raven/snapshot al massimo una al secondo, cache per istante e parametri, richieste superate annullate; testi 'Terra a 0,9 gradi sull'orizzonte' e variazione della perdita in spazio libero"}
  - {ref: frontend/src/pages/viewer/bodyState.ts, supports: "il selettore ha solo Luna e Terra; un link con sole o marte torna alla Luna"}
  - {ref: frontend/src/shell/scenario.ts, supports: "scenario condiviso (sito, istante, stazione, guadagno, velocita', k) nell'URL, valori non validi ignorati, nessun cookie"}
  - {ref: backend/domain/grazing/snapshot.py, supports: "stato del link a un istante (aperto, transizione, bloccato), siti fuori copertura DEM senza valori stimati, elevazione della Luna dai complessi DSN, coordinate DSN 810-005 Tabella 5"}
  - {ref: backend/api/raven_routes.py, supports: "GET /api/raven/snapshot con tetto di concorrenza, cache e errori generici 422/503"}
  - {ref: frontend/src/viewports/scene.ts, supports: "describeScene: testo 'azimut X, elevazione Y' e '(sotto l'orizzonte)'"}
  - {ref: frontend/src/pages/viewer/Viewer.svelte, supports: "siti personalizzati come luoghi della Luna"}
---
## Uso

La scena si ruota trascinando o con i tasti freccia; i comandi sono nella barra in basso. In alto,
accanto al titolo, il selettore **Luna / Terra** (Sole e Marte non ci sono su questo ramo: il Sole
resta solo come sorgente reale della luce). La sezione "Descrizione della scena" fornisce un testo
equivalente (azimut ed elevazione in gradi, con "sotto l'orizzonte" quando l'elevazione e' negativa;
per la Terra usa il sito scelto, altrimenti scrive "dato non disponibile"). Le convenzioni degli
angoli sono in [azimut/elevazione](kb:az-el-convention).

Il sito e l'istante scelti nel visualizzatore sono riportati nell'indirizzo e passano alle altre pagine
quando si usano i pulsanti "Analisi completa" e "Apri scena lander" del dettaglio del sito.

## Luna: sito, linea verso la Terra, stato del link

- Ogni luogo dell'elenco e ogni marcatore e' un pulsante (anche da tastiera: Tab, Invio). Scelto un
  sito dell'analisi, la scena si centra e compare una **linea dal sito verso la Terra** con la scritta,
  ad esempio, "Terra a 0,9° sull'orizzonte" e l'azimut. Angolo e azimut sono quelli veri del
  servizio (parallasse e librazione reale) e si aggiornano con data e ora. La linea e' uno schema
  sul disco (proiezione ortografica), non una misura.
- I **marcatori sono colorati per stato del link**, sempre con forma e testo oltre al colore:
  **aperto** (margine >= 0 e Terra sopra il crinale), **transizione** (margine >= 0 ma il crinale
  blocca la linea di vista geometrica: il link chiude per diffrazione), **bloccato** (margine < 0 al
  bit-rate scelto), **fuori copertura DEM** (il DEM LOLA copre solo latitudini <= -85 gradi: nessun
  valore stimato, solo la geometria della Terra). Lo stato viene da `/api/raven/snapshot`, calcolato
  con il modello unico RAVEN Core su un solo istante (la pagina mostra versione e registro del modello). Se il servizio non risponde (503) o rifiuta
  la richiesta (422) lo stato scompare con un messaggio: non si mostra mai lo stato di un altro istante.
- Nel dettaglio del sito: margine in dB al bit-rate scelto, elevazione del crinale dominante, terreno
  (DEM LOLA) e la nota "correzione simulata, non validata". Due pulsanti: **Apri scena lander** e
  **Analisi completa** (porta a RAVEN con sito, istante, stazione e velocita' gia' impostati; per
  i siti fuori copertura DEM non c'e').

## Terra: stazioni DSN

Le tre stazioni (Goldstone, Madrid, Canberra) sono segnate con le loro antenne da 34 m e da 18 m. Le
coordinate vengono dal servizio e da DSN 810-005 Modulo 301 Rev. P, Tabella 5 (antenna da 34 m); **la
stazione da 18 m e' un'ipotesi dello script della ricerca, senza fonte** e non ha coordinate proprie.
La stazione che vede la Luna all'istante scelto (elevazione >= 6 gradi, limite meccanico di ricezione
DSN 810-005 sez. 2.2.2-2.2.3) e' evidenziata e una linea indica la direzione della Luna. In alto a
destra compaiono la **distanza Terra-Luna del momento** (efemeridi NAIF DE440) e la **variazione
della perdita in spazio libero** rispetto ai 384.400 km fissi (circa tra -0,49 e +0,46 dB nell'arco di
un mese; il valore mostrato e' quello calcolato per l'istante).

## Contesto e limiti (sempre visibili)

Il pannello **"Perche' RAVEN"** spiega in poche righe che dal polo Sud la Terra sta radente
(0,5°-1,5°) e perche' la diffrazione conta. Sotto la scena una riga ricorda sempre i limiti:
copertura DEM solo a latitudine <= -85°, un solo ostacolo dominante, parametri radio ipotesi
illustrative (tag I), cresta da ITU-R P.526-9 (non misurata) con lo split-step come banda. La fisica d'onda sta in Onda 3D, nella
scena lander e nell'analisi; il globo da' solo il contesto geometrico. Nel pannello si scelgono anche
la stazione di terra (34 m o 18 m ipotesi) e la velocita': cambiano lo stato dei marcatori. Il guadagno del rover
selezionato nello scenario condiviso viene usato anche per calcolare il margine del globo; se non e' specificato
si usa il valore predefinito del modello.

## Data e ora (UTC)

Sopra la barra in basso c'e' il selettore "Data e ora (UTC)" (sul telefono si apre con il pulsante
che mostra data e ora). Contiene il campo Data, il campo Ora UTC, il pulsante "Adesso", i passi
"-1 giorno", "-1 h", "+1 h", "+1 giorno" e "Riproduci" con tre velocita' (1 minuto, 1 ora o 1
giorno di tempo simulato al secondo). La luce sulla Luna e sulla Terra e' la direzione reale del
Sole a quell'istante, dal servizio `/api/raven/sky/subsolar` ([metodo](kb:ephemeris-method)); lo stesso
istante muove la Terra, la librazione e lo stato del link. In riproduzione veloce lo stato del link
si aggiorna al massimo circa una volta al secondo.

- Intervallo supportato: dal 1972-01-01 al 2150-01-20, solo UTC. Una data fuori intervallo, un
  formato non valido o il servizio non disponibile mostrano un messaggio e **lasciano l'ultima luce
  valida**: la scena non si rompe.
- L'"ombra" mostrata e' il terminatore (il confine fra giorno e notte, vedi
  [terminatore](kb:glossary-terminator)) piu' l'ombreggiatura del rilievo; non vengono disegnate
  ombre portate.
- La stessa direzione della luce e le stesse linee e marcatori sono usati dal rendering WebGL e da
  quello 2D di riserva.
- Tastiera: tutti i campi e i pulsanti si raggiungono con Tab nell'ordine Data, Ora, passi,
  Riproduci, Velocita'; i bersagli sono di almeno 44 px. Con "riduci movimento" attivo gli
  spostamenti della vista sono immediati.

## Scenario condiviso

Sito, istante, stazione, guadagno dell'antenna, velocita' e k stanno nell'indirizzo
(`?site=&t=&station=&gain=&rate=&k=`) e si ritrovano in RAVEN, Onda 3D, Confronto siti e qui.
Un valore non valido nell'indirizzo viene ignorato. Si salva solo in `sessionStorage` (mai cookie).

## Siti personalizzati

Nel globo della Luna i siti personalizzati (coordinate dell'utente, non verificate) compaiono come luoghi di tipo "Siti
personalizzati", con lo stato del link dal servizio; se i dati di terreno vanno ancora scaricati lo stato e' "terreno da scaricare" e il
margine e' ignoto. Vedi [page-siti](kb:page-siti).
