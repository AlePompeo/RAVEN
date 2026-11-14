<!-- SPDX-License-Identifier: Apache-2.0 -->
# Reti TCP/UDP e protocolli spaziali (Task 19, passi 1-6)

Pacchetto `backend/net/` (solo libreria standard, nessuna dipendenza nuova). Spec §15. Il core
(`backend/core`) conosce solo le porte `Transport`, `Framer`, `ProtocolCodec`, `Channel` in
`backend/core/ports.py`; non importa `socket`/`ssl` (contratto import-linter `core-no-network-libs`)
e l'avvio dell'app non carica `backend.net` (test `test_core_has_no_network_imports_and_app_starts_without_net`).

Fuori da questo documento (passi successivi del Task 19): integrazione con la pipeline (Task 18),
campagna di fuzzing, pagina "Pipeline dati" nel frontend, gateway WebSocket.

## Nota legale

Il template **non trasmette via radio**: `Channel` e' una simulazione software, nessun codice pilota
hardware RF, nessun socket raw, nessuna modalita' promiscua. Qualunque uso con radio reali (per
esempio AX.25 sulle bande radioamatoriali) richiede il rispetto delle norme e delle licenze
applicabili (licenza radioamatoriale, assegnazione di frequenza) ed e' **responsabilita' dell'utente**,
fuori dal template.

## Moduli

| Modulo | Contenuto |
|---|---|
| `config.py` | `ListenerConfig`, `load_listeners()` (env `NET_LISTENERS`), validazione e tetti assoluti |
| `transport.py` | `TcpServerTransport`, `TcpClientTransport`, `UdpTransport` (unicast, client, multicast), `LoopbackTransport`/`loopback_pair`, `start_listeners`, `BoundedQueue`, `PeerLimiter` |
| `framing.py` | `LengthPrefixFramer` (1/2/4 byte BE), `DelimiterFramer`, `SlipFramer`, `KissFramer` |
| `ccsds.py` | `SpacePacket`, `SpacePacketCodec`, `SpacePacketFramer` |
| `csp.py` | `CspPacket`, `CspCodec` (CSP v1, CRC-32C opzionale) |
| `ax25.py` | `Ax25Address`, `Ax25UiFrame`, `Ax25Codec` (UI + FCS CRC-16/X.25), `kiss_encode`/`kiss_decode_frames` |
| `channel.py` | `SimChannel`, `ChannelConfig`, `VirtualClock` |
| `errors.py` | `ProtocolError` (+ `FramingError`, `CrcError`), `TransportError`, `NetConfigError` |

## Configurazione e default chiuso

Nessun listener parte da solo. Si avviano solo quelli dichiarati, da `NET_LISTENERS` (array JSON) o
da oggetti `ListenerConfig` passati a `start_listeners()`:

```json
[{"name": "tm-in", "kind": "udp", "host": "127.0.0.1", "port": 5005,
  "max_message_bytes": 1024, "rate_msgs_per_s": 50, "rate_burst": 100,
  "queue_size": 512, "drop_policy": "drop_oldest"}]
```

- `kind`: `tcp_server`, `tcp_client`, `udp`, `udp_client`, `udp_multicast`.
- Bind solo su indirizzi **loopback** (default `127.0.0.1`). Qualunque altro indirizzo (0.0.0.0,
  interfacce reali) e' rifiutato con `NetConfigError` salvo `NET_ALLOW_PUBLIC_BIND=1` (esattamente `1`).
  La stessa regola vale per gli oggetti costruiti a mano (le classi trasporto rivalidano la config).
  Nomi host non ammessi nel bind (solo IP letterali: nessuna risoluzione DNS).
- Multicast: `group` (IPv4 multicast) e `interface` (IPv4 esplicito, non `0.0.0.0`) obbligatori;
  socket legato all'indirizzo del gruppo, TTL 1. Stessa guardia del bind: `interface` deve essere
  loopback, privata o link-local salvo `NET_ALLOW_PUBLIC_BIND=1`; `group` nel range multicast e
  NON in `224.0.0.0/24` (riservato ai protocolli di rete locale) salvo `allow_reserved_group=true`.
- Valori fuori intervallo, chiavi sconosciute, nomi duplicati: rifiutati, mai corretti in silenzio.
  Tetti assoluti: messaggio 1 MiB, 1024 connessioni, coda 100000.
