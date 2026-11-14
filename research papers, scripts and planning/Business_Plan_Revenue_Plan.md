# GrazingLink

## Business plan e revenue plan

**Documento strategico per lo sviluppo post-hackathon --- NASA Space
Apps Challenge 2026**\
**Versione:** ottobre 2026\
**Valuta:** euro (€), importi al netto dell'IVA, salvo diversa
indicazione

------------------------------------------------------------------------

## Executive summary

GrazingLink è concepito come una piattaforma di supporto alle decisioni
per le comunicazioni delle missioni lunari. Il prodotto combina
geometria Sole-Terra, topografia lunare e modelli di propagazione radio
per aiutare a confrontare siti, date e configurazioni di comunicazione.

La proposta non è quella di sostituire gli strumenti scientifici e i
dataset NASA/JPL, ma di integrarli in un flusso di lavoro più rapido e
comprensibile. L'utente dovrebbe poter confrontare scenari, visualizzare
la Terra rispetto all'orizzonte locale, identificare le finestre di
comunicazione e capire quali fenomeni fisici riducono il margine del
collegamento.

Il progetto GrazingLink v3 descrive già un nucleo tecnico composto da: -
orizzonte reale ricavato da DEM LOLA, curvatura lunare e altezza del
mast; - calcolo della diffrazione da ostacoli e creste; - modello
multipath a due raggi; - caratteristiche dell'antenna, guadagno,
apertura e perdita di puntamento; - link budget e stima del margine; -
compensazione del modello e scelta del bit rate con margine
statistico; - possibile estensione opzionale con relay.

La priorità strategica è rendere il prodotto aderente all'intera traccia
CLPS Lunar Mission Browser: il nucleo radio deve essere inserito in
un'esperienza di pianificazione che permetta di confrontare siti e date,
osservare Sole e Terra rispetto all'orizzonte e valutare finestre di
luce e comunicazione.

**Raccomandazione:** posizionare GrazingLink come piattaforma B2B di
analisi e decision support, con una versione Community/Education
gratuita o a basso costo come canale di diffusione, formazione e
acquisizione utenti. La parte didattica ha senso, ma non dovrebbe
diventare il principale motore di ricavi nella prima fase: va trattata
come prodotto complementare, con costi contenuti e un proprio budget di
sviluppo e gestione.

> **Nota di affidabilità:** i modelli fisici descritti nel progetto si
> basano su letteratura e verifiche analitiche/simulative riportate nel
> documento tecnico. La validazione su dati di volo non è disponibile. I
> parametri radio, d'antenna e di stazione di terra devono essere
> sostituiti con valori specifici di missione quando disponibili.
> GrazingLink non deve essere presentato come software già qualificato
> per decisioni operative di missione.

------------------------------------------------------------------------

# 1. Problema e opportunità

## 1.1 Il problema

Le missioni al Polo Sud lunare devono coordinare esigenze scientifiche e
ingegneristiche in un ambiente caratterizzato da: - illuminazione solare
estrema e variabile; - rilievi, crateri e creste che modificano
l'orizzonte locale; - visibilità della Terra limitata dalla geometria e
dalla topografia; - finestre di comunicazione che possono cambiare con
piccoli spostamenti di sito o data; - necessità di valutare rapidamente
alternative quando cambiano date, hardware o vincoli di missione.

Strumenti come NASA Moon Trek, QuickMap e JPL Horizons rendono
disponibili dati e capacità di analisi importanti, ma l'utente può dover
passare fra più interfacce e trasformare dati specialistici in
decisioni. Il bisogno individuato è quindi un'esperienza integrata che
renda più rapida la comparazione degli scenari.

## 1.2 Il problema specifico affrontato da GrazingLink

La visibilità geometrica della Terra non garantisce da sola un
collegamento radio affidabile. Quando la Terra è vicina all'orizzonte: -
un crinale può introdurre diffrazione e perdita di segnale; - il suolo
può generare riflessioni e multipath; - la direttività e il puntamento
dell'antenna influenzano il collegamento; - il margine radio può variare
nel tempo; - la scelta del bit rate deve considerare un margine di
sicurezza.

GrazingLink intende passare da una risposta binaria --- "la Terra è
visibile/non è visibile" --- a una valutazione più informativa: "quale
margine di collegamento è stimato, quali fenomeni lo limitano e quale
bit rate può essere considerato con un margine dichiarato?".

## 1.3 Opportunità

L'opportunità di prodotto è l'integrazione di tre livelli: 1.
**Geometria e ambiente:** sito, data, posizione di Sole e Terra,
topografia e orizzonte. 2. **Prestazioni radio:** diffrazione,
multipath, antenna, link budget, margine e bit rate. 3. **Decisione e
comunicazione:** confronto di alternative, spiegazione delle cause,
incertezza e report esportabile.

La differenziazione non consiste nell'affermare di aver inventato nuova
fisica: il progetto riconosce che i modelli di diffrazione e multipath
sono già presenti nella letteratura JPL. Il valore proposto è integrarli
in uno strumento leggero e interattivo, con cause esplicite e confronti
rapidi.

