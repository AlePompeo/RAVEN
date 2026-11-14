PY=.venv/bin/python
venv: ; python3 -m venv .venv && $(PY) -m pip install -e ".[dev]"
test: ; $(PY) -m pytest
lint: ; $(PY) -m ruff check . && $(PY) -m mypy && .venv/bin/lint-imports
build-c: ; mkdir -p backend/plugins/fspl_c/bin && gcc -O2 -o backend/plugins/fspl_c/bin/fspl backend/plugins/fspl_c/fspl.c -lm && $(MAKE) build-servo
# servo_ctrl_c: HAL host + controllo PI; SERVO_EXTRA_CFLAGS=-fsanitize=address,undefined per i sanitizer
SERVO_DIR=backend/plugins/servo_ctrl_c
build-servo: ; mkdir -p $(SERVO_DIR)/bin && gcc -std=c99 -Wall -Wextra -Werror -pedantic -O2 $(SERVO_EXTRA_CFLAGS) -Icontracts/hal -I$(SERVO_DIR) -o $(SERVO_DIR)/bin/servo_ctrl $(SERVO_DIR)/servo_ctrl.c $(SERVO_DIR)/control.c contracts/hal/hal_host.c -lm && gcc -std=c99 -Wall -Wextra -Werror -pedantic -O2 $(SERVO_EXTRA_CFLAGS) -Icontracts/hal -I$(SERVO_DIR) -o $(SERVO_DIR)/bin/gimbal_tracker $(SERVO_DIR)/gimbal_tracker.c $(SERVO_DIR)/control.c contracts/hal/hal_host.c -lm
dev: ; $(PY) -m uvicorn --factory backend.bootstrap:build_app --reload
docker: ; docker build -t hackathon-base:dev .
# revisioni manuali (per versione) in scripts/license_reviewed.txt
licenses: ; .venv/bin/pip-licenses --format=json > /tmp/py-licenses.json && $(PY) scripts/license_check.py --python-json /tmp/py-licenses.json --reviewed-file scripts/license_reviewed.txt && $(PY) scripts/license_check.py --node-modules frontend/node_modules --lockfile frontend/package-lock.json --out frontend/public/licenses.json
# E2E reale (Playwright + axe, solo dev): richiede `make venv`, `cd frontend && npm ci`, `cd e2e && npm ci && npx playwright install chromium`
.PHONY: e2e
e2e: ; bash e2e/scripts/build-app.sh && cd e2e && npx playwright test

# Misure di prestazioni (dipendono dal carico: un solo worker, separate dalla suite funzionale)
e2e-perf: ; bash e2e/scripts/build-app.sh && cd e2e && npm run test:perf
.PHONY: e2e-perf

# Demo NASA: costruisce cio che manca e avvia su http://127.0.0.1:8000 (dati SINTETICI, vedi demo/README.md)
demo: build-c
	@test -f frontend/dist/index.html || (cd frontend && npm ci && npm run build)
	@echo "Demo su http://127.0.0.1:8000  (dati SINTETICI, vedi demo/README.md). Ctrl+C per fermare."
	STATIC_DIR=frontend/dist TELEMETRY_CSV=demo/telemetry_demo.csv RATE_LIMIT_PER_MIN=600 $(PY) -m uvicorn --factory backend.bootstrap:build_app --host 127.0.0.1 --port 8000
.PHONY: demo

# Kernel NAIF per le efemeridi (extra `sky`): scarica e verifica in EPHEMERIS_DIR (default build/ephemeris)
.PHONY: ephemeris
ephemeris: ; $(PY) -m backend.ephemeris.fetch

# DEM LOLA per GrazingLink: scarica (range request, ~64 KB a tile) i tile attorno ai siti predefiniti coperti
# (latitudine <= -85) in GRAZING_DEM_DIR (default build/lola, mai nel repository). Vedi docs/domain/grazinglink-plan.md
.PHONY: grazing-dem
grazing-dem: ; $(PY) -m backend.domain.grazing.prefetch

# Tessere LOLA scaricate a richiesta per i siti personalizzati (build/lola/custom, tetto GRAZING_DEM_CACHE_MAX_MB, default
# 200 MB, le piu' vecchie eliminate per prime). `make grazing-dem-status` mostra l'uso, `make grazing-dem-clear` svuota la cache
# dei siti personalizzati (non tocca le tessere dei siti del catalogo).
.PHONY: grazing-dem-status grazing-dem-clear
grazing-dem-status: ; $(PY) -m backend.domain.grazing.dem_cache --status
grazing-dem-clear: ; $(PY) -m backend.domain.grazing.dem_cache --clear

# Rigenera la tabella di compensazione R(nu, raggio) (extra `ml`, circa un minuto); poi eseguire i test
.PHONY: grazing-table
grazing-table: ; $(PY) scripts/gen_compensation_table.py
