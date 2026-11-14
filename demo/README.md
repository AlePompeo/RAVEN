<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dati della demo

`telemetry_demo.csv` contiene **telemetria SINTETICA di segnaposto** per tre siti fittizi (`sito-A`, `sito-B`, `sito-C`): onde sinusoidali con il formato del contratto dati (`contracts/telemetry.schema.json`).

**Non sono dati lunari, né effemeridi, né il risultato di un link budget o di un modello energetico.** Servono solo a mostrare la piattaforma (stream, grafici, tabella, vista 3D). Quando il dominio sarà implementato (`docs/hackathon/nasa-lunar.md`) questo file va sostituito con dati veri, con fonte e licenza dichiarate.

## Avvio

```bash
make venv          # una volta sola
make demo          # http://127.0.0.1:8000
```

Con Docker, senza installare nulla: i dati sintetici sono già dentro l'immagine del branch NASA.

```bash
docker build -t hackathon-base:demo .
docker run --rm -p 127.0.0.1:8000:8000 hackathon-base:demo     # http://127.0.0.1:8000
```

Nota (Fedora/SELinux): se invece monti una cartella dell'host con `-v`, aggiungi `:z` al volume (`-v "$PWD/demo:/demo:z"`); senza, SELinux nega la lettura e il replay della telemetria resta spento.

La vista 3D usa WebGL quando c'è e passa da sola a un renderer Canvas 2D quando manca, quindi funziona anche su computer senza accelerazione grafica.
