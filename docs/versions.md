# Versioni verificate (Python 3.14.7, venv + pip)

```
cyclonedx-bom==7.5.0
datamodel-code-generator==0.83.0
fastapi==0.143.0
httpx==0.28.1
import-linter==2.15
mypy==2.4.0
pip-licenses==5.5.5
pydantic==2.14.1
pytest==9.1.1
pytest-asyncio==1.4.0
ruff==0.17.0
uvicorn==0.54.0
```

Tutte le dipendenze dev si installano su Python 3.14.7 senza modifiche.

## Efemeridi (extra `sky`, verificato 2026-10-20 su Python 3.14.7)

```
skyfield==1.55   (MIT, ruota pura Python; richiede certifi, jplephem, numpy, sgp4)
jplephem==2.24   (MIT)
numpy==2.5.4     (gia' usato dagli altri extra)
```

`pip install skyfield==1.55 jplephem` su Python 3.14.7: installazione riuscita, `load.timescale()` e `framelib.itrs` funzionano. I kernel NAIF (de440s.bsp ecc.) non sono nel pacchetto: si scaricano con `make ephemeris` (vedi `docs/ephemeris.md`). `backend.core` non puo' importare skyfield/jplephem (`.importlinter`).

# Versioni verificate frontend (Node 20.18.1, npm 10.8.2)

Verificato con `npm view <pkg> engines.node` il 2026-10-12. Le versioni correnti di Vite (8.3.4: `^20.19 || >=22.12`), Vite 7.3.x (`^20.19.0 || >=22.12.0`), `@sveltejs/vite-plugin-svelte` 6/7 (`^20.19`), jsdom 27+ (`^20.19`) e vitest 5 (`>=22.12`) NON supportano Node 20.18.1. Scelta: ultime major compatibili. Aggiornare a Vite 7+/8 richiede Node >=20.19 o 22.

```
vite==6.4.4                 (node ^18 || ^20 || >=22)
@sveltejs/vite-plugin-svelte==5.1.1
svelte==5.57.2
vitest==4.1.11              (node ^20 || ^22 || >=24; 3.2.7 aveva advisory tinypool/mocker)
jsdom==26.1.0               (node >=18)
@testing-library/svelte==5.4.2
@testing-library/dom==10.4.2
svelte-check==4.7.6
typescript==5.9.3           (TS 7.0.2 non adottato: ecosistema svelte-check ancora su 5.x)
@tsconfig/svelte==5.0.8
```

`npm audit`: 0 vulnerabilità con questo set.

## Dipendenze 3D e grafici (Task 11)

Verificato con `npm view` il 2026-10-12: nessuno dei tre pacchetti dichiara `engines` (compatibili con Node 20.18.1). Versioni esatte, licenze MIT; le dipendenze transitive di three (fflate, meshoptimizer, @tweenjs/tween.js: MIT; @dimforge/rapier3d-compat: Apache-2.0) e di @types/three (@types/webxr, @types/stats.js: MIT) sono tutte ammesse. `npm audit`: 0 vulnerabilità.

```
three==0.186.1              (MIT, dependencies)
uplot==1.6.32               (MIT, dependencies)
@types/three==0.186.0       (MIT, devDependencies)
@types/node==20.19.43       (MIT, devDependencies; tipi Node 20 per il test che legge la fixture del contratto)
```

## Budget del bundle iniziale

Misura (`npm run build`, 2026-10-12): chunk iniziale `index-*.js` = 51006 B raw (~19.3 kB gzip), unico file nel percorso di caricamento iniziale. `three` (747 kB raw, 192 kB gzip) e `uplot` (52 kB raw, 23 kB gzip) sono chunk separati caricati con `import()` dinamico da viewer e telemetria.

Il renderer di ripiego senza WebGL (`canvas2dViewport`, 12,7 kB raw, ~5,1 kB gzip, nessuna dipendenza) e' un chunk pigro a parte: il chunk iniziale resta 51012 B raw (19355 B gzip), soglia invariata.

