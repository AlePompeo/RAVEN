// SPDX-License-Identifier: Apache-2.0
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const csv = path.join(here, 'fixtures', 'telemetry.csv');
const py = path.join(root, '.venv', 'bin', 'python');
// Porta del backend principale: E2E_PORT permette di evitare una 8000 già occupata (es. un server di
// sviluppo con altro CSV e rate limit predefinito, che reuseExistingServer riuserebbe).
const perf = !!process.env.E2E_PERF;
const port = Number(process.env.E2E_PORT ?? 8000);
const appPort = Number(process.env.E2E_APP_PORT ?? 8002);
const proxyPort = Number(process.env.E2E_PROXY_PORT ?? 8001);

const serve = (port: number, staticDir: string) => ({
  command: `${py} -m uvicorn --factory backend.bootstrap:build_app --port ${port}`,
  cwd: root,
  url: `http://127.0.0.1:${port}/health`,
  reuseExistingServer: !process.env.CI,
  timeout: 60_000,
  // rate limit alzato solo per la suite (decine di caricamenti pagina dallo stesso IP)
  // ASSISTANT_PROVIDER fisso sull'estrattivo: l'e2e non deve dipendere da un Ollama eventualmente attivo sulla macchina
  // (la base di conoscenza è quella del repository: docs/knowledge e backend/plugins/*/knowledge, cwd = root).
  env: { STATIC_DIR: staticDir, ENV: 'dev', TELEMETRY_CSV: csv, RATE_LIMIT_PER_MIN: '100000', ASSISTANT_PROVIDER: 'assistant-extractive', GRAZING_DEM_ALLOW_DOWNLOAD: '0' },
});

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0, // nessun retry: un test instabile deve emergere, non essere mascherato
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    locale: 'it-IT',
    // Le specifiche esistenti verificano il contenuto completo: partono in modalità Avanzato (hb.mode, la scelta salvata
    // dell'interruttore). Le specifiche della modalità (mode.spec.ts) e della privacy ripartono da un archivio vuoto.
    storageState: {
      cookies: [],
      origins: [port, proxyPort, appPort].map((p) => ({ origin: `http://127.0.0.1:${p}`, localStorage: [{ name: 'hb.mode', value: 'avanzato' }, { name: 'hb.lang', value: 'it' }] })),
    },
  },
  // Due esecuzioni separate: `npm test` (funzionale, parallela) e `npm run test:perf` (E2E_PERF=1, un worker solo).
  // Le specifiche di prestazioni misurano frame al secondo con la CPU rallentata: in parallelo con altri browser
  // misurano il carico della macchina, non l'app.
  projects: perf
    ? [{ name: 'perf', testMatch: /perf-.*\.spec\.ts$/, fullyParallel: false, use: { ...devices['Desktop Chrome'] } }]
    : [
        { name: 'chromium', testIgnore: [/perf-.*\.spec\.ts$/, /i18n-default\.spec\.ts$/], use: { ...devices['Desktop Chrome'] } },
        // lingua predefinita: nessuna lingua salvata, browser in inglese (docs/i18n.md)
        {
          name: 'en-default',
          testMatch: /i18n-default\.spec\.ts$/,
          use: { ...devices['Desktop Chrome'], locale: 'en-US', storageState: { cookies: [], origins: [] } },
        },
      ],
  webServer: [
    serve(port, process.env.E2E_STATIC_DIR ?? path.join(root, 'frontend', 'dist')),
    serve(appPort, process.env.E2E_APP_STATIC_DIR ?? path.join(here, '.dist-app')), // build con base /app/, servita alla radice
    {
      // reverse proxy che simula il deploy sotto /app/ (toglie il prefisso)
      command: `node ${path.join(here, 'scripts', 'prefix-proxy.mjs')} ${proxyPort} ${appPort}`,
      url: `http://127.0.0.1:${proxyPort}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
