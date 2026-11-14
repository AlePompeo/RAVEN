<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 19a (passi 1-6): reti e protocolli spaziali - report

Stato: DONE (passi 1-6). Fuori da questo invio: integrazione pipeline, fuzzing, pagina frontend.

## Commit
- 6ae2a25 porte, config a default chiuso, loopback, import-linter
- da23024 framer (length prefix, delimiter, SLIP, KISS)
- 09095a8 trasporti TCP/UDP/multicast con limiti
- 08d0c4e CCSDS Space Packet + framer da intestazione
- 928e0ff CSP v1 e AX.25/KISS
- 490d757 + a867271 canale simulato (+ fix lint)
- 0c7d477 docs/net.md, docs/versions.md

## Verifiche
- tests/backend esclusa pipeline, due volte: 862 passed, 49 skipped (di cui 235 in tests/backend/net, 0 skip: il test multicast e' stato eseguito e passato su loopback).
- ruff check . pulito; mypy backend pulito (74 file); lint-imports 3 contratti kept; gen.py --check ok.
- ruff format --check segnala backend/core/ports.py:154, riga PREESISTENTE (non mia, area Environment); i file di net sono formattati.

## Layout verificati su fonte primaria (testo letto il 2026-10-13)
- CCSDS Space Packet, CCSDS 133.0-B-2 (giugno 2020), https://public.ccsds.org/Pubs/133x0b2e2.pdf: sez. 4.1.2, 4.1.3.2-4.1.3.5 (tutti i campi, idle, lunghezza = ottetti-1, 7..65542).
- AX.25 v2.2 rev. 10/09/2017 (wiki.oarc.uk): indirizzi, SSID, UI 0x03/0x13, PID 0xF0, info 256, FCS ISO 3309. ERRATA nel documento: Fig. 3.4 stampa 0x98 per 'N' (corretto 0x9C per la regola di 3.12); il codice segue la regola.
- CRC-16/X-25 e CRC-32C: catalogo RevEng (check 0x906E, 0xE3069283).
- SLIP RFC 1055; KISS (ax25.net/kiss.aspx); ordine byte FCS = HDLC (RFC 1662 App. C).
- CSP v1: letto dal sorgente libcsp v1.6 (csp_types.h, csp_if_kiss.c, csp_crc32.c, csp_io.c); non esiste standard formale.

## NON verificato
- Ordine dei byte dell'FCS AX.25 sul filo contro una cattura reale; interoperabilita' CSP con nodo reale; CRC32 CSP non copre l'intestazione (limite); HMAC/XTEA CSP rifiutati; CCSDS: intestazione secondaria/Octet String non implementati; flag sequenza idle '11' e pattern 0x00 sono scelte del template; length prefix e delimiter sono definizioni locali.
- Proprieta' round-trip con cicli a seme fisso (Hypothesis non installato); nessuna campagna di fuzzing; solo Linux.

## Decisioni di sicurezza da rivedere
- Rate limit per IP (non per connessione): su loopback condiviso i client dividono la quota.
- SLIP: ESC non valido scarta il frame (piu' stretto di RFC 1055 che suggerisce di tenere il byte).
- Nuovo contratto import-linter `core-no-network-libs` (oltre all'aggiunta di backend.net alla lista di core-independent).
- Nessun TLS; UDP senza idle timeout; client TCP senza riconnessione.

## Codice applicativo fuori perimetro
Nessuno trovato per firmware-hardware-engineer / avionics-cpp-engineer.

## Fix round 1 (revisione di sicurezza)
Commit: 3a1ace3 (+ import order), 97333f0, 013bcb0, 8261fee.
- (1) BER: rifiutato se non 0 o in [1e-12, 1]; `SimChannel.send` transazionale (contatori, banda, stato RNG ripristinati se solleva). Test: subnormali, invariante dopo errore interno.
- (2) `max_connections_per_ip` (default 2, per IPv4 o /64 IPv6, contatore `rejected_per_ip`); test con sorgenti 127.0.0.1/2/3.
- (3) Ogni framer espone `in_frame`/`bytes_since_frame`; timer di messaggio armato dal primo byte dopo l'ultimo frame completato; `max_discard_bytes` (default 4*max+1024) chiude la connessione; frame vuoti: length-prefix li rifiuta (`allow_empty`), altri ignorati/contati senza azzerare il rumore. Test per slip/kiss/delim1/delim2 e trickle TCP (timeout reali brevi 0.3 s: i trasporti usano loop.time(), nessun orologio virtuale iniettabile).
- (4) Rate limiter: chiave IPv6 /64, evizione solo di bucket gia' pieni, altrimenti bucket di overflow condiviso, tetto globale per listener; contatore `peer_table_overflow`.
- Minor: guardia multicast (interfaccia loopback/privata/link-local salvo opt-in; gruppo non in 224.0.0.0/24 salvo `allow_reserved_group`); framer personalizzato con eccezione non-ProtocolError -> `framing_errors` e chiusura solo di quella connessione; `OversizeError` per tipo; CSP/AX.25 controllano la dimensione prima di copiare; bit R AX.25 (sez. 3.12.1/2: "se non implementati, posti a uno"): encoder a 1, decoder tollerante con contatore, `strict_reserved` opzionale; import-linter `core-no-network-libs` con `allow_indirect_imports = False` (verificato: rileva catene indirette, nessun falso positivo); docs/net.md aggiornato con protezioni precise e rischio residuo.
- Verifica: tests/backend escluso pipeline 2 volte: 908 passed, 49 skipped; mypy ok; lint-imports 3 kept; gen.py --check ok. `ruff check .` segnala solo 4 RUF100 in tests/backend/pipeline/test_round5.py (altro agente, non toccato).
- Non risolto: botnet/UDP spoofato (documentato come residuo); allow_indirect_imports resta True negli altri due contratti; il test di integrazione dei timer usa tempo reale breve.