Soglia in `frontend/scripts/check-bundle.mjs`: 70000 B raw (2026-10-27, i18n della shell: misura 69825 B, tetto concordato per questa fase; prima 65000 B dopo la misura di 64553 B con la correzione della navigazione TV, vedi `docs/design/design-system.md` §12). Lo script usa il manifest di Vite (`vite build --manifest`, `dist/.vite/manifest.json`): parte da index.html (script, modulepreload/preload, anche URL assoluti) e dagli entry, segue solo `imports` statici (non `dynamicImports`) e fallisce se nel grafo compaiono moduli/chunk di three/uplot; il controllo su marcatori nel codice minificato è solo secondario. Esecuzione: `npm run build && npm run check:bundle`. Aggiornare soglia e questa nota solo dopo una nuova misura.

## Node.js

Node 20 ha raggiunto la fine del supporto (EOL, aprile 2026). Il toolchain frontend e il CI (`setup-node`) restano fissati su 20.18, verificato localmente. L'immagine Docker usa `node:22` (LTS): verificato il 2026-10-12 in un container node:22 (v22.23.3) con `npm ci`, `npm run check`, `npm test` (118 test), `npm run build` e `npm run check:bundle`, tutti OK. Migrare CI e `engines` a 22 e' un passo successivo, da fare con una verifica completa.

## Test end-to-end (Task 13b, solo dev, in `e2e/`)

Verificato con `npm view` il 2026-10-12 (Node 20.18.1). Pacchetto separato `e2e/package.json`: non entra in `frontend/` ne' nel bundle distribuito.

```
@playwright/test==1.64.0      (Apache-2.0, node >=20)
@axe-core/playwright==4.13.0  (MPL-2.0, peer playwright-core >=1)
axe-core==4.13.0              (MPL-2.0, dipendenza di @axe-core/playwright, node >=4)
@types/node==20.19.43         (MIT)
```

`npm audit` (e2e): 0 vulnerabilita'. Browser: `npx playwright install chromium` (Chrome Headless Shell 156.0.8078.4, scaricato in `~/.cache/ms-playwright`, non versionato).

Licenze: Playwright e' Apache-2.0. **axe-core e `@axe-core/playwright` sono MPL-2.0** (copyleft a livello di file): usati solo come strumento di test in `e2e/devDependencies`, mai importati dal frontend, mai copiati nel bundle ne' nell'immagine Docker, non modificati. Quindi nessun obbligo di distribuzione del sorgente MPL e nessun impatto sulla licenza Apache-2.0 del progetto. `scripts/license_check.py` non scansiona `e2e/` (non e' distribuito).

## Sensor fusion: imufusion (Task 16 step 3, extra opzionale `[fusion]`)

Verificato il 2026-10-12 su Python 3.14.7 (Linux x86_64):

- `pip index versions imufusion`: ultima 1.3.3. Esiste una wheel precompilata `cp314-cp314-manylinux_2_28_x86_64` (anche macOS x86_64/arm64, Linux aarch64, Windows amd64): installa senza compilatore. La build da sdist non e' stata riuscita nell'ambiente isolato (richiede setuptools+numpy come build deps), ma sulle piattaforme sopra non serve.
- Licenza: MIT. Metadati PyPI (`License-Expression: MIT`), `LICENSE.md` presente nella wheel e nell'sdist 1.3.3 ("The MIT License (MIT), Copyright (c) 2021 x-io Technologies"). Repository: github.com/xioTechnologies/Fusion.
- Pin: `imufusion==1.3.3` in `pyproject.toml` extra `fusion`. La wheel non dichiara `numpy` come dipendenza ma lo importa a runtime: l'extra aggiunge `numpy` (testato con 2.5.4; BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 secondo pip-licenses, "da rivedere" per `scripts/license_check.py`: serve una riga in `scripts/license_reviewed.txt` prima di installare l'extra in un ambiente soggetto al gate).
- Comportamento verificato: nei primi ~3 s (fase di avvio) Fusion ignora il giroscopio; il plugin chiama `skip_startup()` perche' l'assetto iniziale e' l'identita' dichiarata.
- Il plugin `estimator_imu` si carica solo con l'extra: senza, il loader registra un PluginError per quel solo plugin e i test dedicati vengono saltati (`importorskip`).

