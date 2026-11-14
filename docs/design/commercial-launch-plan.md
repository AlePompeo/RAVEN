# RAVEN: piano per vendita e attivazione reali

Stato: **pianificazione richiesta, non implementazione**. Verifica del prodotto: 2026-11-08.
Nessun pagamento, account, prezzo definitivo o diritto di accesso viene attivato da questo documento.

Aggiornamento del punto 5: trasparenza tecnica EN/IT in Privacy/Cookie, condizioni del
prototipo in `/terms`, help self-service in Contatti e collegamenti footer/Piani implementati.
La procedura operativa e' in `docs/process/pilot-runbook.md`. Non sono ancora completati
informativa/contratti legali, contatti reali, backup del futuro database o apertura del pilota.

## 1. Perimetro e decisione proposta

Mantenere esattamente **Free, Premium, Enterprise** e un solo RAVEN Core Model.
Vendere servizio ospitato, persistenza, capacita' di elaborazione e supporto; non una presunta
maggiore accuratezza del modello pagato, qualificazione di volo o esclusiva sul codice Apache-2.0.
Il software resta supporto a ricerca/formazione e studi preliminari, non una certificazione di missione.
Non suggerire approvazione NASA.

MVP consigliato: Free pubblico, Premium individuale con abbonamento e account, Enterprise su
preventivo per prestazioni effettivamente disponibili. Checkout e portale cliente ospitati dal
fornitore; niente trattamento diretto dei dati di carta in RAVEN. API commerciali, SSO aziendale,
dashboard di classe, relay, installazioni dedicate e PDF server non sono prerequisiti del primo
Premium: non venderli come gia' consegnati.

Il business plan storico contiene cinque segmenti: Community ed Education individuale confluiscono
in Free; Professional in Premium; Mission License, Enterprise ed Education istituzionale in
Enterprise. Non aggiungere due nuove schede. Le sue cifre, incluso Premium a 199 euro/mese,
restano **ipotesi non approvate**, non un listino o una promessa di ricavi.

## 2. Prodotto reale contro promesse commerciali

| Ambito | Gia' disponibile nel prototipo | Gap da risolvere prima di venderlo |
|---|---|---|
| Geometria, siti/date, RF, hardware custom, Learn | Motore unico, wizard, visualizzazioni e lezioni; funzioni implementate accessibili a tutti | Definire quota/capacita' di servizio per piano, distinguendo demo pubblica da servizio autenticato; nessun paywall gia' esistente |
| Cronologia | Locale nel browser: 8 snapshot, 2 milioni di caratteri, eliminazione/esportazione | Persistenza account nel backend, sincronizzazione dispositivi, autorizzazioni e retention; non chiamare lo storico locale "cloud" |
| Report | JSON e report strutturato stampabile/salvabile in PDF dal browser | Rinominare la voce generica `pdf`: questa funzione esiste; il PDF server automatico/riproducibile e' separato e futuro |
| Pagamenti | Un URL HTTPS puo' rendere visibile un link esterno | Sessione checkout creata dal server, prezzo approvato, pagamento verificato e attivazione; il ritorno alla pagina non prova il pagamento |
| Account / licenze / misura uso | Nessun sistema commerciale di utenti, abbonamenti e diritti | Identita', database, entitlement e quote applicati nel backend, portale cliente e gestione del ciclo di vita |
| Enterprise | Preventivo come proposta, non un servizio gia' acquistabile | Contratto e capacita' reale di consegna; team, API, priorita', deployment e supporto con responsabilita'/tempi approvati |

Prima del lancio riallineare `plans.ts`, `Pricing.svelte`, testi EN/IT e documentazione:
`history`/`pdf` oggi risultano ancora "Prevista" senza distinguere locale/browser da cloud/server.
La matrice proposta dei piani non costituisce enforcement. Il comportamento gratuito attuale
non cambia durante questa pianificazione.

Catalogo MVP da approvare:

| Piano | Proposta di servizio | Condizione di disponibilita' |
|---|---|---|
| Free | Explore/Learn, scenari dimostrativi e strumenti locali gia' disponibili; quota pubblica del servizio | Preservare l'accesso attuale fino a una migrazione annunciata e verificata; nessuna cancellazione silenziosa dello storico locale |
| Premium | Account individuale, missioni/storico cloud, capacita' di calcolo approvata e supporto standard | Attivare soltanto dopo consegna di persistenza, pagamento, enforcement e assistenza; report browser gia' esistente non e' il nuovo vantaggio cloud |
| Enterprise | Servizi Premium piu' quanto esplicitamente consegnabile nel preventivo | Organizzazioni, multiutente, API o infrastruttura dedicata soltanto dopo implementazione e collaudo, oppure contratto di sviluppo chiaramente separato |

