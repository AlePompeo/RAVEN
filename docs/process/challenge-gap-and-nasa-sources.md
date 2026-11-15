<!-- SPDX-License-Identifier: Apache-2.0 -->
# RAVEN: gap rispetto alla sfida e fonti NASA

Analisi del codice al commit `b8d66ec`, rispetto alla traccia Lunar Landing Site Navigator
fornita dal team e ai criteri di [NASA Space Apps](https://www.spaceappschallenge.org/resources/judging-awards-guide/):
Impact, Creativity, Validity, Relevance, Presentation. È una valutazione tecnica, non una
previsione del punteggio. Il documento storico `gap-analysis-2026-11-04.md` si riferisce a
un'altra versione e a endpoint ritirati; non va preso come stato corrente.

## Cosa esiste già

| Obiettivo della traccia | Evidenza attuale | Limite importante |
|---|---|---|
| Confronto siti e date, coordinate personalizzate | `frontend/src/pages/planner/MissionPlanner.svelte`, `timeline.ts` e `backend/api/raven_routes.py`: due scenari, mappa e coordinate | I centri di feature non sono automaticamente punti di atterraggio certificati. |
| Sole, Terra, variazione temporale e finestre | `JourneyPreview.svelte`, `VisibilityFigures.svelte`, `timeline.ts` e `/api/raven/evaluate` | I countdown sono **campionati**, non istanti continui esatti; dati ignoti non devono diventare visibilità certa. |
| Energia e DTE | Pipeline S1-S7, grafici, margine e report; `docs/domain/validation.md` | I parametri energetici e RF sono in parte illustrativi; la fattibilità non è qualificazione di volo. |
| 2D/3D e didattica | Planner, `/simula`, `/learn` e scene con fallback 2D | La verifica completa delle traduzioni IT/EN è ancora aperta; non dichiarare il sito interamente bilingue. |
| NASA e confronti | DE440/NAIF, LOLA/PDS e fixture Horizons: `docs/ephemeris.md`, `backend/domain/grazing/dem.lock.json`, `docs/domain/validation.md` | Horizons e dati LOLA sono già utilizzati: non presentarli come integrazioni nuove o come validazione di tutta la catena. |

Il quadrante e la mappa nello step 07 sono **esempi didattici con crinale sintetico**,
non predizioni del sito selezionato. L'interfaccia lo dichiara in `LinkPreview.svelte`.
I confronti con Horizons riguardano la geometria su sfera liscia; S2 terreno e S4/S5 fisici
restano non validati e S3 resta plausibilità, secondo l'audit più recente in
`docs/domain/validation.md`. L'analisi LROC WAC è utile ma non like-for-like: condivide
alcune basi geodetiche LOLA e ha diversa definizione e supporto spaziale.

## Lettura secondo i cinque criteri

| Criterio | Evidenza e lavoro ancora utile |
|---|---|
| Impact | Il confronto rapido e la didattica rispondono a pubblici diversi; non sono documentati risultati di utilizzo o benefici misurati. Raccogliere riscontri reali senza inventare metriche. |
| Creativity | L'unione di orizzonte, energia, RF e vista didattica è una proposta integrata; dimostrare cosa rende il flusso più comprensibile, senza sostenere che i singoli modelli siano invenzioni originali. |
| Validity | Ci sono benchmark geometrici e test numerici; restano aperte le validazioni fisiche e osservative indicate sotto. |
| Relevance | Il confronto A/B di siti/date usa dati NASA e risponde alla traccia; mostrare esplicitamente come una variazione cambia una decisione, con incertezze. |
| Presentation | Esistono grafici e report, ma manca la demo finale; preparare una narrazione breve in inglese e verificare accesso pubblico e traduzioni. |

## Priorità, dalla meno alla più complessa

La complessità è relativa, non una stima temporale. Le dipendenze esterne sono indicate.

1. **Presentazione e requisiti di submission — bassa.** Registrare una vera demo pubblica
   di massimo 30 s o preparare fino a 7 slide, in inglese come richiesto; `/demo` è solo
   un segnaposto. Mostrare problema, due scenari, differenza concreta, provenienza NASA e
   limiti. Completare citazioni e disclosure SI; chiarire con gli organizzatori lavoro
   pre-evento e contenuti commerciali. Vedi `space-apps-2026-submission-check.md`.
   Criteri: Presentation, Relevance. Dipende da team e organizzatori.
2. **Comunicare affidabilità senza eccessi — bassa.** Allineare README, demo e report ai
   limiti effettivi: distinguere dati, ipotesi, confronto numerico e validazione fisica;
   indicare modello/versione, copertura, risoluzione e dati ignoti. Evitare affermazioni
   non dimostrate come «publication-grade» o conformità di accessibilità universale.
   Criteri: Validity, Presentation.
3. **Completare IT/EN e percorso per giuria — bassa/media.** Terminare audit delle pagine,
   simulatori 2D/3D, messaggi server e fallback, poi verificare cambio lingua e assenza di
   stringhe miste; non soltanto la presenza di chiavi. Preparare un esempio A/B coerente,
   ripetibile e con risultato interpretabile e fonte, verificando che i dati siano disponibili.
   Criteri: Impact, Presentation.
4. **Rendere le finestre decisionali più leggibili — media.** I countdown esistono già:
   mostrare esplicitamente la precisione del passo e il motivo di chiusura, distinguendo
   Sole, ostacolo, radio, DSN e dato ignoto; testare scenari e date con risoluzioni diverse.
   Valutare raffinamento delle transizioni solo quando i dati contigui sono noti, senza
   interpolare oltre l'intervallo. Criteri: Relevance, Validity.
5. **Ampliare il confronto Horizons riproducibile — media.** Estendere le fixture esistenti
   con casi ai poli, siti, date e cambi di frame; conservare query, risposta, versione e
   tolleranze. Verificare lon/lat, quota, sistema temporale, elevazione apparente airless,
   tempo di luce e frame prima di confrontare. Horizons verifica geometria ed efemeridi,
   non orizzonte da terreno o link RF. Criteri: Validity, Relevance.
6. **Quantificare la sensibilità del terreno — medio/alta.** Confrontare lo stesso sito e
   l'orizzonte con prodotti 5 m regionali quando coperti e con 20 m/240 m attuali, usando
   uguali frame, pixel registration, quota, raggio e distanze; mostrare differenze e celle
   interpolate/ignote. Lo stesso LOLA non è una misura indipendente. Criteri: Validity.
7. **Validazione osservativa comparabile e incertezza — alta.** Costruire un benchmark
   con osservazioni LROC/prodotti georeferenziati, stessi istanti, quota osservatore,
   pixel/area e criterio di illuminazione; affrontare la discrepanza al polo documentata.
   Propagare incertezza DEM e passo temporale alle finestre, senza inventare intervalli di
   confidenza. Richiede verifica delle fonti e probabilmente revisione specialistica.
   Criteri: Validity, Impact.
8. **Qualificazione energia e radio — molto alta.** Acquisire dati indipendenti e confronti
   completi per batteria/pannello/carichi e per RF (geometria, antenna, EIRP, G/T, perdite,
   codifica, rate, margine, terreno e multipath). Richiede dati di missione o prove di
   laboratorio e revisione esperta. Le identità matematiche e le fixture condivise non
   equivalgono a misure. Criteri: Validity, Impact.

## API e dataset NASA/JPL: cosa aggiungere e cosa dimostra

| Fonte primaria | Utilizzo consigliato | Vincoli e indipendenza |
|---|---|---|
| [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html), [manuale](https://ssd.jpl.nasa.gov/horizons/manual.html) | API GET o POST per osservatore lunare, Sole e Terra; espandere i benchmark topocentrici già presenti in `tests/backend/ephemeris/`. | Entrambi impiegano effemeridi/modelli JPL correlati: confronto di implementazione e convenzioni, non osservazione indipendente. Salvare risposta completa e metadati; niente dipendenza live necessaria alla demo. |
| [NASA Moon Trek WMTS](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon), [descrizione](https://trek.nasa.gov/moon/jpl/config/textAbout.html) | Livelli cartografici, immagini e confronto visivo di profili; identificare layer, `GetCapabilities`, proiezione e provenienza specifica. | La documentazione WMTS consultata descrive tile immagine PNG/JPEG, non garantisce quote numeriche. Non decodificare colori come metri senza scala/metadati espliciti. Un layer derivato da LOLA non è indipendente da LOLA. |
| [LOLA/PDS](https://pds-geosciences.wustl.edu/missions/lro/lola.htm) | RAVEN usa già `LDEM_85S_20M`, `LDEM_75S_240M` e globale `LDEM_128_FLOAT` per i casi previsti; estendere copertura o confronti con le relative label. | Non usare la risoluzione nominale come accuratezza; verificare datum, unità, interpolazione e hash. Dati mancanti restano ignoti. |
| [NASA PGDA mosaico LOLA 5 m](https://pgda.gsfc.nasa.gov/products/81), [Barker et al.](https://ntrs.nasa.gov/citations/20205009660) | DEM, pendenza e numero di ritorni per sensibilità locale e qualità del terreno nei siti coperti da 87°S a 90°S; priorità alle regioni di interesse. | GeoTIFF DEM di 3,3 GB, MOON_ME DE421, pixel registration; verificare conversione e copertura. Barker riporta incertezze per specifici prodotti/regione: non trasferirle automaticamente ai DEM 20/240 m. LOLA contro LOLA non è validazione indipendente. |
| [NASA PGDA illuminazione polare](https://pgda.gsfc.nasa.gov/products/69) | Confrontare statistiche medie Sole/Terra su finestre e definizioni equivalenti; già analizzato in `docs/domain/validation.md`. | Mappe modellate su circa 18,6 anni; la Terra è visibile se una parte del disco è libera, non necessariamente la DSN. Non confrontare una media con uno stato istantaneo; gli overview COG possono mediare pixel. |
| [LROC WAC osservativo, PDS](https://pds.mcp.nasa.gov/data/store/img/lunar_reconnaissance_orbiter/pds4/lroc/lro-l-lroc-5-rdr/LROLRC_2001/DATA/BDR/WAC_POLE/WAC_POLE_ILL_TWI_SOUTH/) | Ampliare il confronto già documentato con osservazioni ottiche e cercare dati di illuminazione georeferenziati comparabili. | Modalità radiometrica, epoche e supporto spaziale possono differire; proiezione su DEM LOLA. Misurare bias, RMS e casi mancanti, non chiamare il confronto «validazione completa». |
| [NASA NAIF/SPICE](https://naif.jpl.nasa.gov/naif/toolkit.html) | Strumento separato per verificare trasformazioni di frame, geometria e nuovi kernel; i kernel NAIF sono già usati. | Stessi kernel/modelli condividono errori sistematici: utile come controllo indipendente del software, non del dato fisico. Fissare versioni e convenzioni. |

Le API remote non devono sostituire i calcoli offline senza esplicitarne disponibilità,
versione, cache, limiti di richiesta e errori; l'analisi proposta non è stata eseguita
come nuova validazione scientifica.

## Aggiornamento operativo: priorità per la giuria e validazione

Aggiornamento del 2026-11-15, successivo alle traduzioni parziali e ai nuovi confronti
polari in `docs/ephemeris.md`. I cinque criteri ufficiali valutano Impact, Creativity,
Validity, Relevance e Presentation: le azioni sotto sono proposte del progetto, non
requisiti aggiuntivi della competizione né garanzie di premio.

| Ordine e complessità | Attività e risultato verificabile | Dipendenze e limite |
|---|---|---|
| 1 — bassa | Preparare candidatura inglese, video pubblico di massimo 30 s o slide entro il limite ufficiale, fonti e disclosure SI. Dimostrare un A/B e la decisione che cambia. | Team; confermare con organizzatori lavoro pre-evento e contenuti commerciali. Vedi checklist submission. |
| 2 — bassa | Correggere claim troppo forti nel README, report e demo; indicare modello, provenienza, precisione temporale, stati ignoti e finalità non operative. | Usare solo evidenze riproducibili; non chiamare qualificata la missione. |
| 3 — bassa/media | Preparare un percorso A/B ripetibile: due siti/date con input, risultato e fonti registrati; spiegare il compromesso tra energia e DTE. | I grafici sintetici dello step 07 restano esempi, non misure dei due scenari. |
| 4 — media | Completare IT/EN per analisi, simulatori 2D/3D, errori backend e fallback; verificare cambio lingua e percorso della giuria. | L'audit precedente non ha coperto tutto il sito. |
| 5 — media | Risolvere gate licenze `pyphen` con revisione documentata; ripetere smoke di installazione realmente pulita; aggiornare E2E e ripetere CI. | La CI locale precedente non equivale a installazione pulita; E2E era stato interrotto. |
| 6 — media | Rendere evidenti durata campionata, passo, cause di chiusura e intervalli ignoti; testare transizioni ai bordi e dati mancanti. | Non interpolare attraverso dati ignoti né attribuire precisione continua non dimostrata. |
| 7 — media | Ampliare fixture Horizons con casi polari e quota, conservare risposte e convenzioni; valutare confronto software separato con NAIF/SPICE. | Primo ampliamento eseguito: otto confronti in `docs/ephemeris.md`. Horizons e kernel JPL sono correlati, non una validazione osservativa. |
| 8 — medio/alta | Confrontare orizzonti ottenuti con LOLA 5 m e i prodotti correnti sugli stessi siti, frame, pixel e raggio; riportare copertura e sensibilità. | Avviato a Shackleton su quattro direzioni fino a 10 km: risultati e ritorni in `docs/domain/validation.md`. Mancano altri siti, azimut e orizzonte completo; lo stesso strumento LOLA non è indipendenza fisica. |
| 9 — alta | Pianificare confronto osservativo di Sole/terreno con LROC a stesso luogo, tempo, quota, supporto spaziale e criterio; indagare la discrepanza polare già documentata. | Richiede dati comparabili e incertezza DEM; WAC radiometrico non equivale automaticamente a illuminazione geometrica istantanea. |
| 10 — molto alta | Qualificare energia e RF su dati indipendenti, configurazioni e incertezze note; definire protocolli e soglie prima del confronto. | Richiede tracce hardware o soluzioni indipendenti convergenti e revisione esperta; test aritmetici non bastano. |
| 11 — variabile | Raccogliere riscontri reali da utenti con competenze diverse; migliorare accessibilità e presentazione sulla base delle osservazioni. | Non inventare metriche di impatto o qualificazioni degli utenti. |

### Fonti: decisione di integrazione

- **Horizons:** già usato come benchmark; proseguire con fixture offline versionate,
  inclusi frame, tempo e risposte originali, invece di rendere la demo dipendente
  dal servizio. Le nuove risposte polari usano DE441 contro DE440s di RAVEN.
- **Moon Trek / WMTS:** [GetCapabilities del layer LOLA](https://trek.nasa.gov/tiles/Moon/EQ/LRO_LOLA_DEM_Global_128ppd_v04/1.0.0/WMTSCapabilities.xml)
  dichiara tile `image/png`. È candidato come sfondo cartografico con attribuzione;
  non usarlo come quota numerica senza una codifica e scala ufficiali verificabili.
  Un layer LOLA non è prova indipendente dal DEM LOLA usato da RAVEN.
- **LOLA/PDS, PGDA e NAIF/SPICE:** già presenti o studiati sopra. Dare priorità a
  provenienza, sensibilità del terreno e controllo separato delle trasformazioni
  prima di aggiungere altre dipendenze; registrare copertura e risoluzione reali.
- **SDEM LROC/LOLA:** i [prodotti NASA shape-from-shading](https://pgda.gsfc.nasa.gov/products/104)
  combinano immagini NAC con DEM LOLA per 13 regioni Artemis III, e includono
  mappe di copertura e differenze rispetto a LOLA. Sono candidati per confronti
  del terreno con dettaglio aggiuntivo, non dati indipendenti da LOLA né validazione
  delle finestre: verificare copertura, frame, licenza, incertezza e costi dei file
  prima dell'integrazione.
- **«donky»:** potrebbe indicare [DONKI](https://api.nasa.gov/), database NASA di
  eventi meteorologici spaziali, non un'API di geometria o terreno. È solo un'ipotesi:
  una prova dell'endpoint FLR con `DEMO_KEY` ha restituito HTTP 404. Non integrare
  finché nome, documentazione, accesso e utilità per il caso d'uso non siano chiariti.
  Eventuali avvisi meteo sarebbero separati dalla validazione delle finestre DTE.

### Evidenza realmente riprodotta

Kernel locali verificati con `python -m backend.ephemeris.fetch --check`. Eseguiti
88 test mirati efemeridi e stadi S1–S7, più 128 test terreno/orizzonte/multipath e
matrice; tutti passati senza skip. Dopo l'aggiunta delle quattro risposte Horizons,
23 test del modulo efemeridi passati. Questi risultati confermano le verifiche
esercitate, non elevano S2, S4 o S5 a validazione fisica né S3 oltre la plausibilità.
Dettagli e limiti delle prove fisiche restano in `docs/domain/validation.md`.

### Prova A/B del motore corrente: risultati e limite

Il 15 novembre 2026 due chiamate locali a `/api/raven/evaluate` hanno usato
`start_utc: 2027-04-07T00:00:00Z`, `days: 7`, `step_min: 60`, `include_steps: false`
e i default del server (DSN 34 m, 100 kbit/s, quote di pannello e antenna 2 m,
parametri energia/RF illustrativi). Kernel e tile LOLA erano presenti;
nessun download è stato consentito. Sono risultati del modello, non osservazioni
né previsioni certificate.

| `site_id` | Coordinate usate | Ore utili note | Ore ignote | Sole campionato | Energia raccolta |
|---|---|---:|---:|---:|---:|
| `malapert-massif` | −85,98°, −1,67° E, centro della feature | 140 | 0 | 0 h | 0 Wh |
| `nobile-rim` | −85,28°, 53,27° E, centro del cratere | 127 | 41 | 33 h | 110,96 Wh |

Per Nobile i dati ignoti impediscono di stabilire il totale delle ore utili e
di scegliere un vincitore sulla sola base della tabella. L'energia raccolta è
parziale e il minimo SOC riportato (28,3%) riguarda soltanto i passi noti.
Nobile usa il centro del cratere, non
le regioni sul bordo: non rappresenta un sito Artemis selezionato. Per Malapert
il minimo SOC è 16,7% sull'intera finestra. I conteggi hanno passo orario; i
parametri di batteria, pannello e radio non sono una configurazione qualificata.
Nella stessa prova spostare Malapert al 7 maggio ha dato gli stessi valori
aggregati: non è una dimostrazione convincente di un compromesso fra date.

Questa prova espone gli ignoti invece di nasconderli, ma **non completa**
l'esempio A/B per la giuria: bisogna scegliere coordinate e date documentate
con dati sufficienti, riprodurre le impostazioni del Planner e spiegare una
decisione senza considerare ignoto come successo o fallimento.
