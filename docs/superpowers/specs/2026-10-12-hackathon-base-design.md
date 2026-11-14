# Hackathon Base — Design Spec

Data: 2026-10-12 · Stato: bozza per revisione · Licenza progetto: Apache-2.0

## 1. Scopo e successo

Base riusabile per hackathon a tema spazio (proof of concept / presentazione), su cui costruire ricerca.
Primo caso d'uso: branch `hackathon/nasa-lunar` (NASA Space Apps, confronto siti/date lunari, link budget RF, energia, mission-hours).

Criteri di successo:
- S1. Un nuovo hackathon = nuovo branch da `master` che aggiunge solo `plugins/` e `domain/`, senza modificare `core/`.
- S2. Aggiungere una simulazione in C, Python o MATLAB/Octave = una cartella plugin con manifest, senza toccare altro.
- S3. `make dev` (o `docker compose up`) avvia l'intera app in locale; lo stesso container va online dietro reverse proxy.
- S4. Funzioni minime presenti nel template: pagine multiple, grafici 2D telemetria, vista 3D, chatbot LLM, sorgenti dati spaziali.
- S5. Nessuna violazione di licenza nota; nessun cookie non essenziale per default; a11y WCAG 2.2 AA verificata in CI.
- S6. Complicabile: backend o rendering pesanti sostituibili senza cambiare il resto (vedi §7).

Non-obiettivi (YAGNI): microservizi, database relazionale obbligatorio, autenticazione utenti, multi-tenancy, mobile nativo.

## 2. Assunzioni e dati non verificabili

- Le versioni esatte di librerie (Svelte, Three.js, uPlot, CesiumJS, FastAPI) si fissano e verificano in fase di piano, non in questa spec.
- Stato licenze attuali di Redis/Valkey e condizioni d'uso di ogni API (NASA, ESA, ASI, LLM gratuite): da verificare a mano per ogni sorgente; ogni plugin dichiara `terms_url`.
- La conformità legale (GDPR/ePrivacy, Garante) qui è impostata in modo prudente a livello tecnico; non è consulenza legale.
- I "migliori plugin UI di ottobre 2026" per Claude non sono noti a priori: si cercano e verificano in fase di piano; non vengono nominati qui.

## 3. Architettura

Monolite modulare, architettura esagonale (ports & adapters). Nessun microservizio (decisione motivata: team di 2, 48 ore, costo operativo non giustificato). Via di fuga: ogni plugin è dietro una porta che non assume lo stesso processo, quindi un adapter remoto (HTTP/gRPC) sostituisce quello locale senza toccare il core (strangler).

Regola di dipendenza (verificata in CI con import-linter): `core/` non importa mai da `plugins/` né `domain/`. Le dipendenze vanno solo verso il centro.

```
backend/ (Python, FastAPI)
  core/            # porte, registry, errori, config, contratto dati
  adapters/        # in-process, subprocess (C/MATLAB/Octave), cache, http
  api/             # router REST + SSE/WebSocket
  plugins/         # una cartella per plugin, con manifest.toml
  domain/          # (solo nei branch hackathon)
frontend/ (Vite + TypeScript + Svelte 5)
  shell/           # layout, router, tema, a11y, consenso
  pages/           # un modulo per pagina, auto-registrato
  viewports/       # implementazioni di ViewportPort (Three.js di default)
  charts/          # wrapper grafici 2D (candidato uPlot)
contracts/         # JSON Schema = fonte unica; genera Pydantic e tipi TS
docs/ ops/ tests/
```

### 3.1 Porte (interfacce del core)

| Porta | Responsabilità | Implementazioni iniziali |
|---|---|---|
| `DataSource` | Recupero dati spaziali con metadati di licenza | NASA open APIs (esempio), fixture offline |
| `Simulation` | Esegue un modello: input/output tipizzati, timeout, cancellazione | Python nativo, C (subprocess/ctypes), MATLAB/Octave |
| `LLMProvider` | Chat con streaming | Provider con tier gratuito + stub locale per test |
| `TelemetryStream` | Pubblica campioni a sottoscrittori | in-memory, replay da file |
| `CachePort` | get/set con TTL | in-memory (default), Valkey/Redis opzionale |
| `ViewportPort` (frontend) | Monta una scena, riceve stato, rilascia risorse | Three.js |

