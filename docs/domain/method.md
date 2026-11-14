<!-- SPDX-License-Identifier: Apache-2.0 -->
# Metodo dell'analisi lunare (Fase C)

Codice: `backend/domain/lunar/` (model, visibility, link, energy, mission, runs), API `backend/api/lunar_routes.py`. Tutti i risultati sono **potenziale nelle ipotesi dichiarate**, non una previsione di missione.

**Limiti noti (valgono ovunque):** orizzonte locale piatto con maschera di elevazione (nessun terreno; l'illuminazione polare reale dipende dalla topografia), nessuna atmosfera ne' rifrazione, link budget semplificato (spazio libero, G/T costante, nessun guadagno di codifica verificato).

## Timeline per il Mission Planner

`POST /api/lunar/timeline` accetta la stessa richiesta di `/api/lunar/analyze` e usa lo stesso
calcolo. Restituisce per ogni sito azimut ed elevazione di Sole e Terra, `sun_up`,
`earth_visible`, visibilita' DSN, `link_ok`, margine, `useful`, potenza `gen_w` e carica
`soc`, con `series_time_unix` comune. I valori sono **non mediati**: geometria e potenza
sono valutate all'inizio di ogni passo `[t, t + step_min)`, mentre `soc` e' la carica
alla fine del passo. Gli istanti di transizione sono approssimati alla risoluzione scelta.
Come nel modello esistente, il numero di passi e' `max(1, floor(days * 1440 / step_min))`:
un eventuale resto della durata non e' campionato; se la durata e' piu' breve di un passo,
l'unico passo si estende oltre la durata richiesta.

Il limite `max_total_points` restituito da `/api/lunar/defaults` vale anche qui:
`n_steps * numero_siti * timeline_series_per_site` non puo' superarlo. Una richiesta troppo
grande riceve 422, senza decimazione silenziosa; ridurre durata o siti oppure aumentare il passo.
Il margine e' `null` quando la Terra non e' visibile; `link_ok` include visibilita' Terra,
disponibilita' di almeno una stazione DSN e soglia del modello RF semplificato. Non rappresenta
la diffrazione di GrazingLink. Il terreno e le ombre topografiche non sono modellati: questa
timeline e' una base didattica provvisoria, non una stima dell'orizzonte reale.
La stima energetica usa la stessa ipotesi di Sole su orizzonte piatto e il link lunare
semplificato per il carico di comunicazione: il confronto DEM solare sperimentale e il
confronto RF GrazingLink non modificano il risultato energetico.

Il risultato `solar-terrain` include anche una **sensibilita' energetica ipotetica**, separata
e non sostitutiva: per ciascun passo la potenza del pannello e' quella della timeline (stessa
irradianza, stessa incidenza) moltiplicata per la **frazione visibile del disco solare** contro
la maschera d'orizzonte (disco uniforme, nessun oscuramento al bordo); la maschera piatta della
timeline non si applica (una cima puo' vedere il Sole poco sotto l'orizzonte astronomico).
Ripete il modello esistente della batteria con lo stesso carico e link lunare semplificato.
Se anche un solo passo ha frazione del disco ignota, **nessuna** storia della batteria o metrica
aggregata viene prodotta per quel sito. Il limite di 240 passi vale anche per questa sensibilita'.

`POST /api/lunar/solar-terrain` accetta la richiesta della timeline piu' `observer_height_m`
(0-100 m, default 2 m, tag I) e, per ogni istante, confronta il Sole con la **maschera
d'orizzonte del sito** (`backend/domain/grazing/horizon.py`): 1440 azimut, LDEM_85S_20M a passo
10 m fino a 10 km, poi LDEM_75S_240M a passo 120 m fino a 200 km, interpolazione bilineare,
curvatura della sfera di 1737,4 km inclusa, occhio a `observer_height_m` sopra il suolo
interpolato. La maschera e' calcolata una volta per (sito, altezza) in 0,2-0,5 s e poi letta
dalla cache in memoria o su disco (`build/lola/horizon/`); il tetto di richieste concorrenti e'
quello delle altre rotte lunari. Per ogni passo riporta: `state` (bordo superiore sopra o sotto
la maschera; nomi storici `upper_above_profile` / `upper_below_profile` mantenuti),
`upper_limb_visible`, `centre_visible`, `lower_limb_visible`, `disc_fraction` (frazione visibile
del disco, 48 strisce verticali, semidiametro dalla distanza reale del Sole), `horizon_deg`
(maschera all'azimut del centro) e, per sito, `mask` (prodotti e hash, passi, frazione di azimut
completi, frazione in cui domina il terreno oltre 10 km, tempo di calcolo, origine dalla cache).
I campi `centre_above_profile` e `lower_above_profile` restano come alias compatibili.
`assumptions.coverage_limits` dichiara i limiti.

