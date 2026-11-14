#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compila il frontend due volte: base "/" (frontend/dist) e base "/app/" (e2e/.dist-app).
set -euo pipefail
cd "$(dirname "$0")/../../frontend"
npm run build
npx vite build --base=/app/ --outDir ../e2e/.dist-app --emptyOutDir