### 3.2 Pattern (solo dove servono)

Plugin Registry + Factory (scoperta da `plugins/*/manifest.toml`), Strategy (LLM, solver), Adapter (linguaggi C/MATLAB), Observer (telemetria), Repository (cache dati), Dependency Injection esplicita alla composizione (`bootstrap.py`). Principi SOLID applicati come vincoli di review.

### 3.3 Manifest plugin

```toml
id = "example-sim"
kind = "simulation"            # data_source | simulation | llm | telemetry
version = "0.1.0"
entry = "python:plugin.main:Sim"   # oppure exec:./build/sim, matlab:fn
license = "Apache-2.0"
terms_url = ""                 # obbligatorio per data_source e llm
inputs_schema = "schemas/in.json"
outputs_schema = "schemas/out.json"
timeout_s = 30
```

## 4. Contratto dati

- JSON Schema in `contracts/` è la fonte unica; da esso si generano modelli Pydantic e tipi TypeScript (CI fallisce se i generati sono disallineati).
- Campo `schema_version` (semver) in ogni messaggio; unità nel nome del campo (`elevation_deg`, `power_w`, `margin_db`); tempi in UTC ISO-8601.
- Messaggio esempio (illustrativo, il dominio vero sta nei branch): `{schema_version, t_utc, site_id, sun:{az_deg, el_deg}, earth:{az_deg, el_deg}, power_w, link_margin_db}`.
- Telemetria in transito: JSON per eventi; per serie dense, buffer binari (Float64Array) con header di schema.
- Da definire nelle prime 2 ore di ogni hackathon: il contratto del dominio, scritto insieme (elettronica/informatica).

## 5. Frontend

- Svelte 5 + Vite + TypeScript; routing a pagine, ognuna un modulo registrato (`pages/*/index.ts` esporta `{path, title, load}`) con `import()` pigro.
- Pagine del template: Home, Telemetria (lista + dettaglio con grafici), Vista 3D, Chat, Simulazioni, Licenze, Privacy, Cookie, 404/500/offline.
- Moduli pesanti (3D, grafici) sono TypeScript puri dietro `ViewportPort`/wrapper grafici: nessuna dipendenza dal framework, caricati solo dove usati.
- Escalation prestazioni: rendering in Web Worker con OffscreenCanvas; implementazioni alternative (CesiumJS/deck.gl, WebGPU) dietro la stessa porta; budget di bundle in CI per i chunk iniziali.
- a11y: HTML semantico, focus gestito al cambio pagina, `prefers-reduced-motion` e `prefers-color-scheme` rispettati, alternativa testuale/tabellare ai grafici e alla vista 3D, contrasto AA, navigazione da tastiera completa.

## 6. Compliance open source e dati

- Apache-2.0 come licenza progetto; intestazioni SPDX (convenzione REUSE).
- CI: allowlist licenze (MIT, BSD, Apache-2.0, ISC, ecc.); blocco di GPL/AGPL nel codice distribuito; SBOM CycloneDX a ogni build; pagina `/licenses` generata.
- MATLAB solo come adapter opzionale; il codice di esempio gira anche con GNU Octave.
- Mappe/dati: default su fonti aperte (OpenStreetMap, NASA GIBS, Moon Trek); niente Google Earth/Maps nel default per i loro termini d'uso.
- Ogni `DataSource` e `LLMProvider` dichiara attribuzione e `terms_url`; verifica manuale registrata nel piano.

## 7. Solidità web

