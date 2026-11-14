# RAVEN: differenze intenzionali rispetto ai motori precedenti

## Correzioni 1.4: raggi polari, creste e disco solare (2026-11-08)

`raven-core-1.4` usa una rotazione cartesiana condivisa per profili, maschere
e impronte di download. Ai poli la vecchia formula faceva collassare raggi
diversi sulle longitudini +/-90 gradi. La maschera passa a
`raven-horizon-v2`: le cache precedenti non sono riutilizzate.
Il fit di curvatura richiede un apice interno ai campioni disponibili;
terreno lineare non diventa una cresta risolta per arrotondamento numerico.
Questo puo' rendere ignoti altri margini RF prima calcolati con raggi extrapolati.

S3 integra l'area esatta sopra ogni tratto lineare della maschera, dividendo
le 48 strisce di base ai nodi di interpolazione. Il precedente orizzonte
costante al centro della striscia inventava luce anche con un disco interamente
coperto da un orizzonte inclinato. Si controllano tutti i bin attraversati.
Proiezioni parziali prossime allo zenit fuori dal dominio restano ignote.

Queste sono verifiche numeriche, non nuove misure: S2 resta non validato
fisicamente e S3 solo plausibilita'. Il registro e gli archivi non cambiano.
La riproduzione LROC usa ora l'archivio NASA PDS migrato, con lo stesso SHA-256.
Evidenze e porte ancora aperte: `docs/domain/validation.md`,
sezione «S2/S3 closure attempt and numerical corrections».

## Correzioni 1.3: SOC, cause ignote, curvatura e risultato RF (2026-11-08)

`raven-core-1.3` include lo SOC iniziale nel minimo sul prefisso energetico noto
e attribuisce una causa limitante S7 solo a un falso esplicito, non a un ignoto.
Il fit S2 usa quote relative: terreno costante a quota negativa non produce
piu' un raggio numerico enorme spacciato per risolto.
Se nu e' positivo, manca un raggio finito e la correzione arrotondata e' attiva,
S5 restituisce `outside_model` con margine ignoto. La lama senza correzione
resta disponibile solo quando viene scelta esplicitamente; nessun fallback automatico.
I passi cinematici del gimbal restano continui e un blocco noto da terreno lontano
non viene trasformato in ignoto.

Questo cambia intenzionalmente alcuni risultati reali precedentemente presentati
come margini completi, inclusi de Gerlache e Shackleton al 2027-04-07 00:00 UTC.
Le scene mantengono terreno, camera e puntamento ma non mostrano margini legacy
quando il margine corrente e' nullo. Esportazione e puntamento conservano l'ignoto.
La matrice separa le nuove prove aritmetiche S2/S7 dalla qualificazione fisica.
Il registro non cambia; gli archivi 1.2 restano storici. Prove e limiti:
`docs/domain/validation.md`, sezione «Remaining-stage arithmetic and applicability corrections».

Registro richiesto da `docs/domain/raven-model.md` (4.1). Ogni riga è una scelta di progetto con un test che fissa il nuovo valore.
Valgono solo per la catena nuova (`backend/domain/raven`, `/api/raven/*`). Gli endpoint `/api/lunar/*` e `/api/grazing/*` restano sui
numeri precedenti (congelati dai golden `tests/backend/domain/golden/`) finché non diventano adattatori (M11, M15).

