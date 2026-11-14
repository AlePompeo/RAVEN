# ML e data science (spec §13, Task 17)

Stato: porte, registro modelli, esempio scikit-learn, job di addestramento, ambiente RL, esempio
deep learning (ONNX) implementati e provati. NON implementati: pagina frontend "Modelli ed
esperimenti", endpoint `GET /api/models`, CLI di promozione.

## Ciclo chiuso con promozione umana

```
telemetria/simulazione --> dataset sintetico (seme, sha256) --> POST /api/train
   --> subprocess (trainer) --> candidato ONNX + model_card.json (status = candidate)
   --> valutazione sul test set FISSO, contro baseline (media e regressione lineare)
   --> promozione: metriche >= soglia della card  E  approvazione umana esplicita
   --> modello promosso (stack di promozioni) --> rollback alla versione promossa precedente
```

Nessun modello cambia da solo il comportamento in esecuzione: il trainer salva solo candidati;
`promote(version, approver=..., approved=True)` richiede il flag esplicito e un nome di
approvatore, e rifiuta se una qualsiasi metrica in `threshold` manca o e' sotto soglia. L'API
HTTP NON espone la promozione, per scelta di sicurezza (decisione del controllore, che sostituisce il
pulsante di promozione della spec §13.4): la promozione passa dall'API Python del registro; una CLI
dedicata e una pagina di sola lettura sono lavoro aperto.
La soglia scritta nella card dal trainer di esempio e' `max(0.25, skill del modello promosso)`:
una regressione rispetto al promosso non passa il cancello.

## Porte e isolamento

`Predictor` (kind `model`), `Trainer` (`trainer`), `ModelRegistry` in `backend/core/ports.py`;
il manifest accetta anche `environment` (porta `Environment` non ancora definita).
`.importlinter` vieta a `backend.core` di importare torch, sklearn, gymnasium,
stable_baselines3, pandas, numpy, scipy, onnx, onnxruntime, skl2onnx, joblib. Test: app e test
`core` passano con questi moduli bloccati (`tests/backend/core/test_ml_ports.py`). I plugin
importano le librerie ML in modo pigro: senza `.[ml]` si caricano ma non predicono.

## Registro modelli (`backend/ml/registry.py`)

Directory `MODEL_REGISTRY_DIR` (default `build/models`), una cartella `vNNNN` per versione con
`model.bin` e `model_card.json` (versione, seed, `dataset_sha256`, versioni delle librerie,
metriche, soglia, `model_sha256`, `created_utc`, `status` = candidate|promoted|rolled_back) e un
file `promotions.json` (pila delle promozioni). Scritture atomiche (file temporaneo + rename),
id di versione validati da regex (nessun percorso), link simbolici e file oltre i tetti rifiutati.

**Scelta sul formato (rischio documentato).** Il registro non usa mai pickle: salva byte opachi.
I modelli scikit-learn sono esportati in **ONNX** (skl2onnx, Apache-2.0; onnx Apache-2.0;
onnxruntime MIT) e letti da onnxruntime: ONNX e' un formato dati, non codice. Se in futuro si
usasse joblib/pickle, l'unica difesa sarebbe lo sha256 nella card verificato prima del
caricamento, che protegge da corruzione e da sostituzione del solo `model.bin`, NON da chi
puo' scrivere anche la card: la directory del registro e' una frontiera di fiducia e deve essere
scrivibile solo dal servizio. Un solo processo scrittore (lock di thread), non multi-nodo.

## Esempio `predictor_baseline`

Dati sintetici: `link_margin_db = 40 + 10 log10(power_w) - 20 log10(distance_km/1000) + rumore
(0.5 dB)`, generati da seme (origine: generati, licenza Apache-2.0; nessun dato esterno).
Test set fisso (500 campioni, seme 20261012). Modello: GradientBoosting esportato in ONNX,
valutato sull'artefatto ONNX servito. Baseline: media e regressione lineare (conta il migliore).
Margine dichiarato: `skill = 1 - MSE_modello / MSE_baseline >= 0.25`. Misurato (seed 1,
2000 campioni): RMSE modello 0.574 dB, baseline lineare 1.289 dB, media 4.554 dB, skill 0.80.

