---
id: model-validation
title: Modello RAVEN e validazione, stadi, stati e limiti
kind: decision
summary: >-
  RAVEN e' una catena di sette stadi (S1-S7 piu' il contesto S0) con un registro unico dei parametri; ogni stadio
  dichiara cosa e' verificato, contro cosa, con quale scarto e cosa NON e' validato. Le formule di geometria,
  orizzonte, diffrazione e spazio libero sono verificate contro fonti o reimplementazioni; i numeri di potenza, i
  parametri radio illustrativi e le definizioni di ora utile non sono validati. Nessun risultato e' una misura
  radio o di potenza sulla Luna: e' un potenziale nelle ipotesi dichiarate.
tags: [validazione, RAVEN, modello unico, registro parametri, V D I, verificato, plausibilita, non validato, ignoto, terreno lontano, DSN, classifica, finestre, limiti]
applies_to: [siti, compare, simula]
related: [page-compare, ephemeris-method, link-budget]
level: tecnico
lang: it
last_verified: 2026-11-08
sources:
  - {ref: docs/domain/raven-model.md, supports: "stadi, matrice di validazione (3), stato di implementazione"}
  - {ref: docs/domain/validation.md, supports: "scarti numerici, confronti con Horizons, arbitro indipendente, LROC WAC, ITU-R P.526-9"}
  - {ref: docs/domain/raven-changes.md, supports: "differenze intenzionali della catena nuova rispetto ai motori precedenti (D2-D5, D7-D9)"}
  - {ref: backend/domain/raven/validation.py, supports: "stato di validazione per stadio e per gruppo di parametri, con evidenza e frase ammessa"}
  - {ref: backend/domain/raven/ranking.py, supports: "classifica lessicografica senza punteggio, gruppo non confrontabile"}
  - {ref: tests/backend/domain/raven/test_validation.py, supports: "ogni stadio ha una voce e ogni voce verificata ha evidenza esistente"}
---
## Come leggere i giudizi

Il modello corrente e' `raven-core-1.4`: 22 controlli verificati, 4 solo plausibilita',
6 non validati e 1 ignoto. Sono conteggi di evidenze, non percentuali di qualificazione.
S2/S4/S5 restano non validati; S3 solo plausibilita'. Verificati anche il fit
aritmetico della parabola S2 e la logica a tre valori S7, non il terreno reale
o la politica operativa. Il minimo SOC include lo stato iniziale.
Un ostacolo con nu positivo e raggio ignoto non diventa una lama implicita:
con correzione arrotondata attiva il margine RF resta ignoto, anche se la
geometria della scena e' disponibile. Lo spigolo ideale richiede una scelta
esplicita. Un blocco noto da terreno lontano rimane noto senza margine numerico.
I riquadri Model/Validation diventano Verified solo quando tutti i controlli
registrati dello stadio sono verificati; aggiornamento e focus rileggono lo stato.
Sono verificati anche i raggi ai poli contro un oracolo cartesiano indipendente.
S3 integra esattamente i tratti lineari della maschera, senza il vecchio
orizzonte costante per striscia. Una cresta extrapolata fuori dal fit non e'
risolta. Non sono nuove misure di terreno o illuminazione lunare.

Ogni stadio ha uno stato: **verificato** (formula pubblicata, reimplementazione indipendente o dati
indipendenti alla pari, con lo scarto), **solo plausibilita'** (dati indipendenti con criterio non identico, o un
intervallo di letteratura), **non validato** (nessun controllo indipendente dei numeri: l'aritmetica puo' essere
verificata, i valori sono illustrativi o scelte di progetto), **ignoto** (affermazione di un documento non ancora
rieseguita). L'elenco completo, con fonte, scarto e frase ammessa, e' in `GET /api/raven/validation`.
I parametri hanno tag V (letto in una fonte primaria), D (derivato con formula ripetibile) o I (illustrativo).

## Numero di modelli

Una catena di missione: sette stadi e un registro di parametri sotto `/api/raven/*`, usata anche dalla
telemetria. I vecchi endpoint `/api/lunar/*`, `/api/grazing/*` e `/api/sky/*` rispondono 410. Onda e cielo
sono `/api/raven/wave` e `/api/raven/sky/*`. Gli esperimenti `/api/raven/experiments/*` condividono le formule
RF ma non valutano la missione completa: hanno ambito didattico esplicito. Gli oracoli storici restano
isolati in `scripts/raven_reference/`, solo per i golden e i test.

## Posizioni di Sole e Terra

Dalle efemeridi JPL DE440 (NAIF). Scarto contro JPL Horizons: 8,2e-7 gradi e 7 m per il Sole, 1,2e-6 gradi e
0,16 m per la Terra. Non e' quantificata l'incertezza di UT1 oltre gennaio 2027 (predetto).

## Terreno

Reale: LOLA a 20 m fino a 10 km e a 240 m fino a 200 km, con SHA-256 dei file bloccato. Nessun profilo inventato
nella catena; un tile mancante rende ignoto il risultato, mai un orizzonte libero. Il terreno oltre 200 km non e'
modellato.