------------------------------------------------------------------------

# 2. Prodotto e miglioramenti prioritari

## 2.1 Architettura del prodotto

Il prodotto può essere organizzato in due modalità collegate.

### Modalità Mission Planner

Pensata per pianificatori, responsabili di missione, ricercatori e
utenti non specialisti. - selezione di siti lunari predefiniti; -
inserimento di coordinate personalizzate; - scelta di data e ora; -
visualizzazione della posizione di Sole e Terra rispetto
all'orizzonte; - durata della luce solare e finestre di visibilità della
Terra; - confronto side-by-side fra siti e date; - timeline delle
finestre operative; - sintesi dei principali indicatori e spiegazione
dei rischi.

### Modalità RF Engineer

Pensata per ingegneri radio e specialisti. - profilo del terreno verso
la Terra; - altezza del mast configurabile; - banda radio e parametri di
trasmissione; - preset di antenna e perdita di puntamento; - diffrazione
e multipath; - link budget, margine e bit rate; - analisi di
sensibilità; - incertezza del modello e avvisi fuori dal dominio di
validità.

Le due modalità dovrebbero utilizzare lo stesso motore di calcolo. La
differenza è il livello di dettaglio mostrato.

## 2.2 Funzionalità da sviluppare

  ------------------------------------------------------------------------
  Priorità          Funzionalità      Valore per         Indicazione
                                      l'utente           
  ----------------- ----------------- ------------------ -----------------
  P0                Selezione sito e  Definisce lo       Necessaria
                    coordinate        scenario           

  P0                Data e ora        Permette di        Necessaria
                                      valutare cambi di  
                                      programma          

  P0                Posizione         Aderenza diretta   Necessaria
                    Sole/Terra        alla traccia       
                    rispetto                             
                    all'orizzonte                        

  P0                Confronto di      Riduce il tempo di Necessaria
                    almeno due        valutazione        
                    scenari                              

  P0                Finestra          Base della         Necessaria
                    geometrica di     valutazione        
                    visibilità                           

  P0                Profilo del       Aggiunge realismo  Prioritaria
                    terreno e         topografico        
                    orizzonte LOLA                       

  P1                Diffrazione       Differenziazione   Prioritaria
                                      RF                 

  P1                Link budget e     Traduce la fisica  Prioritaria
                    margine           in una metrica     

  P1                Antenna e perdita Valutazione di     Prioritaria
                    di puntamento     configurazioni     

  P1                Multipath         Analisi RF più     Dopo il nucleo
                                      approfondita       

  P1                Report PDF/CSV    Utilità            Prioritaria
                                      professionale e    
                                      ricavo             

  P2                Compensazione     Gestione           Dopo il nucleo
                    statistica        dell'incertezza    

  P2                Relay what-if     Estensione di      Opzionale
                                      missione           

  P2                Modalità          Diffusione e       Versione
                    educativa         apprendimento      complementare
  ------------------------------------------------------------------------

## 2.3 Esperienza utente consigliata

Il flusso ideale è: 1. L'utente seleziona un sito o inserisce
coordinate. 2. Imposta data e ora. 3. Visualizza Sole, Terra e orizzonte
locale. 4. Aggiunge un secondo sito o una seconda data. 5. Confronta
finestre di luce e comunicazione. 6. Attiva l'analisi RF per comprendere
le perdite. 7. Esporta un report con risultati, ipotesi e incertezze.

La schermata iniziale dovrebbe mostrare poche metriche essenziali: -
elevazione solare; - durata stimata dell'illuminazione; - elevazione
apparente della Terra; - finestra geometrica di visibilità; - margine
radio stimato; - percentuale di interruzione stimata, se supportata dal
modello; - bit rate stimato con margine; - livello di confidenza o
avviso di incertezza.

Non bisogna confondere visibilità geometrica, visibilità radio e
disponibilità operativa: sono concetti collegati, ma distinti.

## 2.4 La scena 3D come elemento dimostrativo

La scena 3D dovrebbe mostrare: - lander e altezza del mast; - superficie
lunare e profilo dell'orizzonte; - Terra e direzione del collegamento; -
cono dell'antenna; - cresta che ostacola il collegamento; - percorso
diretto e riflesso, se il modello multipath è attivo; - variazione del
margine al cambiare di banda, antenna o altezza.

La scena non deve essere soltanto decorativa: ogni controllo dovrebbe
produrre un cambiamento misurabile nei risultati.

------------------------------------------------------------------------

# 3. Analisi competitiva

## 3.1 Competitor e alternative

La concorrenza è composta da strumenti che risolvono parti del problema,
non necessariamente da un prodotto identico.

### NASA Moon Trek

Portale di esplorazione e analisi geospaziale lunare. È un riferimento
per visualizzazione e consultazione dei dati della superficie. - **Punto
di forza:** dati e strumenti di esplorazione lunare. - **Limite rispetto
al posizionamento GrazingLink:** il progetto GrazingLink intende
integrare la valutazione del collegamento radio e spiegare perdite e
margini.