- Privacy: nessun cookie non essenziale e nessun tracker per default (nessun banner necessario). Modulo `consent` opzionale: categorie, registro, blocco script finché non c'è consenso. Pagine `/privacy` e `/cookies` come template con elenco reale dei trattamenti. Log senza dati personali, IP troncati. Il chatbot avvisa che il testo va a un servizio esterno.
- Sicurezza: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, CORS ristretto, rate limiting, validazione input con Pydantic, segreti solo da variabili d'ambiente, chiavi API mai nel client.
- Cache: browser (`Cache-Control`, `ETag`, asset con hash, `stale-while-revalidate`); server con `CachePort` e TTL (anche per rispettare i limiti di richiesta delle API esterne); service worker opzionale per demo offline.
- Redirect e pagine d'errore: redirect da file di configurazione, `canonical`, pagine 404/500/offline accessibili.
- Resilienza: timeout e retry con backoff verso API esterne, circuit breaker semplice, endpoint `/health`.

## 8. Branch e flusso git

- `master`: core, shell, plugin di esempio, documentazione, test, CI. Nessun dominio specifico.
- `hackathon/nasa-lunar`: da `master`; aggiunge solo `domain/` e `plugins/` (effemeridi e orizzonte, link budget, energia, mission-hours, confronto siti, eventuale ottimizzatore).
- Miglioramenti generici: su `master`, poi merge nel branch hackathon. Il core non si modifica nel branch.
- Commit convenzionali; hook locali (lint, test rapidi, licenze); GitHub Actions per CI remota.

## 9. Test e verifica requisiti

- Unit sul core; contract test eseguiti su ogni plugin (stessa suite per ogni implementazione di una porta); e2e minimi con browser headless.
- CI: lint e type-check (Ruff, mypy/pyright, eslint, svelte-check), import-linter, a11y automatizzata, controllo licenze, budget bundle, controllo sync dei contratti generati.
- Tracciabilità: requisiti numerati S1–S6 e §5–§7 mappati a test; matrice mantenuta in `docs/`.
- Diagrammi C4/UML generati dal codice quando possibile, per evitare divergenze.

## 10. Team di agenti (sobrio)

`fastapi-developer`, `frontend-developer`, `test-automator`, `accessibility-tester`, `architect-reviewer`; `security-auditor` e `license-engineer` per revisioni mirate. Nessuna installazione extra se gli agenti disponibili bastano.

## 11. Rischi

| Rischio | Mitigazione |
|---|---|
| Troppa ambizione nel template | Il piano è a fasi; ogni fase è usabile da sola |
| Dipendenze pesanti in anticipo | Caricamento pigro, budget bundle in CI |
| Termini d'uso API cambiano | `terms_url` per plugin, cache, fixture offline |
| Subprocess C/MATLAB insicuri | Timeout, percorsi allowlist, nessuna shell, input validato da schema |
| Demo online fallisce | Replay telemetria da file, service worker, video di backup |

## 12. Estensione: embedded/firmware in simulazione e sensor fusion (aggiunta 2026-10-12)

Obiettivo: poter aggiungere parti embedded e di controllo (motori, servo, sensori, antenne) e stimatori di stato senza toccare `core/`.

### 12.1 Livelli di simulazione firmware (dal più semplice al più fedele)

| Livello | Cosa | Licenza (verificata sulla pagina del repository) | Limiti dichiarati |
|---|---|---|---|
| L0 (default) | Codice di controllo C/C++ compilato **su host** contro una HAL minima (`servo`, `adc`, `uart`, `time`) con implementazione finta alimentata dai modelli di sensori/antenne. Gira come `ExecSimulation` esistente. | licenza del progetto | Non emula il chip: valida logica e temporizzazioni logiche, non timing hardware. |
| L1 | `avr8js`: CPU AVR (ATmega328p, Arduino Uno) in browser/Node. | MIT | Solo AVR, **non ESP32**; simula solo la CPU, le periferiche si scrivono a mano. |
| L2 | Fork QEMU di Espressif come processo separato lato server (`firmware` plugin con adapter subprocess). | GPL-2.0 / LGPL-2.1 | Chip ESP32 effettivamente supportati e modalità d'uso: **non verificati** (docs in `esp-toolchain-docs`); da verificare nel piano. Esecuzione come processo separato, nessun linking; parere legale non incluso. |
| L3 (opzionale) | Wokwi come strumento esterno (link o CI con token). | Servizio proprietario: piano gratuito "Community" per progetti open source, CI a pagamento (pagina prezzi) | Nessuna API di embed ufficiale trovata; condizioni d'uso non verificate. Non è una dipendenza del template. |

