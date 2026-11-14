---
id: az-el-convention
title: Convenzione azimut/elevazione di Sole e Terra nella scena 3D
kind: method
summary: >-
  Sole e Terra sono dati come azimut (0 = nord, orario) ed elevazione (0 = orizzonte) in gradi;
  la scena li converte in un vettore unitario con x = est, y = su, z = sud:
  [cos(el)*sin(az), sin(el), -cos(el)*cos(az)].
tags: [azimut, elevazione, az_deg, el_deg, sole, terra, scena 3D, azElToVector, vettore]
applies_to: [viewer, telemetry]
related: [glossary-azimuth, glossary-elevation, telemetry-contract, glossary-terminator]
level: tecnico
lang: it
last_verified: 2026-10-15
sources:
  - {ref: frontend/src/viewports/scene.ts, supports: "funzione azElToVector e descrizione testuale describeScene"}
  - {ref: contracts/telemetry.schema.json, supports: "oggetti sun e earth con az_deg ed el_deg"}
---
## Conversione

`azElToVector({az_deg, el_deg})` restituisce un vettore unitario `[x, y, z]` con gli assi
x = est, y = su, z = sud:

- x = cos(el) * sin(az)
- y = sin(el)
- z = -cos(el) * cos(az)

Gli angoli in ingresso sono in gradi e vengono convertiti in radianti (moltiplicando per pi/180).

## Casi di controllo

- az = 0, el = 0 (nord, sull'orizzonte): [0, 0, -1]; il nord e' quindi l'asse -z.
- az = 90, el = 0 (est): [1, 0, 0].
- el = 90 (zenit): [0, 1, 0], qualunque sia l'azimut.

## Sotto l'orizzonte

Un'elevazione negativa vuol dire che l'astro e' sotto l'orizzonte; la descrizione testuale della
scena (`describeScene`) lo indica con la dicitura "(sotto l'orizzonte)".