### NASA QuickMap

Strumento cartografico per consultare dati lunari. - **Punto di forza:**
esplorazione e consultazione di dati geospaziali. - **Limite rispetto al
posizionamento GrazingLink:** GrazingLink mira a tradurre i dati in una
comparazione di prestazioni radio.

### JPL Horizons

Servizio per effemeridi e geometria dei corpi celesti. - **Punto di
forza:** calcolo e accesso a dati di posizione e osservabilità. -
**Limite rispetto al posizionamento GrazingLink:** non è presentato come
un workflow integrato per diffrazione, multipath, antenna e link budget
lunare.

### NAIF SPICE

Infrastruttura e strumenti per geometria e navigazione spaziale. -
**Punto di forza:** capacità tecniche e flessibilità per utenti
specialistici. - **Limite rispetto al posizionamento GrazingLink:**
richiede competenze e integrazione nel workflow dell'utilizzatore.

### Software RF e strumenti di simulazione

Software di simulazione elettromagnetica e propagazione possono essere
utilizzati per analisi più approfondite. - **Punto di forza:**
simulazioni specialistiche. - **Limite rispetto al posizionamento
GrazingLink:** possono richiedere configurazione, competenze e tempi
maggiori per rispondere a una domanda di confronto rapido fra scenari
lunari.

## 3.2 Matrice qualitativa

La tabella è una valutazione strategica qualitativa, non un benchmark
sperimentale. Le funzionalità precise dei prodotti concorrenti devono
essere verificate con test e documentazione aggiornata prima di
utilizzarla in una presentazione commerciale.

  ----------------------------------------------------------------------------
  Capacità       Moon Trek      QuickMap       JPL              GrazingLink
                                               Horizons/SPICE   proposto
  -------------- -------------- -------------- ---------------- --------------
  Esplorazione   Forte          Forte          Non è il focus   Da integrare
  del terreno                                  principale       

  Effemeridi e   Da verificare  Da verificare  Forte            Da integrare
  geometria      per il caso                                    
  celeste        specifico                                      

  Confronto      Da verificare  Da verificare  Richiede         Obiettivo
  rapido di                                    workflow         centrale
  siti/date                                    aggiuntivo       

  Diffrazione    Non è il focus Non è il focus Non è il focus   Elemento
  radio sul      dichiarato     dichiarato     principale       distintivo
  terreno                                                       

  Multipath      Non è il focus Non è il focus Non è il focus   Modello
                 dichiarato     dichiarato     principale       previsto

  Antenna e link Non è il focus Non è il focus Non è il focus   Modello
  budget         dichiarato     dichiarato     principale       previsto

  Report         Da verificare  Da verificare  Richiede         Obiettivo
  decisionale                                  elaborazione     centrale
  integrato                                    aggiuntiva       

  Modalità       Possibile uso  Possibile uso  Uso              Da progettare
  educativa      divulgativo    divulgativo    specialistico    
  ----------------------------------------------------------------------------

## 3.3 Posizionamento competitivo

GrazingLink non dovrebbe competere sulla quantità di dati disponibili:
NASA e JPL hanno un vantaggio strutturale in questo ambito. Deve invece
competere su: - integrazione dei dati; - semplicità del workflow; -
confronto rapido fra alternative; - spiegabilità dei risultati; -
collegamento fra geometria, terreno e prestazioni radio; - report
ripetibili e tracciabili.

La barriera competitiva futura sarà costituita dalla qualità
dell'integrazione, dai test e dalla fiducia degli utenti, non dalla sola
interfaccia 3D.

------------------------------------------------------------------------

# 4. Clienti e mercato di riferimento

## 4.1 Segmenti prioritari

  -------------------------------------------------------------------------
  Segmento          Bisogno             Proposta di       Priorità
                                        valore            
  ----------------- ------------------- ----------------- -----------------
  Aziende che       Analizzare finestre Confronto         Molto alta
  sviluppano lander e configurazioni di sito/data e link  
                    comunicazione       budget            

  Integratori RF e  Valutare antenne,   Modello RF e      Molto alta
  operatori di      perdite e margini   report            
  comunicazione                                           
  spaziale                                                

  Università e      Simulare e          Licenza           Alta
  laboratori        documentare scenari accademica e      
                                        ambiente          
                                        didattico         

  Agenzie e         Studi di            Analisi e report  Alta, con vendita
  programmi         fattibilità e       tracciabili       più lunga
  istituzionali     supporto alla                         
                    pianificazione                        

  Scuole, musei e   Spiegare le sfide   Modalità          Strategica per
  divulgatori       dell'esplorazione   educativa         diffusione
                    lunare                                

  Studenti e        Imparare attraverso Community         Bassa
  pubblico          visualizzazioni     gratuita          monetizzazione
                    interattive                           diretta
  -------------------------------------------------------------------------

## 4.2 Cliente iniziale consigliato

Il cliente iniziale più realistico potrebbe essere un laboratorio
universitario, un gruppo di ricerca o una piccola azienda spaziale
che: - lavora su comunicazioni o missioni lunari; - ha competenze
tecniche per valutare il modello; - può fornire parametri di missione o
casi di test; - è disposto a partecipare a un progetto pilota.