- Il client (`tcp_client`, `udp_client`) apre una connessione in uscita verso l'host configurato: la
  destinazione e' una scelta dell'operatore; se mai derivasse da input utente servirebbe una allowlist.

## Garanzie e limiti (tutti coperti da test)

| Limite | Meccanismo | Contatore |
|---|---|---|
| Connessioni | oltre `max_connections` la connessione e' chiusa subito; oltre `max_connections_per_ip` (default 2, per IPv4 o per /64 IPv6) idem, cosi' un solo IP non occupa tutti gli slot | `rejected_connections`, `rejected_per_ip` |
| Dimensione messaggio | TCP: il prefisso di lunghezza e' confrontato con il massimo PRIMA di leggere/allocare; UDP: `len(datagramma) > max` scartato prima di ogni copia/parsing; invio oltre il massimo -> `LimitExceeded` | `oversize` |
| Inattivita' | nessun byte entro `idle_timeout_s` -> chiusura pulita | `idle_timeouts` |
| Slowloris / rumore a goccia | il timer `message_timeout_s` parte dal primo byte dopo l'ultimo frame COMPLETATO (`bytes_since_frame`, esposto da ogni framer: vale anche in stato di scarto di SLIP/KISS/delimitatore, dove `pending` e' 0) e si azzera solo quando esce un frame; in piu' `max_discard_bytes` (default `4*max_payload+1024`) chiude la connessione dopo troppi byte senza frame; frame vuoti ignorati ma non azzerano il contatore | `message_timeouts`, `framing_errors` |
| Velocita' | token bucket per **IP** (IPv6 aggregato per /64, IPv4-mapped come IPv4) piu' tetto globale del listener (`global_rate_msgs_per_s/burst`); tabella `max_peers`: un peer sconosciuto a tabella piena sostituisce il meno recente solo se il suo bucket e' gia' pieno (evizione senza perdita), altrimenti condivide UN bucket di overflow (nessun burst fresco per sorgenti spoofate); `rate_disconnect_after` violazioni consecutive -> chiusura (TCP) | `rate_limited`, `peer_table_overflow` |
| Code | `BoundedQueue` con `drop_oldest` (default, telemetria: vale il dato recente) o `drop_newest` | `dropped` |
| Scrittura lenta | `drain` con timeout; peer lento chiuso, nessun accumulo di memoria | `TransportClosed` |
| Frame malformati | `FramingError` sul prefisso non valido (o lunghezza zero, salvo `allow_empty`): connessione chiusa, server vivo; un framer personalizzato che solleva un'eccezione NON `ProtocolError` chiude solo quella connessione | `framing_errors` |

Sempre: `receive()` restituisce `None` a trasporto chiuso (nessun blocco), `close()` e' idempotente,
nessuna eccezione non tipizzata esce dai parser (solo `ProtocolError`).

