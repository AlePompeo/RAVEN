# Pipeline dati (spec 14, Task 18 passi 1-5 e 7)

Pipeline in-process: sorgente -> coda -> processor -> store a livelli (Parquet) -> query (DuckDB),
con scheduler e metriche. Gira senza infrastruttura; le librerie dati sono nell'extra `[data]`
(`pip install -e ".[data]"`). **Senza l'extra l'app parte comunque** (test in
`tests/backend/pipeline/test_ports.py`): `backend.core` e `backend.api` non importano pyarrow/duckdb.
Per attivarla: variabile d'ambiente `PIPELINE_DIR` (directory dello store). Senza, `GET
/api/pipeline/metrics` risponde `{"enabled": false}` e le query rispondono 503.

## Garanzie

- **Consegna at-least-once**: un messaggio ritirato (`get`) e non confermato (`ack`) torna in coda
  dopo `visibility_timeout_s` (anche dopo un crash, con `DurableQueue`); dopo `max_attempts`
  consegne va in dead-letter con un motivo. Un `ack`/`nack` con lease scaduto e riconsegnato
  ritorna `False`: nessun doppio ack.
- **Elaborazione idempotente => effectively-once su `clean`**: chiave di dedup
  `(source_id, site_id, t_utc)`. Lo stesso record due volte, nello stesso batch, in batch diversi o
  dopo un riavvio (le chiavi della partizione si rileggono dallo store), produce una sola riga in
  `clean`. La compattazione deduplica ancora per chiave e, come la pipeline, tiene il primo ricevuto.
  La chiave e' *transazionale*: ammessa provvisoriamente, confermata solo dopo la scrittura Parquet
  durevole del suo file e rilasciata su qualunque altra uscita (errore, scrittura parziale su piu'
  giorni, interruzione): un retry di un record non scritto non e' mai un falso duplicato.
  **Non** si promette exactly-once end-to-end: `raw` e' il registro di cio' che e' arrivato e puo'
  contenere un record piu' volte (riconsegna dopo un crash fra scrittura e ack).
- **Ordinamento solo per partizione** (sorgente + giorno UTC del dato). L'arrivo fuori ordine e'
  accettato: il record finisce nella partizione della propria data, i file `clean` sono ordinati
  per `t_utc`, e il fatto e' contato in `out_of_order`. Nessuna garanzia di ordine tra sorgenti o
  tra giorni, ne' di consegna in ordine dalla coda dopo nack/riconsegna.
- **Backpressure**: coda con limite; politica `block` (il produttore attende, con timeout
  opzionale) o `drop_with_counter` (scarta e conta in `dropped`).
- **Scritture atomiche**: file temporaneo `.tmp-*` nella stessa directory, `fsync`, `os.replace`,
  `fsync` della directory. I lettori vedono solo `part-*.parquet`, mai un file parziale.
  La compattazione pubblica il file unito (che elenca in `hb_replaces` i file sostituiti) e solo
  dopo cancella i sorgenti: i file sostituiti sono nascosti, quindi nessun doppione nemmeno se il
  processo muore a meta' (la pulizia riprende alla compattazione successiva).

## Layout dei dati

```
<PIPELINE_DIR>/{raw,clean,curated}/source=<id>/date=YYYY-MM-DD/part-*.parquet
<PIPELINE_DIR>/.meta/query.duckdb      database vuoto, aperto solo in sola lettura dalle query
```

| Livello | Contenuto | Data di partizione |
|---|---|---|
| `raw` | messaggio come arrivato (`payload_json`), `received_utc`; immutabile | giorno di ricezione |
| `clean` | record validato sul contratto `telemetry`, unita'/tempi normalizzati (UTC), dedup, `raw_file_id` | giorno di `t_utc` |
| `curated` | aggregati orari per sito (n, media/min/max di `power_w`) con `raw_file_ids` (lineage) | giorno dell'ora |

`curated` ha un solo file deterministico per partizione (`part-agg.parquet`) sostituito
atomicamente a ogni ricostruzione. La retention (per livello, in giorni, sulla data di partizione)
cancella intere partizioni: tenere `raw` almeno quanto `curated` se si vuole il lineage risolvibile.
Valori predefiniti del servizio: raw 365, clean 365, curated 365 giorni. Il servizio **rifiuta**
all'avvio una retention `raw < curated` (`allow_lineage_loss=True` per accettarla) e `apply_retention`
non cancella le partizioni raw ancora referenziate dal lineage dei curated rimasti (anche dopo la
compattazione: `resolve_raw_ids` risolve gli id originali tramite `hb_replaces`), salvo `force=True`;
le partizioni saltate sono in `store.retention_skipped`.

## Validazione e unita'

Il `TelemetryProcessor` valida con il modello Pydantic generato da `contracts/telemetry.schema.json`
(`backend/contracts_models.py`, modalita' strict). Normalizza: tempi con offset -> UTC, epoch numerico
-> UTC, `power_kw` -> `power_w`, `az_rad`/`el_rad` -> `_deg`. Un record scartato porta un motivo
`<codice>[:<campo>]` (campo ripulito): `not_an_object`, `invalid_source_id`, `invalid_received_utc`,
`non_finite_value`, `invalid_timestamp`, `naive_timestamp`, `conflicting_units`, `unknown_field`,
`missing_field`, `schema_violation`. NaN/inf (anche come testo `"nan"`, `"inf"`, che e' come
arrivano da CSV/JSON stretto) vanno in dead-letter, mai in `clean`. La versione maggiore di
`schema_version` **non** viene confrontata: il contratto ne verifica solo il formato semver.

## Interrogazione

`GET /api/pipeline/query/{name}`: solo `latest_samples`, `power_hourly`, `stale_sources`
(`backend/pipeline/query_spec.py`). Il client sceglie il nome e fornisce parametri validati (regex
per `site_id`/`source_id`, `limit` 1..1000, parametri sconosciuti o ripetuti rifiutati con 422).
Il testo SQL e' costante in `query.py`; i valori sono parametri legati. Connessione DuckDB 1.5.6:
database aperto `read_only=True`, `allowed_paths` = i soli file Parquet elencati dallo store,
`enable_external_access=false`, `lock_configuration=true`, `memory_limit` e `threads` limitati,
estensioni non caricabili/installabili. Un `site_id` che non rispetta la regex
(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`) non e' interrogabile (anche se il contratto accetta
qualunque stringa non vuota).

