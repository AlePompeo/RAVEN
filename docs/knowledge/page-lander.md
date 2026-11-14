---
id: page-lander
title: Pagina Scena lander
kind: page
summary: >-
  La Scena lander mostra per un istante il terreno LOLA attorno a un sito del polo Sud con luce radente, il rover con
  l'antenna in banda X, il fascio con l'HPBW vero, la prima zona di Fresnel come tubo verde, ambra o rosso secondo il
  margine di link reale, la Terra alla sua elevazione e il crinale dominante. Accanto ci sono i numeri (nu, raggio di
  Fresnel, perdita di diffrazione, multipath, margine, stato) e una sezione laterale. Un solo ostacolo dominante; il
  terreno non e' inventato.
tags: [pagina, scena lander, terreno LOLA, crinale, zona di Fresnel, tubo, fascio, HPBW, errore di puntamento, margine di link, nu, luce radente, WebGL, Canvas 2D, sezione laterale]
applies_to: [lander, simula]
related: [page-simula, page-grazinglink, page-wave, page-viewer]
level: intermedio
lang: it
last_verified: 2026-10-26
sources:
  - {ref: frontend/src/pages/lander/Lander.svelte, supports: "controlli (sito, stazione, bit-rate, guadagno, altezza del palo, errore di puntamento, esagerazioni), schede Numeri, Sezione laterale, Descrizione testuale, Limiti, esportazione JSON"}
  - {ref: frontend/src/pages/lander/model.ts, supports: "contratto della risposta, raggio di Fresnel, stato (verde/ambra/rosso e testo), perdita di puntamento 12,04 (errore/HPBW)^2, throttle e annullamento delle richieste"}
  - {ref: frontend/src/pages/lander/grazingLight.ts, supports: "istante predefinito: primo istante nel mese successivo con Sole tra 1 e 3 gradi sull'orizzonte del sito, dalla serie GET /api/raven/sky/series (Sole vero)"}
  - {ref: frontend/src/pages/lander/view.ts, supports: "camera orbitale e preset, ombreggiatura con ombre portate, anelli del tubo, sezione laterale"}
  - {ref: backend/domain/grazing/scene.py, supports: "campo di quote LOLA, profilo lungo l'azimut della Terra, crinale, raggio di Fresnel al crinale, termini di perdita e stato del link"}
  - {ref: backend/api/raven_routes.py, supports: "endpoint GET /api/raven/scene (guadagno, sito personale con lat/lon, versione del modello), errori 422 e 503 generici"}
  - {ref: frontend/src/pages/lander/Lander.svelte, supports: "siti personalizzati nell'elenco"}
---
## Cosa mostra

Dal polo Sud la Terra sta pochi gradi sopra l'orizzonte. La scena disegna il terreno (dal prodotto LOLA a 20 m,
campionato su una griglia piu' grossolana), il rover con un palo (altezza predefinita 2 m, tag I) e la parabola, il cono del
fascio con l'HPBW vero, la linea di vista verso la Terra e il crinale dominante evidenziato. La Terra e' disegnata con il
suo diametro angolare vero e alla sua elevazione (cambia con la librazione) ma a distanza simbolica: sta a circa 384 000 km.

## La zona di Fresnel e il colore

Il tubo e' la prima zona di Fresnel, raggio r1 = radice(lambda d1 d2 / (d1 + d2)) (Crane e Blood, sez. 2.3, eq. 2). Con la Terra
lontanissima vale circa radice(lambda d1): pochi metri al crinale. Il tubo e' valido solo nel campo vicino all'antenna e il suo raggio
e' disegnato ingrandito (x20 predefinito, dichiarato in pagina; il valore vero e' nei numeri). Il colore viene dal margine di link del
motore: verde = aperto (margine >= 0 e linea di vista libera), ambra = transizione (margine >= 0 ma il crinale blocca la linea di
vista, il link chiude per diffrazione), rosso = bloccato (margine < 0 al bit-rate scelto). Lo stato e' sempre scritto, non solo colorato.
Il rapporto h/r1 dice quanto del raggio e' occupato dal crinale.

## Antenna e puntamento

Il cursore "errore di puntamento" ruota l'asse del fascio sopra la Terra. La perdita e' 12,04 (errore/HPBW)^2 dB; oltre meta' HPBW il
cono diventa rosso. Il margine dell'API e' calcolato con errore zero, la pagina mostra anche il margine con la perdita di puntamento.

## Luce

La luce e' il Sole reale all'istante scelto (JPL DE440, dal servizio del cielo), con ombre portate dal campo di quote campionato. Se la
luce non e' disponibile si usa un Sole fisso a 1,5 gradi, dichiarato come non reale. Con il Sole sotto l'orizzonte il terreno e' scuro.

**Istante predefinito.** Se lo scenario non ha un istante esplicito (nessun `t` nell'URL), a Sole al sito vicino all'orizzonte
(circa -1,5 gradi) tutto il terreno sarebbe buio. La pagina cerca allora, con il Sole vero (serie oraria del servizio del cielo,
un mese lunare di 29,53 giorni dall'ora attuale), il primo istante in cui il Sole sta tra 1 e 3 gradi sull'orizzonte del sito
(luce radente) e lo usa, scrivendo sotto la barra del tempo "Istante scelto perche' il Sole e' radente" con la quota del Sole.
L'istante resta visibile e modificabile nel pannello della data e finisce nello scenario condiviso (anche i link verso le altre
pagine lo portano); se lo si cambia la nota sparisce. Se un istante simile non esiste, resta quello dato e la pagina lo dice
(con il Sole sotto l'orizzonte: "il terreno e' in ombra"); se il servizio non risponde resta l'ora attuale, senza nota. La luce
non e' mai simulata per far apparire il rilievo. Con `t` esplicito non c'e' nessuna ricerca.

## Limiti dichiarati

Ostacolo singolo dominante sul solo azimut della Terra; nessuna misura radio reale al polo Sud; regolite da letteratura; la correzione della
cresta arrotondata e' T(m,n) di ITU-R P.526-9 par. 4.2 (formula verificata sul testo, non misurata), con lo scarto
dallo split-step simulato come incertezza; la risoluzione del terreno (20 m, griglia piu'
grossolana) puo' nascondere rocce e creste piu' piccole; i parametri radio hanno tag I (illustrativi). Il termine multipath puo' risultare
"non applicabile" (punto speculare oltre il crinale o Terra sotto l'orizzonte). I siti fuori dalla copertura DEM sono disabilitati
("fuori copertura DEM"): il terreno non viene mai inventato. Senza WebGL la pagina mostra la sezione laterale in Canvas 2D.

## Sito personalizzato

L'elenco dei siti include quelli personalizzati (stesso elenco della pagina Siti). Per un sito senza dati di terreno la scena non
viene inventata: la richiesta risponde che il terreno e' sconosciuto. Se i dati vanno scaricati compare la conferma con i MB.