Usa **solo tile gia' in cache** (`python -m backend.domain.grazing.prefetch` li scarica per i
siti del registro: 22,8 MB a 20 m, 18,1 MB a 240 m). Un campione DEM assente rende l'azimut
incompleto: un criterio vero che dipende da un azimut incompleto diventa `null` (stato
`missing_dem`), mentre un "sotto la maschera" resta noto (altro terreno puo' solo nascondere di
piu'); `outside_coverage` se il sito e' fuori dal prodotto a 20 m. Mai un orizzonte libero
inventato.

**Altezza dell'osservatore** (sensibilita' misurata, 2027, `docs/domain/validation.md`):
Malapert, disco medio 31,0 % a 0 m, 33,0 % a 2 m, 45,9 % a 10 m; Nobile 34,5 / 34,5 / 34,6 %;
Haworth, de Gerlache e Shackleton 0 % a tutte e tre le altezze. Il valore di default 2 m e'
illustrativo (altezza tipica di pannelli su un lander), non un dato di missione.

Non modellati: terreno oltre 200 km, incertezza verticale del DEM e rilievo sotto il pixel,
oscuramento al bordo del disco, il lander stesso. La maschera e' confrontata con un'implementazione
indipendente (`scripts/solar_horizon_arbiter.py`: nel 2027 i cinque siti concordano entro 1 passo
su 4380) e, vicino al polo, con le mappe osservative LROC WAC; non e' una previsione di missione.
Il motore usa `MOON_ME_DE440_ME421`, azimut da Nord verso Est e DE440, gia' confrontati con JPL
Horizons in `tests/backend/ephemeris/test_validation.py`. Fino al 2026-11-04 l'endpoint usava un
solo profilo di 10 km lungo l'azimut del Sole, che nei centri di Haworth e de Gerlache non
raggiungeva il bordo del cratere e li dava illuminati nel 22-35 % dei passi.


