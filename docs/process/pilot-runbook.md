# RAVEN: trasparenza, backup e pilota del prototipo

Stato verificato: 2026-11-08. Questo runbook riguarda il prototipo attuale, non un servizio
commerciale gia' attivo. Pagamenti e account applicativi restano fuori da questo blocco.

## Deployment scelto: Oracle Always Free e Cloudflare Tunnel

Scelta del proprietario: 2026-11-08. Configurazione in `compose.oracle.yaml` e
`deploy/oracle/nginx.conf`; non usare `compose.yaml` o `.env.example` per questa produzione.
La preparazione del repository non significa che esistano gia' VM, dominio o Tunnel attivi.
L'app resta gratuita per i visitatori e il repository puo' restare privato.

### Risorse e prerequisiti esterni

1. Creare un account Oracle Cloud Free Tier, senza upgrade automatico a pagamento. La carta
   serve alla verifica; la pre-autorizzazione non e' un canone e l'importo dipende dal fornitore.
   Scegliere con cura la home region: le risorse Always Free devono essere li'.
2. Creare una VM Ubuntu ARM con shape **VM.Standard.A1.Flex**, non A2 o una shape a pagamento:
   massimo **2 OCPU e 12 GB RAM complessivi**, entro 1500 OCPU-ore e 9000 GB-ore/mese.
   Usare solo risorse ammissibili Always Free e verificare il costo nella console.
   Non confondere il credito iniziale da 300 dollari/30 giorni con la gratuita' permanente.
3. Usare storage persistente entro **200 GB totali**, includendo i volumi di avvio e tutti
   gli altri dischi della tenancy; backup gratuiti massimo cinque, da configurare e provare.
   Il deployment funziona anche con il disco di avvio iniziale: non serve acquistare storage.
4. Per SSH e uscita Internet usare una subnet pubblica con Internet Gateway e l'indirizzo
   pubblico della VM, verificando l'ammissibilita' gratuita. Non aggiungere un NAT Gateway,
   load balancer o altri servizi a pagamento. Tunnel non richiede porte web pubbliche:
   consentire SSH solo dall'indirizzo amministrativo; lasciare chiuse 80, 443, 8000 e 8080
   sia nel firewall host sia nelle regole OCI. Consentire DNS/HTTPS e TCP/UDP 7844 in uscita.