La vendita diretta a grandi agenzie spaziali può richiedere cicli di
procurement, requisiti di sicurezza e validazioni importanti. È quindi
opportuno non basare il primo piano commerciale esclusivamente su tali
clienti.

## 4.3 Validazione del mercato

Prima di investire in una versione commerciale completa, svolgere: -
10--15 interviste con potenziali utenti tecnici; - 3--5 sessioni di test
con prototipo; - almeno 3 manifestazioni d'interesse per un progetto
pilota; - verifica della disponibilità a pagare per report, licenza o
integrazione; - raccolta dei requisiti di accuratezza, dati e
documentazione.

Le manifestazioni d'interesse non equivalgono a contratti o ricavi:
servono a ridurre il rischio commerciale.

------------------------------------------------------------------------

# 5. Business Model Canvas

  -----------------------------------------------------------------------
  Blocco                              Definizione per GrazingLink
  ----------------------------------- -----------------------------------
  Segmenti di clientela               Aziende di lander, integratori RF,
                                      operatori di comunicazione,
                                      università, laboratori, enti
                                      educativi

  Proposta di valore                  Confrontare siti e date e
                                      comprendere come geometria, terreno
                                      e antenna influenzano il
                                      collegamento Terra-Luna

  Canali                              Web app, partnership universitarie,
                                      conferenze aerospace, programmi di
                                      innovazione, demo tecniche e
                                      contatti diretti

  Relazione con i clienti             Self-service per
                                      Community/Education; onboarding,
                                      supporto e revisione tecnica per
                                      clienti professionali

  Flussi di ricavo                    Abbonamenti, licenze per missione,
                                      report, API, servizi di analisi,
                                      licenze accademiche e contratti
                                      educativi

  Risorse chiave                      Motore RF, dati LOLA, effemeridi,
                                      software, modelli, test,
                                      documentazione e competenze
                                      scientifiche

  Attività chiave                     Sviluppo, manutenzione, verifica
                                      numerica, confronto scenari,
                                      supporto e aggiornamento dati

  Partner chiave                      Università, laboratori RF,
                                      ricercatori, fornitori di dati,
                                      aziende spaziali e organizzazioni
                                      educative

  Struttura dei costi                 Sviluppo, validazione,
                                      infrastruttura, manutenzione,
                                      supporto, sicurezza, licenze e
                                      vendita
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 6. Revenue model e strategia di pricing

I prezzi sono ipotesi commerciali da validare. Non rappresentano tariffe
di mercato verificate né ricavi già acquisiti. Sono espressi in euro,
IVA esclusa.

## 6.1 Offerta a livelli

### Community --- gratuito

**Target:** pubblico, studenti, docenti e curiosi. - siti predefiniti; -
visualizzazione base di Sole e Terra; - timeline semplificata; -
confronto limitato; - spiegazioni dei concetti fondamentali; - tutorial
e scenari didattici; - nessuna garanzia di impiego operativo.

**Obiettivo economico:** acquisizione utenti, diffusione, feedback e
generazione di contatti. Non deve essere considerato un centro di
profitto nella fase iniziale.

### Education --- gratuito per uso individuale, licenza istituzionale opzionale

**Target:** scuole, università, musei, planetari e divulgatori. -
percorsi didattici guidati; - scenari preconfigurati; - esercizi su
illuminazione e comunicazione; - visualizzazione interattiva 2D/3D; -
schede per docenti; - attività di gruppo e materiali didattici; -
eventuale dashboard per classe o laboratorio.

Prezzi ipotetici: - singolo docente o piccolo gruppo: gratuito o
€99--199/anno; - istituto scolastico: €300--1.000/anno; - università o
laboratorio didattico: €1.000--3.000/anno; - museo, planetario o
installazione: €2.000--8.000/anno, con eventuale costo di
configurazione.

Questi prezzi vanno testati con interviste e progetti pilota. La
versione Education deve essere semplice da mantenere e non richiedere
supporto tecnico personalizzato continuo.

### Professional --- €199/mese per utente o piccolo team

**Target:** ricercatori, consulenti e piccoli team. - scenari
personalizzati; - analisi RF avanzata; - confronto multi-scenario; -
report PDF/CSV; - storico delle simulazioni; - parametri
configurabili; - supporto standard.

Da valutare se applicare un prezzo per utente, per team o per volume di
simulazioni. Per i primi clienti può essere più semplice una licenza
team annuale.

### Mission License --- €10.000--30.000 per studio o missione

**Target:** aziende di lander, integratori e gruppi di missione. -
configurazione di un caso di missione; - analisi multi-sito e
multi-data; - parametri di antenna e stazione di terra; - report tecnico
dedicato; - sessione di revisione dei risultati; - supporto per la
configurazione.

Il prezzo dipende da complessità, numero di scenari, dati disponibili e
livello di supporto. La licenza non deve essere venduta come
certificazione o garanzia di successo della missione.