## Orizzonte

Un'implementazione indipendente concorda entro un passo su 4380 in un anno; la lettura verso la Terra e'
confrontata con la stessa implementazione con una tolleranza di 0,06 gradi (il valore misurato non e' riportato qui).
Contro le osservazioni LROC WAC vicino al polo: r = 0,95 e 4-6 punti RMS, con criteri non identici (solo
plausibilita').

## Haworth e de Gerlache al buio

Sono centri di grandi crateri: la maschera a 200 km li tiene in ombra nel 2027 e LROC da' 0 anche per de Gerlache.
Le coordinate sono centri di feature, non zone di atterraggio.

## Margine radio

Il budget assoluto di progetto Surveyor NASA CR-69102 e' riprodotto entro 0,0471 dB;
non e' una misura di volo e non valida il link operativo corrente. Le formule di diffrazione
sono quelle di ITU-R P.526-9, confrontate anche con P.526-16; i parametri radio non letti
da una fonte restano illustrativi (tag I). Occorrono misure equivalenti e revisione RF.

## Progressi S2-S5 e falci solari

Il modello corrente e' raven-core-1.2: S3 integra l'area circolare esatta in ciascuna
delle 48 strisce, mantenendo l'orizzonte al punto medio. Non perde piu' una falce sottile
su orizzonte piatto; la frazione corretta alimenta S4. Confronto analitico entro 2e-15
su orizzonte piatto e integrale indipendente delle strisce entro 1e-9 su orizzonte variabile.
Geometria RF campionata S2, aritmetica S4 e formule di riflessione S5 hanno voci verificate
separate. Questo non valida il terreno reale, l'hardware o il multipath lunare.
Gli stati complessivi restano S2/S4/S5 non validati e S3 solo plausibilita'.
Model/Validation mostra conteggi di prove e condizioni di sblocco, non percentuali
di qualificazione. Nessun parametro hardware illustrativo viene promosso.

## Cresta arrotondata

Si usa ITU-R P.526-9 par. 4.2, fonte pubblicata e piu' conservativa; la simulazione split-step da' meno perdita
(fino a 2,4 dB in meno) e la distanza tra le due e' la banda di incertezza. Il termine resta non validato da misure.

## Tag V, D, I

V letto in una fonte primaria (una copia, non una misura), D derivato con formula ripetibile, I illustrativo da
sostituire con dati del cliente. Ogni risposta dell'API riporta il tag e la fonte di ogni parametro usato.

## Energia

L'aritmetica si' (casi analitici, conservazione a 1e-9); i numeri no: pannello, batteria e carichi sono illustrativi
e non c'e' un confronto con un lander reale.

## Ora utile

Stato operativo, link utilizzabile (margine almeno 3 dB, tag V, oppure nessun blocco noto del terreno) e Luna
visibile da un complesso DSN da 34 m. Le ore che dipendono da ingressi ignoti sono contate a parte e mai come utili.
La definizione e' una scelta di progetto, non una validazione.

## Pianificazione DSN

Non considerata: solo visibilita' geometrica sopra 6 gradi (DSN 810-005/301); la classe da 18 m ha visibilita' ignota.

## Simulatore d'onda

Non calcola il link: e' fisica illustrativa (split-step scalare parassiale) per spiegare la diffrazione; alimenta solo la banda di
incertezza della correzione della cresta.

## Slider del browser

Sono uno specchio delle formule S5 con geometria manuale e set radio unificato. La parita' e' registrata
in `s5.browser_mirror`: 30 casi Python, tolleranza 0,01 dB sui termini radio, 1e-6 dB sulla lama esatta
e 1e-9 relativo sulla geometria. Le fixture sono state rigenerate senza differenze e i test TS rieseguiti.
E' una verifica d'implementazione, non una validazione fisica o una misura lunare.

## Orari delle finestre

I bordi delle finestre di luce e di link utilizzabile sono raffinati per bisezione a 1 s, con verifica su un caso
analitico (Sole sinusoidale); si assume un solo cambio per passo. Le finestre di ora utile restano alla risoluzione
del passo perche' la batteria ha memoria. I bordi accanto a passi ignoti non sono raffinati.

## Cosa non e' modellato

Terreno oltre 200 km, diffrazione su piu' creste (il terreno lontano oltre il profilo RF e' una stima a ostacolo
singolo con soglia illustrativa di 30 dB: sopra e' un blocco noto, sotto e' ignoto), oscuramento al bordo solare,
codifica CCSDS, atmosfera e pioggia a terra, polvere, termica, ostruzione del lander. L'elenco e' in `declared_limits`
di ogni risposta. Controlli dichiarati in documenti precedenti e non rieseguiti (Malapert con la Terra fino a 10,7
gradi, tramonto di circa 8 giorni, relay 77 % e 100 %) vanno considerati ignoti finche' non rieseguiti.