## 3. Decisioni del proprietario che bloccano il lancio

| Decisione | Output necessario | Responsabile proposto |
|---|---|---|
| Soggetto venditore e clienti ammessi | Dati legali/contact reali, paesi, B2B/B2C, responsabilita' fiscali | Proprietario con commercialista/legale |
| Fornitore e ruolo fiscale | Scegliere PSP con checkout/subscriptions oppure Merchant of Record; verificare paesi, commissioni, rimborsi, fiscalita' e portabilita' | Proprietario |
| Listino | Prezzi, valuta, IVA/visualizzazione, periodicita', rinnovo, cancellazione, eventuali trial e rimborsi | Proprietario |
| Diritti e consumo | Funzioni effettive, quote misurate, capienza cloud, retention, limiti team e politica per insoluti | Proprietario + sviluppo/operations |
| Supporto | Canale reale, chi risponde, tempi sostenibili e cosa non e' supporto operativo di missione | Proprietario |
| Dati e hosting | Regione, fornitori, trattamento delle configurazioni di missione, retention/backups e budget operativo | Proprietario + responsabile privacy/operations |

Nessuna quota, durata di conservazione, SLA o identita' legale viene inventata qui.
Le decisioni devono precedere la configurazione live del fornitore.

## 4. Architettura minima proposta

Conservare FastAPI e `/api/raven/*`; aggiungere moduli commerciali separati dagli stadi scientifici.
Per l'MVP proporre PostgreSQL e identita' OIDC gestita, evitando un nuovo sistema artigianale di
password. Confermare il fornitore identita' e i suoi accordi sul trattamento dati prima del provisioning.
Il percorso pubblico/installazione Linux resta utilizzabile senza dipendere dal servizio commerciale.

Persistenza minima: identita' interna con issuer/subject univoci, clienti del provider, abbonamenti,
entitlement, missioni/snapshot versionati, contabilita' d'uso e registro eventi webhook.
Organizzazioni/inviti/ruoli servono prima di offrire multiutente Enterprise, non come finto requisito
del Premium individuale. Migrazioni, backup e ripristino sono parte della consegna del database.

Flusso di acquisto: autenticazione -> scelta del piano -> sessione checkout creata dal backend
con prezzo whitelistato -> pagina ospitata -> verifica server/webhook -> entitlement -> pagina
account con stato esplicito. Il client non sceglie liberamente importo, price ID, identita' pagante
o diritti. L'URL HTTPS statico attuale non svolge nessuno di questi passaggi.

Webhook: verificare firma sul corpo originale e finestra temporale secondo il provider; usare
event ID univoco, elaborazione transazionale/idempotente e riconciliazione dello stato autorevole.
Gestire duplicati, retry, consegna fuori ordine e interruzione dopo una scrittura parziale.
Non concedere Premium per un redirect, una richiesta del browser o una sola sessione creata.
Le notifiche inviano al provider soltanto i dati necessari al pagamento, non gli scenari scientifici.

Enforcement server-side su salvataggio/lettura cloud, esecuzioni commerciali, export protetti
ed eventuali API/azioni amministrative. Controllare proprietario/organizzazione per ogni oggetto.
Nessun diritto affidato a localStorage, pulsanti nascosti o modello TypeScript. I diritti riguardano
il servizio ospitato: non possono impedire l'uso o self-hosting consentito dal codice open source.
Conservare limiti scientifici e download esistenti: 1500 passi, 10 MB/sito, 40 MB/richiesta,
200 MB/cache e capienza condivisa dei calcoli non si aggirano pagando. Dimensionare quote/queue
da misure, senza alzare il limite di concorrenza per nascondere 503.

Ciclo di vita: pagamento iniziale, rinnovo, insoluto, recupero pagamento, cancellazione a fine
periodo, scadenza, rimborso e contestazione. Ogni stato deve avere una politica di accesso approvata.
Per errori o webhook in ritardo mostrare attivazione in attesa/errore, non un successo fittizio.
Prevedere riconciliazione periodica, intervento amministrativo autenticato e audit senza segreti.

## 5. Fasi, dipendenze e criteri di accettazione