### Enterprise --- €30.000--100.000+ all'anno

**Target:** organizzazioni con uso continuativo. - accesso
multiutente; - API e integrazioni; - configurazioni e modelli
personalizzati; - supporto prioritario; - gestione dei progetti; -
report e tracciabilità; - eventuali installazioni dedicate o requisiti
di sicurezza.

Questa fascia è plausibile solo dopo aver maturato prodotto, referenze,
documentazione, sicurezza e validazione adeguati.

## 6.2 Fonti di ricavo

1.  **Abbonamento SaaS:** ricavi ricorrenti da utenti professionali.
2.  **Report tecnici:** studi puntuali su siti, date e configurazioni.
3.  **Licenze mission-specific:** contratti legati a un progetto o a una
    missione.
4.  **API e integrazioni:** utilizzo del motore in strumenti di terze
    parti.
5.  **Servizi di analisi e validazione:** supporto tecnico e confronto
    con modelli indipendenti.
6.  **Licenze Education:** istituzioni, musei, planetari e università.
7.  **Workshop e formazione:** sessioni formative per università, enti e
    aziende, se richieste.

## 6.3 Mix di ricavi raccomandato

Nei primi 12--24 mesi il mix dovrebbe essere orientato al B2B: - report
e progetti pilota; - licenze mission-specific; - primi abbonamenti
Professional; - licenze accademiche selezionate.

La componente Education può contribuire alla diffusione e generare
ricavi complementari, ma non dovrebbe essere considerata il motore
principale finché non esistono canali di vendita e contenuti didattici
scalabili.

------------------------------------------------------------------------

# 7. La componente didattica: conviene inserirla?

## 7.1 Valutazione strategica

**Sì, conviene includerla, ma come linea complementare e non come
prodotto principale.**

La traccia contempla esplicitamente educatori e pubblico. La modalità
didattica aumenta l'aderenza al challenge e rende il progetto più
accessibile alla giuria, agli studenti e a chi non ha competenze RF.

Inoltre può: - ampliare il numero di utenti; - rendere comprensibili
concetti difficili; - aumentare visibilità e diffusione; - creare
relazioni con università e scuole; - generare opportunità di
partnership; - produrre ricavi tramite licenze istituzionali, workshop e
installazioni.

Tuttavia il mercato Education ha dinamiche diverse dal B2B aerospace:
budget più contenuti, cicli di acquisto legati all'anno scolastico,
necessità di contenuti didattici e supporto agli insegnanti. Non è
opportuno costruire due prodotti separati fin dall'inizio.

## 7.2 Come progettare la modalità didattica senza duplicare il prodotto

La soluzione migliore è una modalità semplificata che utilizzi lo stesso
motore e gli stessi dati.

  -----------------------------------------------------------------------
  Funzione didattica      Descrizione             Costo/complessità
                                                  relativa
  ----------------------- ----------------------- -----------------------
  Tour guidato            Spiega sito, orizzonte, Bassa
                          Sole e Terra            

  Slider temporale        Mostra come cambia la   Bassa-media
                          geometria               

  Confronto di due siti   Evidenzia differenze di Media
                          illuminazione e         
                          visibilità              

  Esperimento antenna     Mostra in modo          Media
                          semplificato l'effetto  
                          della direttività       

  Quiz e mission          L'utente sceglie il     Media
  challenge               sito più adatto secondo 
                          alcuni criteri          

  Schede docente          Obiettivi, spiegazioni  Media
                          e attività              

  Dashboard classe        Gestione di gruppi e    Medio-alta
                          risultati               

  Installazione museale   Interfaccia touch e     Alta
                          contenuti               
                          personalizzati          
  -----------------------------------------------------------------------

Per la prima versione sono sufficienti tour guidato, slider temporale,
confronto di due siti e spiegazioni contestuali. Quiz, dashboard e
installazioni possono arrivare successivamente.

## 7.3 Costi incrementali della didattica

Stime di pianificazione, non preventivi.

  Attività                              Impegno indicativo      Costo ipotetico
  ---------------------------------- --------------------- --------------------
  Progettazione percorso didattico           3--5 giornate        €1.050--2.500
  Testi, illustrazioni e schede              4--7 giornate        €1.400--3.500
  Quiz e tour guidato                        3--5 giornate        €1.050--2.500
  Test con docenti/studenti                  2--4 giornate          €700--2.000
  **Totale prima versione**            **12--21 giornate**   **€4.200--10.500**

Costi ricorrenti aggiuntivi ipotetici: - aggiornamento contenuti:
€100--300/mese; - supporto e gestione istituti: €100--400/mese; -
hosting incrementale: €0--50/mese, se la modalità utilizza la stessa
infrastruttura.

Il costo effettivo può essere più basso se il team produce internamente
testi e materiali, ma il tempo di lavoro deve comunque essere
contabilizzato.

## 7.4 Ricavi didattici potenziali

Esempio di prezzi da validare: - licenza scolastica: €300--1.000/anno; -
licenza universitaria: €1.000--3.000/anno; - museo/planetario:
€2.000--8.000/anno; - workshop: €500--2.000 per sessione o progetto.

