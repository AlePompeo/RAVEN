# SPDX-License-Identifier: Apache-2.0
# Multi-stage: frontend (Node) + plugin C (gcc) -> immagine Python slim, utente non root.
# Nessun segreto nell'immagine: la configurazione arriva da variabili d'ambiente a runtime.

# --- 1. Frontend -----------------------------------------------------------
# node:22 LTS (non slim) include python3, usato solo per generare licenses.json.
FROM node:22 AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
COPY scripts/license_check.py scripts/license_check.py
RUN python3 scripts/license_check.py --node-modules frontend/node_modules \
        --lockfile frontend/package-lock.json --out frontend/public/licenses.json \
    && cd frontend && npm run build

# --- 2. Plugin C (binario statico: nessuna dipendenza di libc a runtime) ----
FROM gcc:14-bookworm AS cbuild
COPY backend/plugins/fspl_c/fspl.c /tmp/fspl.c
COPY backend/plugins/servo_ctrl_c/ /tmp/servo/
COPY contracts/hal/ /tmp/hal/
RUN mkdir -p /out \
    && gcc -O2 -static -o /out/fspl /tmp/fspl.c -lm \
    && gcc -std=c99 -Wall -Wextra -Werror -pedantic -O2 -static -I/tmp/hal -I/tmp/servo \
        -o /out/servo_ctrl /tmp/servo/servo_ctrl.c /tmp/servo/control.c /tmp/hal/hal_host.c -lm \
    && gcc -std=c99 -Wall -Wextra -Werror -pedantic -O2 -static -I/tmp/hal -I/tmp/servo \
        -o /out/gimbal_tracker /tmp/servo/gimbal_tracker.c /tmp/servo/control.c /tmp/hal/hal_host.c -lm

# --- 2b. Kernel NAIF (efemeridi): hash fissati in backend/ephemeris/kernels.lock.json ---------
# Il build FALLISCE se un file non coincide con dimensione e SHA-256 del lock (nessun ripiego).
# Solo libreria standard: nessuna dipendenza da installare in questo stage.
FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS ephemeris
WORKDIR /src
COPY backend/__init__.py backend/__init__.py
COPY backend/ephemeris/__init__.py backend/ephemeris/kernels.py backend/ephemeris/fetch.py \
     backend/ephemeris/kernels.lock.json backend/ephemeris/
RUN EPHEMERIS_DIR=/out python -m backend.ephemeris.fetch \
    && EPHEMERIS_DIR=/out python -m backend.ephemeris.fetch --check \
    && chmod -R a+rX /out

# --- 3. Runtime ------------------------------------------------------------
FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS runtime
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static \
    ENV=prod \
    CORS_ORIGINS="" \
    RATE_LIMIT_PER_MIN=120 \
    TRUSTED_PROXY=0 \
    TELEMETRY_SITE_ID=demo \
    TELEMETRY_MAX_SUBSCRIBERS=100 \
    MAX_BODY_BYTES=65536 \
    CHAT_MAX_STREAM_SECONDS=120
# TELEMETRY_CSV: volutamente non impostata (replay disabilitato di default).
WORKDIR /app
COPY pyproject.toml ./
COPY constraints/ constraints/
COPY backend/ backend/
COPY contracts/*.schema.json contracts/
COPY docs/knowledge/ docs/knowledge/
RUN pip install -c constraints/base.txt -e ".[fusion,sky]" \
    && pip uninstall -y pip \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /app/build/lola \
    && chown app /app/build/lola
COPY --from=cbuild /out/fspl backend/plugins/fspl_c/bin/fspl
COPY --from=cbuild /out/servo_ctrl backend/plugins/servo_ctrl_c/bin/servo_ctrl
COPY --from=cbuild /out/gimbal_tracker backend/plugins/servo_ctrl_c/bin/gimbal_tracker
COPY --from=frontend /src/frontend/dist /app/static
# kernel NAIF alla posizione predefinita di EPHEMERIS_DIR (<radice>/build/ephemeris)
COPY --from=ephemeris /out /app/build/ephemeris
COPY demo/ /app/demo/
RUN chmod -R a+rX /app/demo
ENV TELEMETRY_CSV=/app/demo/telemetry_demo.csv
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "--factory", "backend.bootstrap:build_app", "--host", "0.0.0.0", "--port", "8000"]
