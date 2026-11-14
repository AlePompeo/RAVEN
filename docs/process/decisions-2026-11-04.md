# Decisioni dell'utente, 4 novembre 2026

Fonte: risposta dell'utente all'analisi `gap-analysis-2026-11-04.md`. Valgono come istruzioni di progetto.

| # | Punto | Decisione |
|---|---|---|
| 1 | Nome del prodotto | **RAVEN. Chiuso.** "GrazingLink" resta solo come nome storico della ricerca; URL e documenti si allineano a RAVEN (gli indirizzi `/grazinglink` restano come alias). |
| 2 | Vendita, account, licenze, pagamenti | Rinviato, **punto chiave**: se ne riparla più avanti. Nel frattempo `/pricing` resta una vetrina con acquisti disattivati. |
| 3 | CI non verde | **Da completare, in priorità.** |
| 4 | Revoca del token GitHub | Per ora non serve. |
| 5 | Testo e dataset ufficiali della sfida | Punto aperto: li comunicherà l'utente. |
| 6 | Siti: regioni Artemis (17) e DEM a 5 m | **In priorità da fare** (solo da fonti verificabili; nessuna coordinata inventata). |
| 7 | Contatti e dati legali | (non discusso: restano aperti) |
| 8 | Struttura Home/Planner/Explore/Learn, scheda Model Validation, lezioni di Learn, pagina About | **D'accordo, da fare.** |
| 9 | Modalità Demo per la giuria (scenari precalcolati offline) e rapporto PDF strutturato | **D'accordo, da fare.** |
| 10 | Timeline base del Planner con orizzonte piatto | **Da sistemare, in priorità** (confluisce nel modello unico). |
| 11 | (lacuna di validazione del multipath ed energia) | Rimane punto aperto. |
| 12 | Validazione RF assoluta, cresta arrotondata | **Tenuto come punto aperto.** |

## Nuova richiesta: un solo modello per tutto il sito
"Ci sono troppi motori paralleli: va racchiuso tutto in un modello unico per l'intero sito, in modo che sia spiegabile
alla giuria che potrebbe farci domande sulla validazione dei dati."
Conseguenze: un solo motore (RAVEN Core Model) con un solo registro di parametri e una sola catena di calcolo; ogni
pagina e ogni API lo usa; ogni modulo ha uno stato di validazione dichiarato con le prove; il vecchio modello lunare a
orizzonte piatto non resta come motore parallelo. Progetto in `docs/domain/raven-model.md`.

## Altro
- **README da rifare** (inglese, nome RAVEN, avvio rapido, architettura, validazione, limiti).
- Lingue: solo inglese e italiano (decisione precedente).

## Nuova richiesta (5 nov): sito definito da coordinate qualsiasi
"Oggi si scelgono solo siti predefiniti: serve poter decidere un sito qualsiasi dalle sue coordinate, per rendere lo
strumento generalizzato."
Progetto concordato (da realizzare dopo la migrazione delle pagine al modello unico):
- **Sito personalizzato** (S0): latitudine/longitudine selenografiche (est positiva) con nome, altezza del pannello e
  dell'antenna; validazione lato server (limiti, nessun eco dell'input), massimo 8 siti personalizzati per scenario,
  salvati nell'URL (link condivisibile) e in sessionStorage; usabili in Planner, Simula (sito reale), Confronto, Lander,
  Viewer. Inserimento da campi numerici e **clic sul globo** (punto selezionato con coordinate scritte).
- **Terreno**: scelta automatica del miglior prodotto LOLA che copre il punto (20 m a lat <= -85, 240 m a lat <= -75;
  fase 2: prodotto globale a circa 240 m con letture a intervalli solo delle tessere usate). Fuori da ogni prodotto il
  terreno è SCONOSCIUTO: i risultati che dipendono dall'orizzonte e dal profilo RF diventano ignoti (mai orizzonte piatto
  spacciato per vero); restano valide geometria, efemeridi, DSN e il margine in spazio libero, etichettato come tale.
  La risoluzione usata compare sempre nei risultati e nella pagina Model & Validation.
- **Sicurezza e costi**: download solo dall'URL fisso del nodo PDS, tetto di tessere per richiesta e per ora, cache su
  disco, nessun URL dato dall'utente, limite di velocità e di concorrenza come le altre rotte.