La modalità didattica può diventare economicamente sostenibile se il
costo marginale per nuovo istituto è basso e il supporto è
standardizzato. Se ogni cliente richiede contenuti e installazioni
personalizzati, il modello diventa consulenziale e meno scalabile.

## 7.5 Decisione raccomandata

-   **Hackathon:** includere una piccola modalità educativa per
    dimostrare accessibilità.
-   **MVP:** mantenere tour guidato, spiegazioni e scenari
    preconfigurati.
-   **Dopo i primi test:** proporre un progetto pilota a una scuola o
    università.
-   **Dopo la validazione:** decidere se sviluppare licenze
    istituzionali e installazioni museali.

La didattica è quindi utile sia per il valore sociale sia per la
distribuzione del prodotto, ma non deve sottrarre tempo alle
funzionalità centrali richieste dalla traccia.

------------------------------------------------------------------------

# 8. Analisi dei costi

## 8.1 Costi del prototipo hackathon

Stima di spese vive per un prototipo realizzato principalmente dal team,
utilizzando strumenti e dati gratuiti ove possibile.

  Voce                                       Stima
  ---------------------------------- -------------
  Sviluppo motore e integrazione           €0--300
  Modello RF e verifiche                   €0--200
  Interfaccia e visualizzazione 3D         €0--150
  Hosting, dominio e servizi web            €0--50
  Video, pitch e materiali                 €0--100
  **Totale spese vive**                **€0--800**

Non comprende il valore del tempo di lavoro, attrezzature, eventuali
trasferte o servizi già acquistati.

## 8.2 Costi di sviluppo della prima versione commerciale

Assunzione: costo aziendale medio di €350--500 per giornata/persona. È
un valore di pianificazione da sostituire con costi reali del team.

  Attività                             Giornate/persona                 Stima
  ---------------------------------- ------------------ ---------------------
  Motore geometrico e topografia                 15--25        €5.250--12.500
  Propagazione radio e link budget               20--35        €7.000--17.500
  Interfaccia web e 3D                           20--30        €7.000--15.000
  Dati, test e validazione                       15--25        €5.250--12.500
  Backend, report e sicurezza                     8--15         €2.800--7.500
  **Totale**                                **78--130**   **€27.300--65.000**

Questa stima riguarda una prima versione limitata e presuppone che parte
del prototipo sia già disponibile. Le attività possono sovrapporsi e non
sono tutte necessariamente aggiuntive.

Per una versione professionale più robusta, con integrazione nei
workflow dei clienti, validazione indipendente, documentazione,
sicurezza e supporto, il budget può salire indicativamente a
**€60.000--150.000 o più**.

## 8.3 Costi operativi ricorrenti

  Voce                                         Stima mensile
  --------------------------------- ------------------------
  Hosting e backend                                 €20--200
  Storage e gestione dati                           €10--100
  Monitoraggio e backup                             €20--100
  Manutenzione software                          €500--2.000
  Supporto e verifica scientifica                €500--2.000
  **Totale**                          **€1.050--4.400/mese**

Non sono inclusi marketing, amministrazione, legale, assicurazioni,
imposte, costi di vendita e compensi eventualmente non inclusi.

## 8.4 Costi specifici della modalità Education

La prima versione educativa comporta un investimento incrementale
ipotizzato di €4.200--10.500 e costi ricorrenti aggiuntivi di circa
€200--750 al mese, a seconda del livello di supporto e aggiornamento.

Per evitare di sovrainvestire, la modalità didattica dovrebbe
riutilizzare: - motore geometrico; - dati e visualizzazioni; -
infrastruttura; - componenti UI; - report e scenari predefiniti.

Non si raccomanda di costruire un backend educativo separato nella prima
fase.

## 8.5 Il costo più importante: validazione scientifica

La validazione è un costo strategico, non un'attività accessoria.
Occorre: - implementare test automatici; - confrontare i risultati con
formule e casi di riferimento; - verificare dati di effemeridi e
topografia; - confrontare i modelli con simulazioni indipendenti; -
documentare i parametri assunti; - gestire incertezza e dominio di
validità; - coinvolgere specialisti RF.

La compensazione fra modelli non deve essere descritta come validazione
della realtà. La validazione su dati indipendenti o di volo resta un
obiettivo futuro.

------------------------------------------------------------------------

# 9. Break-even e scenari economici

## 9.1 Ipotesi base

Per un esempio semplificato assumiamo: - costi operativi medi:
€3.000/mese; - costi operativi annui: €36.000; - prezzo Professional:
€199/mese; - prezzo medio Mission License: €15.000; - prezzi al netto
dell'IVA.

Il risultato operativo riportato non include imposte, costi di
acquisizione clienti, investimenti iniziali, ammortamenti o costi non
compresi nella stima operativa.

## 9.2 Esempio di scenario

Con: - 10 clienti Professional; - 2 licenze mission-specific da €15.000
all'anno;

