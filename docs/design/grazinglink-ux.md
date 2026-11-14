# GrazingLink: struttura del sito e esperienza per il pubblico

Problema (feedback dell'utente): aprendo il sito non si capisce di cosa si tratta, le pagine sembrano messe a caso, la
barra ha dieci voci senza ordine. Obiettivo: chi apre la pagina capisce in pochi secondi, e può cambiare dei parametri
e vedere subito come si aggiornano grafici, soprattutto 3D, belli e di impatto.

## La storia in una frase
"Al polo Sud della Luna la Terra sta a un grado dall'orizzonte. Un crinale può bloccare il segnale oppure lasciarlo
passare piegato (diffrazione). GrazingLink calcola se, quando e a che velocità un lander può comunicare."

## Cosa deve poter fare chi arriva (3 azioni, in ordine)
1. **Capire** (home): un'immagine/scena viva e una frase; il problema in tre passi brevi.
2. **Giocare** (Simula): muovere 4-5 controlli (elevazione della Terra, altezza del crinale, raggio del crinale, antenna,
   velocità) e vedere subito: la scena 3D, un indicatore grande del margine (verde / ambra / rosso), un grafico 2D con il
   punto corrente, e una frase che dice cosa significa ("il segnale arriva, 6 dB di margine, 100 kbps").
3. **Usarlo davvero** (Analizza, Siti): scegliere un sito reale e un mese e vedere le ore utili reali.

## Pubblico e livelli (decisione dell'utente)
Il pubblico va dai bambini ai ricercatori. Lo stesso strumento serve entrambi, senza due siti: **due modalità**, scelte da
un **interruttore "Learning | Avanzato" presente in OGNI pagina** (stessa posizione, in testa al contenuto della
pagina, a destra del titolo; non nella barra di navigazione). Regole dell'interruttore:
- Lo stato è unico per tutto il sito: cambiarlo in una pagina lo cambia nelle altre. Si ricorda nel browser
  (`localStorage` in try/catch, senza cookie) e si può forzare con `?mode=learning|avanzato` nell'URL, che ha la
  precedenza e rende il link condivisibile. Default: Learning, per chi arriva la prima volta.
- Accessibile: due pulsanti con `aria-pressed` (gruppo con etichetta "Modalità"), tastiera, bersaglio ≥ 44 px, D-pad
  TV, annuncio del cambio in una regione `aria-live`; il cambio non sposta il contenuto già visibile (nessun salto).
- Ogni pagina definisce cosa cambia, ma i numeri risultanti sono identici nelle due modalità: cambia solo cosa si vede.
  - *Learning*: nomi quotidiani, pochi controlli, testi semplici, tooltip del glossario, missione guidata, indicatori a
    colori con una frase; tabelle e parametri tecnici nascosti (non rimossi: raggiungibili passando ad Avanzato).
  - *Avanzato*: tutti i parametri con unità, tag V/D/I e fonte, incertezze, confronto tra varianti, tabelle dei numeri,
    esportazione completa, stato intero nell'URL, flag del terreno e della correzione.
- Si applica a tutte le pagine: Il problema (home), Simula, Onda 3D, Scena lander, Analizza (GrazingLink), Siti
  (Visualizzatore e Confronto siti), Laboratorio (Telemetria, Simulazioni) e Assistente (il tono delle risposte:
  semplice o tecnico, con le stesse citazioni). Contatti e pagine legali: l'interruttore non compare dove non cambia nulla.
- Implementazione: un solo store (`frontend/src/shell/mode.ts`) e un solo componente (`ModeSwitch.svelte`), lazy dove
  possibile; il bundle iniziale resta sotto la soglia di check-bundle (65.000 B dal 2026-10-27); test di unità (parsing di `?mode=` con valori malevoli,
  persistenza con storage bloccato) ed e2e (interruttore presente su ogni pagina, stato condiviso, i numeri non cambiano
  tra le modalità, axe pulito, nessun overflow a 390 px).

Dettaglio dei due livelli sui controlli:
- **Learning** (default): 4-5 controlli semplici con nomi quotidiani ("Quanto è alta la Terra nel cielo", "Quanto è alto il
  crinale", "Quanto è grande l'antenna", "Quanti dati al secondo"), testi brevi, indicatore verde/ambra/rosso, una frase
  che spiega il risultato, una missione guidata a passi ("1. Metti la Terra alta: il segnale passa. 2. Abbassala: cosa
  succede? 3. Alza il crinale..."). Nessun simbolo senza spiegazione.
- **Avanzato**: tutti i parametri (frequenza, raggio e altezza del crinale, εr e σ del regolite, altezza del mast, guadagno
  e diametro, potenza, Tsys, Eb/N0, margine k, stazione 34/18 m, modalità di correzione), unità e tag V/D/I accanto a ogni
  valore con la fonte, intervalli di incertezza, confronto tra varianti (lama contro cresta arrotondata, antenna dello
  script contro corretta), tabella dei numeri, esporta CSV/JSON con tutti i parametri e link condivisibile con lo stato
  completo nell'URL, così un risultato si riproduce.
- Il livello cambia solo cosa si vede, non i risultati: stessi numeri in entrambi.
- Glossario a tooltip (diffrazione, zona di Fresnel, margine di link, librazione, dB) con definizione di una riga e un
  "ancora più semplice" per i termini centrali; i testi hanno due registri (semplice / tecnico) legati al livello.

## "Dove la soluzione smette di essere vera" (indicatore di validità)
Ogni risultato mostra un **indicatore di dominio di validità**: verde se il modello è dentro il suo campo, ambra se ai
bordi, rosso se fuori, con la frase del perché. Condizioni, tutte già note dal modello (docs/domain/grazinglink-model.md):
ν fuori dall'intervallo della tabella di correzione (−1,5…3) o oscillazioni di Fresnel per ν < −0,78 (incertezza);
distanza del crinale fuori da 0,25–4 volte i 2000 m della tabella (correzione saturata); raggio del crinale non
risolto dal DEM a 20 m; punto di riflessione oltre il crinale (multipath non applicabile); elevazione della Terra ≤ 0;
approssimazione parassiale violata; più di un ostacolo dominante (limite dichiarato); sito fuori copertura DEM.
In Simula c'è anche una **mappa di validità** 2D (elevazione della Terra contro altezza del crinale) che colora le zone
dove la risposta è affidabile, incerta o fuori modello, con il punto corrente: si vede dove la soluzione smette di valere.
Un banner d'onestà fisso dice cosa NON è modellato (ostacolo singolo; nessuna misura radio reale al polo Sud; regolite
da letteratura; parametri radio ipotesi illustrative).

## Struttura (barra di navigazione: 6 voci, non 10)
| Voce | Cosa contiene | Pagine/strumenti esistenti riusati |
|---|---|---|
| **Il problema** (home) | storia in 4 passi con scena viva e mini-simulatore a 3 controlli; pulsante grande "Prova tu" | home attuale, scena lander in modalità ridotta |
| **Simula** | l'esperienza principale: scena 3D (lander, crinale, tubo di Fresnel, Terra) + pannello controlli + indicatore del margine + grafico 2D del margine contro l'elevazione della Terra (con il punto corrente) + scheda "L'onda" (superficie 3D della diffrazione) + scheda "Antenna" | Scena lander, Onda 3D, antenna di GrazingLink |
| **Analizza** | un sito reale su un mese: finestre geometrica contro reale, margine nel tempo, compensatore. Vista semplice per default (3 numeri grandi + 2 grafici), schede avanzate nascoste dietro "Dettagli tecnici" | GrazingLink (6 schede) |
| **Siti** | globo Luna/Terra a sinistra, classifica dei siti a destra; selezionare un sito aggiorna entrambi | Visualizzatore + Confronto siti |
| **Laboratorio** | telemetria del link, simulazioni, strumenti di ricerca (per chi vuole andare a fondo) | Telemetria, Simulazioni |
| **Assistente** | domande sul progetto, con la pagina corrente come contesto | Assistente |
| (piè di pagina) | Team, Licenze, Privacy, Cookie | Contatti spostato qui |

Le rotte esistenti restano valide (reindirizzamenti o alias); nulla di costruito si perde.

## Regole di progetto
- Ogni pagina ha UN titolo chiaro, UNA frase che dice a cosa serve e UNA azione principale evidente. Le opzioni avanzate
  stanno dietro "Dettagli tecnici".
- Valori e grafici si aggiornano in tempo reale mentre si muovono i controlli (calcolo nel browser per il modello
  chiuso: perdita a lama, correzione della cresta dalla tabella, spazio libero, guadagno d'antenna; la API serve per i
  dati veri del terreno e i mesi interi). Mai un pulsante "Calcola" per la parte giocabile.
- Colore e testo insieme (verde / ambra / rosso con parola e simbolo). Niente numeri senza unità né spiegazione breve.
- Scena 3D come protagonista, non decorazione: ogni controllo ha un effetto visibile nella scena.
- Preset a un tocco: "Terra alta", "Terra radente", "Crinale che blocca", "Antenna piccola".
- Onestà: parametri radio illustrativi dichiarati, copertura del terreno LOLA, ostacolo singolo, nessuna misura reale al
  polo. Una riga fissa nella pagina Simula e nei dettagli, non in ogni angolo.
- Testi in italiano semplice; niente gergo senza una spiegazione di una riga ("diffrazione: il segnale si piega
  attorno allo spigolo").
- Nessuna banda di rimando in testa alle pagine (rifiutata dall'utente). I collegamenti stanno nei pulsanti pertinenti.

## Priorità di realizzazione (cambia il piano precedente)
1. Struttura: barra a 6 voci, alias delle vecchie rotte, home come racconto con mini-simulatore.
2. Simula: la pagina interattiva principale con modello nel browser.
3. Analizza semplificata e Siti (globo + classifica insieme).
4. Laboratorio, Assistente (contesto della pagina), Telemetria del link, plugin: dopo.
5. Revisione, pubblicazione, CI.

## Lingue (decisione finale dell'utente: solo inglese e italiano)
Lingua di default **inglese**; selettore lingua con **English** e **Italiano** (nomi nella propria lingua). Le altre lingue
proposte in origine (hindi, cinese, arabo, coreano) sono state escluse: nessun RTL, nessun font non latino. Dettagli in
`docs/i18n.md`.
- **Infrastruttura**: cataloghi di messaggi per lingua (`frontend/src/i18n/{en,it}.json`, chiavi stabili, inglese come
  lingua sorgente), funzione `t()` con segnaposto e plurali (`Intl.PluralRules`), numeri/date/unità con `Intl` della lingua
  scelta, catalogo italiano come chunk lazy (l'inglese è nel bundle iniziale solo per le stringhe della barra e della
  home; il resto lazy). Scelta della lingua: `?lang=` > `localStorage` (try/catch, niente cookie) > lingua del browser
  se supportata > inglese; valori sconosciuti ignorati. `<html lang dir>` aggiornati (sempre ltr); titolo tradotto.
- **Contenuti del backend**: le risposte API non devono contenere frasi italiane. Il backend restituisce codici e
  valori; il frontend li traduce. Le descrizioni dei parametri, le etichette V/D/I, gli stati ("aperto / transizione /
  bloccato / fuori copertura DEM") e i messaggi d'errore hanno chiavi di traduzione.
- **Assistente**: i documenti `docs/knowledge/` hanno l'inglese come sorgente (copia italiana mantenuta). Il fornitore
  estrattivo (senza chiave) cita i testi in inglese o in italiano; con un modello vero la risposta segue la lingua scelta
  (istruzione nel prompt, citazioni invariate). Il limite è dichiarato nella pagina Assistente.
- **Selettore**: pulsante con globo e nome della lingua corrente, bersaglio 44 px, menu a tendina con tastiera
  (frecce, Invio, Esc) e annuncio del cambio; nella barra su schermi larghi, in fondo al menu sotto 834 px.
- **Test**: unità (t, plurali, segnaposto, fallback all'inglese, `?lang=` malevolo, storage bloccato, parità en/it), e2e
  (selettore su ogni pagina, cambio senza ricarica, nessun overflow a 390 e 1440, axe pulito); gli e2e esistenti girano
  in `it` (contesto Playwright con `lang=it`), più un progetto `en`.
- **Ordine**: dopo la ristrutturazione (barra, home, Simula, Analizza, Siti), così le stringhe si traducono una volta sola.
  Da subito, ogni nuova interfaccia scrive le stringhe tramite `t()`.