| Data | Decisione | Prima | Dopo | Test |
|---|---|---|---|---|
| 2026-11-05 | D2 set radio unico | lunare 8,425 GHz, G/T 54,1 dB/K, Eb/N0 9,6 dB, 20 W, 20 dBi; GrazingLink 8,4 GHz, stazione 68 dBi, Tsys 30 K, Eb/N0 2,5 dB, 10 dBW, 15 dBi, perdite 3 dB | 8,425 GHz (V), stazione 68,29 dBi (D), Tsys 26,2 K (V), Eb/N0 9,6 dB (D, non codificato), preset codificato 2,5 dB (I); 10 dBW, 15 dBi, perdite 3 dB (I). Il carico radio della batteria usa 10 W (prima 20 W nel solo modello energetico) | `test_m8_unification.py::test_d2_*`, `test_unified_margin_differs_from_legacy_by_the_analytic_amount` |
| 2026-11-05 | D3 soglia del link utilizzabile | margine >= 0 (missione, confronto GrazingLink), >= 3 dB (vecchio B5) | `rf.required_margin_db` = 3 dB (V, TP-2019-220391 §11); «margine >= 0» resta il confine fisico mostrato a parte | `test_d3_*`, `test_threshold_3_db_changes_the_usable_decision` |
| 2026-11-05 | D4 terreno lontano oltre il profilo RF | ignorato (solo ostacolo dominante entro 10 km) | perdita a lama dell'ostacolo lontano >= 30 dB (I): `blocked_far_terrain`, NOTO «no»; < 30 dB: `outside_model`, ignoto | `test_s2_s3.py::test_far_terrain_*`, `test_s5.py` |
| 2026-11-05 | D7 «luce» | quattro criteri | `disc_fraction > 0`; potenza sempre con la frazione del disco | `test_s2_s3.py::test_lit_rule_*` |
| 2026-11-05 | D8 altezze | `observer_height_m` (0-100, 2) e `antenna_height_m` (0,1-100, 2) | `rf.panel_height_m` e `rf.antenna_height_m`, due parametri, intervallo 0,1-100, default 2 m (I) | `test_d8_*`, `test_raven_api.py` |
| 2026-11-05 | D9 tetti | lunare 20000 punti, grazing 5000 campioni (uscita decimata a 1500), mission 1500 | 1500 passi per sito, 6000 in totale, nessuna decimazione, 422 oltre il tetto; la finestra lunare di default (29,53 d a 10 min = 4252 passi) è fuori tetto | `test_s0_context.py::test_cap_*`, `test_raven_api.py` |
| 2026-11-05 | C1/C3/C11 | Sole su orizzonte piatto con 0,27 fisso | nella catena nuova esiste solo la maschera LOLA e il semidiametro vero per istante | `test_s1_geometry.py`, `test_s2_s3.py` |

| 2026-11-05 | D5 classifica unica | `/api/lunar/analyze` (media pesata normalizzata, colonna «Punteggio») e `/api/grazing/compare` (lessicografica: ore reali, margine mediano, id) | `/api/raven/compare` usa `raven/ranking.py`: lessicografica su componenti scelti dall'utente (default: ore utili, ore ignote, margine minimo), pareggi per id dichiarato, nessun punteggio; i siti con componenti ignoti stanno in `not_comparable` con il motivo; un sito con tutti i passi bloccati da terreno lontano noto (margine senza numero) è l'ultimo, non ignoto | `test_ranking.py`, `test_raven_api.py::test_compare_*` |

**Endpoint vecchi che restano com'erano** (golden): `/api/lunar/analyze` e `/api/lunar/compare`-equivalenti (punteggio pesato) e `/api/grazing/compare`
(ore reali, margine mediano) conservano il proprio ordinamento e il proprio contratto; la differenza con la classifica unica è voluta e dura fino
a M11/M15. Le tre classifiche possono dare ordini diversi sugli stessi siti perché usano insiemi di parametri e definizioni di «ora utile» diversi
(C6, C7 di raven-model.md).