si ottiene:

  Fonte                                Calcolo            Ricavo annuo
  ------------------------------------ ---------------- --------------
  Professional                         10 × €199 × 12          €23.880
  Mission License                      2 × €15.000             €30.000
  **Totale**                                               **€53.880**
  Costi operativi                      €3.000 × 12             €36.000
  **Risultato operativo indicativo**                       **€17.880**

Questo scenario copre i costi operativi ipotizzati, ma non recupera
necessariamente l'investimento di sviluppo.

## 9.3 Esempio di contributo Education

Aggiungiamo un esempio illustrativo: - 5 licenze scolastiche da
€500/anno; - 2 licenze universitarie da €2.000/anno; - 1 workshop da
€1.000.

Ricavi Education: - scuole: €2.500; - università: €4.000; - workshop:
€1.000; - **totale: €7.500/anno**.

Se la gestione Education comportasse €300/mese di costi incrementali,
pari a €3.600/anno, il contributo prima dei costi di acquisizione e
delle imposte sarebbe €3.900.

Questa simulazione mostra che la didattica può contribuire, ma non è
sufficiente da sola a sostenere il prodotto tecnico. È un ricavo
complementare e un canale di diffusione.

## 9.4 Formule di riferimento

-   Ricavo Professional annuo = clienti × prezzo mensile × 12.
-   Ricavo missioni annuo = numero di licenze × prezzo medio.
-   Ricavo Education = licenze scolastiche + licenze universitarie +
    workshop.
-   Risultato operativo semplificato = ricavi complessivi − costi
    operativi.
-   Break-even operativo = ricavi ricorrenti e contratti sufficienti a
    coprire i costi ricorrenti.

È importante distinguere il break-even operativo dal recupero
dell'investimento iniziale.

------------------------------------------------------------------------

# 10. Go-to-market e acquisizione clienti

## 10.1 Fase iniziale: credibilità e primi utilizzatori

Canali consigliati: - contatti con gruppi universitari di ingegneria
aerospaziale e telecomunicazioni; - laboratori di radiofrequenza e
navigazione; - community e conferenze aerospace; - programmi di
innovazione e incubatori; - contatti diretti con aziende che sviluppano
lander e payload; - dimostrazioni tecniche con casi di studio.

## 10.2 Strategia dei progetti pilota

Proporre un pilot con perimetro chiaro: 1. un sito o una piccola
regione; 2. un numero definito di date; 3. configurazioni radio
concordate; 4. parametri e ipotesi documentati; 5. report finale; 6.
sessione di feedback.

Il pilot può essere gratuito solo se fornisce accesso a competenze,
dati, revisione scientifica o una referenza utile. Altrimenti è
preferibile un pilot a pagamento, anche con prezzo iniziale ridotto.

## 10.3 Materiali commerciali necessari

-   demo web;
-   video di 60--90 secondi;
-   report tecnico campione;
-   documentazione delle ipotesi;
-   matrice di validazione;
-   scheda prodotto;
-   listino pilota;
-   pagina Community/Education.

------------------------------------------------------------------------

# 11. Roadmap di sviluppo a 12 mesi

  -----------------------------------------------------------------------
  Periodo                 Attività                Risultato atteso
  ----------------------- ----------------------- -----------------------
  Mese 0--1               Hackathon, demo e       Prototipo e feedback
                          interviste              

  Mesi 2--3               MVP stabile, confronto  Prima versione
                          scenari, dati e report  utilizzabile

  Mesi 4--6               Test indipendenti e     Prime evidenze di
                          pilot tecnici           affidabilità e
                                                  disponibilità a pagare

  Mesi 7--9               Professional, API       Primi ricavi ricorrenti
                          limitata e licenze      
                          accademiche             

  Mesi 10--12             Enterprise e            Primi contratti più
                          integrazioni            strutturati
  -----------------------------------------------------------------------

Gli obiettivi quantitativi dovranno essere definiti dopo le interviste e
i pilot. Le tempistiche dipendono dalla disponibilità dei dati e dal
livello di validazione richiesto.

------------------------------------------------------------------------

# 12. Piano delle 48 ore per l'hackathon

  -----------------------------------------------------------------------
  Ore                     Attività                Gate
  ----------------------- ----------------------- -----------------------
  0--8                    Orizzonte, geometria e  Scenario end-to-end
                          Terra nel browser per   
                          un sito reale           

  8--18                   Diffrazione e primo     Risultato radio
                          link budget             dimostrabile

  18--24                  Antenna, finestre e     MVP
                          confronto fra due       
                          scenari                 

  24--34                  Multipath, margine,     Funzioni principali
                          report e spiegazione    bloccate
                          delle cause             

  34--44                  Scena 3D, test e video  Demo stabile

  44--48                  Pitch, consegna e       Presentazione finale
                          revisione               
  -----------------------------------------------------------------------

La modalità educativa per l'hackathon dovrebbe limitarsi a un tour
guidato e a spiegazioni contestuali, senza sottrarre tempo alle funzioni
principali.

------------------------------------------------------------------------