- **Limiti dichiarati**: siti vicini al polo hanno terreno a 20 m; altrove 240 m (crinali piccoli non risolti).

### Precisazione sul costo dei dati (5 nov)
L'utente chiede il minimo possibile di download. Regole: nessun download per i siti personalizzati all'installazione;
solo tessere vicine al sito, a richiesta; stima mostrata e conferma prima di scaricare (tetto circa 10 MB per sito);
cache su disco con tetto totale (circa 200 MB) ed eliminazione delle tessere meno recenti, con pulsante per svuotarla;
orizzonte vicino a risoluzione fine e lontano a risoluzione grossolana; nessun prodotto globale ad alta risoluzione.
Misura di riferimento: circa 8 MB per sito polare (41 MB per 5 siti). Per i siti fuori dal polo il costo reale va misurato
in implementazione: se supera i tetti ci si ferma e si decide con l'utente. Opzione A (solo zone polari) resta valida.

## Rinviato (5 nov): struttura del sito, modalità Demo, rapporto PDF
L'utente ha letto le domande e vuole ripensarci più avanti. Da riprendere insieme:
1. Pubblico della Demo: giuria in presenza (con chi presenta) o che apre da sola? (percorso a passi o automatico)
2. Scenari della Demo: bastano 2-3 (es. Terra radente a Malapert, sito al buio a Haworth, un confronto)? Un sito scelto dall'utente?
3. Rapporto PDF: per chi (giuria, partner, ricercatori) e quanto lungo? Proposta: 2 pagine (scenario, risultato con numeri e limiti, stato di validazione).
4. Struttura: tenere la barra attuale (Home, Mission Planner, Explore, Learn, Piani, Contatti) o riordinare in 4-5 voci
   (Il problema, Simula, Analizza, Siti, Modello)?
Restano anche in coda: regioni Artemis e terreno a 5 m (ricerca in corso), pagina About e lezioni di Learn.

## Piani (5 nov)
I piani diventano **3**: Free, Premium, Enterprise, con tabella di confronto (check/croce) sotto. Acquisti sempre disattivati
finché non c'è fornitore di pagamento; prezzi indicati come ipotesi; le funzioni non ancora realizzate sono etichettate.

## Pagina Modello e validazione (5 nov)
Le "domande che può fare la giuria" vengono tolte dal sito (pagina, cataloghi, documento di conoscenza dell'assistente).

## Terreno a 5 m (6 nov)
I 27 DEM a 5 m (PGDA 78) NON vengono aggiunti: riferimento DE421 non verificato rispetto ai nostri dati, nessuna coordinata
NASA per scegliere la regione, formato a righe da integrare, pochi siti ne beneficiano, nessuna validazione indipendente.
Alternativa valutata, non avviata: LDEM_80S_20MPP_ADJ (20 m fino a circa -80 gradi, a tessere) per colmare il vuoto
tra -85 e -80 gradi; richiede prima un confronto sull'area in comune con il 20 m già in uso.
Valutazione costi/benefici (6 nov): anche LDEM_80S_20MPP_ADJ NON viene aggiunto ora. Beneficio limitato alla fascia
-85/-80 gradi (un sito in più analizzabile: Mons Mouton); costo: nuovo lettore COG, lock, CI/installatori, possibile
giunzione fra due fonti a -85 gradi, nessuna validazione nuova. Il sito personalizzato usa 240 m fuori dalla zona a 20 m e
dichiara la risoluzione. Da riconsiderare se i dati ufficiali della sfida richiedono siti in quella fascia.

## Coda lavori: pagina About (6 nov)
Da fare: pagina **About** che spiega tutto il progetto (richiesta dell'utente). Contenuto proposto: il problema (Terra a
circa 1 grado dall'orizzonte al polo Sud), cosa fa RAVEN, come funziona (modello unico S0-S7, in breve), da dove vengono i
dati e le fonti (JPL NAIF, LOLA/PDS, ITU-R P.526 citata, NASA), cosa è validato e cosa no (rimando a Model e validazione),
limiti dichiarati, la storia (ricerca GrazingLink -> RAVEN), team e contatti (segnaposto finché mancano i dati veri),
licenze, link a Roadmap, Piani e README. Learning: testo semplice; Avanzato: dettagli tecnici e riferimenti ai documenti.
Inglese e italiano. Va nel piè di pagina (la barra non ha spazio) e come scheda dell'hub Learn.