Renode (MIT) elenca Xtensa tra le architetture, ma il supporto a ESP32 non è confermato: da verificare prima di usarlo.

### 12.2 Nuove porte e tipi di plugin

- `kind = "firmware"`: porta `FirmwareSim` (`load(image)`, `step(dt_s, inputs) -> outputs`, `reset()`), con adapter L0 (exec), L1 (frontend worker), L2 (QEMU subprocess).
- `kind = "estimator"`: porta `Estimator` (`predict(dt_s)`, `update(measurement) -> state`), con stato e covarianza nei messaggi del contratto dati (nuovo schema `state_estimate`).
- HAL: header C minimo in `contracts/hal/` con implementazioni `host` (finta) e `target` (Arduino/ESP-IDF), per usare lo stesso codice di controllo in simulazione e su ESP32.

### 12.3 Sensor fusion

- Default: **xioTechnologies/Fusion** (libreria C per IMU, algoritmo AHRS da Madgwick, pacchetto Python `imufusion`), licenza MIT secondo la pagina del repository. Funziona come adapter exec (C) o in-process (Python).
- Filtri di Kalman (EKF/UKF) per stima di assetto/puntamento: implementazione propria minimale con NumPy in un plugin `estimator`, testata contro casi analitici; nessuna libreria aggiuntiva assunta. Librerie come `filterpy` non sono state verificate (manutenzione e licenza): non fanno parte del default.
- Da evitare per vincoli di licenza nel codice distribuito: pacchetti Madgwick GPL (es. `imu_filter_madgwick` per ROS, R `RAHRS`).
- Le formule e le ipotesi di fusione/puntamento specifiche del dominio (orizzonte lunare, antenna) restano nel branch hackathon e vanno validate da chi ha le competenze RF/controllo.

## 13. Estensione: ML, RL, deep learning e data science (aggiunta 2026-10-12)

Obiettivo: studiare e prevedere comportamenti del sistema e migliorarlo nel tempo, senza appesantire il template né mettere dipendenze pesanti nel core.

### 13.1 Principi

- **Opzionale e isolato**: i framework ML sono extra di installazione (`pip install .[ml]`, `.[rl]`, `.[dl]`) e vivono solo in plugin e adapter. `core/` non li importa mai (import-linter). Un'installazione senza extra deve continuare a funzionare e a passare i test.
- **Addestramento fuori dal processo web**: l'addestramento è un job separato (processo/subprocess con timeout e limiti di risorse), mai nel ciclo richiesta/risposta. L'API serve solo inferenza e stato dei job.
- **Auto-miglioramento a ciclo chiuso ma con cancello**: raccolta dati (telemetria e risultati di simulazione) → dataset versionato → addestramento offline → valutazione su un set di test fisso con metriche e soglie dichiarate → **promozione del modello solo se supera il cancello e dopo approvazione umana** → modello versionato con possibilità di rollback. Nessun modello cambia da solo il comportamento in esecuzione (sicurezza e riproducibilità).
- **Riproducibilità**: seed fissati, versioni delle librerie e hash del dataset registrati con ogni modello (model card minima).

### 13.2 Porte e tipi di plugin

| Porta (`kind`) | Responsabilità |
|---|---|
| `Predictor` (`model`) | `predict(features) -> prediction` con intervallo/incertezza quando disponibile; metadati del modello e versione. |
| `Trainer` (`trainer`) | `fit(dataset_ref, config) -> model_ref` come job asincrono con avanzamento e annullamento. |
| `Environment` (`environment`) | Interfaccia in stile Gymnasium (`reset`, `step(action) -> obs, reward, terminated, truncated, info`) che avvolge una `Simulation` esistente (es. servo, antenna, energia) così un agente RL si addestra sulle stesse simulazioni della demo. |
| `ModelRegistry` | Salva/carica modelli versionati, metriche e model card; adapter su file system (default) e opzionale MLflow. |

Scambio dei modelli in formato aperto (ONNX) quando possibile, per l'inferenza leggera nel backend o nel browser.