# 13. Rischi e mitigazioni

  -----------------------------------------------------------------------
  Rischio                 Impatto                 Mitigazione
  ----------------------- ----------------------- -----------------------
  Modello non validato su Alto                    Dichiarare limiti, test
  dati di volo                                    indipendenti e
                                                  coinvolgere esperti

  Parametri radio         Alto                    Usare preset
  ipotizzati                                      documentati e
                                                  configurazioni
                                                  specifiche quando
                                                  disponibili

  Aderenza insufficiente  Alto                    Integrare Sole, Terra,
  alla traccia                                    date, siti e confronto
                                                  scenari

  Eccesso di complessità  Medio-alto              Separare Mission
  nell'interfaccia                                Planner e RF Engineer

  Scope troppo ampio per  Alto                    Definire gate e
  48 ore                                          funzionalità P0

  Competitor gratuiti e   Medio-alto              Competere su workflow,
  dati pubblici                                   integrazione e report

  Cicli di vendita        Alto                    Iniziare con laboratori
  aerospace lunghi                                e progetti pilota

  Mercato Education poco  Medio                   Mantenere costi
  monetizzabile                                   marginali bassi e
                                                  vendere licenze
                                                  istituzionali standard

  Dipendenza da dati e    Medio                   Verificare condizioni
  licenze                                         d'uso, attribuzione e
                                                  redistribuzione

  Risultati interpretati  Alto                    Disclaimer,
  come garanzia operativa                         tracciabilità e
                                                  separazione fra stima e
                                                  validazione
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 14. KPI da monitorare

## Prodotto

-   tempo necessario per confrontare due scenari;
-   percentuale di utenti che completa il workflow;
-   numero di scenari analizzati per sessione;
-   numero di report esportati;
-   errori e anomalie del motore;
-   copertura dei test;
-   differenza rispetto ai casi di riferimento.

## Commerciali

-   interviste effettuate;
-   organizzazioni interessate;
-   pilot avviati e convertiti;
-   ricavi ricorrenti mensili (MRR);
-   ricavi annuali ricorrenti (ARR);
-   valore medio dei contratti;
-   tasso di rinnovo;
-   costo di acquisizione cliente, quando misurabile.

## Education

-   scuole e università attive;
-   studenti che completano i percorsi;
-   docenti che riutilizzano i materiali;
-   conversione da versione gratuita a licenza istituzionale;
-   costo di supporto per istituzione;
-   ricavo medio per istituzione.

------------------------------------------------------------------------

# 15. Raccomandazione strategica conclusiva

GrazingLink dovrebbe nascere come prodotto tecnico con una modalità
didattica integrata, non come due prodotti separati.

La priorità è: 1. soddisfare la traccia con siti, date, Sole, Terra e
confronto; 2. valorizzare il differenziatore RF con diffrazione,
multipath, antenna e link budget; 3. rendere i risultati spiegabili e
accompagnati da ipotesi e incertezza; 4. vendere inizialmente studi
pilota e report a organizzazioni tecniche; 5. utilizzare la modalità
Education per diffusione, partnership e ricavi complementari.

**Modello raccomandato:** - Community gratuita per accessibilità e
acquisizione utenti; - Education con licenze istituzionali e workshop; -
Professional in abbonamento; - Mission License per studi specifici; -
Enterprise per integrazione e uso continuativo.

La componente didattica ha senso perché è coerente con la traccia e può
aumentare la diffusione del prodotto. Deve però riutilizzare il motore
esistente, avere contenuti standardizzati e un costo di supporto
controllato. Il suo contributo economico iniziale va considerato
complementare.

La vera proposta di valore di GrazingLink è rendere comprensibile e
confrontabile il rapporto fra geometria lunare, topografia e
affidabilità delle comunicazioni. Il progetto può così servire sia gli
ingegneri che devono valutare scenari sia gli educatori che vogliono
spiegare perché comunicare dalla superficie lunare è complesso.

------------------------------------------------------------------------

## Appendice A --- Assunzioni economiche

Tutte le cifre economiche del documento sono stime di pianificazione e
devono essere validate. In particolare: - prezzi e fasce di licenza sono
ipotesi commerciali; - costi del personale dipendono da localizzazione,
seniority e forma contrattuale; - costi cloud dipendono da traffico,
calcolo e storage; - il costo della validazione può aumentare
significativamente; - i ricavi Education dipendono da accesso a scuole,
università e istituzioni; - il break-even illustrato non comprende tutte
le spese aziendali e non equivale a una previsione finanziaria.

## Appendice B --- Riferimento al progetto tecnico

Questo business plan utilizza come base progettuale il documento
**"GrazingLink v3: descrizione e svolgimento del progetto"**, aggiornato
a ottobre 2026. In particolare, riprende l'architettura SPICE/LOLA, il
motore geometrico, i moduli di diffrazione e multipath, l'antenna, il
link budget, la compensazione e il piano di lavoro per l'hackathon.

Le descrizioni dei competitor e le ipotesi commerciali sono una
rielaborazione strategica e non devono essere interpretate come
benchmark certificato o ricerca di mercato quantitativa.