| Fase | Dipende da | Consegna | Criterio di uscita |
|---|---|---|---|
| P0 - Offerta e decisioni | Nessuna | Catalogo di tre piani, ambito di servizio, proprietario/fornitori, listino e politiche approvati; testi coerenti con le funzioni reali | Nessuna funzione futura presentata come disponibile; tutte le decisioni della sezione 3 assegnate |
| P1 - Identita' e persistenza | P0 | Login/logout, sessioni sicure, dati account, snapshot cloud, entitlement, migrazioni e isolamento oggetti | Due utenti non accedono ai dati reciproci; logout/revoca funzionano; snapshot vecchi/ignoti rispettano le regole del modello; ripristino database provato |
| P2 - Pagamento in ambiente test | P0, P1 | Checkout server, firma/idempotenza webhook, mapping prezzi/cliente, portale cliente | Pagamento test attiva l'utente giusto una sola volta; client manomesso, firma invalida e redirect senza pagamento non concedono diritti |
| P3 - Diritti, quote e lifecycle | P1, P2 | Enforcement backend, contabilita' d'uso, cancellazione/insoluti/rimborsi e riconciliazione | Duplicati/fuori ordine/crash sono recuperabili; quote atomiche resistono a richieste concorrenti; scadenza e rimborso seguono la politica; nessun bypass chiamando l'API direttamente |
| P4 - Legale e operazioni | P0; verifica finale dopo P3 | Privacy/condizioni, fatture/IVA e recesso secondo il caso, contatti/supporto, segreti server, monitoraggio e runbook | Revisione professionale completata; backup/ripristino, incidenti pagamento e disabilitazione nuove vendite provati; dati e log minimizzati |
| P5 - Collaudo e pilota | P3, P4 | E2E dell'intero acquisto/accesso/cancellazione e pilota limitato con utenti reali consenzienti | CI pertinente verde, flussi accessibili, attivazioni riconciliate, costi/supporto misurati; niente addebiti reali prima dell'approvazione al pilota |
| P6 - Apertura vendite | P5 + approvazione proprietario | Configurazione live server-side, prezzi verificati, monitoraggio e supporto presidiati | Primo acquisto reale, diritto, ricevuta/fattura e cancellazione verificati end-to-end; rollback commerciale praticabile senza perdere abbonamenti o dati |

P4 puo' iniziare insieme a P1/P2, ma non puo' essere dichiarata conclusa prima di verificare i
flussi effettivi. Gli arretrati CI/E2E e quota artifact sono un gate di rilascio separato:
questo piano non li corregge e non autorizza a nascondere errori o disattivare controlli.

Prima di P6 testare almeno: acquisto riuscito/annullato/fallito, ritorno prima del webhook,
pagamento riuscito con finestra chiusa, evento duplicato o fuori ordine, crash durante attivazione,
prezzo/utente manomessi, insoluto/recupero, rinnovo e cancellazione, rimborso/contestazione,
accesso incrociato fra account e saturazione quote. Includere keyboard/mobile e il significato
commerciale degli stati "in attesa"/errore. L'audit di sicurezza va fatto sul sistema implementato,
non sostituito da questo elenco.

## 6. Documenti e operazioni indispensabili

Condizioni del servizio, privacy, eventuali cookie/consensi secondo i trattamenti effettivi,
informazioni di acquisto/rinnovo/cancellazione e gestione dei diritti del cliente devono usare
dati reali e avere revisione legale/fiscale. Distinguere fornitore PSP da Merchant of Record:
non presumere che il primo assolva gli obblighi del venditore. Prevedere richiesta di export/
eliminazione account e conservazione obbligatoria dei documenti fiscali senza conservare
indefinitamente tutti gli scenari. Definire il trattamento di configurazioni di missione riservate.

Segreti del provider solo lato server nel sistema operativo/deployment: mai `VITE_*`, commit,
report o log. Separare ambienti test/live. Monitorare webhook falliti, attivazioni in attesa,
incoerenze abbonamento/diritti, errori di calcolo, quote e spesa. Runbook per rimborso, ripristino,
riconciliazione, rotazione chiavi e incidente; portale/contatti realmente raggiungibili.
Disabilitare nuove vendite non deve interrompere silenziosamente i servizi gia' acquistati.

Il nuovo audit scientifico verifica budget e formule, **non chiude la qualificazione fisica**:
conservare provenienza V/D/I, ignoti, versione/hash e limiti nei report e nel materiale commerciale.
Un pilota di ricerca puo' avere uno scope non operativo esplicitamente accettato; una promessa
operativa richiede le evidenze della sezione finale di `docs/domain/validation.md`.

## Riferimenti verificati nel repository

`frontend/src/pages/pricing/{Pricing.svelte,plans.ts,checkout.ts}`: tre piani, tabella proposta,
link HTTPS senza fulfilment. `frontend/src/pages/planner/history.ts` e
`frontend/src/pages/dashboard/Dashboard.svelte`: storico locale, non backend cloud.
`docs/process/BACKLOG.md`: report JSON/browser PDF, limiti e rinvii.
`research papers, scripts and planning/Business_Plan_Revenue_Plan.md`, sezioni 2.2 e 6.1:
ipotesi commerciali storiche, non listino approvato. `docs/domain/validation.md`:
evidenze e qualificazione scientifica.