## Job di addestramento (`backend/ml/runner.py`, `backend/api/ml_routes.py`)

`POST /api/train {trainer, config}` (202; config: massimo 32 chiavi, valori scalari, stringhe
<= 256), `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`. Stati `queued/running/done/failed/
cancelled`. Il trainer gira in un subprocess (`python -I -c <boot> ...`, nessuna shell, nuova
sessione, ambiente minimo senza segreti ereditati), con timeout (`timeout_s` del manifest),
`RLIMIT_AS` (default 4 GiB; solo Unix), tetto di 64 KiB su stdout, metriche non finite o non
numeriche rifiutate, al massimo 2 job in esecuzione e 4 attivi (oltre: 429 + `Retry-After`),
storico limitato a 100 job terminati. Errori verso il client solo come codici generici
(`timeout`, `failed`, `invalid_output`, `output_too_large`, `cancelled`); lo stderr del figlio
resta nei log del server. Gli id dei job sono 32 caratteri esadecimali casuali; altri -> 404.
Lo `status` dei job e' in memoria: un riavvio del server perde la cronologia (i modelli salvati
restano nel registro).

Il worker usa `-I -c` e non `-m` perche' `-I` toglie la cartella corrente da `sys.path` e il
pacchetto `backend` potrebbe non essere installato.

## Indurimento (fix round 1)