**Missione accoppiata** (`POST /api/lunar/mission`, `backend/domain/lunar/coupled.py`): un sito
(`site_id`, eventuale `custom_site`), `start_utc`, `days` (<= 90), `step_min` (>= 10), al massimo
1500 passi; `observer_height_m` (default 2 m, I), `rate_bps`, `station` (`dsn34` o `dsn18`),
`rf_overrides` (parametri GrazingLink) ed `energy_overrides`. A ogni passo: frazione visibile del
disco dalla maschera d'orizzonte -> potenza del pannello (`terrain_energy.terrain_generation_w`)
-> batteria (`energy.simulate_energy`, con il modo "solo comunicazioni" quando il pannello copre
sopravvivenza + comunicazioni ma non il carico attivo) -> margine RF GrazingLink al bitrate scelto
(terreno LOLA lungo l'azimut della Terra, crinale dominante, lama + cilindro ITU-R P.526-9) ->
visibilita' geometrica DSN 34 m. `link_usable` = margine >= 0 E DSN visibile; `useful` = stato
operativo E `link_usable`. Stati: `operational`, `comms_only`, `survival`, `dark` (carico non
servito: blackout), `unknown`. Ogni ingresso ignoto (DEM mancante, RF non calcolato o non
sincronizzato, stazione 18 m di cui non si conosce la visibilita') rende ignoto quel passo e,
poiche' la batteria ne dipende, tutti i successivi: nulla di ignoto e' contato come utile. Obiettivi:
ore utili, ore ignote, ore per stato, frazioni limitate da energia / link / visibilita' / piu'
cause, SOC minimo (sui soli passi noti, dichiarato), tempo al primo blackout. Ogni parametro ha
la sua etichetta V/D/I; la risposta riporta i limiti (ostacolo singolo per l'RF, maschera a
200 km per le ombre, carichi illustrativi). Errori: 422 generico, 503 senza efemeridi o oltre il
tetto di richieste concorrenti; i risultati sono in cache LRU. Prova di regressione
(`tests/backend/domain/test_lunar_mission_api.py`, 2027-01-01, 30 giorni a 60 min): Haworth ha
disco visibile 0 in ogni passo, 0 ore utili e un blackout; Malapert ha ore di Sole e ore utili.
Il Mission Planner la mostra come una timeline unica (stato e passi utili), con spiegazione
semplice nel percorso guidato e numeri, parametri e limiti nel percorso avanzato. Sostituisce nel
Planner lo "scenario combinato" (`/api/lunar/coupled-sensitivity`, che resta disponibile).

`POST /api/lunar/horizon`, con `site_id` e `observer_height_m` (0–100 m), espone 72 profili
campionati ogni 5 gradi; per ognuno riporta angolo, distanza e stato. Le direzioni tra i profili
non sono interpolate; i dati assenti restano espliciti. Questo profilo circolare non e' usato per
approssimare la timeline solare, che campiona direttamente ciascun azimut solare.

Il confronto radio opzionale usa `POST /api/grazing/compare` con `timeline: true`.
Per ogni sito coperto aggiunge `window_samples`: tempi, visibilita' geometrica rispetto al crinale,
stato del link al bitrate scelto, margine e bitrate dichiarato dal compensatore, ai passi originali
e non decimati. Rimangono validi i limiti gia' applicati al confronto GrazingLink (1500 passi per
sito e 6000 totali); siti fuori DEM non hanno campioni. Il planner mostra i campioni solo se gli
istanti coincidono con la timeline lunare. I risultati restano distinti: il link semplificato lunare
include la visibilita' DSN, mentre GrazingLink include terreno e diffrazione secondo le proprie
ipotesi e non va interpretato come lo stesso link.

Il Planner mostra anche l'intersezione dei campioni RF GrazingLink e della visibilita' geometrica
di almeno uno dei tre complessi DSN da 34 m. E' una **sovrapposizione indicativa**, non un
budget unificato o un contatto operativo: la stazione RF e' una classe di antenna generica,
non un'antenna assegnata, e non sono modellati pianificazione e disponibilita' DSN. Il modello
energetico continua a usare il collegamento lunare semplificato, non questa intersezione.
Per la configurazione RF da 18 m la sovrapposizione non viene calcolata, poiche' la timeline
DSN usa soltanto antenne da 34 m; campioni RF mancanti o non sincronizzati restano sconosciuti.

Il Planner permette di dichiarare una priorita' e soglie percentuali opzionali, senza
modificare il modello ne' produrre una classifica aggregata. La soglia di luce si confronta
con `sun_fraction` del modello a orizzonte piatto; quella RF con la frazione di campioni
`link_ok` del confronto GrazingLink al bitrate scelto. La soglia RF resta non disponibile
se mancano copertura o campioni sincronizzati, non viene trattata come non rispettata.
Le percentuali descrivono i passi simulati, non una garanzia sulla durata richiesta ne' una
validazione delle condizioni reali.

Legenda parametri: **V** letto da fonte primaria, **D** derivato con formula ripetibile, **I** illustrativo (nessuna fonte, da sostituire con i dati del cliente). Tutti i parametri sono modificabili nell'API (`overrides`) entro limiti validati; la tabella completa con limiti e fonti e' in `GET /api/lunar/defaults`.

## 1. Geometria (motore validato)

Un solo calcolo vettoriale per sito e corpo con `backend.ephemeris` (az/el apparenti, DE440, sfera 1737.4 km, vedi `docs/ephemeris.md`). Ogni passo i rappresenta [t_i, t_i + dt); la geometria e' campionata all'inizio del passo.

- **Sole su**: `el_centro + 0.27 deg >= maschera_sole` (semidiametro solare 0.27 deg, esplicito: conta il bordo superiore). Maschera di default 0 deg (I).
- **Terra visibile**: `el_centro >= maschera_terra` (default 0 deg, I). Il disco terrestre (semidiametro ~0.95 deg) NON e' aggiunto.
- **Luna visibile dalla Terra**: elevazione della Luna >= 6 deg (V, DSN 810-005/301 Rev. P sez. 2.2.2-2.2.3) ad almeno uno dei complessi Goldstone (DSS-24), Canberra (DSS-34), Madrid (DSS-54). Coordinate geodetiche WGS 84 dalla Tab. 5 di DSN 810-005 Module 301 Rev. P, https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf, accesso 2026-10-20, `verified: true`. Il motore calcola osservatori terrestri con `topocentric_azel("earth", ...)`: nessuna modifica a `backend/ephemeris`.

## 2. Collegamento

```
FSPL_dB    = 20 log10(4 pi d / lambda),  lambda = c / f        [d in m]
EIRP_dBW   = 10 log10(P_W) + G_tx_dBi
C/N0_dBHz  = EIRP - FSPL - L_punt - L_altre + G/T + 228.6      [k = -228.6 dBW/K/Hz]
Eb/N0_dB   = C/N0 - 10 log10(R_bps) - L_impl
margine_dB = Eb/N0 - Eb/N0_richiesto
```
Con il guadagno da diametro `D` (se > 0): `G = 10 log10(eta (pi D / lambda)^2)`. La FSPL coincide con `92.45 + 20 log10(d_km) + 20 log10(f_GHz)` del plugin fspl-c a meno di una **costante di +0.0022 dB** (la costante esatta e' 92.44778): 210.994 dB (plugin) contro 210.992 dB (esatta) a 384400 km e 2.2 GHz. L'analisi usa la forma esatta. `d` e' la distanza astrometrica sito-Terra del motore (355 685-407 000 km circa).

| Parametro | Default | Stato | Fonte |
|---|---|---|---|
| frequency_ghz | 8.425 GHz (banda X) | V | DSN 810-005/104 Rev. Q Tab. 7 |
| tx_power_w | 20 W | I | illustrative (TP-2019-220391 documenta 61 W come esempio) |
| tx_antenna_gain_dbi | 20 dBi | I | illustrative |
| tx_dish_diameter_m / tx_aperture_efficiency | 0 (non usato) / 0.55 | I | illustrative |
| pointing_loss_db, other_losses_db | 1, 1 dB | I | illustrative |
| ground_gt_dbk | 54.1 dB/K | D | 68.29 dBi - 10 log10(26.2 K), DSN 810-005/104 Rev. Q (S-band: 42.3) |
| data_rate_bps | 4000 | V | NASA/TP-2019-220391 sez. 11 (TBR) |
| required_ebn0_db | 9.6 dB | D | BPSK non codificato, BER 1e-5 = 9.59 dB (Proakis) |
| implementation_loss_db | 2 dB | I | illustrative |
| required_margin_db | 3 dB | V | NASA/TP-2019-220391 sez. 11 |
| earth_site_elevation_mask_deg | 0 deg | I | illustrative |
| ground_station_min_elevation_deg | 6 deg | V | DSN 810-005/301 Rev. P |

## 3. Energia

```
S = 1360.8 / r_AU^2                              [W/m2; Kopp & Lean 2011, SORCE/TIM; r = distanza Sole-Luna del motore]
cos(inc) = max(0, n . s)                         [n normale del pannello, s direzione del Sole, in ENU locale]
P = S A eta k (1 - deg) cos(inc)   se Sole su, 0 altrimenti
```
Orientamenti: `horizontal` (n = zenit, cos = sin el), `tilted` (`tilt_deg` dall'orizzontale, `tilt_azimuth_deg` della normale), `tracking` (cos = 1 con Sole su).

Per passo (dt in h): `diretto = min(P, carico)`; surplus carica `+eta_c * surplus * dt` fino alla capacita' (il resto e' scartato); deficit scarica `deficit * dt / eta_d` limitata dall'energia presente (il resto e' "non servito"). Modalita': **operativa** (`active_load_w` piu', se il link e' disponibile, la potenza media di comunicazione `comms_duty * tx_power_w / pa_efficiency`) quando il pannello copre il carico operativo OPPURE l'energia e' sopra la riserva `min_soc`; altrimenti **sopravvivenza** (`survival_load_w`). Questa e' la definizione di "energia disponibile": rispetto a "Sole su OR SOC sopra la riserva" richiede che il pannello copra davvero il carico (un Sole radente con 1 W non conta).

| Parametro | Default | Stato | Fonte |
|---|---|---|---|
| array_area_m2 | 1 m2 | I | illustrative |
| cell_efficiency | 0.295 | V | NASA SoA Power 2022 Tab. 3-1 |
| packing_factor | 0.80 | I | illustrative |
| degradation_fraction | 0.02 | I | illustrative (1-3 %/anno, tassi non quantificati dalla fonte) |
| orientation, tilt_deg, tilt_azimuth_deg | horizontal, 0, 0 | I | illustrative |
| sun_elevation_mask_deg | 0 deg | I | illustrative |
| battery_capacity_wh | 10000 Wh (~83 kg a 120 Wh/kg) | I | illustrative |
| charge/discharge_efficiency | 0.95 / 0.95 | I | illustrative (round trip 0.90) |
| min_soc, initial_soc | 0.2, 1.0 | I | illustrative |
| survival_load_w, active_load_w | 10 W, 50 W | I | illustrative |
| pa_efficiency | 0.5545 | D | 61 W RF / 110 W DC, TP-2019-220391 sez. 11.6.7 |
| comms_duty | 0.25 | I | illustrative |

## 4. Ore utili e classifica

Passo **utile** = energia disponibile AND Terra visibile AND Luna visibile da un complesso DSN AND margine >= richiesto. Metriche per sito: `useful_hours`, `useful_fraction`, `longest_gap_h`, `n_windows`, margine medio/minimo (sui passi con Terra visibile), `sun_fraction`, `earth_fraction`, frazioni DSN e link, energia (raccolta, ore di Sole, buio piu' lungo, SOC minimo, sopravvissuta si/no, energia non servita).

Classifica: `score = sum_k w_k c_k/max_siti(c_k) / sum_k w_k`, con `c_1 = useful_fraction`, `c_2 = SOC minimo`, pesi 1 e 1 (parametri). Le componenti, normalizzate e non, sono sempre restituite. La regola e' una scelta di progetto (I).

## 5. Come leggere i risultati

- Il confronto tra siti e' piu' robusto del valore assoluto. Con i default il margine e' ~43 dB: la comunicazione non limita, limitano visibilita' della Terra ed energia.
- Il SOC minimo 0 significa batteria esaurita nella finestra; `survived: false` indica energia non servita.
- Ai poli i risultati con pannello orizzontale sono pessimistici (Sole radente); provare `tracking` o `tilted`. L'ombreggiatura del terreno, non modellata, puo' invece peggiorare i risultati reali.
- La finestra tronca i cicli: una finestra di 29.53 d non e' allineata a un mese sinodico vero (29.27-29.83 d).

## 6. Esempio svolto (motore reale)

Finestra 2027-04-07T00:00:00Z, 29.53 d, passo 10 min, parametri di default (tabelle sopra), orientamento orizzontale.

| Sito | ore utili (frazione) | Sole | Terra | SOC min | sopravvive |
|---|---|---|---|---|---|
| apollo11 | 0.833 | 0.502 | 1.000 | 0.078 | si |
| apollo17 | 0.817 | 0.505 | 1.000 | 0.063 | si |
| malapert-massif | 0.182 | 0.404 | 0.712 | 0.000 | no |
| haworth | 0.182 | 0.342 | 0.635 | 0.000 | no |
| mons-mouton | 0.195 | 0.431 | 0.756 | 0.000 | no |
| nobile-rim | 0.200 | 0.421 | 0.654 | 0.000 | no |
| de-gerlache | 0.182 | 0.184 | 0.521 | 0.000 | no |
| shackleton | 0.182 | 0.000 | 0.508 | 0.000 | no |

Margine minimo/medio 43.0/43.5 dB. Classifica a pesi uguali: apollo11 1.00, apollo17 0.896, poi nobile-rim 0.12, mons-mouton 0.117 e gli altri ~0.109. Le ore utili polari (0.18-0.20) sono quasi tutte ore di sola sopravvivenza/operativita' a batteria prima dell'esaurimento: i poli con pannello orizzontale non rigenerano energia (raccolta 0-4 kWh contro ~70 kWh equatoriali).

Singolo passo, link: 384400 km, 8.425 GHz: FSPL 222.655 dB, EIRP 33.010 dBW, C/N0 91.055 dBHz, Eb/N0 53.035 dB, margine 43.435 dB (test `test_lunar_knowledge.py`).