Viste (`/api/raven/snapshot`, `/scene`, `/horizon`): con il set radio precedente, geometria, margine, stato e elevazioni DSN sono uguali a
`/api/grazing/snapshot` e `/scene` (test); l'unica differenza è lo stato dei siti coperti da terreno lontano (D4, es. Haworth): `blocked` noto o `unknown`
al posto di `open`/`transition`. Con il set unificato (default dell'API) i margini differiscono per D2.

Non ancora applicato: D6 (410 dei vecchi endpoint, M15).

**Aggiornamento 2026-11-08:** D6 e' applicato: gli endpoint legacy in produzione rispondono 410;
gli oracoli congelati sono solo test. Il compensatore k e' di nuovo collegato alla selezione
prudenziale del bitrate, non al margine fisico a bitrate fisso.

## Correzione multipath e identita' del modello (2026-11-08)

`raven-core-1.1` corregge l'applicabilita' del multipath sotto 0,05 gradi: la distanza
speculare usa l'angolo reale, non il limite numerico della correzione coerente. Con antenna
2 m, elevazione 0,01 gradi e crinale a 5000 m il punto e' oltre il crinale (11 459 m), quindi
il termine e' escluso; prima veniva applicato. Python e specchio TypeScript concordano.
Prove: `test_multipath.py::test_numeric_angle_floor_does_not_move_the_specular_point`,
`simula/linkModel.test.ts`, 32 vettori di parita'. Non e' nuova validazione fisica.

Il registro dei parametri non cambia, ma la versione si': i risultati `raven-core-1` non
vengono ripristinati come correnti nel Planner. La cronologia Dashboard conserva gli
archivi compatibili con il registro in sola lettura e dichiara la versione originale.

## Area del disco solare (2026-11-08)

`raven-core-1.2` sostituisce i rettangoli al punto medio con l'area circolare esatta
di ciascuna delle 48 strisce, mantenendo il campionamento dell'orizzonte.
Una falce con raggio 0,27 gradi e centro a -0,26999 gradi sopra un orizzonte piatto
non viene piu' classificata come frazione zero. Generazione ed energia S4 ricevono
la nuova frazione; RF, parametri e hash del registro non cambiano.
Il cambio di versione impedisce di ricalcolare silenziosamente un archivio 1.1.
Residui e limiti sono in `validation.md`; non e' una nuova misura lunare.

## Differenze introdotte dalla migrazione del frontend (M10-M12, 2026-11-05)

| Cambiamento | Prima | Dopo | Test |
|---|---|---|---|
| Timeline del Planner | Sole e Terra sopra un orizzonte piatto (`/api/lunar/timeline`) | Sole e Terra sopra la maschera LOLA del modello unico; passo e finestra con i tetti D9 (1500/6000), default 7 giorni a 10 minuti | `planner/ravenAdapter.test.ts` |
| Compensatore k nel Planner e nel Confronto | k scelto dall'utente, bit-rate «sostenibile», interruzioni | assente: il compensatore è ricerca (GrazingLink), non una fase della catena; il bit-rate è quello scelto | `compare/ravenCompare.test.ts` |
| Stazione 18 m nel set unificato | (non definito) | guadagno 62,5 dBi dalla tabella (I); 68,29 dBi (D) solo per la 34 m | `test_raven_api.py::test_station_18m_*` |
| Specchio TS di Simula | 8,4 GHz, 68 dBi, Tsys 30 K, Eb/N0 2,5 dB | 8,425 GHz, 68,29 dBi, Tsys 26,2 K, Eb/N0 9,6 dB dal registro; tolleranza 0,01 dB sulla fixture del motore Python | `simula/linkModel.test.ts`, `test_link_parity_fixture_*` |
| Soglia «link utilizzabile» in Simula | margine >= 0 | il margine mostrato è fisico (>= 0 chiude); la soglia di 3 dB del modello vale per «utile» nelle pagine con missione | (D3) |

Aggiunte all'API `raven` (nessun endpoint legacy toccato):
`GET /api/raven/sites` (catalogo, copertura DEM, efemeridi), `parameters_used` in `evaluate`/`compare`, `energy_orientations` in `/parameters`,
`lat_deg`/`lon_deg_east` per orizzonte e scena di un sito personale, `gain_dbi` in `snapshot` e `scene`, `model_version`/`registry_sha256` in scene,
snapshot, orizzonte e compensazione, `GET /api/raven/compensation`. Test in `tests/backend/api/test_raven_api.py`.

### `/api/raven/snapshot`: distanza Terra-Luna e delta FSPL (2026-11-06)

Il corpo della risposta ora contiene `earth_moon_range_km` (distanza vera centro Terra-centro Luna all'istante, dalle efemeridi) e
`fspl_delta_db` (`20 log10(distanza / 384400 km)`, riferimento `reference_range_km`), come l'endpoint legacy. Mancavano dopo la migrazione e
`parseSnapshot` del Viewer rifiutava la risposta, quindi il testo `fspl-delta` spariva. Test: `test_views.py::test_snapshot_carries_the_true_earth_moon_range_and_its_fspl_delta`.

## 10 nov 2026 (sera): catalogo siti da 8 a 14, vista per giorno lunare, numeri chiave, mappa polare 2D
- `backend/domain/data/sites.json`: aggiunti Apollo 12, 14, 15, 16 (coordinate del Lunar Module dalla pagina NSSDCA, stessa fonte e
  stesso sistema di Apollo 11 e 17), Chang'e 4 (Statio Tianhe) e Chandrayaan-3 (Statio Shiv Shakti) dal Gazetteer IAU/USGS
  (centro della stazione, `coordinate_basis: feature_centre`, non un'ellisse di atterraggio). Altri programmi: nessuna coordinata
  senza fonte primaria letta. Il terreno di questi siti è ignoto (nessuna tessera LOLA oltre il limite di latitudine): resta ignoto.
- Golden `lunar_sites` e `grazing_snapshot`: aggiornati SOLO con l'aggiunta delle sei voci in coda; nessun numero esistente è cambiato
  (una rigenerazione completa in questo ambiente dava differenze numeriche non spiegate sull'orizzonte e non è stata accettata).
- Frontend: `visibilityStats.ts` (elevazione del Sole, ore, sequenze continue più lunghe, conto alla rovescia a tramonto e Earthset
  all'inizio della finestra, giorni lunari di 29,53 d), `SitePolarMap.svelte` (mappa polare 2D cliccabile nel passo Siti),
  report: numeri chiave e vista per giorno lunare nella parte 2.

### Catalogo a 51 siti e terreno globale per i siti fuori dal prodotto a 20 m (10 nov 2026, sera)
Altri 15 atterraggi robotici dalla tabella NSSDCA "lunar artifact landings and impacts" (Luna 9, 13, 16, 17, 20, 21, 23, 24;
Surveyor 1, 3, 5, 6, 7; Chang'e 3 e 5; sistema DE421, longitudine ovest scritta come est negativa). Decisione dell'utente: un sito
del catalogo fuori dal prodotto a 20 m (`dem_coverage` falso) è valutato da `/api/raven/evaluate` col terreno globale a 237 m, con
la stessa conferma esplicita del download (409 prima) dei siti personalizzati; identità, nome e fonte restano quelli del catalogo.
`/api/raven/compare` NON lo fa: la classifica confronta solo siti sullo stesso prodotto di terreno. Scena 3D e orizzonte restano
solo per i siti coperti a 20 m. Cambia il comportamento di Apollo 11 e simili in `/evaluate` (prima: tutto ignoto, ora: terreno noto
a 237 m dopo il consenso); test `test_catalogue_site_outside_the_polar_product_gets_downloaded_terrain`.

### Catalogo a 36 siti (10 nov 2026, sera)
Aggiunti 22 siti dal Gazetteer IAU/USGS (centro della feature, letto il 10 nov 2026; planetografico est-positivo): 21 crateri
del polo sud (Amundsen, Cabeus, Bay, Brill, Burbidge, Cartwright, Boguslawsky, Boussingault, Casatus, Boltzmann, Bailly, Brashear,
Antoniadi, Alekhin, Ashbrook, Braude, Blancanus, Bettinus, Berlage, Cabannes, Bellinsgauzen) e Chang'e 6 (Statio Tianjiang).
Copertura del terreno (stato in questo ambiente): solo Brill ha le tessere LOLA a 20 m in cache; Cabeus, Bay, Burbidge e Cartwright
sono nel prodotto a 20 m ma le loro tessere non sono in cache (stato "unavailable" nello snapshot, terreno `missing_dem` nel motore);
gli altri 21 sono fuori dal prodotto a 20 m (terreno `outside_coverage`: solo geometria di Sole e Terra, il resto ignoto). Per
calcolarli con il terreno globale a 237 m si inseriscono come coordinate personalizzate. Lo snapshot legacy ora degrada per sito
(una tessera mancante non produce più un 503 su tutto). Il test snapshot reale accetta "unavailable" solo per i siti coperti senza tessera.