- **Abuso anonimo**: `POST /api/train` ha un limite per IP client di `ML_TRAIN_PER_HOUR` (default
  20, intero > 0 validato all'avvio; chiave = IP del peer, `X-Forwarded-For` solo con
  `TRUSTED_PROXY=1`, come il rate limiter globale). Il registro tiene al massimo
  `ML_MAX_CANDIDATES` candidati (default 50): si potano i piu' vecchi non promossi, mai i
  promossi ne' il precedente promosso. Le directory `.tmp-<pid>-*` orfane sono rimosse all'apertura
  del registro (se piu' vecchie di 1 h) e subito dopo l'uccisione di un trainer (per pid).
- **Processi**: niente `preexec_fn`; un boot `-I -c` applica `RLIMIT_AS` e `PR_SET_PDEATHSIG`
  (Linux) e poi fa `exec` del trainer. A ogni fine job si fa `killpg` sull'intero gruppo anche se il
  leader e' gia' uscito (un nipote che tiene le pipe aperte non blocca ne' sopravvive).
- **File system**: letture con `open(O_NOFOLLOW)` + `fstat` sul descrittore, traversal relativo a
  dir_fd (cartella di versione symlink rifiutata). `promoted_version()`/`promoted_card()` falliscono
  chiusi (`ModelIntegrityError`) se `promotions.json`, card (status, soglia) e sha256 non
  concordano; l'hash e' ricalcolato solo se cambiano inode/size/mtime/ctime del file. La directory
  del registro deve essere scrivibile solo dal servizio.
- **Concorrenza**: `flock` su `.lock` protegge allocazione delle versioni e promozioni tra processi
  (senza `fcntl`, es. Windows, resta un lock di thread: un solo processo scrittore). Gli id di
  versione sono limitati a 8 cifre; oltre, `save` rifiuta con errore chiaro.
- **Letture coerenti** (round 2): la promozione scrive prima la card e poi lo stack, il rollback
  prima lo stack e poi la card, e `promoted_card()` riprova se lo stack cambia durante la lettura:
  un lettore concorrente vede solo lo stato vecchio o quello nuovo. `promoted_snapshot()` restituisce
  i byte verificati della stessa lettura e il plugin costruisce la sessione ONNX da quelli (chiave
  di cache: versione, sha256, inode, size, mtime_ns, ctime_ns). Il boot controlla `getppid()` dopo
  `PR_SET_PDEATHSIG`; `_kill` fa `killpg` solo se il leader e' ancora vivo (altrimenti lo ha gia'
  fatto `leader_exit` subito dopo il reaping, senza finestra di riuso del pid).
- **Flood anonimi e candidati**: senza autenticazione, un client puo' addestrare in serie e,
  grazie al tetto `ML_MAX_CANDIDATES`, far potare candidati non promossi prima della revisione
  umana. Per questo esistono il limite per IP (`ML_TRAIN_PER_HOUR`), i tetti di job attivi e
  il tetto sui candidati (che protegge disco e CPU ma non l'integrita' della coda di revisione).
  Esposto oltre localhost, mettere davanti un livello di autenticazione/autorizzazione (reverse
  proxy con auth o middleware) e non lasciare l'endpoint raggiungibile da anonimi.
- Residuo: il controllo per-IP e il lock sono in memoria/file locale (non multi-nodo); la cache di
  verifica per stat non vede una riscrittura che conservi inode, size, mtime e ctime.

## Cosa NON e' verificato

- **Divario sim-to-real**: i dati sono sintetici e il modello fisico e' semplificato; il margine
  misurato contro il baseline vale solo per questa distribuzione. Su telemetria reale la skill
  puo' essere molto diversa: serve un set di test reale e una nuova soglia.
- **Nessuna GPU assunta**: tutto gira su CPU (onnxruntime `CPUExecutionProvider`, 1 thread);
  addestramento di reti profonde non e' testato.
- `RLIMIT_AS` limita la memoria virtuale, non la residente; non esiste su Windows (nessun tetto)
  e non e' stato provato su macOS. Il limite non e' un sandbox: il trainer e' codice di plugin
  fidato (come ogni plugin), non codice utente arbitrario.
- Nessuna autenticazione sugli endpoint dei job: valgono rate limit e tetti, ma chiunque
  raggiunga l'API puo' avviare job (fino ai tetti). Da proteggere a monte in produzione.
- Il registro non e' multi-processo/multi-nodo e la card non e' firmata.
- Nessun rilevamento di deriva e nessun riaddestramento automatico (non previsti in questo passo).

## Apprendimento per rinforzo (Task 17 passo 5)

**Porta.** `Environment` (+ dataclass `BoxSpace` con `low/high/shape`) in `backend/core/ports.py`,
solo tipi standard: `reset(seed) -> (obs, info)`, `step(azione) -> (obs, ricompensa, terminated,
truncated, info)`. Il core non importa gymnasium ne' numpy (import-linter + test).

**`SimulationEnv`** (`backend/ml/rl/env_adapter.py`, plugin `env-servo`, kind `environment`).
Scelta: invece di lanciare `servo_ctrl_c` a ogni passo (un processo per `step`, episodio chiuso con
PI interno, nessuno stato intermedio, non e' un MDP a passi) si usa un **impianto di riferimento in
Python puro** (`ServoPlant`: velocita' con ritardo del primo ordine verso `u * rate_dps`, angolo
integrato, finecorsa a +-180 deg), che ricalca la fisica del servo. Vantaggi: veloce (un
episodio da 100 passi in pochi decimi di ms), deterministico, nessuna dipendenza. Il confronto
numerico dell'impianto con il binario C **non e' stato fatto**.

- Azione: 1 componente in [-1, 1]. Finita ma fuori limite: clippata e penalizzata. NaN/inf, tipo
  errato o lunghezza diversa da 1: `ValueError` prima di toccare lo stato (mai propagati).
- Osservazione (3, in [-1, 1]): errore misurato/180 deg (rumore gaussiano 0.2 deg), velocita'/rate,
  setpoint/90 deg.
- Ricompensa: `r = -|errore_vero_deg|/90 - 0.05 * [azione fuori limite]`, limitata in
  `[-(270/90) - 0.05, 0]`. Sempre <= 0: terminare prima (assestamento) e' meglio.
- `terminated` = assestato (errore <= 1 deg e velocita' <= 5 deg/s); `truncated` a 100 passi.
- Determinismo: `reset(seed)` riavvia un `random.Random` dedicato; i semi sono interi in
  [0, 2^32-1] (altro: `ValueError`).

**Addestramento senza torch** (`backend/ml/rl/linear_policy.py`, `evaluation.py`, `training.py`,
plugin `trainer-rl`). ARS (random search aumentata, Mania et al. 2018) di una politica lineare
`a = clip(W . obs)`, avviata a caldo dal PD sintonizzato; esportata in **ONNX** (MatMul + Clip) e
valutata *sul modello ONNX servito*. Prima del salvataggio si verifica ONNX (float32) contro la
politica numpy (float64): tolleranza 1e-4 sull'azione in [-1, 1]. Gira nel subprocess del
`TrainerRunner` (`POST /api/train {"trainer": "trainer-rl"}`), salva un **candidato**, non promuove
(nessun endpoint HTTP di promozione).

**Gate di promozione (round 1 di correzioni).**
- Baseline = migliore controllore di una griglia P/PD (9 kp x 8 kd, kd = 0 e' un P) sintonizzato
  sui 20 semi di *training* (mai su quelli di valutazione). Vede errore E velocita', cioe' la
  stessa informazione della politica. Un P a guadagno 2 e l'azione zero restano solo come
  riferimenti deboli (`gain_mean_vs_untuned_p`, informativa, non nel gate).
- Guadagno = (R_politica - R_baseline)/|R_baseline| su **300 episodi appaiati** (stessi semi);
  bootstrap appaiato (2000 ricampioni, seme fisso 20261013), IC 95% a due code; si salvano
  `gain_mean` e `gain_ci_low`. Soglie (ogni metrica della soglia deve essere >=):
  `gain_ci_low >= max(0.15, valore del promosso)` e `gain_ci_low_perturbed >= 0.15`.
- Insieme **perturbato**: tau e rate dell'impianto scalati uniformemente di +-20% per episodio,
  semi distinti dal blocco nominale (offset 1 000 000), baseline invariato (tarato sul nominale).
- **Cosa e' davvero "tenuto fuori"**: i semi di valutazione danno setpoint e rumore del sensore
  diversi da quelli di training, ma sullo stesso impianto nominale e con la stessa distribuzione;
  NON e' generalizzazione a un impianto diverso. Solo l'insieme perturbato cambia la fisica, e
  solo entro +-20% di due parametri.
- **Maledizione del vincitore**: rivalutare molti candidati su un insieme fisso seleziona il
  fortunato e gonfia il guadagno. Ogni candidato usa un blocco di semi di valutazione nuovo
  derivato dal seme registrato (`eval_seed_base(seed)`, salvato come metrica `eval_seed_base` e
  incluso nello sha256 della card). Non elimina il rischio se si provano molti semi e si tiene il
  migliore: servirebbe un test finale indipendente, non implementato.
- **Risultato misurato, onesto**: su questo impianto un PD sintonizzato (kp 45, kd -2) e' quasi
  ottimo. ARS (40 iterazioni x 16 direzioni, 20 episodi di training per valutazione, 1.6-2.0 s di
  CPU, con la valutazione ~3-4 s in totale) lo eguaglia: seme 0/1/2 guadagno medio -0.003/-0.002/
  -0.003, `gain_ci_low` -0.004/-0.003/-0.004 (perturbato -0.005/-0.009/-0.003). Contro il P non
  sintonizzato il guadagno e' 0.46-0.49. Quindi il candidato ARS di esempio **non supera il gate
  e non e' promuovibile**: il gate funziona (test: una politica uguale al PD e' rifiutata, una
  nettamente migliore del baseline debole passa, la promozione richiede comunque l'approvazione
  umana), ma l'esempio NON dimostra che l'RL batta un controllore classico ben tarato. Con una
  politica lineare non si puo' battere un PD (e' nella stessa classe); tentativi con MLP e
  con feature `v|v|` non hanno dato margine (guadagno ~0, prove esplorative non conservate).
- **Budget di tempo** dichiarato: test di addestramento in-process < 30 s (misurato ~2-4 s) e
  < 90 s tramite runner (misurato ~2 s), CPU, 1 thread.
- Limiti dell'ambiente per l'interpretazione: velocita' e setpoint sono osservati quasi senza
  rumore (il rumore di 0.2 deg e' solo sull'errore), quindi la stima di stato e' triviale e
  una politica "riceve" piu' informazione di un firmware reale. `SAT_PENALTY` conta solo per
  algoritmi che emettono azioni fuori limite (PPO con distribuzione gaussiana); le politiche
  ONNX lineari clippano gia' e non la pagano mai.
- **Riproducibilita' numerica**: il determinismo e' verificato su questa macchina (stessi byte di
  risultato a parita' di seme); non e' garantito tra piattaforme/versioni di libm, numpy o
  onnxruntime (float e `math.exp`/`tanh` possono differire all'ultimo bit).

**Non linearita' opzionali e profilo `servo_realistic` (round 2).** `ServoPlant`/`SimulationEnv`
accettano, default 0 (spente, comportamento identico a prima), `deadband_deg` (comando ignorato se
lo spostamento comandato per periodo `|u|*rate*dt` e' sotto la soglia), `stiction_dps` (attrito
statico come velocita' equivalente: sotto soglia il giunto si "incolla", stick-slip a bassa
velocita') e `backlash_deg` (gioco totale: l'uscita misurata segue il motore solo dopo aver preso
+-gioco/2). Il profilo `servo_realistic` (usato da `trainer-rl` di default; `nominal` = tutto
spento) vale **deadband 1.0 deg, stiction 5.0 dps, backlash 1.0 deg**. Criterio, fissato PRIMA di
ogni confronto: punto medio dell'intervallo tipico di un servo hobby per banda morta (0.5-2 deg) e
gioco (0.5-2 deg); attrito statico ~5% della velocita' massima (90 dps). Sono valori **illustrativi,
non misurati su hardware**. I valori sono registrati nella card (`profile_*`) e nello sha256 della
configurazione. La perturbazione di valutazione (+-20%) si applica anche a deadband, stiction e
backlash (se non nulli), oltre a tau e rate. Baseline invariato (griglia P/PD sintonizzata sul
profilo, stessa informazione) e stesso gate (`gain_ci_low >= 0.15`, nominale e perturbato).

**Esito (onesto): ancora NESSUN margine.** Si e' eseguito un solo confronto sul profilo
dichiarato piu' un controllo di sensibilita' su 3 insiemi dichiarati in anticipo (i tre sotto,
nessun altro provato; tutti i risultati riportati, nessuno scartato). ARS lineare avviato a caldo
dal PD (40 iterazioni x 16 direzioni, 20 episodi di training per valutazione, 300 episodi appaiati,
bootstrap 2000, ~2 s per candidato, 3 semi 0/1/2); baseline scelto dalla griglia: kp 45, kd -2 in
tutti i casi.

| insieme (deadband deg / stiction dps / backlash deg) | `gain_mean` (semi 0,1,2) | `gain_ci_low` | `gain_ci_low_perturbed` | guadagno vs P non tarato |
|---|---|---|---|---|
| low (0.5 / 2.5 / 0.5) | -0.0041, -0.0025, -0.0029 | -0.0048, -0.0032, -0.0034 | -0.0050, -0.0032, -0.0064 | 0.65-0.68 |
| **servo_realistic (1.0 / 5.0 / 1.0)** | -0.0044, -0.0025, -0.0020 | -0.0051, -0.0033, -0.0025 | -0.0048, -0.0019, -0.0030 | 0.76-0.79 |
| high (2.0 / 10.0 / 2.0) | -0.0184, -0.0049, -0.0096 | -0.0239, -0.0059, -0.0161 | -0.0158, -0.0009, -0.0146 | 0.85-0.87 |

Nessun insieme supera 0.15 (il migliore e' ~0): i candidati ARS restano **non promuovibili** e
il gate non e' stato toccato. Perche': un PD ad alto guadagno satura il comando (bang-bang), quindi
banda morta e stiction (che agiscono su comandi piccoli) quasi non lo penalizzano: il ritorno del
baseline passa da -2.41 (nominale) a -2.45 (realistic), e il gioco di 1 deg e' vicino alla
tolleranza di assestamento (1 deg). Controllo esplorativo con **PPO** (SB3, MLP 64x64, extra
`[rl]`, 1 seme, profilo `servo_realistic`, stessi 300 semi di valutazione, non registrato): 50 000
passi (17 s) ritorno -3.01 contro PD -2.449 (guadagno -0.23, IC low -0.24); 200 000 passi (68 s)
-2.453 (guadagno -0.0014, IC low -0.0020). PPO raggiunge il PD ma non lo supera. Conclusione:
con questi parametri illustrativi, un PD ben tarato resta praticamente ottimo; l'esempio RL
dimostra pipeline e gate, non superiorita' dell'RL. Non si sono cercati altri parametri.

**Stable-Baselines3 (extra `[rl]`, opzionale).** `backend/plugins/env_servo/gym_shim.py`
(`ServoGymEnv`, `gymnasium.Env`, spazi Box float32). Verificato su Python 3.14.7: gymnasium 1.4.0
(MIT, wheel pura) e stable-baselines3 2.9.0 (MIT, wheel pura) si installano; SB3 richiede torch,
disponibile per cp314 manylinux x86_64 dall'indice CPU (`torch-2.14.1+cpu`, 196 MB wheel, ~770 MB
installato). `check_env` di gymnasium passa; smoke test PPO a 8192 passi (~5 s CPU): ritorno medio
-2.96 su 30 episodi di valutazione contro P -3.35 e zero -37.6 (50 000 passi: -1.81). Il test
richiede solo di battere l'azione zero: e' un test d'integrazione, non un benchmark. Senza gli
extra il test e' saltato e importare lo shim da' un ImportError esplicito.

## Deep learning (Task 17 passo 6, extra `[dl]`)

`backend/plugins/predictor_nn/`: MLP 2-16-16-1 (tanh) in PyTorch CPU sugli stessi dati sintetici di
`predictor_baseline` (include standardizzazione di ingresso e uscita nel grafo). Esportazione ONNX
con l'esportatore `dynamo` (richiede `onnxscript`, MIT; l'esportatore TorchScript legacy funziona
ma e' deprecato) e inferenza con onnxruntime nel plugin di servizio `predictor-nn`, che serve solo
il modello promosso del registro `<MODEL_REGISTRY_DIR>/predictor_nn` (separato da quello del
baseline) e non importa mai torch.

- **Tolleranza ONNX vs PyTorch dichiarata: 1e-4 dB** (float32); misurata 4e-6 sul test set fisso.
  `train_candidate` rifiuta di salvare se supera la tolleranza.
- Misurato (seed 1-3, 2000 campioni, 400 epoche Adam, ~1-2 s): RMSE 0.529-0.531 dB contro baseline
  lineare 1.288 dB, skill 0.83 contro soglia dichiarata 0.25.
- Senza extra: il plugin si carica, l'app parte, `predict` solleva `PluginError`; importare
  `training` solleva `ImportError` (test con moduli bloccati). Non esiste un trainer-job per la NN
  (la funzione `train_candidate` e' invocabile direttamente): non fatto in questo passo.
- **Niente estrapolazione silenziosa** (round 1): `train_candidate` salva nella card le metriche
  `train_power_w_min/max` e `train_distance_km_min/max` (potenza ~[1, 20] W, distanza ~[500, 2000]
  km). Il servizio rifiuta con `PluginError` ("fuori dal dominio di addestramento [...]") ogni
  ingresso oltre `min * 0.9` / `max * 1.1` (margine 10% sui bordi, feature strettamente positive);
  senza intervalli nella card rifiuta (fail-closed). I limiti assoluti di sanita' sono stati
  ristretti a potenza [0.1, 100] W e distanza [100, 10 000] km.
- **Seme riservato**: `fit`/`train_candidate` rifiutano `FIXED_TEST_SEED` (il test set fisso e'
  `make_dataset(500, FIXED_TEST_SEED)`: usarlo per il training lo riprodurrebbe). Il test verifica
  che nessuna riga di training coincida con una del test set.
- Disponibilita' torch su Python 3.14.7 / Linux x86_64: **si**, wheel cp314 dall'indice CPU
  (196 MB). Da PyPI senza indice CPU la build predefinita e' CUDA (diversi GB): installare prima
  torch dall'indice CPU (vedi commento in `pyproject.toml`).

## Sim-to-real e cosa NON e' verificato (RL/DL)

- **Divario sim-to-real**: l'ambiente e' un modello semplificato (primo ordine + limite di
  velocita'); nessun attrito, gioco, saturazione di corrente, ritardo di comunicazione o
  quantizzazione del sensore. Una politica con alto ritorno qui non e' validata su hardware: serve
  randomizzazione di dominio (tau, rate, rumore), identificazione del sistema e un filtro di
  sicurezza (limiti di velocita'/angolo, fallback al P) prima di qualsiasi uso fisico.
- Il ritorno e' misurato su una sola distribuzione (setpoint uniforme in +-90 deg, partenza da 0);
  nessun test fuori distribuzione ne' avversariale. Nessuna garanzia di stabilita' formale: la
  politica lineare non e' stata analizzata (margini di guadagno/fase).
- Il guadagno e' relativo a un PD sintonizzato su una griglia finita (9 x 8) con 20 semi di
  training: un baseline migliore (es. controllo ottimo nel tempo) ridurrebbe ancora il margine.
  La soglia 0.15 e' una scelta di progetto sul limite inferiore dell'IC, non derivata da una teoria.
- L'impianto Python non e' stato confrontato con `servo_ctrl_c`; non esiste un `Environment`
  che avvolga direttamente una `Simulation` esec per passo.
- ARS provato con 3 semi di training nel gate (gli IC bootstrap coprono solo la variabilita' degli
  episodi di valutazione, non quella dell'addestramento), PPO con 1: nessuna analisi sui semi.
- Esportazione ONNX di SB3/PPO nel registro non implementata (solo la politica lineare ARS e'
  esportata e promossa); il formato `onnx` e' l'unico ammesso dal registro.
- La NN e' addestrata solo su dati sintetici; su telemetria reale servono nuova soglia e test set
  reale. Nessuna GPU (tutto CPU, 1 thread). Non provato su Windows/macOS/ARM.
- Resta aperto il passo 7 (pagina "Modelli ed esperimenti") e la promozione via HTTP.
- `predictor_baseline`/`trainer_baseline` (round 2): `train_candidate` rifiuta `FIXED_TEST_SEED`
  (anche via trainer-job, dove il job fallisce), salva `train_*_min/max` nella card e il servizio
  rifiuta con `PluginError` ingressi oltre `min*0.9`/`max*1.1` (fail-closed se la card non ha gli
  intervalli). I limiti assoluti sono ristretti come per `predictor_nn`. Modelli promossi PRIMA
  di questa modifica non hanno gli intervalli nella card e ora vengono rifiutati: va riaddestrato.