Residuo dichiarato (non risolto): chi controlla MOLTI indirizzi (botnet, `/64` multipli, sorgenti UDP
spoofate) puo' comunque: (a) occupare gli slot di connessione fino a `max_connections` con
`max_connections_per_ip` connessioni ciascuno, per al piu' `idle_timeout_s`; (b) far consumare CPU al
parsing dei datagrammi prima del rate limit (il controllo di dimensione e' O(1), il resto no); (c)
con UDP spoofato, esaurire il bucket di overflow e il tetto globale, facendo scartare anche traffico
legittimo da sorgenti nuove (il traffico dei peer gia' noti con bucket in uso non viene resettato).
Il template non offre difesa efficace contro questo: servono filtri a monte (firewall, rete) o
autenticazione. Il rate limit e' per IP, quindi dietro NAT/loopback condiviso i client si dividono la
quota; UDP non ha idle timeout (senza connessione); nessuna riconnessione automatica del client TCP;
nessun TLS (se serve, va davanti o va aggiunto: vedi sotto); testato solo su Linux.

## Framer

| Framer | Semantica | Difesa |
|---|---|---|
| `LengthPrefixFramer(1/2/4)` | prefisso BE + payload | lunghezza > max -> `FramingError` senza allocare; framer "rotto" fino a `reset()` |
| `DelimiterFramer` | messaggi terminati dal delimitatore | frame > max scartato e contato, resync al delimitatore successivo |
| `SlipFramer` | RFC 1055 | ESC + byte diverso da ESC_END/ESC_ESC: frame **scartato** e contato (l'RFC suggerisce di tenere il byte: scelta piu' stretta, deliberata) |
| `KissFramer` | SLIP + byte di comando (porta/comando); restituisce solo i frame dati (comando 0, qualunque porta; la porta e' scartata) | altri comandi ignorati e contati (`ignored_commands`) |
| `SpacePacketFramer` | lunghezza dall'intestazione CCSDS | versione != 0 o lunghezza > max sull'intestazione -> `FramingError` |

Frame vuoti: `LengthPrefixFramer` rifiuta la lunghezza 0 (`allow_empty=False` di default); SLIP/KISS/delimitatore li ignorano e li contano (`empty_frames`) senza azzerare il contatore di rumore. Il rumore prima del primo FEND/END in SLIP/KISS forma un frame "sporco": e' compito del livello
superiore (CRC/codec) scartarlo; `KissFramer` da solo non ha integrita'.

## Protocolli: che cosa e' stato verificato su fonte primaria

Verifica del 2026-10-13 (testo scaricato e letto, non ricordato a memoria).

| Elemento | Esito | Fonte |
|---|---|---|
| **CCSDS Space Packet**: intestazione 6 ottetti (versione 3 b, tipo, flag sec., APID 11 b, flag sequenza 2 b, conteggio 14 b mod 16384, lunghezza = ottetti - 1), campo dati 1..65536, pacchetto 7..65542, idle = APID tutti uno con flag sec. 0 | **Verificato** (sez. 4.1.2, 4.1.3.2-4.1.3.5) | CCSDS 133.0-B-2, Blue Book, giugno 2020, <https://public.ccsds.org/Pubs/133x0b2e2.pdf> |
| CCSDS: flag di sequenza dei pacchetti idle ('11') e riempimento 0x00 | **Non dettati dallo standard** (pattern lasciato al progetto, 4.1.4.3.4): scelta del template | - |
| CCSDS: intestazione secondaria, servizio Octet String, gestione dei percorsi | **Non implementati** (campo dati opaco) | - |
| **AX.25**: codifica indirizzi (carattere << 1, ottetto SSID `CRRSSSS0`/`HRRSSSS1`, estensione LSB, fino a 8 ripetitori), controllo UI 0x03/0x13, PID 0xF0, info 256 ottetti, FCS = ISO 3309 | **Verificato** (sez. 3.4, 3.5, 3.7, 3.9, 3.12, 4.3.3.6, 4.4.6) | AX.25 v2.2 rev. 10/09/2017, <https://wiki.oarc.uk/_media/packet:ax25.2.2.10.pdf> |
| AX.25 **errata nel documento**: la Figura 3.4 stampa 0x98 per la lettera `N`; la regola di 3.12 (shift a sinistra) da' 0x9C e tutti gli altri ottetti della figura sono coerenti con la regola | Segnalata; il codice segue la **regola** (test con 0x9C) | stesso documento |
| CRC-16/X-25 (poly 0x1021 rifl., init/xorout 0xFFFF, check 0x906E, residuo 0xF0B8) | **Verificato** su catalogo, e riscontrato con riferimento bit a bit indipendente nei test | <https://reveng.sourceforge.io/crc-catalogue/16.htm> |
| AX.25: ordine dei byte dell'FCS sul filo (byte basso per primo) | **Non verificato su AX.25**: segue HDLC/RFC 1662 App. C (letto); mai confrontato con una cattura reale | RFC 1662 |
| AX.25 bit riservati R dell'SSID: sez. 3.12.1/3.12.2 "se non implementati, posti a uno"; l'encoder li pone a 1, il decoder li accetta (uso concordato lecito) contando `nonstandard_reserved`, o li rifiuta con `strict_reserved=True` | **Verificato** (testo) | AX.25 v2.2 |
| AX.25 con bit C entrambi uguali (v2.0), frame I/S/U non-UI, bit stuffing/flag HDLC | **Non implementati** (rifiutati o fuori livello) | - |
| **KISS**: FEND/FESC/TFEND/TFESC = C0/DB/DC/DD, byte di comando (porta nibble alto), comando 0 = dati, FESC + altro = errore | **Verificato** | <https://www.ax25.net/kiss.aspx> |
| **SLIP**: END/ESC/ESC_END/ESC_ESC = C0/DB/DC/DD | **Verificato** | RFC 1055 |
| **CSP v1**: intestazione 32 bit (pri 2, src 5, dst 5, dport 6, sport 6, flag 8), flag HMAC 0x08 / XTEA 0x04 / RDP 0x02 / CRC32 0x01, ordine di rete, CRC-32C big-endian in coda calcolato sui soli dati | **Verificato sul sorgente di riferimento libcsp v1.6** (non esiste uno standard formale pubblico); nessun codice copiato (LGPL) | <https://github.com/libcsp/libcsp> (`csp_types.h`, `csp_if_kiss.c`, `csp_crc32.c`, `csp_io.c`) |
| CSP: CRC-32C check 0xE3069283 | **Verificato** su catalogo | <https://reveng.sourceforge.io/crc-catalogue/17plus.htm> |
| CSP: interoperabilita' con un nodo reale; HMAC/XTEA (rifiutati); RDP (opaco); l'intestazione NON e' coperta dal CRC (compatibilita' csp1.x) | **Non verificata / non implementati / limite dichiarato** | - |
| Prefisso di lunghezza e delimitatore | Definizioni **locali** (non standard) | - |

Altro **non** verificato: nessuna campagna di fuzzing (passo 8); le proprieta' `decode(encode(x)) == x`
sono cicli con seme fisso (Hypothesis non e' installato); nessun test di interoperabilita' con
implementazioni esterne; nessuna misura di prestazioni; test su Linux soltanto (il test multicast
si salta se l'host non lo supporta: su questo host e' stato eseguito e passato su loopback).

## Canale simulato

`SimChannel` (modello semplificato, deterministico con `seed`, orologio virtuale `VirtualClock`
oppure `now_s` esplicito, nessuno sleep): finestre di contatto `[inizio, fine)` valutate sia
all'invio sia all'istante di arrivo, banda (frame trasmessi uno alla volta), perdita, ritardo +
jitter uniforme `[0, jitter_s]` (mai in anticipo), errori sui bit indipendenti con salto
geometrico (`bit_error_rate` deve essere 0 oppure in [1e-12, 1]: valori minori, anche subnormali, sono rifiutati; `send` e' transazionale: se solleva, contatori, banda e stato casuale tornano come prima). `deliver` restituisce in ordine di **arrivo**: con jitter maggiore della spaziatura i
frame si riordinano (documentato e testato); senza jitter e' FIFO. Invariante testata (200 semi):
`sent == delivered + lost + dropped_outside_window + in_flight`, e a canale drenato senza
`in_flight`. Non modellati: Doppler, fading, errori a raffica, perdita dipendente dalla distanza.

Isolamento del core: il contratto `core-no-network-libs` usa `allow_indirect_imports = False`
(verificato: rileva anche catene indirette core -> modulo -> socket, nessun falso positivo). Gli
altri due contratti restano con `allow_indirect_imports = True`.

## Threat notes (STRIDE-lite per i listener)

| Minaccia | Superficie | Mitigazione nel template | Residuo |
|---|---|---|---|
| **S**poofing | UDP: IP sorgente falsificabile; nessuna autenticazione dei peer | rate limit per IP con tabella limitata; HMAC CSP rifiutato (non finto) | Nessuna autenticazione: serve un livello sopra (TLS/DTLS, firma applicativa; vedi `embedded-security`) |
| **T**ampering | Bit corrotti in transito | CRC (AX.25 FCS, CSP CRC32 sui dati); codec con validazione stretta | KISS e CCSDS Space Packet non hanno integrita'; CRC-32C CSP non copre l'intestazione; un CRC non e' autenticazione |
| **R**epudiation | Nessun log di sicurezza persistente | contatori per listener | Log strutturati/audit: da fare con la pipeline |
| **I**nformation disclosure | Traffico in chiaro; bind pubblico accidentale | bind loopback di default, 0.0.0.0 solo con opt-in esplicito; messaggi di errore senza dati grezzi | Nessun TLS: dati in chiaro su qualunque interfaccia abilitata |
| **D**enial of service | Connessioni, flood, slowloris, datagrammi enormi, tabelle peer | limiti elencati sopra, tutti con contatore e test | Un attaccante con molti IP puo' comunque saturare la CPU; nessun limite per byte/s oltre ai messaggi/s |
| **E**levation of privilege | Parser su dati ostili | niente `eval`/pickle/shell, lunghezze controllate prima della lettura, solo `ProtocolError`, nessun raw socket/promiscuo; core senza rete | Il fuzzing sistematico non e' ancora stato fatto |

Un listener in piu' amplia la superficie d'attacco: attivarne uno e' una decisione dell'operatore.
SO_REUSEADDR sul multicast consente ad altri processi locali di legarsi alla stessa porta.