## HAL C e servo_ctrl_c (Task 16 step 2)

Verificato il 2026-10-12 su Linux x86_64: gcc 15.3.1 (`-std=c99 -Wall -Wextra -Werror -pedantic -O2`, nessun warning), cppcheck 2.19.1 (`--enable=all`: solo `unusedFunction` sulle funzioni HAL non usate dall'esempio, atteso). Runtime sanitizer `libasan`/`libubsan` **assenti** in questa macchina (`/usr/lib64/libasan.so.8.0.0` non trovato): la build `-fsanitize=address,undefined` fallisce al link e il test viene saltato; in alternativa e' eseguita la build `-fsanitize=undefined -fsanitize-trap=undefined` (senza runtime). La build per ESP32/Arduino **non** e' stata eseguita ne' provata.

## Machine learning (Task 17, extra opzionale `[ml]`)

Verificato il 2026-10-12 su Python 3.14.7 (Linux x86_64): tutte le ruote sono binarie
(`pip install` senza compilatore; `pip download --only-binary=:all:` riuscito). Licenze lette con
`pip-licenses` sull'ambiente installato.

```
numpy==2.5.4            BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0
scipy==1.18.1           BSD (BSD-3-Clause)
scikit-learn==1.9.1     BSD-3-Clause
skl2onnx==1.20.0        Apache-2.0
onnx==1.23.2            Apache-2.0
onnxruntime==1.31.0     MIT
(transitive) joblib 1.6.0 BSD-3-Clause, threadpoolctl 3.7.0 BSD-3-Clause,
protobuf 7.36.2 BSD-3-Clause ("3-Clause BSD License"), ml_dtypes 0.6.0 Apache-2.0,
flatbuffers 25.12.19 Apache-2.0, cloudpickle 3.1.2 BSD-3-Clause, narwhals 2.27.1 MIT
```

Esportazione e inferenza ONNX verificate: scarto massimo tra `predict` di scikit-learn e
onnxruntime su LinearRegression e GradientBoostingRegressor < 1e-6 (float32).

`scripts/license_check.py` segnala `protobuf@7.36.2` come "da rivedere" perche' la stringa
"3-Clause BSD License" non e' nell'allowlist (la licenza e' BSD-3-Clause, permissiva): serve una
riga in `scripts/license_reviewed.txt` (fuori dal perimetro di questo task, non modificato).

Misura del baseline (seed 1, 2000 campioni, test set fisso di 500): RMSE modello 0.574 dB,
baseline lineare 1.289 dB, media 4.554 dB, skill 0.80 contro soglia dichiarata 0.25.

## Pipeline dati (Task 18, extra opzionale `[data]`)

Verificato il 2026-10-13 su Python 3.14.7 (Linux x86_64): le ruote cp314 esistono per entrambi
(`pip download --only-binary=:all:` riuscito, nessun compilatore). Licenze lette con `pip-licenses`
sull'ambiente installato; nessuna dipendenza transitiva obbligatoria (`Requires:` vuoto).

```
pyarrow==26.0.0   Apache-2.0   (pyarrow-26.0.0-cp314-cp314-manylinux_2_28_x86_64)
duckdb==1.5.6     MIT License  (duckdb-1.5.6-cp314-cp314-manylinux_2_26_x86_64)
```

`scripts/license_check.py` sull'ambiente con gli extra: nessuna segnalazione per questi due pacchetti.
Impostazioni DuckDB usate (nomi letti da `duckdb_settings()` sulla 1.5.6, non assunti):
`allowed_paths`, `allowed_directories`, `enable_external_access`, `lock_configuration`,
`memory_limit`, `threads`, `autoinstall_known_extensions`, `autoload_known_extensions`.
Vincoli osservati: `allowed_paths` va impostata dopo la connessione e prima di
`enable_external_access=false`; con `TimeZone` locale i `TIMESTAMPTZ` verso Python richiedono `pytz`
(non installato): le query restituiscono tempi gia' formattati come testo UTC.
Il passo 9 (benchmark) non e' stato eseguito: nessuna cifra di throughput e' dichiarata.

## Reinforcement learning e deep learning (Task 17 passi 5-6, extra opzionali `[rl]` e `[dl]`)

Verificato il 2026-10-13 su Python 3.14.7, Linux x86_64. `pip download --only-binary=:all:` e
installazione riusciti; licenze lette con `pip-licenses` sull'ambiente installato.

```
gymnasium==1.4.0           MIT      (wheel pura, 476 KB)
stable-baselines3==2.9.0   MIT      (wheel pura, 188 KB; richiede torch)
torch==2.14.1+cpu          Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND
                           BSD-3-Clause AND BSL-1.0 AND MIT
                           (indice https://download.pytorch.org/whl/cpu, cp314 manylinux_2_28
                           x86_64, wheel 196 MB, ~770 MB installato)
onnxscript==0.7.2          MIT      (esportatore ONNX dynamo di torch; 7.6 MB)
(transitive) onnx-ir 1.0.0 Apache-2.0, farama-notifications 0.0.6 MIT, sympy 1.14.0 BSD,
mpmath 1.3.0 BSD, networkx 3.7 BSD-3-Clause, filelock 4.1.1 MIT, fsspec 2026.9.0 BSD-3-Clause,
cloudpickle 3.1.2 BSD-3-Clause, Jinja2 3.1.6 BSD, MarkupSafe 3.0.4 BSD-3-Clause,
typing_extensions 4.16.0 PSF-2.0
```

Le dipendenze transitive non sono state fissate. Da PyPI senza `--index-url` CPU `torch` e' la
build CUDA (non scaricata ne' misurata qui). SBOM non rigenerato per questi extra.
Misure: vedi `docs/ml.md` (guadagno ARS 0.28-0.36 vs P, skill NN 0.83, ONNX vs torch 4e-6).

## Rete e protocolli spaziali (Task 19, passi 1-6)

Nessuna dipendenza nuova: `backend/net/` usa solo la libreria standard di Python 3.14.7 (`asyncio`,
`socket`, `struct`/`int.from_bytes`, `ipaddress`, `heapq`). Hypothesis non e' installato: le proprieta'
usano cicli con seme fisso. Fonti consultate il 2026-10-13 (dettaglio in `docs/net.md`): CCSDS
133.0-B-2 (giugno 2020), AX.25 v2.2 (rev. 10/09/2017), RFC 1055, RFC 1662, KISS (ax25.net),
libcsp v1.6 (LGPL-2.1, solo letto), catalogo CRC RevEng.

## Vincoli di base (2026-10-13)

`constraints/base.txt` fissa le versioni esatte delle 23 dipendenze di base (senza extra) provate in questa sessione, ed e usato dal Dockerfile con `pip install -c`. Non ci sono hash ne un lockfile completo per gli extra ([ml], [rl], [dl], [data], [fusion]) ne per gli strumenti di sviluppo: la riproducibilita della build e quindi parziale (follow-up: `pip-compile --generate-hashes`).

## Learning Assistant (2026-10-15)

Nessuna dipendenza pesante. `backend/assistant/` usa la libreria standard, PyYAML 6.0.3 (gia' in
`constraints/base.txt`, arriva con `uvicorn[standard]`; extra esplicito `[assistant]`) per il
front-matter e httpx 0.28.1 (dipendenza di base) per il provider OpenAI-compatibile. Nessun modello,
embedding o servizio esterno e' richiesto dal provider predefinito. Dettagli e limiti: `docs/assistant.md`.