## Metriche e stato `stale`

`GET /api/pipeline/metrics` (JSON): per livello `in/out/dropped/dead_letter`; per sorgente
`status` (`ok` | `stale` | `no_data`), `last_seen_utc`, `lag_s`, `data_lag_s`, contatori
(`out_of_order`, `ingest_dropped`, `store_errors`); controlli di qualita' per livello
(`required_fields`, `finite_values`, `not_in_future`, `non_empty_payload`, `n_positive`,
`min_le_mean_le_max`: conteggi superati/falliti, non scartano righe); coda; stato dei job. Una
sorgente silenziosa oltre `stale_after_s` (default 300, per sorgente configurabile) e' `stale`;
registrata e mai vista e' `no_data` fino alla soglia. L'orologio e' iniettabile nei test.

## Scheduler

`AsyncScheduler`: job `drain`, `curate`, `compaction`, `retention` e `ingest:<sorgente>`, con
timeout per job (il job viene cancellato), non sovrapposizione (giro saltato e contato in
`skipped`), isolamento dei guasti (si conserva solo il nome del tipo di errore). Lo scheduler
parte e si ferma con il ciclo di vita dell'app.

## Thread, backoff e arresto

La parte bloccante (batch di validazione/scrittura, SQLite, compattazione, retention, curated) gira
nell'executor del servizio (`ThreadPoolExecutor`, 4 thread), mai sul loop; `GET /api/pipeline/*`
usa `to_thread`. **Un thread non si puo' uccidere**: allo scadere del timeout del job l'attesa
asyncio viene cancellata e al thread arriva un flag cooperativo (`should_stop`), controllato fra
una partizione e l'altra; un batch di drain gia' avviato termina (al massimo `batch_size` messaggi)
e un secondo batch non parte in parallelo (lock). Un batch interrotto a meta' viene riconsegnato
(idempotente). `PipelineService.aclose()` ferma scheduler e job, attende i thread e chiude coda ed
executor.

