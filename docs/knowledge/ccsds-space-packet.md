---
id: ccsds-space-packet
title: CCSDS Space Packet (intestazione di 6 ottetti)
kind: concept
summary: >-
  Il Space Packet CCSDS 133.0-B-2 ha un'intestazione primaria di 6 ottetti (versione 3 bit, tipo,
  flag intestazione secondaria, APID 11 bit, flag di sequenza 2 bit, conteggio di sequenza 14 bit,
  lunghezza dati = ottetti - 1). Il codec del sito e' in backend/net/ccsds.py.
tags: [CCSDS, Space Packet, APID, 133.0-B-2, intestazione, pacchetto, protocollo, rete]
applies_to: [net]
related: [pipeline-guarantees]
level: tecnico
lang: it
last_verified: 2026-10-15
sources:
  - {ref: docs/net.md, supports: "campi dell'intestazione verificati su CCSDS 133.0-B-2 (Blue Book, giugno 2020), sez. 4.1.2 e 4.1.3.2-4.1.3.5"}
  - {ref: "https://public.ccsds.org/Pubs/133x0b2e2.pdf", supports: "standard primario letto il 2026-10-13 secondo docs/net.md"}
  - {ref: backend/net/ccsds.py, supports: "SpacePacket, SpacePacketCodec, SpacePacketFramer"}
---
## Campi (verificati su fonte primaria secondo docs/net.md)

| Campo | Dimensione | Note |
|---|---|---|
| versione | 3 bit | il framer rifiuta versione diversa da 0 |
| tipo | 1 bit | |
| flag intestazione secondaria | 1 bit | |
| APID | 11 bit | l'APID con tutti i bit a uno identifica il pacchetto idle (con flag secondario 0) |
| flag di sequenza | 2 bit | |
| conteggio di sequenza | 14 bit | modulo 16384 |
| lunghezza | 16 bit | numero di ottetti del campo dati meno 1 |

Il campo dati ha da 1 a 65536 ottetti; il pacchetto intero da 7 a 65542 ottetti.

## Cosa NON e' dettato dallo standard / non implementato

- Il pattern del flag di sequenza dei pacchetti idle ('11') e il riempimento 0x00 sono scelte del template, non dello standard.
- Intestazione secondaria, servizio Octet String e gestione dei percorsi non sono implementati: il campo dati e' opaco.
- Il template non trasmette via radio: il canale e' una simulazione software.