### 13.3 Framework candidati (licenze da verificare sulle fonti primarie al momento del piano; indicate qui dalla mia conoscenza, non ricontrollate)

- Data science: pandas, NumPy, SciPy, scikit-learn (licenze permissive BSD).
- Deep learning: PyTorch (BSD-3), eventuale export ONNX con ONNX Runtime (MIT).
- Reinforcement learning: Gymnasium (MIT) e Stable-Baselines3 (MIT).
- Tracciamento esperimenti e registro modelli: MLflow (Apache-2.0), opzionale.
- Il piano deve confermare versioni e licenze installate (`pip-licenses`) e bloccare in CI eventuali dipendenze con licenze fuori allowlist.

### 13.4 Frontend

Pagina "Modelli ed esperimenti": elenco modelli e versioni, metriche, stato job, confronto con il baseline e pulsante di promozione con conferma esplicita; grafici delle curve di addestramento e delle previsioni con alternativa tabellare (a11y).

### 13.5 Rischi e limiti dichiarati

Modelli addestrati su dati simulati non garantiscono prestazioni sul sistema reale (gap sim-to-real): le metriche vanno riportate come relative alla simulazione. Costo di calcolo (GPU): non assunta; tutto deve funzionare su CPU con dataset e modelli piccoli per le demo. Dati personali: nessuno previsto; se un hackathon ne introduce, vale §7.

## 14. Estensione: data engineering e big data per l'acquisizione di dati spaziali (aggiunta 2026-10-12)

Obiettivo: una pipeline vera di ingestione → coda → elaborazione → archiviazione → interrogazione, usabile con dati di telemetria e osservazione, che parte leggera (un solo processo, nessuna infrastruttura) e scala cambiando adapter, non il codice di dominio.

### 14.1 Principi

- **Leggero di default, scalabile per sostituzione**: la pipeline gira in-process con code in memoria e file locali. Per volumi maggiori si sostituiscono gli adapter (code distribuite, object storage, motori di calcolo distribuiti) dietro le stesse porte, con il pattern strangler già usato per i plugin. Non si introducono Kafka, Spark o Airflow nel template: si progettano le porte per accoglierli.
- **Dati a livelli (medallion)**: `raw` (byte/record così come arrivano, immutabili, con metadati di origine e timestamp di ricezione) → `clean` (validati contro i contratti di §4, deduplicati, unità normalizzate) → `curated` (aggregati e feature pronti per grafici e ML). Il livello `raw` permette di rielaborare tutto in caso di bug o di cambio di schema.
- **Garanzie dichiarate**: consegna *at-least-once* con elaborazione **idempotente** (chiave di deduplicazione per record), quindi effetto *effectively-once* sui livelli successivi; ordinamento garantito solo per partizione (sorgente + finestra temporale). Non si promette *exactly-once* end-to-end.
- **Backpressure e isolamento dei guasti**: code con limite, politica esplicita quando sono piene (rallenta il produttore o scarta con contatore, secondo la sorgente), *dead-letter queue* per record non validi o non elaborabili, retry con backoff, circuit breaker già previsto in §7.
- **Qualità e tracciabilità dei dati**: controlli di qualità per livello (campi obbligatori, intervalli fisici plausibili, tempi monotoni, completezza per finestra), metriche (record in/out/scartati, latenza, ritardo rispetto al tempo reale) e *lineage* minimo (da quale raw proviene ogni record curated).
- **Licenze e termini d'uso dei dati**: ogni sorgente registra licenza e `terms_url` (§6); dataset grandi hanno limiti di richiesta e di redistribuzione da rispettare e verificare.

### 14.2 Porte

