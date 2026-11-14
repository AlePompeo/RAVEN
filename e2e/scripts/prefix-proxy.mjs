// SPDX-License-Identifier: Apache-2.0
// Reverse proxy minimale che simula un deploy sotto /app/: toglie il prefisso "/app" dalle richieste
// non-API e le inoltra al backend (che serve il frontend compilato con `--base=/app/` alla radice).
// Le chiamate /api e /health (percorsi assoluti del client) passano invariate.
import http from 'node:http';

const [listen, target] = process.argv.slice(2).map(Number);
if (!listen || !target) throw new Error('uso: prefix-proxy.mjs <porta-ascolto> <porta-backend>');

http
  .createServer((req, res) => {
    let url = req.url ?? '/';
    if (url === '/app') url = '/';
    else if (url.startsWith('/app/')) url = url.slice('/app'.length);
    const up = http.request(
      { host: '127.0.0.1', port: target, path: url, method: req.method, headers: req.headers },
      (r) => {
        res.writeHead(r.statusCode ?? 502, r.headers);
        r.pipe(res);
      },
    );
    up.on('error', () => {
      res.writeHead(502).end();
    });
    req.pipe(up);
  })
  .listen(listen, '127.0.0.1');
