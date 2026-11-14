# SPDX-License-Identifier: Apache-2.0
"""Nomi riservati della pipeline (modulo puro, senza dipendenze)."""

# Sorgente del canarino di salute dello store: scritta e subito cancellata, mai visibile ai
# lettori, rifiutata dal processor come source_id dei messaggi.
CANARY_SOURCE = "canary-healthcheck"