| Porta | Responsabilità | Adapter iniziali |
|---|---|---|
| `IngestSource` | Produce record/pacchetti da una sorgente (polling API, file, flusso). | API HTTP con cache, lettore file/CSV, replay |
| `Queue` | `put`/`get` con limite, ack/nack, dead-letter. | in memoria (asyncio), durevole su file/SQLite |
| `Processor` | Funzione pura record → record(s) con validazione e normalizzazione. | validazione sul contratto, conversione unità |
| `Sink`/`Store` | Scrive i livelli raw/clean/curated, partizionati per sorgente e tempo, in formato colonnare. | file Parquet su disco |
| `QueryEngine` | Interroga i livelli per UI, grafici e ML. | motore SQL embedded su Parquet |
| `Scheduler` | Esegue job periodici (ingestione, compattazione, retention). | scheduler leggero in-process |

Adapter distribuiti previsti ma non nel template: stream/log distribuito, object storage S3-compatibile, motore di calcolo distribuito.

### 14.3 Formati spaziali

Il formato di ingresso è dichiarato nel manifest della sorgente. Supporto iniziale: JSON, CSV e pacchetti binari definiti da un parser a plugin (struttura a campi a larghezza fissa, in stile pacchetti CCSDS). Formati scientifici (FITS, HDF5, NetCDF, CDF) tramite plugin con librerie opzionali, caricate solo se installate.

### 14.4 Candidati tecnologici (licenze e versioni da verificare al momento del piano; indicati dalla mia conoscenza, non ricontrollati ora)