Guasti d'infrastruttura (scrittura che fallisce con `OSError`...) fanno `nack(count_attempt=False,
delay_s=backoff)`: il messaggio non consuma tentativi e non finisce in dead-letter per colpa del
disco. Backoff esponenziale `base * 2^n` con tetto e jitter (`0.5 + 0.5 * random`), azzerato al
primo batch senza guasti; durante il backoff `drain_once` non tocca la coda. Un messaggio
veleno (processor che solleva, riga che lo store rifiuta con `StoreError`) consuma tentativi e dopo
`max_attempts` va in dead-letter con motivo `max_attempts:<causa>`; i vicini non ne risentono (le
righe di un gruppo si riscrivono una per una per isolare la velenosa). Un guasto infrastrutturale
*persistente* non uccide i messaggi ma li lascia in coda: va visto in `store_errors` e nello stato
del job `drain`.

## Scrittore unico

Compattazione e retention prendono un `fcntl.flock` non bloccante per livello
(`<PIPELINE_DIR>/.locks/<livello>.lock`), valido fra thread e processi: se e' occupato il giro viene
saltato (nessun doppione, nessuna perdita con due compattatori in processi diversi). Solo
Linux/macOS. I file corrotti (footer illeggibile) vengono rinominati `*.corrupt` (fuori dal glob dei
lettori), registrati in `store.quarantined` e nel log; letture e query proseguono sui file sani.
I `*.corrupt` non vengono cancellati automaticamente.

## Classificazione degli errori (round 2)

- `OSError` (ENOSPC, EIO, EMFILE...) e `LayerBusy` = guasto d'infrastruttura: retry senza consumare
  tentativi, con backoff, **al massimo `PIPELINE_MAX_INFRA_RETRIES` consegne** (default 20) per
  messaggio; poi dead-letter `infra_retry_exhausted`, contatore `infra_retry_exhausted` e log
  `ALLARME`.
- Qualunque altra eccezione di scrittura (`StoreError`, `ArrowNotImplementedError`, `TypeError`,
  `ValueError`...) su un gruppo fa riscrivere le righe una per una; sulla riga singola e' veleno:
  dead-letter subito con motivo `store_rejected:<TipoEccezione>`; i vicini sani sono scritti e il
  backoff globale non scatta.
- Un'eccezione inattesa nel batch (bug) non e' trattata come interruzione: il batch viene bisecato
  fino al messaggio colpevole, che consuma un tentativo, ha un ritardo proprio e va in dead-letter
  con `max_attempts:internal_error:<Tipo>` (mai il payload nel log). Solo cancellazione/interruzione
  vera (`CancelledError`, `KeyboardInterrupt`) rilascia i messaggi senza consumare tentativi.
- Quarantena (`*.corrupt`) solo per corruzione Parquet *verificata* (`pyarrow.ArrowInvalid`
  rileggendo il file); mai per `OSError` ne' per errori DuckDB generici (binder, memoria, I/O): la
  query ripete la verifica file per file e mette da parte solo quelli confermati invalidi. Il file
  non e' mai cancellato; se era l'unico della partizione il log e' CRITICAL. Limite: un file con
  footer valido ma pagine interne corrotte non viene rilevato dalla verifica del footer.

## Round 3: breaker, idempotenza interna, cancellazione

- **Quarantena confermata**: prima di rinominare un file in `*.corrupt` si verifica che il footer sia
  illeggibile oppure che una lettura completa del singolo file fallisca. Un `ArrowInvalid` dovuto a
  colonne/schema richiesti su un file sano e' uno `StoreError` ("colonne o schema non conformi"), mai
  una quarantena. Il controllo "unica copia" (CRITICAL) si fa dopo la rinomina, con il lock del
  livello, contando solo i file visibili (esclusi quelli nascosti da una compattazione).
- **Classificazione**: anche `MemoryError` e `LockOrderError` sono guasti d'infrastruttura. **Circuit
  breaker** (`PIPELINE_POISON_BREAKER`, default 50): dopo N dead-letter `store_rejected` consecutivi
  *senza alcuna scrittura riuscita* il drain va in `breaker_open` (log `ALLARME`, `status()` e
  `snapshot()["drain"]`), i messaggi restanti sono rilasciati (non persi); dopo il backoff
  (30 s x 2^k con tetto 600 s) passa a `half_open` e fa una sonda da 5 messaggi: se lo store e'
  ancora rotto riapre senza nuovi dead-letter, se scrive il breaker si chiude. Un batch con
  scritture riuscite dimostra che i veleni sono veri e non fa scattare il breaker.
- **Idempotenza interna**: per ogni messaggio (id di coda + hash del payload) si ricorda cosa e'
  gia' su disco (`_done_raw`, `_done_clean`, LRU da 100k): bisezioni, riconsegne dopo cancellazione e
  retry non riscrivono `raw` e non contano due volte le metriche. La memoria e' per processo: dopo un
  riavvio una riconsegna puo' ancora duplicare `raw` (clean resta corretto).
- **Cancellazione**: `task.cancel()` su `drain_once` alza un flag cooperativo; il thread controlla
  il flag prima di ogni scrittura (`BatchInterrupted`), `drain_once` lo attende e poi rilascia i
  messaggi senza consumare tentativi (o applica gli esiti se il thread aveva gia' finito).

## Round 4: liveness del breaker, scritture parziali, doppia cancellazione

- **Canarino di salute**: in `half_open` il drain scrive una riga nota-buona sullo stesso percorso
  dello store (`clean`, sorgente riservata `canary-healthcheck`, cancellata subito, invisibile ai
  lettori, rifiutata dal processor come `source_id`). Se riesce, i messaggi cattivi lo sono davvero:
  il breaker si chiude e il batch e' normale, ma al massimo N (`PIPELINE_POISON_BREAKER`)
  dead-letter `store_rejected` per intervallo, poi riapre. Se fallisce (store rotto in generale) la
  sonda e' di 5 messaggi, i veleni sono rilasciati e il breaker riapre con backoff esponenziale:
  nessun dead-letter nuovo. Un blocco di veleni in testa alla coda viene quindi smaltito a N per
  intervallo senza bloccare i messaggi sani dietro di lui. Ogni messaggio e' contato una volta sola
  perche' conta solo quando va davvero in dead-letter (i rilasciati non contano).
- **Scritture parziali**: ogni scrittura durevole (file di gruppo o riga) registra subito `_done_raw`,
  la conferma della chiave di dedup, `_done_clean` e le metriche. Un'interruzione dopo k righe su n
  non perde traccia delle k scritte: la riconsegna riscrive solo le n-k restanti.
- **Doppia cancellazione**: dopo il primo `cancel()` il drain alza il flag e attende il thread
  anche se arrivano altre `cancel()`; rilascia i messaggi solo a thread concluso, oppure dopo
  `PIPELINE_SHUTDOWN_WAIT_S` (default 30 s) con ALLARME (in quel caso una scrittura tardiva e'
  possibile, ma idempotente per chiave).

## Round 5: backoff del breaker e canarino

- Il successo del canarino azzera anche il *livello* di backoff: ogni ciclo attende al massimo
  l'intervallo base (30 s), quindi N veleni per intervallo non diventano minuti di attesa per i
  messaggi sani. Un blocco di 80 veleni con N=5 e' smaltito in 16 cicli; il test avanza il tempo
  virtuale di soli 31 s per giro e verifica che tutto sia scritto entro 20 giri.
- La sonda non gira a coda vuota (niente canarino a ogni tick), e i residui del canarino lasciati da
  un crash si cancellano all'apertura dello store.
- Il canarino **non** prende il lock del livello `clean`: scrive solo nella sorgente riservata, che
  compattazione, retention e lettori ignorano (`_partition_dirs`), quindi non interagisce con
  loro; prendere il lock lo farebbe fallire (e dichiarare lo store malato) ogni volta che una
  compattazione e' in corso.

## Ordine dei lock

`curated -> clean -> raw` (`store.LOCK_ORDER`; `LockOrderError` se violato). `build_curated` prende il
lock `curated` (`LayerBusy` se occupato: la partizione resta "dirty" e si riprova); la retention del
`raw` prende `curated` poi `raw`, cosi' una ricostruzione in corso non puo' referenziare file che
stanno per essere cancellati; compattazione e retention degli altri livelli prendono un solo lock.
I lettori non prendono lock. Il lineage `clean.raw_file_id` verso un raw gia' scaduto per retention
resta pendente (retention raw piu' corta di clean: configurazione da evitare).

## Coda: limiti e orologi

Payload massimo 64 KiB per messaggio (`PayloadTooLarge`, contato in `ingest_oversize`). I lease di
`MemoryQueue` usano `time.monotonic`; quelli di `DurableQueue` usano epoca-all'apertura + tempo
monotono (immune ai salti dell'orologio di sistema nel processo, confrontabile fra processi entro la
sincronia dell'orologio all'apertura). `PIPELINE_QUEUE=durable` crea il file in
`<PIPELINE_DIR>/queue/`, con `base_dir` obbligatoria (confinamento reale). Query DuckDB concorrenti:
al massimo `PIPELINE_MAX_QUERIES` (default 4), oltre 503 con `Retry-After`; estensioni DuckDB
(anche community) disabilitate.

## Plugin `ingest-csv` (termini d'uso)

`backend/plugins/ingest_csv` e' una `IngestSource` (kind `data_source`) che legge un CSV locale
(`INGEST_CSV_PATH`, sito predefinito `INGEST_CSV_SITE_ID`) con le colonne del contratto. Non
contatta servizi esterni. La lettura e' incrementale: a ogni poll emette solo le righe complete
aggiunte dall'ultimo (offset in byte + `size`/`mtime_ns` + hash di testa e coda del prefisso
consumato; file troncato o riscritto -> riletto da capo; `reset()` forza la rilettura). Lo stato
si registra ogni 1000 righe e a fine poll (l'hash costa fino a ~68 KB: O(blocchi), non O(righe)); un
consumatore interrotto si vede riconsegnare al massimo un blocco (la dedup lo scarta). Lo stato
e' in memoria: dopo un riavvio il file si rilegge tutto (la dedup tiene `clean` corretto, `raw`
riceve il file una volta in piu'). Celle CSV con newline fra virgolette non supportate. Licenza e condizioni d'uso dei dati nel file restano quelle della loro
origine: chi lo carica e' responsabile di verificarle e di non inserire dati personali. Il codice
e' Apache-2.0.

## Cosa NON e' verificato

- **Prestazioni**: nessun benchmark (passo 9 non eseguito); nessuna soglia di throughput/latenza e'
  dichiarata.
- **Durabilita'**: `DurableQueue` usa SQLite WAL con `synchronous=NORMAL`: sopravvive al crash del
  processo, non e' garantito contro la perdita di corrente dell'ultimo commit. Un solo nodo, nessuna
  alta disponibilita'. Nessun test su filesystem di rete.
- **Non supportato**: piu' processi *scrittori di ingestione* sulla stessa `PIPELINE_DIR` (dedup per
  processo). Lo stato CSV e' in memoria: dopo un riavvio il file si rilegge e `raw` lo riceve una
  volta in piu'.
- Concorrenza testata con task asyncio, thread, due istanze sulla stessa coda e due compattatori in
  processi separati. **Non** testata: piu' processi *di ingestione* sulla stessa `PIPELINE_DIR`
  (il Deduplicator e' per processo: due scrittori `clean` concorrenti possono duplicare chiavi, che la
  compattazione poi deduplica); `flock` non e' affidabile su filesystem di rete.
- Una query lunga non e' interrompibile (solo tetto di righe, memoria e thread); la lettura di molti
  file piccoli senza compattazione rallenta le query.
- `COPY ... TO` verso un file Parquet gia' elencato non e' bloccato dal motore: la difesa e' il testo
  SQL costante e non influenzabile dal client, non un permesso negato dal database.
- Orologi non sincronizzati fra sorgenti: si conservano sia `t_utc` sia `received_utc`, ma non si
  corregge lo sfasamento.
- Non inclusi: sorgenti HTTP esterne e parser di pacchetti binari (passo 6), pagina frontend (passo 8),
  benchmark (passo 9), protocolli di rete.
- Raw puo' contenere duplicati dopo un retry; i curated sono ricostruiti per intera partizione (costo
  proporzionale alla partizione `clean`).
