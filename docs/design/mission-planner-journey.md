# Mission Planner: piano di implementazione del percorso guidato

## Obiettivo e perimetro

Sostituire la pagina monolitica con un percorso simile a un checkout:
**Missione > Siti > Periodo > Energia > Comunicazioni > Simulazione > Report**.
Non cambia il modello scientifico, non si aggiungono acquisti e non si modifica la home.
Il risultato finale e' un rapporto consultabile, scaricabile in JSON e stampabile/salvabile
in PDF tramite il browser.

## Sequenza di realizzazione

1. **Stato e contratto del calcolo.** Separare bozza, richieste e ultimo calcolo;
   validare i singoli passaggi, mantenere i dati ignoti e riconoscere risultati obsoleti.
   Conservare la bozza nella sessione e usare la libreria locale gia' esistente.
2. **Percorso e controlli.** Stepper, riepilogo laterale, indietro/continua, URL del
   passaggio e navigazione del browser. Pulsanti per le scelte discrete; slider con
   campo numerico esatto per i valori continui; selettori per bitrate e risoluzione;
   campi UTC per le date. Layout a colonna singola su schermi stretti.
3. **Viste interattive riutilizzate.** Globo condiviso con marcatori e catalogo
   ricercabile; coordinate personalizzate; anteprima Sole/Terra/potenza da RAVEN Core;
   scena lander e profilo dell'orizzonte visibili all'ingresso nelle Comunicazioni. L'analizzatore d'onda
   viene incorporato senza la navigazione della pagina autonoma e resta un esperimento
   didattico separato, esplicitamente non usato per il report.
4. **Calcolo e confronto.** Una richiesta RAVEN per scenario, eseguite su una copia
   immutabile della configurazione. Conferma esplicita per i download del terreno,
   annullamento, errori visibili, timeline e grafici sincronizzati, replay, metriche
   A/B e finestre operative. Nessun ricalcolo completo automatico mentre si modifica.
5. **Rapporto e verifica.** Anteprima del documento con configurazione, soglie,
   risultati, grafici, finestre, coordinate, modello, registro, parametri realmente
   usati, fonti, limiti e nota decisionale. Test di richieste, ripristino, valori
   ignoti e controlli; browser per percorso completo, export, modifiche, cronologia,
   due date, consenso, errori, lingua e accessibilita' mobile. Check Svelte, build e
   budget iniziale di 70.000 B.

## Invarianti

- Solo `/api/raven/*` produce risultati di missione; nessuna stima locale alternativa.
- Un risultato e' associato alle richieste esatte, comprese le coordinate personalizzate.
  Modificarle invalida il report finche' il calcolo non viene ripetuto.
- Modificare nome, obiettivi o nota decisionale non richiede ricalcoli fisici.
- Un campione ignoto non diventa falso o zero; se la serie contiene ignoti, la
  percentuale complessiva viene indicata come ignota.
- La vista lander e l'onda sono ausili esplicativi facoltativi: non sostituiscono il
  calcolo missione e dichiarano le proprie differenze di perimetro.
- Nessun quiz obbligatorio per avanzare; approfondimenti tecnici progressivi.
- Inglese e italiano, con identiche chiavi di traduzione.

## Struttura tecnica

`MissionPlanner.svelte` orchestra il percorso e riusa i servizi esistenti.
`journey.ts` contiene bozza, validazione, richieste e lettura delle sessioni.
`ParameterControl.svelte` e' il controllo slider/campo.
`JourneyResults.svelte` serve sia il confronto interattivo sia il rapporto.
`SeriesChart.svelte` riceve un cursore opzionale condiviso.
La precedente vista `Planner.svelte` (e i moduli usati solo da essa: `MissionTimeline`, `explain`, `quality`, `rfDsnOverlap`,
`sensitivity`, `windows`, `sessionCache`, `persistent*`) e' stata eliminata il 10 novembre 2026: era irraggiungibile.
La rotta pubblica carica esclusivamente il nuovo percorso.

## Visualizzazioni in primo piano e dashboard (8 novembre 2026)

- Periodo ed Energia aprono i grafici sopra ai parametri. Per siti con DEM gia'
  disponibile viene calcolata automaticamente un'anteprima dell'intero periodo,
  con lo stesso passo e gli stessi parametri RAVEN. Dopo una modifica l'anteprima
  diventa obsoleta: si aggiorna esplicitamente oppure all'ingresso nel passaggio.
  Non salva un risultato definitivo e non sblocca il report. Nessun download custom
  viene avviato automaticamente.
- Comunicazioni apre la scena 3D; l'orizzonte dei siti coperti segue sito e altezza
  con debounce. Per la scena custom resta un'azione esplicita e il consenso del
  servizio terreno. Simulazione mostra gia' il lander prima del calcolo e poi lo
  sincronizza con la timeline; numeri e sezioni sono un approfondimento richiudibile,
  senza togliere crediti, luce e stato dalla vista principale;
  nel Report i risultati precedono i parametri e la provenienza.
- I grafici condividono cursore, slider accessibile, istanti UTC e valore selezionato.
  Oltre a potenza, SOC e margine sono esposti Sole, Terra e bitrate scelto con k,
  quando presente nel contratto. Non si interpolano i campioni mancanti.
- `/dashboard`, nella barra principale, e' il controllo interattivo dell'ultimo
  calcolo della scheda del browser, non telemetria dal vivo. Riusa `JourneyResults`
  e valida archivio, richieste e registro; segnala la bozza modificata e non offre
  il report obsoleto. Senza risultati mostra un invito al Planner, mai dati fittizi.
- I moduli del registro importano direttamente gli export default, evitando
  wrapper di namespace inutili nel bundle iniziale; tutte le viste restano lazy.