Apache Arrow/Parquet via PyArrow (Apache-2.0), DuckDB (MIT) per SQL su Parquet, Polars o pandas per l'elaborazione, Astropy per FITS e tempi astronomici (BSD), xarray per array multidimensionali, APScheduler per i job. Per la scalabilità futura: Apache Kafka (Apache-2.0); per l'object storage, **attenzione**: alcuni server S3-compatibili popolari usano licenze copyleft forti (da verificare caso per caso prima dell'adozione). Il piano deve confermare ogni licenza con `pip-licenses` e bloccare in CI quelle fuori allowlist.

### 14.5 Frontend e osservabilità

Pagina "Pipeline dati": stato per sorgente e per stadio, record al secondo, scarti e dead-letter, ritardo, ultimo dato ricevuto, con avvisi quando una sorgente tace oltre una soglia. Endpoint `/api/pipeline/metrics` (formato JSON e, opzionale, testo Prometheus). Alternative tabellari ai grafici (a11y).

### 14.6 Rischi e limiti dichiarati

Throughput reale sulla macchina dell'utente non misurato: il piano prevede un benchmark con soglie dichiarate dopo la misura, non assunte ora. Un solo nodo non offre alta disponibilità: nessuna promessa di durabilità oltre il disco locale. Orologi non sincronizzati tra sorgenti: i timestamp di origine e di ricezione sono entrambi conservati.

## 15. Estensione: reti TCP/UDP e protocolli di comunicazione satellitare e spaziale (aggiunta 2026-10-12)

Obiettivo: ricevere, inviare e simulare traffico di telemetria/telecomando su reti reali e su canali simulati, con i protocolli usati nelle missioni, senza far entrare nel core né socket né dettagli di protocollo.

### 15.1 Principi

- **Il browser non apre socket TCP/UDP grezzi**: la rete vive nel backend (gateway). Il frontend riceve i dati già decodificati via REST/SSE/WebSocket (§3). Nessun accesso a socket dal client.
- **Separazione a livelli**, ciascuno sostituibile dietro una porta: `Transport` (byte da/verso la rete) → `Framer` (delimitazione dei messaggi nel flusso) → `ProtocolCodec` (codifica/decodifica del protocollo) → `Processor`/`Queue` della pipeline dati di §14. Il core conosce solo le porte.
- **Default sicuro**: nessun server in ascolto all'avvio; ogni listener è dichiarato nella configurazione con indirizzo di bind esplicito (default solo `127.0.0.1`), porta, dimensione massima dei messaggi, timeout, limite di connessioni e di velocità. Nessun socket raw né modalità promiscua nel template.
- **Tutto ciò che arriva dalla rete è non fidato**: i parser sono scritti difensivamente (lunghezze controllate prima di leggere, nessuna allocazione proporzionale a un campo non validato, errori mai fatali per il processo) e testati con fuzzing e pacchetti malformati.
- **Nessuna trasmissione radio reale**: il template non pilota radio. Qualunque uso con hardware RF richiede verifica delle norme e delle licenze applicabili (per esempio licenza radioamatoriale per le bande amatoriali) ed è responsabilità dell'utente, fuori dal template.

### 15.2 Porte e adapter

| Porta | Responsabilità | Adapter iniziali |
|---|---|---|
| `Transport` | Connessione/endpoint: `send`, `receive` asincroni, chiusura, metadati del peer. | TCP client/server, UDP unicast e multicast, loopback in memoria per i test |
| `Framer` | Dal flusso di byte ai messaggi e viceversa. | lunghezza con prefisso, delimitatore, SLIP/KISS, lunghezza dal campo d'intestazione del protocollo |
| `ProtocolCodec` | Codifica/decodifica con validazione e tipi forti. | Space Packet (CCSDS), CSP, AX.25, framing KISS, MQTT |
| `Channel` | Canale simulato tra due endpoint con parametri dichiarati: ritardo di propagazione, jitter, perdita di pacchetti, errori sui bit, banda limitata, finestre di visibilità (contatti) ed effetto Doppler se richiesto. | modello semplice configurabile, collegabile al link budget del dominio |

### 15.3 Protocolli candidati (da verificare sugli standard ufficiali al momento del piano; elencati dalla mia conoscenza)

- **CCSDS**: Space Packet Protocol (pacchetti con APID), TM/TC Space Data Link Protocol e AOS (frame con campi di controllo e CRC), CFDP per il trasferimento file, Proximity-1 per i collegamenti tra veicoli vicini. I Libri Blu sono pubblici sul sito CCSDS; la versione e le opzioni da implementare si fissano nel piano.
- **CSP (CubeSat Space Protocol)** e **AX.25** con **KISS** per piccoli satelliti e amatoriali.
- **DTN**: Bundle Protocol e LTP per collegamenti con ritardi e interruzioni lunghi, in forma di modello semplificato (store-and-forward con code e contatti pianificati); implementazioni complete esistenti da valutare separatamente, con licenza da verificare.
- **Reti IP generali**: TCP (flusso affidabile), UDP (datagrammi, multicast per distribuzione di telemetria), MQTT per pub/sub leggero.
- Il piano non assume librerie di terze parti per i codec CCSDS/CSP/AX.25: si scrivono con `struct`/`int.from_bytes` e test su vettori noti; librerie esterne si valutano dopo, con licenza verificata.

### 15.4 Integrazione con il resto del sistema

I messaggi decodificati diventano record validati contro i contratti di §4 ed entrano nella pipeline di §14 (coda, dead-letter, livelli raw/clean/curated). Il `Channel` simulato permette di provare ricezione, perdita e ritardi in demo senza hardware, e di alimentare il modello di link budget e il controllo di puntamento del dominio. Le metriche di rete (pacchetti, errori di CRC, perdite, ritardo, ultimo contatto) compaiono nella pagina "Pipeline dati".

### 15.5 Rischi e limiti dichiarati

Un listener in ascolto amplia la superficie d'attacco: da qui i default chiusi e i limiti. UDP non garantisce consegna né ordine: i codec devono tollerare perdite, duplicati e riordino; l'affidabilità si costruisce sopra (numeri di sequenza, ack) solo dove serve. Il canale simulato è un modello semplificato e non sostituisce una verifica sul collegamento reale. La conformità completa agli standard CCSDS non è un obiettivo del template: si implementa il sottoinsieme necessario e lo si dichiara.

### 13.6 Deviazione registrata in esecuzione (2026-10-13)

L'`Environment` di esempio (`env-servo`) usa un modello Python puro del servo (`ServoPlant`) e **non** avvolge una `Simulation` in C per passo, come indicato in §13.2. Motivo: un processo `exec` a episodio chiuso (come `servo_ctrl_c`, con il proprio PI interno) non è un processo decisionale a passi e un'esecuzione per passo sarebbe troppo lenta. L'adattatore generico `SimulationEnv` resta pensato per simulazioni che espongono lo stato passo-passo. Il confronto numerico tra il modello Python e il binario C non è stato fatto: è un lavoro aperto.