5. Installare Docker Engine e il plugin Compose seguendo la
   [procedura ufficiale Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
   Abilitare l'avvio del daemon al boot. L'app usa Python nel container: non usare
   `install.sh`, il server di sviluppo o un ambiente Python dell'host come produzione.
6. Clonare il branch privato `hackathon/nasa-lunar` con un accesso GitHub autorizzato,
   senza token nella URL o nei file. Non rendere pubblico il repository per il deployment.
   Registrare il commit con `git rev-parse HEAD`.

Oracle puo' non avere capacita' libera e puo' recuperare istanze considerate inattive:
il piano non ha SLA gratuito. Non generare carico o traffico fittizio per aggirare questa
regola. Un upgrade a pagamento non e' una garanzia di costo zero.
Fonti: [quote Oracle](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[fine del trial](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

### Avvio privato e dati scientifici

Nella copia del repository sulla VM:

```bash
cp .env.oracle.example .env.oracle
docker compose --env-file .env.oracle -f compose.oracle.yaml config --quiet
docker compose --env-file .env.oracle -f compose.oracle.yaml build --pull app proxy
docker compose --env-file .env.oracle -f compose.oracle.yaml run --rm --no-deps app \
  python -m backend.ephemeris.fetch --check
docker compose --env-file .env.oracle -f compose.oracle.yaml run --rm --no-deps app \
  python -m backend.domain.grazing.prefetch --dry-run
docker compose --env-file .env.oracle -f compose.oracle.yaml run --rm --no-deps app \
  python -m backend.domain.grazing.prefetch
docker compose --env-file .env.oracle -f compose.oracle.yaml up -d --wait app proxy
curl --fail http://127.0.0.1:8080/health
```

Il prefetch esplicito riguarda solo i siti del catalogo coperti, circa 41 MB di tessere:
non scarica DEM globali o siti personalizzati. I kernel sono nell'immagine e verificati
contro il lock; LOLA e cache custom stanno nel volume `lola`, scrivibile dall'UID 10001.
Conservare quel volume fra aggiornamenti; **non usare `down -v` sul deployment reale**.
Richieste custom continuano a richiedere stima/consenso e rispettano i limiti scientifici
10 MB/sito, 40 MB/richiesta, 300 MB/cache. Un terreno mancante resta ignoto.

Il frontend compilato e FastAPI condividono l'origine. Il backend non pubblica porte;
solo il proxy e' raggiungibile su loopback 8080. La rete ingress `172.30.86.0/28` deve
essere libera sulla VM: se confligge con reti esistenti, cambiare insieme subnet Compose
e `set_real_ip_from` in Nginx. Il proxy riscrive X-Forwarded-For da CF-Connecting-IP,
non dagli header arbitrari del visitatore. Non esporre app/proxy direttamente a Internet
o aggiungere altri servizi non fidati alle reti di questo stack.

La root filesystem resta read-only. Il mount `:ro,Z` applica l'etichetta SELinux al solo
file Nginx di questo deployment; non disabilitare SELinux e non montare directory condivise.
Su Ubuntu senza SELinux non e' richiesta una configurazione aggiuntiva.
L'assistente e' locale estrattivo: nessuna API LLM a pagamento o scoperta automatica.
I POST di training e gli endpoint dei job del template sono bloccati esplicitamente
con 403 dal proxy pubblico; gli strumenti RAVEN non dipendono da questi endpoint.
Pipeline dati opzionale non attivata. Nessun account, pagamento o database aggiunto.

### Correzioni dell'audit di sicurezza

- **Dipendenze:** Certifi fissato a 2026.10.19 (rimozione della CA compromessa,
  [GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)).
  Il proxy viene costruito da `deploy/oracle/nginx.Dockerfile`, con base multiarch
  bloccata e aggiornamenti Alpine; la build richiede almeno Brotli 1.2.1-r0
  ([CVE-2026-111497](https://github.com/advisories/GHSA-9v8h-qqgm-4m35)).
  Il runtime Python applica gli aggiornamenti Debian prima di installare l'app.
  Dopo l'installazione rimuove pip e le sue librerie vendorizzate dal runtime:
  non installare dipendenze nei container pubblici, ricostruire invece le immagini.
  Non avviare il vecchio proxy upstream al posto della build corretta.
- **Segreti:** esclusioni Docker/Git anche nelle sottocartelle: `.env`, `.secrets`,
  configurazioni private npm/PyPI/netrc, chiavi PEM/KEY e SSH. Gli esempi `.env.example`
  e `.env.oracle.example` restano ammessi e devono contenere solo valori non segreti.
  Il test opt-in `RAVEN_TEST_DOCKER_CONTEXT=1 .venv/bin/python -m pytest -q
  tests/deployment/test_build_context.py` costruisce ed elimina un canary con soli
  segreti fittizi. Non scannerizzare/pubblicare valori reali nei log.
- **Estimatori del template:** i nomi di sessione non autorizzano l'accesso allo stato.
  `GET /api/estimators/session` emette l'header opaco `X-Estimator-Owner`; conservarlo
  in memoria e reinviarlo negli update/reset. Anche il primo update riuscito senza
  header ne emette uno. Senza header ogni richiesta e' indipendente; header falsificati
  ricevono 403. L'identita' e' una capability bearer firmata dal server, valida solo
  per quell'istanza dell'app; il riavvio invalida identita' e stato. Non registrarla
  nei log o in Git e trasmetterla solo su HTTPS fuori dal loopback di sviluppo.
  Nessun cookie aggiunto; il Planner RAVEN non usa questi endpoint.
- **Calcolo:** horizon usa lo stesso tetto delle analisi RAVEN. Richieste eccedenti
  ricevono 503 con Retry-After; `RAVEN_MAX_COMPUTE_SECONDS` (default 120) limita l'attesa
  HTTP con 504. Timeout/disconnessione NON liberano il posto finche' il thread non
  termina davvero: Python non puo' interrompere in sicurezza quel calcolo.
- **Disco:** maschere del catalogo entro 128 file/8 MB, separate dalle tessere LOLA.
  Per i siti custom, 128 maschere e quota complessiva di 300 MB incluse le tessere,
  applicata a ogni inserimento, non soltanto dopo download. Cache non scrivibile o
  quota non disponibile: calcolo valido non persistito, errore esplicito nei log;
  file parziali rimossi. La cache non sostituisce un backup.
- **Telemetria:** massimo tre stream per IP normalizzato, 429 con Retry-After
  oltre il tetto; lease di 300 secondi anche con backpressure, poi riconnessione
  tramite il client esistente. Si conserva il tetto globale di 100. IP condivisi
  (NAT) condividono questa quota; non e' autenticazione o protezione DDoS illimitata.

Prima di pubblicare: MFA/passkey su GitHub/Oracle/Cloudflare, SSH con chiave e allowlist,
nessuna porta web pubblica sulla VM, aggiornamenti host, token Tunnel con permessi
verificati e procedura di rotazione, backup/ripristino provati. Accesso al socket Docker
equivale a privilegi root: non montarlo nei container e non darlo a codice non approvato.
Le scansioni delle immagini vanno ripetute e gli advisory valutati sul software realmente
installato: gli SBOM dei plugin opzionali non provano che tutti i loro pacchetti siano
presenti. Non riutilizzare release con queste vulnerabilita' note neppure per rollback.
I controlli dell'updater restano da implementare; nessuna certificazione o verifica
del dominio/VM reale e' implicita nelle prove locali.

### Cloudflare e pubblicazione

1. Aggiungere il dominio a **Cloudflare Free**, se non e' gia' li'. Prima di cambiare
   nameserver verificare e conservare tutti i record esistenti, in particolare MX,
   SPF/DKIM/DMARC e servizi gia' attivi; non occorre trasferire il registrar.
2. In **Networking > Tunnels** creare il Tunnel stabile `raven-oracle`.
   Non usare Quick Tunnel/trycloudflare (dominio temporaneo e streaming SSE non supportato).
3. Conservare il token del connettore **sulla VM**, mai in chat, Git, report o comandi
   con token inline. Il servizio usa `--token-file`, non token in variabili Compose.
   Per inserirlo senza eco nel terminale della VM:

```bash
sudo install -d -m 700 /etc/raven
read -r -s -p 'Cloudflare Tunnel token: ' tunnel_token
printf '\n'
printf '%s' "$tunnel_token" | sudo tee /etc/raven/cloudflare-tunnel-token >/dev/null
unset tunnel_token
sudo chown 65532:65532 /etc/raven/cloudflare-tunnel-token
sudo chmod 400 /etc/raven/cloudflare-tunnel-token
```

4. Impostare in `.env.oracle` solo il percorso:
   `TUNNEL_TOKEN_FILE=/etc/raven/cloudflare-tunnel-token`.
   I secrets Compose basati su file sono bind mount: UID/GID/mode non vengono riscritti
   magicamente. L'UID 65532 deve poter leggere il file montato; l'app non riceve il token.
5. Avviare `docker compose --env-file .env.oracle -f compose.oracle.yaml up -d tunnel`
   e verificare **Healthy** nella dashboard Cloudflare.
6. Pubblicare la route concordata, per esempio `raven.<dominio>`, verso
   **`http://proxy:8080`**, non localhost e non `app:8000`: cloudflared gira in un container
   distinto e deve attraversare il proxy che normalizza l'identita' del client.
   Non sostituire record di servizi esistenti senza verifica del proprietario.
7. Non creare regole "cache everything" sulle API/stream; mantenere Pseudo IPv4 disattivato
   e non aggiungere Worker che riscrivono gli header identificativi. Nginx disabilita il
   buffering e la cache delle risposte upstream per preservare SSE.
   Abilitare il redirect HTTP verso HTTPS per il solo hostname RAVEN, senza modificare
   indiscriminatamente le impostazioni TLS dei servizi gia' presenti sul dominio.

Fonte: [creazione e route Tunnel](https://developers.cloudflare.com/tunnel/get-started/).
Non attivare componenti Cloudflare a pagamento. Le quote di traffico/risorse restano
applicabili: il rilascio non promette calcolo illimitato o disponibilita' continua garantita.

### Collaudo, aggiornamenti e limiti del rilascio

Lo smoke test opt-in controlla frontend/asset, modello/matrice correnti, dati reali,
calcolo S0-S7, streaming dell'assistente e blocco del training:

```bash
RAVEN_DEPLOY_TEST_URL=https://raven.example.org \
  .venv/bin/python -m pytest -q tests/deployment
```

Eseguirlo da una macchina con le dipendenze di test del progetto, non installando tool
di sviluppo nel container di produzione. Il test di spoofing/rate limit e' separato:
solo proxy loopback isolato, limite server 3 e `RAVEN_TEST_PROXY_RATE_LIMIT=3`,
selezionando `-k spoofed`; mai abbassare il limite del servizio pubblico per questo test.
Prima di dichiarare online verificare anche il percorso Planner nel browser, export,
consenso custom, EN/IT, TLS/DNS reali, riavvio della VM, ripristino del volume e carico
su hardware Oracle reale. La build ARM in emulazione non misura le prestazioni della VM.

Per aggiornare: registrare il commit precedente, conservare il volume, fare fast-forward
del branch approvato, ricostruire `app` e `proxy`, verificare i lock e usare
`up -d --wait app proxy`.
Il proxy aggiorna la risoluzione DNS interna quando il container app cambia.
Verificare salute, matrice e calcolo prima di annunciare l'aggiornamento. Per il rollback
ricostruire da una copia separata del commit registrato, senza cancellare dati o resettare
una worktree condivisa. Il token Tunnel e' gestito separatamente dal codice.

### Consegna continua e aggiornamento del browser (da implementare)

Il proprietario richiede che il sito online segua le nuove versioni. La procedura manuale
sopra e' documentata; **updater, timer e avviso nel browser non sono ancora implementati**.
La produzione deve seguire l'ultima versione **approvata**, non ogni commit sperimentale.

Flusso previsto:

1. Lavorare sul branch attuale `hackathon/nasa-lunar` e completare le verifiche richieste.
   La CI esistente resta il gate: regressioni e problemi di quota ancora aperti non vengono
   ignorati per pubblicare. Le evidenze scientifiche non diventano qualificazione fisica.
2. Promuovere esplicitamente il commit verificato su un branch di distribuzione dedicato
   `deploy/production` (da creare al primo rilascio). Questa promozione approva il rilascio.
   Non richiedere piani GitHub a pagamento per rendere operativo il processo.
3. Sulla VM, un servizio systemd con timer ogni 15 minuti legge quel branch tramite una
   deploy key GitHub **read-only**, limitata al solo repository privato. L'accesso e' outbound:
   niente webhook pubblico, apertura SSH ai runner GitHub o credenziali Oracle in GitHub.
   CI privata resta soggetta alle quote esistenti; niente registry/build cloud aggiuntivi.
4. Se il commit non cambia, non fare build o riavvii. Se cambia, acquisire un lock per evitare
   due deployment simultanei, preparare una directory di release separata e costruire
   l'immagine ARM mentre il servizio corrente continua a funzionare. Verificare prima
   spazio/RAM disponibili e integrita' dei kernel; mai cancellare una worktree dell'utente.
5. Collaudare il candidato su un'origine privata e solo poi sostituire l'app, con gestione
   dei calcoli/stream attivi e arresto graceful. Se non si puo' terminare in sicurezza,
   rinviare l'aggiornamento. Tunnel, hostname e volume LOLA restano stabili.
   La sostituzione su una sola VM puo' comportare una breve interruzione: niente promessa
   di zero downtime o deploy istantaneo; il tempo include timer, build e collaudo.
6. Dopo il cambio verificare salute, versione effettiva, matrice, calcolo reale e streaming.
   In caso di guasto tornare all'immagine precedente verificata, senza eliminare dati/segreti.
   Registrare comunque il deployment come fallito e il commit effettivamente attivo:
   un rollback non e' un aggiornamento riuscito. Non ritentare lo stesso commit fallito
   indefinitamente; richiedere una nuova versione o un intervento esplicito.

Versione e cache fanno parte dello stesso lavoro, non sono una conseguenza automatica
del riavvio del backend:

- Incorporare il commit di build nella stessa immagine di frontend/backend ed esporlo in
  un endpoint non cacheabile, distinto da `model_version`, che identifica il modello
  scientifico. Verificare che l'origine pubblica serva proprio la release promossa.
- HTML e informazioni di versione devono essere rivalidati/non cacheati; JS/CSS con nomi
  content-hash possono avere cache lunga. Non applicare cache CDN alle API o agli stream.
- Conservare gli asset della release attiva e delle due precedenti per la finestra di
  aggiornamento/rollback: una scheda gia' aperta puo' ancora richiedere chunk della vecchia
  build. Tenere l'immagine attiva e una precedente verificata; pulizia limitata agli artefatti
  di questo deployment, con controllo delle quote, mai prune globale di Docker o dati LOLA.
- Il browser controlla la versione al ritorno sulla scheda e periodicamente. Se cambia,
  mostra un avviso EN/IT e un pulsante di aggiornamento, senza ricaricare forzatamente.
  Salvare la bozza, attendere operazioni pendenti e rispettare i contratti di compatibilita'
  degli archivi; non presentare risultati del vecchio modello come calcolo corrente.

Interventi del proprietario: autorizzare la deploy key pubblica nelle impostazioni del
repository (la chiave privata resta sulla VM), approvare le release e definire il canale
per gli errori operativi. Io preparo updater/unit/timer, metadati, cache, UI e prove.
Modifiche a Compose/proxy/Tunnel, credenziali, formati dati o migrazioni richiedono revisione
e applicazione esplicita: il timer ordinario non deve cambiare policy o fare migrazioni
invasive. Non prevedere nuovi account applicativi, checkout o costi di hosting aggiuntivi.

Criteri di consegna: un commit approvato arriva al dominio con frontend/backend coerenti;
un commit non promosso non viene distribuito; avvisi/cache funzionano con una scheda vecchia
aperta e una bozza salvata; guasto e rollback sono riproducibili; dati/token sopravvivono
al cambio; nessuna doppia esecuzione o ciclo infinito di build; misure sul reale hardware
Oracle confermano che build e servizio rientrano nelle risorse gratuite.

I servizi ripartono con `unless-stopped`; log Docker limitati a tre file da 10 MB per
servizio. Access log Nginx/Uvicorn disabilitati, ma errori e provider possono ancora
contenere IP/dati tecnici: completare l'inventario e la retention reali, senza promettere
anonimizzazione. Prima del lancio pubblico completare i contatti/informativa effettivi
e rendere coerente la comunicazione dei Piani con accesso gratuito a tutto il prototipo,
mantenendo distinta la roadmap commerciale. Nessuna qualificazione scientifica promossa.

## Cosa va nella web app

| Dove | Implementazione | Limite dichiarato |
|---|---|---|
| `/privacy` | Flussi server/browser, assistente esterno, hosting/log, gestione dei dati e stato dell'informativa | Mancano titolare, contatto privacy e politiche effettive del deployment; non e' un'informativa legale definitiva |
| `/cookies` | Inventario localStorage/sessionStorage, cronologia attuale e compatibilita', consenso EN/IT, export/eliminazione | Consenso opzionale non cancella missioni o log; nessuna promessa di backup cloud |
| `/terms` | Uso di ricerca/formazione, evidenze, limiti, piani proposti, licenze | Non e' un contratto commerciale approvato o una garanzia operativa |
| `/contacts` | Aiuto self-service verso Learn, Model e controlli dei dati | Team segnaposto non e' assistenza o contatto del titolare; non inventare email/ticket/SLA |
| Footer e Piani | Collegamenti raggiungibili alle informazioni pertinenti | Non aggiungere accettazione contrattuale o iscrizione al pilota senza un processo reale |

Il repository del progetto e' privato: un link alle sue issue non sarebbe assistenza pubblica.
Prima di aggiungere un canale occorrono indirizzo/servizio verificati, responsabile e politica
di trattamento delle richieste. Il learning assistant non e' supporto commerciale o privacy.

## Copie dei dati: comportamento attuale

Il browser conserva la libreria delle configurazioni e fino a 8 calcoli storici, entro
2 milioni di caratteri. Non esistono database account, sincronizzazione o backup cloud.
La memoria di sessione puo' essere recuperata dal ripristino del browser; chiudere una scheda
non e' una garanzia di cancellazione. Cancellare cookie/consensi non elimina questi archivi.

Procedura utente prima di cancellare i dati del sito o cambiare dispositivo:

1. Aprire Dashboard, selezionare ciascun calcolo necessario e scaricarne il JSON.
2. Conservare anche i report necessari tramite stampa/salvataggio PDF nel browser.
3. Verificare che i file si aprano e contengano scenario/versione attesi; conservarli in uno
   spazio sotto il proprio controllo, evitando condivisioni di dati riservati.
4. Eliminare selettivamente la cronologia nella Dashboard o le configurazioni nel Planner;
   per tutte le copie locali usare le impostazioni del browser.

Questi export sono documenti di conservazione/analisi, **non** un backup completo importabile:
non e' implementato il ripristino generale di report esportati o dell'intera libreria.
Non vendere questa procedura come recupero garantito o migrazione automatica.

## Responsabilita' del gestore

Prima del pilota assegnare un responsabile per deployment, contatti/privacy, assistenza,
collaudo e incidenti. Registrare commit, versione del modello, hash del registro e build usati.
Verificare `/health` e `/api/raven/model`: la nuova matrice deve contenere le tre evidenze
Surveyor, base circolare lossless e formula ITU corrente, non solo il vecchio contenuto servito
da un processo precedente. Non riutilizzare un server di versione incerta come prova di rilascio.

Per il server attuale:

- Conservare sorgenti/versione e configurazione necessaria a ricreare il deployment; segreti
  soltanto nel sistema scelto dal gestore, protetto, mai in Git, report o ticket.
- Registrare versioni/fonti dei dati scientifici. Cache DEM/kernel non sono un backup delle
  missioni dei visitatori: si possono ricostruire secondo download, hash, consenso e limiti.
- Inventariare storage e log effettivi di host/proxy/app, accessi e retention. Non dichiarare
  IP anonimi/troncati senza averlo implementato e verificato sul deployment reale.
- Fare una prova di ricostruzione in un ambiente Linux isolato: build, avvio, salute, matrice,
  navigazione e un caso di calcolo noto. Non cancellare cache o fermare processi condivisi
  per eseguire questa prova.

Quando arrivera' il database commerciale, aggiungere backup cifrati, accessi/retention,
frequenza e obiettivi di recupero approvati, ripristino verificato e riconciliazione di
abbonamenti/diritti. Queste capacita' non esistono ancora: non assegnare valori RPO/RTO o SLA
per renderle apparentemente disponibili.

## Gate di collaudo e pilota

Verifiche del blocco UI: pagine e consenso in EN/IT, footer/Piani, percorsi `/` e `/app/`,
messaggi onesti con storage bloccato, gestione dei dati senza cancellazioni implicite,
navigazione da tastiera e vista mobile. Tipi, traduzioni, build e bundle devono passare.
Per il rilascio complessivo usare la CI e gli E2E esistenti; regressioni/quota artifact
ancora aperte non diventano risolte perche' questi test mirati sono verdi.

Prima di invitare utenti reali servono contatti e informativa completati/revisionati,
ambito non operativo accettato, dati ammessi, canale di assistenza raggiungibile,
regole di feedback, versioni tracciate e responsabile degli incidenti.
Non raccolti automaticamente in questo blocco: iscrizioni, email, feedback, pagamenti.
Non esportare scenari completi nei ticket senza controllo del contenuto.

In caso di errore: registrare pagina/versione e passi minimi, distinguere ignoto da guasto,
conservare gli export necessari e ripristinare una versione nota nel deployment gestito.
Non aumentare concorrenza, trasformare ignoti in zero o promuovere stati di validazione per
rendere verde il pilota. Un rilascio commerciale richiede inoltre tutti i gate di
`docs/design/commercial-launch-plan.md`.
