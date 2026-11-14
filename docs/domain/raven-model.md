<!-- SPDX-License-Identifier: Apache-2.0 -->
# RAVEN Core Model: un solo modello per tutto il sito

Stato: **progetto**, 2026-11-04. Nessun codice è stato cambiato. Richiesta dell'utente (decisioni del 4 novembre,
`docs/process/decisions-2026-11-04.md`): «Ci sono troppi motori paralleli: va racchiuso tutto in un modello unico
per l'intero sito, in modo che sia spiegabile alla giuria che potrebbe farci domande sulla validazione dei dati».

Letti per questo progetto: `docs/process/{decisions,gap-analysis}-2026-11-04.md` (§1, §5 contraddizioni, §6 rischi),
`docs/domain/{method,validation,assumptions,grazinglink-model}.md`, `backend/domain/lunar/*`, `backend/domain/grazing/*`,
`backend/ephemeris/*`, `backend/api/{lunar,grazing,sky}_routes.py`, le pagine `frontend/src/pages/{planner,simula,
compare,lander,wave,viewer,analizza,siti,home,grazinglink,telemetry}`, i plugin `fspl_c`, `servo_ctrl_c`,
`grazinglink_link`, `.importlinter`, `contracts/gen.py`, `frontend/scripts/check-bundle.mjs` e, nella cartella di
ricerca, DA (`DESCRIZIONE AGGIORNATA PROGETTO.pdf`), MP (`MissionPlanning + Didattica_IdeaFiga.pdf`), RO
(`RiorganizzazioneSitoIdeeElaborate_v6.pdf`), DT (`GRAZINGLINK-descrizione-tecnica.md`), BP e TUT. Le sigle sono
quelle della gap analysis. Dove un fatto non è stato controllato sul codice o sulla fonte è scritto **non verificato**.

Requisiti di partenza dai documenti: «un solo motore scientifico, due esperienze utente, risultati tracciabili e
assunzioni sempre visibili» (MP, ultima pagina); «Non bisogna creare un secondo motore fisico per il Mission
Planner» (RO §7); tre verifiche per la giuria, geometrica, topografica e temporale, più un caso RF riproducibile,
distinguendo visibilità geometrica, ricezione per diffrazione e collegamento sopra soglia (DA §12).

## Stato di implementazione

Aggiornato il 2026-11-06. Il resto del documento resta il progetto storico; questa tabella e l'aggiornamento
seguente distinguono il codice attuale dalle tappe precedenti.
Controlli a ogni passo: ruff, mypy, lint-imports, `contracts/gen.py --check`, pytest completo.

**Ritiro delle API e parita'.** La produzione non registra piu' i motori HTTP storici: `/api/lunar/*`,
`/api/grazing/*` e `/api/sky/*` rispondono 410 con i percorsi sostitutivi. Gli oracoli immutati sono
in `scripts/raven_reference/`, esclusi dal pacchetto backend e mai importati dalla produzione, per
conservare golden e regressioni. Telemetria usa `evaluate`, anche per i margini di tutti i rate
(`rf_series`, senza decimazione); `steps.chosen_rate_bps` rende osservabile l'effetto di k.
Le funzioni frontend delle vecchie classifiche non usate sono rimosse; restano i tipi e gli helper
realmente necessari agli adattatori del Planner. Non resta la vecchia finestra da 29,53 giorni/4252 passi.

Onda e cielo sono `/api/raven/wave` e `/api/raven/sky/*`, con versione e hash del registro. Il cielo
riusa lo stesso servizio S1. Onda resta uno strumento didattico, non il motore della missione.
`/api/raven/experiments/*` conserva profili e sweep didattici con formule S5 e parametri radio unificati,
senza download implicito: l'ambito a ostacolo singolo e' dichiarato in risposta e UI, non equiparato
al terreno completo di S2. Le primitive condivise restano in `domain/grazing/` per non duplicare le formule;
non e' stato attivato il contratto architetturale piu' restrittivo `api-through-raven`.

| Passo | Stato | Dove | Scostamenti dal progetto |
|---|---|---|---|
| M0 golden | fatto | `scripts/raven_golden.py`, `tests/backend/domain/golden/{synthetic,real}.json`, `test_golden.py` | cartella `tests/backend/domain/golden/` (non `.../raven/golden/`); i golden passano dall'API in-process e coprono 8 casi sintetici e 10 reali; `/api/grazing/wave`, `/compensator`, `/api/lunar/coupled-sensitivity` non sono congelati; il set reale gira solo con kernel e tile in cache |
| M1 registro | fatto | `backend/domain/raven/params.py` | chiavi `<scope>.<nome>` (`lunar.`, `grazing.`, `common.`): `frequency_ghz` resta definita due volte (8,425 e 8,4 GHz) fino a M8; niente alias: le vecchie tabelle sono viste del registro (`lunar.model.PARAMS`, `grazing.model.PARAMS`); aggiunte 5 costanti sparse (+2 tetti D9 in M4); non ancora nel registro: `RATES`, guadagni di stazione, Boltzmann duplicati, intervalli di `linkModel.ts` |
| M2 generazione | fatto (solo file) | `contracts/raven_params.json`, `frontend/src/contracts/raven_params.ts`, `raven/export.py`, `contracts/gen.py` | `GET /api/raven/parameters` rinviato a M7; `linkModel.ts` non importa ancora i valori generati (componenti non toccati); TS controllato solo con `tsc --noEmit` sul file |
| M3 scheletro | fatto | `raven/{known,pipeline,s0..s7}.py`, `.importlinter` (4 contratti) | `raven-research-isolated` non scritto (manca `research/`, M13); `api-through-raven` non attivo (M15); aggiunto `legacy-below-stages` (lunar/grazing non importano gli stadi: evita cicli) |
| M4 S0-S3 | fatto | `raven/s0_context.py` ... `s3_illumination.py`, `horizon.horizon_at/horizon_distance_m` | gli stadi AVVOLGONO il codice esistente; i vecchi moduli non sono ancora adattatori degli stadi (inversione prevista da M5-M6, per evitare cicli) e restano invariati (golden verdi); `snapshot.py` legge la soglia DSN dal registro; S1 usa altezza 0 e distanza Sole-Luna centro-centro (come `coupled`); `pipeline.evaluate` non ancora scritta (arriva con M6) |
| M5 S5 | fatto | `raven/s5_rf.py`, `grazing.analysis.link_series` | `analyze` chiama `link_series` (estratta senza cambiare numeri) invece di diventare adattatore di S5 (ciclo); specchio TS non rigenerato; gimbal con buchi nel terreno rende tutto ignoto; stati S5: `closes` False per `blocked_far_terrain`, ignoto per `outside_model` |
| M6 S4, S6, S7, `evaluate` | fatto | `raven/s4_power.py`, `s6_dsn.py`, `s7_mission.py`, `pipeline.evaluate` | S4/S7 dividono `coupled.couple` e lo riproducono (test contro `couple` e golden Malapert); Haworth: stati uguali al golden, RF «bloccato noto» (D4); `/api/lunar/mission` NON è ancora adattatore di `evaluate` |
| M7 API `/api/raven/*` | fatto | `backend/api/raven_routes.py`, `raven_experiments.py`, `sky_routes.py` | `evaluate`, `compare`, `parameters` (7 d a 10 min = 1008 passi), `model`, `validation`, `snapshot`, `scene`, `horizon`, `wave`, `sky/*`; schemi Pydantic/TS di risposta non generati |
| M8 unificazione | fatto per la catena nuova | `raven/params.py` (scope `rf`), `s5_rf.unified_link_inputs`, `docs/domain/raven-changes.md` | gli endpoint vecchi restano sui numeri vecchi (golden); `test_lunar_knowledge.py` e i documenti di conoscenza non aggiornati; D5 non applicata |
| M9 bisezione | fatto | `raven/windows.py`, `pipeline.instant_predicates/refined_windows`, `include_windows` in `/api/raven/evaluate` | bisezione a 1 s per `lit` e `link_usable` (S1-S3, S5, S6 a un istante); `useful` resta al passo (la batteria ha memoria); assunto un solo cambio per passo; bordi accanto a passi ignoti non raffinati e marcati non risolti; caso analitico (Sole sinusoidale) entro 1 s verificato; i «bordi entro un passo dai vecchi» sono verificati su Malapert con la catena nuova, non confrontando i vecchi golden dei bordi (non esistono) |
| Classifica D5 (parte di M11) | fatto per `/api/raven/compare` | `raven/ranking.py`, `test_ranking.py` | `/api/lunar/analyze` e `/api/grazing/compare` invariati (golden); le pagine Confronto e Siti non sono migrate |
| Viste (parte di M12) | fatto lato backend | `raven/views.py`, `/api/raven/{snapshot,scene,horizon}` | snapshot e scena uguali ai vecchi dove le regole coincidono (test); differenza intenzionale D4 per i siti coperti da terreno lontano; Lander e Viewer non migrati |
| Validazione (parte di M14) | fatto | `raven/validation.py`, `/api/raven/validation`, pagina Model, `docs/knowledge/model-validation.md` | `s5.browser_mirror` verificato entro 0,01 dB contro il motore Python su 32 casi di fixture (più 61 punti del bordo a lama entro 1e-6 dB), prova `linkModel.test.ts`; parita' d'implementazione, non validazione fisica |
| M10 client e Planner | fatto | `frontend/src/shell/ravenApi.ts`, `pages/planner/ravenAdapter.ts`, wizard a sette passi | tipi manuali verificati con fixture reali; orizzonte LOLA unico; k trasmesso in `rf_overrides`, rate selezionato visibile (il margine a rate fisso non cambia); finestre raffinate, versione, stati e parametri effettivi nel rapporto |
| M11 classifica e Siti | fatto | `pages/compare/RavenCompare.svelte`, `ravenRanking.ts` | sostituiscono Confronto GrazingLink e confronto energetico a punteggio (rimossi); componenti visibili, nessun punteggio, non confrontabili con il motivo; in Learning 3 componenti, in Avanzato tutte |
| M12 viste e Simula | fatto | Lander e Viewer su `/api/raven/{scene,snapshot}`; specchio S5 e registro generato | stazione 18 m con guadagno 62,5 dBi illustrativo; tabella `/api/raven/compensation`; parita' registrata in `s5.browser_mirror` |
| Divieto chiamate legacy | fatto senza eccezioni | `shell/noLegacyCalls.test.ts` | nessuna chiamata `/api/lunar/`, `/api/grazing/` o `/api/sky/` nel frontend di produzione |
| M13, ritiro HTTP M15 | fatto con scostamento architetturale | `raven_experiments.py`, `retired_routes.py`, `scripts/raven_reference/` | scope didattico esplicito, 410 legacy; primitive condivise in `domain/grazing/`, contratto `api-through-raven` non attivato |
| Sito personalizzato (S0/S2, 5 nov) | fatto | `raven/s0_context.custom_site(strict=True)`, `grazing/{dem_select,dem_cache}.py`, `raven/custom_terrain.py`, `api/raven_custom.py`, `POST /api/raven/terrain-estimate`; frontend `shell/{customSites.ts,CustomSite*.svelte,GlobePicker.svelte,TerrainPrompt.svelte}` | vedi la sezione «Sito personalizzato» sotto: prodotto per sito, portata dell'orizzonte ridotta dal tetto di dati, terreno ignoto fuori dai tetti, nord polare non coperto |

**Aggiornamento validazione 8 nov:** il modello corrente e' `raven-core-1.2`.
S3 conserva le 48 strisce e l'orizzonte al loro punto medio, ma integra l'area circolare
esatta invece dei rettangoli, correggendo le falci solari perse e l'energia S4 dipendente.
Le nuove voci `s2.rf_geometry`, `s4.energy_arithmetic`, `s5.reflection_formulas`
separano la matematica verificata dalla qualificazione fisica ancora mancante.
Stati complessivi S2/S4/S5 non validati e S3 solo plausibilita', parametri invariati.
Residui, riproduzione e criteri di sblocco: `validation.md`, sezione
«Incremental S2-S5 validation and S3 correction».

### Sito personalizzato: stato, misure e limiti (5 nov 2026)

**Che cosa fa.** Un sito `{id c-..., name, lat_deg, lon_deg_east (-180..360, normalizzata), panel_height_m, antenna_height_m}`
(al massimo 8 per richiesta) entra in `evaluate`, `compare`, `scene`, `snapshot` e `horizon`. Validazione: `extra=forbid`,
limiti numerici, nome 1-40 caratteri `[A-Za-z0-9 ._,()'-]`, id `c-...` (nessun id del catalogo comincia per `c-`, controllato al
caricamento), risposta 422 generica senza eco. Le altezze del sito sostituiscono quelle della richiesta.

**Prodotto di terreno per sito** (`dem_select.plan_site`, sola funzione, nessuna rete): `LDEM_85S_20M` (20 m) se il disco di 10 km sta
nel prodotto (lat <= -85,1); `LDEM_75S_240M` (240 m) a sud di 75 S purché il disco dell'orizzonte stia nel prodotto; altrimenti il
prodotto globale `LDEM_128_FLOAT` (128 pixel/grado, 0,2369 km/pixel all'equatore), agganciato in `dem.lock.json` con dimensione
4 246 732 800 byte, ETag `"8c7512ec2927d31:0"`, sha256 dell'etichetta e sha256 del file intero (calcolato una volta in streaming il
5 nov 2026, 9,5 minuti a 7,4 MB/s, file non conservato). Orientamento e registrazione del pixel verificati su 18 punti (86-88 S, sei
longitudini) contro `LDEM_75S_240M`: scarto quadratico 1,9 m su una deviazione standard di 924 m, correlazione 0,999998.
Il nord polare non ha un prodotto polare agganciato: vicino a 90 N la griglia cilindrica richiede troppe tessere e il sito resta
**terreno ignoto** (stato `exceeds_site_cap`); i prodotti polari nord (`ldem_75n_240m`, `ldem_85n_20m`) esistono nel nodo PDS ma non
sono stati verificati né agganciati.

**Orizzonte vicino fine, lontano grossolano.** Sono campionati 1440 azimut: vicino 10 km al passo del pixel del prodotto vicino
(20 o 240 m), lontano al passo del pixel del prodotto lontano. La portata lontana è la più ampia fra 200, 150, 100, 75, 50 e 30 km
per cui le tessere stanno nel tetto di 10 MB per sito; è dichiarata in ogni risultato (`terrain.horizon_range_km`,
`mask.far_range_m`): il terreno oltre la portata non si vede, quindi l'orizzonte è un limite inferiore. Per i siti del catalogo la
portata resta 200 km.

**Tetti.** 10 MB per sito e 40 MB per richiesta, contati sul traffico (le risposte a più intervalli pesano 1,28 volte le tessere:
misurato 1,27-1,28), 120 MB/ora per il server (`RAVEN_DEM_MAX_MB_PER_HOUR`), un download alla volta, cache su disco
`<GRAZING_DEM_DIR>/custom` di al più `GRAZING_DEM_CACHE_MAX_MB` (200) con eliminazione delle tessere meno usate (mtime aggiornato
a ogni lettura); `make grazing-dem-clear` la svuota, `make grazing-dem-status` mostra l'uso. Nulla viene scaricato
all'installazione. Il download parte solo con `allow_download: true`; senza, la risposta è 409 `needs download` con la stima
(`POST /api/raven/terrain-estimate` la dà senza scaricare); 413 oltre il tetto per richiesta, 429 oltre quello orario, 503 se il nodo
non risponde. Solo gli URL del file di blocco (HTTPS, host `pds-geosciences.wustl.edu`); l'utente non fornisce URL.

**Misura reale** (download dal nodo PDS, 5 nov 2026, 3 punti, cache vuota):

| Punto | Prodotto (risoluzione) | Portata | Tessere | Sul disco | Sul filo | Tempo |
|---|---|---|---|---|---|---|
| polare coperto, -89,0 / 100,0 | 20 m + 240 m | 100 km | 113 | 7,41 MB | 9,42 MB | 104 s |
| lat -78, 40,0 | 240 m (polare) | 75 km | 29 | 1,90 MB | 2,41 MB | 28 s |
| equatoriale, 0,0 / 10,0 | globale 236,9 m | 150 km | 88 | 5,77 MB | 7,38 MB | 77 s |

**Confronto con il catalogo** (motore reale, stesse coordinate, 14 giorni a 60 min, `test_raven_custom_real.py`): `lit` identico, margini
uguali a 1e-9 dB (stesso profilo RF a 20 m), orizzonte del Sole entro 1,5° (limite del test 2°) e della Terra entro 0,45° (limite
0,6°); differenza dovuta al passo radiale 20 m invece di 10 m, alla portata di 100 km invece di 200 e al passo lontano 240 m invece di
120 m. **Non validato**: nessun confronto con un'altra implementazione fuori dal catalogo; il prodotto a 240 m non risolve creste più
strette di circa 500 m.

**Terreno ignoto.** Fuori da ogni prodotto o oltre i tetti: orizzonte, profilo RF e ciò che ne dipende (`lit`, margine, stato RF, ore
utili) sono `None`/`unknown`; restano validi (e sono etichettati) geometria S1, efemeridi, visibilità DSN e la perdita in spazio libero
dalla distanza vera (`steps.free_space_loss_db`, non un margine di collegamento). Un orizzonte piatto non viene mai sostituito.

### Misura D4 (M4): terreno oltre il profilo RF che nasconde la Terra

`scripts/raven_d4_measure.py`, finestra 2027-01-01 per 365 giorni, passo 60 min (8760 passi), maschera 2 m, profilo RF 10 km,
altezza antenna 2 m, DEM in cache. Conteggio per sito dei passi in cui il punto più alto della maschera verso la Terra è oltre 10 km
e sopra il centro della Terra. È un limite inferiore (la maschera tiene solo il campione più alto per azimut).

| Sito | Passi con Terra sopra l'orizzonte piatto | Passi `outside_model` (tutti) | `outside_model` con Terra sopra il piatto | Distanza del terreno che copre |
|---|---|---|---|---|
| malapert-massif | 5923 | 0 | 0 | |
| haworth | 5219 | 8760 (100 %) | 5219 (100 %) | 26,3-44,8 km, fino a 9,8° sopra la Terra |
| nobile-rim | 5420 | 6914 (78,9 %) | 3574 (65,9 %) | 33,8-38,2 km, fino a 7,6° sopra la Terra |
| de-gerlache | 4149 | 0 | 0 | |
| shackleton | 4038 | 0 | 0 | |

Maschera completa (frazione azimut 1,0) in tutti e cinque i siti: nessun passo ignoto per dati mancanti.

**D4 aggiornata (decisione del 2026-11-05).** Per il terreno oltre il profilo RF che copre il centro della Terra, S2 calcola con la
formula esistente del bordo a lama (`diffraction.knife_edge_loss_db`, ostacolo singolo, approssimato e dichiarato) la perdita
dell'ostacolo lontano dominante, con d1 = distanza dell'orizzonte della maschera, d2 = distanza Terra - d1 e l'angolo sopra il
bordo SUPERIORE della Terra. Soglia `common.far_terrain_blocked_loss_db` = 30 dB (tag I).
- perdita >= 30 dB: stato NOTO `blocked_far_terrain` (il link non chiude: per S7 è un «no», mai ok, mai ignoto);
- perdita < 30 dB: `outside_model` (ignoto: più ostacoli o diffrazione fuori modello); un «sì» di una finestra con un ingresso ignoto resta ignoto;
- terreno lontano che non supera la Terra: nessun cambiamento.

Stessa misura con la nuova regola (passi per stato di `terrain_reason`, 8760 per sito):

| Sito | `ok` | `outside_model` (ignoto) | `blocked_far_terrain` (noto) |
|---|---|---|---|
| malapert-massif | 8760 | 0 | 0 |
| haworth | 0 | 1051 (12,0 %) | 7709 (88,0 %) |
| nobile-rim | 1846 | 712 (8,1 %) | 6202 (70,8 %) |
| de-gerlache | 8760 | 0 | 0 |
| shackleton | 8760 | 0 | 0 |

Limiti: ostacolo singolo, soglia di 30 dB illustrativa, limite inferiore dei casi (la maschera tiene solo il campione più alto per azimut), nessuna misura radio.

## 0. Principi

1. **Una catena**: sette stadi S1-S7 più il contesto S0; ogni numero mostrato dal sito esce da uno stadio o da una
   vista di sola lettura sugli stadi. Nessuna pagina ricombina nel browser uscite di motori diversi.
2. **Un registro dei parametri**: ogni valore numerico ha una sola definizione (valore, unità, intervallo, tag
   V/D/I, fonte); backend, default dell'API, tipi TypeScript e tabelle dei documenti sono generati da lì.
3. **L'ignoto resta ignoto**: un ingresso mancante (DEM, efemeridi, stazione senza dati) rende ignoto ogni valore
   che ne dipende; `unknown` non diventa mai `ok`, né per default né in un'aggregazione.
4. **Nessun dato inventato**: terreno solo LOLA o profilo dell'utente; profili sintetici solo nei test, marcati.
5. **Uno specchio, non un secondo motore**: il modello TypeScript per gli slider è una copia dichiarata della sola
   forma chiusa di S5, verificata con fixture generate dal Python.
6. **Validazione per stadio**: ogni stadio dichiara cosa è verificato, contro cosa, con quale residuo, e la frase
   esatta che UI e README possono usare (§3).

## 1. Inventario di ciò che esiste oggi

### 1.1 Motori e modelli di calcolo

Verdetti: **assorbito** (il codice diventa uno stadio, invariato o quasi); **sostituito** (il risultato viene
dal nucleo, il motore sparisce); **oracolo** (resta solo come riferimento nei test); **specchio** (copia
dichiarata, verificata per parità); **vista** (sola lettura sul nucleo); **ricerca** (modulo esplicativo, fuori
dalla catena).

| ID | Motore (file) | Cosa calcola; ingressi → uscite | Ipotesi principali | Dove è usato | Verdetto |
|---|---|---|---|---|---|
| B1 | `backend/ephemeris/engine.py` (`Engine`, `topocentric_azel`, `sun_distance_au`, `subsolar_point`) | az/el apparenti, distanze, punti subsolare e sub-Terra; UTC → serie | DE440s, frame `MOON_ME_DE440_ME421`, sfera 1737,4 km, UT1 predetto, nessuna rifrazione | tutte le rotte lunari e grazing, `/api/sky/*`; `tests/backend/ephemeris/*` | **assorbito** come base di S1 |
| B2 | `lunar/visibility.py` | Sole «su» = `el + 0,27° ≥ maschera` (orizzonte piatto); Terra visibile = centro `≥ maschera`; Luna vista dai 3 complessi DSN 34 m a ≥ 6° | orizzonte piatto, semidiametro fisso 0,27° | `/api/lunar/analyze`, `/timeline`, `coupled.py` (solo DSN) | DSN **assorbito** in S6; criteri Sole/Terra piatti **sostituiti** da S2-S3; restano come **oracolo** del limite «terreno piatto» |
| B3 | `lunar/link.py` | FSPL esatta, EIRP, C/N0, Eb/N0, margine; distanza → margine | spazio libero, G/T costante, nessuna codifica | `/api/lunar/analyze`, `/timeline`; test NASA (`test_nasa_*` in `test_lunar_link.py`) | primitive **assorbite** in S5 (i test NASA restano su di esse); set di parametri **sostituito** dal registro |
| B4 | `lunar/energy.py` (`array_power_w`, `simulate_energy`) | irradianza `1360,8/r²`, incidenza, potenza, batteria a tre modi | pannello e carichi I | timeline, `terrain_energy`, `coupled` | **assorbito** in S4 |
| B5 | `lunar/mission.py` (`analyze_site`, `rank_sites`) | passo utile = energia ∧ Terra (piatto) ∧ DSN ∧ margine ≥ 3 dB; classifica a punteggio pesato | orizzonte piatto, link semplificato | `/api/lunar/analyze` → `compare/lunar.ts` → `EnergyCompare.svelte` (colonna «Punteggio») | **sostituito** (S7 e una sola classifica, §2.11) |
| B6 | `/api/lunar/timeline` (stesso calcolo di B5 con serie) | serie per sito su orizzonte piatto | come B5 | Planner (`planner/timeline.ts`) | **sostituito**; il calcolo piatto resta **oracolo** minimo |
| B7 | `lunar/terrain_energy.py` | potenza × frazione del disco; batteria «what-if» di `/solar-terrain` | carico comunicazioni dal link semplificato B3 | `/api/lunar/solar-terrain` | **assorbito** in S3-S4 |
| B8 | `lunar/coupled.py` `evaluate_mission`, `couple` | per un sito: disco → potenza → batteria → margine RF grazing → DSN → stato, obiettivi | ignoto propagato in avanti | `/api/lunar/mission`, Planner (`planner/mission.ts`) | **assorbito**: è lo scheletro di S4+S6+S7 |
| B9 | `lunar/coupled.py` `coupled_sensitivity` | ricalcolo batteria da campioni forniti dal client | combina campioni di motori diversi | `/api/lunar/coupled-sensitivity` (non più usata dal Planner, method.md) | **rimosso** dopo la deprecazione |
| B10 | `grazing/geometry.py` | Terra topocentrica (parallasse, librazione), distanza, diametro angolare | via B1 | `analysis`, `snapshot`, `scene` | **assorbito** in S1 |
| B11 | `grazing/dem.py`, `terrain.py` | tile LOLA 20 m con integrità; profilo lungo l'azimut della Terra; ostacolo dominante (max ν), raggio di curvatura | profilo di 10 km (`profile_length_m`, I), ostacolo singolo | `analysis`, `scene`, `snapshot` | **assorbito** in S2 |
| B12 | `grazing/horizon.py` | maschera per sito, 1440 azimut, 20 m fino a 10 km + 240 m fino a 200 km, curvatura, altezza; criteri bordo/centro/disco | terreno oltre 200 km non modellato | `/solar-terrain`, `coupled` | **assorbito** in S2 (maschera) e S3 (criteri del disco) |
| B13 | `grazing/solar_terrain.py` | `site_solar_terrain` (serie di stati); `circular_horizon` (72 profili da 10 km) | — | `/solar-terrain`, `/api/lunar/horizon` | serie **assorbita** in S3; `circular_horizon` diventa **vista** di S2 |
| B14 | `grazing/diffraction.py`, `compensation.py` | J(ν) esatto, ITU eq. (27), T(m,n) P.526-9 §4.2, tabella split-step come confronto, incertezza | politica ITU predefinita (validation.md) | `analysis`, `/api/grazing/compensation`, Simula | **assorbito** in S5 |
| B15 | `grazing/multipath.py` | due raggi sul regolite, rugosità, applicabilità | suolo piano, parte coerente | `analysis` | **assorbito** in S5 |
| B16 | `grazing/antenna.py`, `gimbal.py` + plugin `servo_ctrl_c` (`gimbal_tracker`) | guadagno, HPBW, perdita di puntamento, montaggio fisso/tracking/gimbal (controllore PI in C) | HPBW 70 λ/D I | `analysis`, `/api/grazing/antenna` | **assorbito** in S5 (il binario C resta un ingresso di S5, invariato) |
| B17 | `grazing/bitrate.py` | compensatore `max R: M − kσ ≥ 0`, interruzioni simulate | σ gaussiano noto (I) | `analysis`, `/api/grazing/compensator` | **assorbito** in S5 (scelta del rate) e S7 (dati consegnati) |
| B18 | `grazing/analysis.py` `analyze` | somma del link per passo e per rate, finestre geometrica/reale/transizione | come B11-B17 | `/api/grazing/analyze`, `compare`, `snapshot`, `scene`, `coupled`, plugin `grazinglink_link`, Telemetria | **assorbito**: si spezza in S2 + S5; `analyze` resta adattatore |
| B19 | `grazing/compare.py` | riassunto per sito e classifica lessicografica (ore reali, margine mediano, id) | margini solo con `el > 0` piatto | `/api/grazing/compare` → `Compare.svelte` | **sostituito** dalla classifica unica |
| B20 | `grazing/snapshot.py` | un istante, tutti i siti + DSN; stato open/transition/blocked | soglia DSN 6,0° scritta nel codice | `/api/grazing/snapshot` → Viewer | **vista** «istantanea» |
| B21 | `grazing/scene.py` | geometria 3D di un istante (patch LOLA, Fresnel, numeri di `analyze` a un passo) | — | `/api/grazing/scene` → Lander, Simula | **vista** «scena» |
| B22 | `grazing/wave.py` | split-step di Fresnel 2D scalare parassiale, cresta assorbente | non è il motore del link | `/api/grazing/wave` → `/simula?tab=onda` | **ricerca**, etichetta «fisica illustrativa, non il motore del link» |
| B23 | `data/compensation_table.json`, `scripts/gen_compensation_table.py`, `study_splitstep_convergence.py` | correzione split-step su griglia ν × R; studio di convergenza | dx non convergente (validation.md) | S5 come confronto e banda | **ricerca** che alimenta l'incertezza di S5 |
| B24 | `scripts/solar_horizon_arbiter.py` | maschera e disco riscritti in modo indipendente | condivide solo `LolaDem` ed efemeridi | `test_solar_horizon_arbiter.py`, validation.md | **oracolo** di S2-S3 |
| B25 | plugin `fspl_c` | FSPL con costante 92,45 (offset +0,0022 dB) | — | `test_lunar_link.py`, sottosistema simulazioni generico | **oracolo** di S5 (non entra nella catena) |
| B26 | plugin `grazinglink_link` | `analyze` su cresta sintetica dichiarata | mai una previsione di sito | sottosistema plugin, `test_grazinglink_plugin.py` | **adattatore** su S5 |
| F1 | `simula/linkModel.ts` (`computeLink`, `p526RoundedTermDb`) + Fresnel/J/ITU di `grazinglink/grazing.ts` | forma chiusa del link con geometria manuale (limite a suolo piano), stato, validità | parità con fixture `simula/fixtures/link_parity.json` (`scripts/dump_link_parity.py`), entro 0,01 dB | Simula, Home (`MiniSim`, `missionStrip`), `wave.ts` (curva del bordo) | **specchio** di S5 |
| F2 | `home/missionStrip.ts` | mese con elevazione sintetica `0,95 ± 0,55°` davanti a un crinale fisso | sintetico, dichiarato in pagina | Home | **ricerca/didattica**, resta sullo specchio con l'etichetta |
| F3 (rimosso il 10 nov: modulo irraggiungibile) | `planner/rfDsnOverlap.ts`, `objectives.ts`, `sensitivity.ts`, `windows.ts`, `quality.ts` | intersezioni nel browser fra RF grazing, DSN e Sole piatto; soglie; finestre campionate | combinano motori diversi | Planner | **sostituiti** da uscite di S6-S7 (il browser solo visualizza) |
| F4 | `compare/lunar.ts`, `grazingCompare.ts` | due contratti e due ordinamenti | — | `EnergyCompare.svelte`, `Compare.svelte`, `SitiCombined.svelte` | **sostituiti** da un solo contratto di confronto |
| F5 | `lander/model.ts` (`fresnelRadius`, `pointing`, `sunLocal`, `FALLBACK_SUN` a 1,5°), `lander/grazingLight.ts` (Sole vero fra 1° e 3°, orizzonte piatto, per scegliere l'istante) | aiuti di disegno | il Sole di ripiego a 1,5° è un valore di resa grafica; come sia etichettato in pagina: **non verificato** | Lander | **vista**; il criterio 1-3° deve leggere S3 (o dichiararsi «solo per l'inquadratura») |
| F6 | `telemetry/linkComparison.ts` `simulateLink` | campioni di link simulati con `Math.random` sopra una previsione | dimostrazione | Telemetria | **ricerca/demo**, etichettata; la previsione viene da S5 |
| F7 | `viewer/snapshot.ts`, `skyLight.ts` | client di B20 e `/api/sky/subsolar` | — | Viewer | **viste** |

Fuori dal perimetro del modello fisico: assistente, ML (`predictor_*`, `trainer_*`), `env_servo`, pipeline e
telemetria generica della base. Non producono numeri di sito.

### 1.2 Sovrapposizioni e conflitti (con i numeri che li rendono visibili)

| # | Conflitto | Evidenza | Conseguenza nel nucleo |
|---|---|---|---|
| C1 | **Timeline a orizzonte piatto contro maschera LOLA**. La timeline del Planner (B6) e l'energia della timeline usano il Sole su orizzonte piatto; `/solar-terrain` e `/mission` la maschera a 200 km | method.md §6 (finestra 29,53 d dal 2027-04-07, piatto): frazione di Sole Haworth 0,342, de Gerlache 0,184; validation.md (anno 2027, maschera): Haworth e de Gerlache 0 % in ogni passo, anche a 10 m. Finestre diverse, ma lo scarto non è spiegabile con la finestra | S3 usa solo la maschera; il calcolo piatto resta un oracolo nei test (decisione n. 10 dell'utente) |
| C2 | **Due modelli RF con parametri diversi** (B3 contro B18) | B3: 8,425 GHz (V), 20 W, 20 dBi, G/T 54,1 dB/K (D), Eb/N0 9,6 dB (D, BPSK non codificato), perdite 1 + 1 + 2 dB, 4 kbit/s (V, TBR), margine richiesto 3 dB (V). B18: 8,4 GHz (I), 10 dBW, 15 dBi, stazione 68 dBi (I) con Tsys 30 K (I), cioè G/T 53,2 dB/K, Eb/N0 2,5 dB (I), perdite varie 3 dB, 100 kbit/s, soglia 0 dB | un solo set nel registro (decisione D2); S5 ha una sola somma |
| C3 | **Quattro criteri per «Sole visibile»** | B2: centro + 0,27° fisso sopra maschera piatta; B12: bordo superiore/centro/inferiore e frazione del disco (48 strisce) con semidiametro dalla distanza vera; B7: potenza × frazione del disco; F5: Sole vero fra 1° e 3° su orizzonte piatto | S3 espone i quattro indicatori della maschera; il booleano «luce» è uno solo (D7); la potenza usa sempre la frazione del disco |
| C4 | **Tre criteri per «Terra visibile»**, nessuno sulla maschera a 200 km | B2: centro ≥ 0° piatto; B18/B20: centro sopra l'ostacolo dominante del profilo di 10 km; B19: margini solo con `el > 0` piatto. Il disco terrestre (0,9-1,0° di raggio) non è aggiunto (DECLARED_LIMITS) | S2 calcola l'orizzonte nella direzione della Terra anche dalla maschera; se il terreno oltre il profilo RF copre la Terra, lo stato RF è «fuori modello» (D4) |
| C5 | **DSN**: soglia e stazioni | B2/B8 leggono `ground_station_min_elevation_deg` (6°, V) dal registro lunare; B20 ha `DSN_MIN_ELEVATION_DEG = 6.0` scritto nel codice; la classe 18 m è ignota in B8 ma usata senza visibilità in B18/B19 | S6 unico; 18 m sempre «ignoto» per la visibilità |
| C6 | **Tre definizioni di ora utile** | B5: energia ∧ Terra piatta ∧ DSN ∧ margine ≥ 3 dB; B8: operativo ∧ margine ≥ 0 ∧ DSN; B19 «ore reali»: margine ≥ 0, senza DSN né energia; Planner (F3): soglia di luce sulla frazione piatta, soglia RF sui campioni grazing | una sola regola in S7 (D3) |
| C7 | **Due classifiche** | B5: media pesata normalizzata (UI «Punteggio»), contraria a DA §10E e RO p. 17; B19: lessicografica (ore reali, margine mediano, id) | una sola implementazione, componenti visibili, nessun punteggio unico (D5) |
| C8 | **Altezze** | `observer_height_m` (Sole, 0-100 m, default 2), `antenna_height_m` (RF, 0,1-100 m, default 2), Lander `MAST_RANGE` 0,5-10 m, `shell/scenario.ts` `MAST_RANGE` 0,1-100 m, Simula `mastM` | due parametri distinti nel registro (pannello, antenna), intervalli unici (D8) |
| C9 | **Tetti e campionamento diversi** | lunare `max(1, floor(days·1440/step))`, 20 000 punti totali, `/solar-terrain` 240 passi e 2 siti; grazing `int(days·1440/step)`, 5000 campioni, uscita decimata a 1500 (`series_step_min`); `/mission` 1500 passi; compare 1500 per sito e 6000 totali. La decimazione produce gli stati `unsynchronised` di `coupled` e del Planner | una sola griglia temporale S0, nessuna decimazione dentro la catena (D9) |
| C10 | **Specchio TS con parametri propri** | `DEFAULT_INPUT`, `RANGES`, `STATION_GAIN_DBI` in `linkModel.ts`; `BITRATES` in `shell/scenario.ts`, `RATES_BPS` in `linkModel.ts` e `DEFAULT_RATES_BPS` in `bitrate.py`; parità numerica 0,01 dB ma default copiati a mano | default e intervalli generati dal registro; la parità resta il test |
| C11 | **Costanti duplicate** | Boltzmann −228,6 (B3) e −228,599 (B16, TS); semidiametro solare 0,27° fisso (B2) e da distanza (B12); `AU_KM` in tre file; FSPL esatta (B3) e con 92,45 (B25) | costanti nel registro con tag; un solo valore per costante |
| C12 | **Energia scollegata dal terreno e dall'RF** nella timeline | method.md: «il confronto DEM solare … e il confronto RF GrazingLink non modificano il risultato energetico»; il carico di comunicazione usa B3 | S4 legge S3 e S5/S6: la batteria vede luce e link della stessa catena |
| C13 | **Due servizi API con semafori e cache separati** | lunare 2 richieste concorrenti e 32 voci; grazing 2 e 16 | un servizio `RavenService` con tetto e cache unici |

## 2. Architettura di destinazione

### 2.1 Catena e pacchetto

```
scenario ──► S0 sito e tempo ──► S1 geometria ──► S2 terreno ──► S3 illuminazione ──► S4 potenza e batteria ─┐
                                      │               └────────► S5 link RF ──────────────────────────────────┤
                                      └──────────────────────────► S6 DSN ────────────────────────────────────┴► S7 stato e obiettivi
```

Pacchetto `backend/domain/raven/` (dentro `backend/domain`, come richiede la regola del branch in
`docs/hackathon/nasa-lunar.md`: si aggiungono solo `backend/domain/` e `backend/plugins/`; D1):

```
backend/domain/raven/
  params.py        registro unico (ParamSpec, REGISTRY, resolve(overrides) -> ResolvedParams)
  known.py         tipi tri-stato e codici di ignoto (Reason)
  s0_context.py    s1_geometry.py  s2_terrain.py  s3_illumination.py
  s4_power.py      s5_rf.py        s6_dsn.py      s7_mission.py
  pipeline.py      evaluate(scenario) -> Evaluation   (unico punto di ingresso)
  views.py         snapshot, scene, horizon_profile, sky  (sola lettura sugli stadi)
  ranking.py       rank(evaluations, order) (unica classifica)
  validation.py    STAGE_STATUS: stato di validazione per stadio, generato in /api/raven/model
  research/        wave.py, compensation table, studi (non importati da pipeline.py)
```

`backend/domain/lunar` e `backend/domain/grazing` diventano, durante la migrazione, **adattatori** e poi
librerie di primitive importate dagli stadi; alla fine i moduli rimasti sono primitive pure (FSPL, J(ν),
batteria, maschera) senza orchestrazione propria.

Contratti `import-linter` da aggiungere in `.importlinter` (oggi ci sono solo i quattro contratti del core):
- `raven-layers` (tipo `layers`): `pipeline | views | ranking` sopra `s7` sopra `s6 | s5 | s4` sopra `s3` sopra
  `s2` sopra `s1` sopra `s0` sopra `params | known`. Nessuno stadio importa uno stadio successivo;
- `raven-no-web` (tipo `forbidden`): `backend.domain.raven` non importa `fastapi`, `starlette`, `backend.api`;
- `raven-research-isolated`: `backend.domain.raven.pipeline` non importa `backend.domain.raven.research`;
- `api-through-raven` (alla fine della migrazione): `backend.api.*_routes` non importa `backend.domain.lunar` né
  `backend.domain.grazing` direttamente, solo `backend.domain.raven`.

### 2.2 Tipi comuni

- `Known[T] = T | None` con un `Reason` parallelo per ogni serie: `ok`, `missing_dem`, `outside_coverage`,
  `missing_ephemeris`, `unknown_station`, `outside_model`, `upstream_unknown`. Regole: un'operazione con un
  ingresso ignoto dà ignoto con `upstream_unknown`; `False ∧ ignoto = False` (un «no» noto resta noto, e non è
  mai un «sì»); `True ∧ ignoto = ignoto`; ogni conteggio (ore utili, frazioni) si fa sui soli passi noti e
  riporta a parte `unknown_hours`. È la regola già usata da `coupled.couple` e `horizon.disc_criteria`, resa
  comune.
- Unità nel nome di ogni campo (`_deg`, `_km`, `_m`, `_w`, `_wh`, `_db`, `_dbw`, `_dbi`, `_bps`, `_unix`), come in
  `contracts/telemetry.schema.json`.
- Frame: corpo fisso lunare `MOON_ME_DE440_ME421` (ME/PA), latitudine planetocentrica, longitudine Est in
  −180..180, sfera di riferimento 1737,4 km; locale ENU topocentrico, azimut da Nord verso Est, elevazione
  apparente senza rifrazione; tempo UTC ISO-8601 con `Z`; ogni passo `i` rappresenta `[t_i, t_i + dt)` con la
  geometria campionata in `t_i` e lo stato di carica alla fine del passo (convenzione attuale, method.md).

### 2.3 S0 Sito e tempo

- Ingressi: `SiteRef = {id} | {custom: {id, lat_deg, lon_deg_east}} | {profile: UserProfile}`, `TimeWindow =
  {start_utc, days, step_min}`.
- Uscite: `SiteRecord(id, name, lat_deg, lon_deg_east, kind, coordinate_basis, source{url, accessed, note},
  verified, dem_coverage)`; `TimeGrid(start_utc, step_min, n_steps, instants, t_unix)`.
- Funzioni: `resolve_site(ref: SiteRef) -> SiteRecord`; `build_grid(w: TimeWindow, limits: Limits) -> TimeGrid`.
- Regole: un solo calcolo di `n_steps = max(1, floor(days · 1440 / step_min + 1e-9))` (oggi due varianti, C9);
  tetto unico per sito e totale, errore 422 oltre il tetto, nessuna decimazione. Catalogo:
  `backend/domain/data/sites.json` (8 siti, campi di provenienza già presenti); le 17 regioni Artemis e i DEM a 5 m
  (decisione n. 6) entrano qui solo con coordinate da fonte verificabile; un sito con coordinate nulle non è
  valutabile (stato `missing_coordinates`), mai riempito.
- Ignoto: sito fuori dal DEM a 20 m → `dem_coverage = false`, propagato a S2.
- Validazione: coordinate copiate dalla fonte primaria (`verified: true` = copiate, non «centro di regione»).

### 2.4 S1 Geometria delle efemeridi

- Uscite: `Geometry(sun_az_deg, sun_el_deg, sun_range_km, sun_semidiameter_deg, earth_az_deg, earth_el_deg,
  earth_range_km, earth_semidiameter_deg, sub_earth_lat_deg, sub_earth_lon_deg, dsn_moon_el_deg[3][n])`.
- Funzione: `geometry(engine: Engine, site: SiteRecord, grid: TimeGrid) -> Geometry`.
- Contenuto: Sole e Terra topocentrici dal sito (parallasse e librazione fisica inclusi: `grazing/geometry.py`),
  semidiametro solare da `asin(695 700 km / distanza)` (oggi `horizon.sun_semidiameter_deg`; sostituisce lo 0,27°
  fisso), semidiametro terrestre `atan(R_E / d)`, elevazione della Luna dai tre complessi DSN (coordinate DSN
  810-005/301 Rev. P Tab. 5).
- Ignoto: efemeridi assenti → 503 per l'intera valutazione (non c'è un risultato parziale sensato).
- Validazione e test: `tests/backend/ephemeris/test_validation.py`, `test_lunar_visibility.py`,
  `grazing/test_geometry.py` (§3).

### 2.5 S2 Terreno

- Uscite: `Terrain(mask: HorizonMask, mask_meta{products, sha256, steps, complete_fraction,
  far_dominant_fraction, cache_source}, sun_horizon_deg[n], earth_horizon_deg[n], rf_obstacle[n]: DominantRidge |
  None, rf_profile_horizon_deg[n], terrain_reason[n])`.
- Funzione: `terrain(site, geo, p: ResolvedParams, dem: LolaDem, store: MaskStore) -> Terrain`.
- Contenuto: maschera per (sito, altezza del pannello) da `horizon.compute_mask` (LDEM_85S_20M a passo 10 m fino
  a 10 km, LDEM_75S_240M a passo 120 m fino a 200 km, curvatura, 1440 azimut); orizzonte letto **anche**
  nell'azimut della Terra (oggi non fatto, C4); profilo RF lungo l'azimut della Terra (quantizzato a 0,1°, lungo
  `profile_length_m`) e ostacolo dominante con raggio di curvatura (`terrain.dominant_ridge`); in alternativa un
  `UserProfile` validato, marcato `user`, o un profilo sintetico solo nei test, marcato `synthetic`.
- Controllo di coerenza nuovo: se `earth_horizon_deg` della maschera supera l'orizzonte del profilo RF oltre la
  sua lunghezza, il terreno lontano copre la Terra e il modello a ostacolo singolo non lo rappresenta:
  `terrain_reason = outside_model` per S5 (D4). Quante volte accada ai siti attuali: **non verificato**.
- Ignoto: tile assente → azimut incompleto → criterio che dipende da quell'azimut ignoto; «sotto la maschera»
  resta noto (altro terreno può solo nascondere di più), come oggi.
- Validazione: arbitro indipendente, LROC WAC, orientamento DEM (§3).

### 2.6 S3 Illuminazione

- Uscite: `Illumination(upper_limb_visible[n], centre_visible[n], lower_limb_visible[n], disc_fraction[n],
  lit[n], reason[n])`, tutti `Known`.
- Funzione: `illumination(geo, terrain) -> Illumination` (oggi `horizon.disc_criteria`, 48 strisce, disco
  uniforme).
- Regola: `lit = disc_fraction > 0` (D7); la potenza usa sempre `disc_fraction`. Nessuna maschera piatta.
- Assorbe: `site_solar_terrain` (B13), la parte di illuminazione di `terrain_energy` (B7) e i criteri di B2.

### 2.7 S4 Potenza e batteria

- Uscite: `Power(irradiance_w_m2[n], cos_incidence[n], gen_w[n], soc[n], mode[n], unmet_wh[n], harvested_wh,
  reason[n])`.
- Funzione: `power(geo, illum, link_available: Known[bool][n], p) -> Power`, con `gen_w = S(r) · A · η ·
  packing · (1 − deg) · cos(inc) · disc_fraction` (`terrain_energy.terrain_generation_w`) e la batteria di
  `energy.simulate_energy` a tre modi (attivo, solo comunicazioni, sopravvivenza).
- Accoppiamento: il carico di comunicazione dipende da `link_available` di S5 ∧ S6 (oggi dal link semplificato,
  C12). Ordine di calcolo in `pipeline.py`: S5 e S6 prima di S4 (non dipendono da S4).
- Ignoto: il primo passo con `gen_w` o `link_available` ignoto rende ignoti quel passo e tutti i successivi (la
  batteria ha memoria), come `coupled.couple`.

### 2.8 S5 Link RF

- Uscite: `RfLink(fspl_db[n], knife_edge_db[n], ridge_correction_db[n], ridge_correction_splitstep_db[n],
  ridge_uncertainty_db[n], multipath_gain_db[n], multipath_applicable[n], pointing_loss_db[n],
  margin_db_by_rate[rates][n], margin_db[n], chosen_rate_bps[n], geometric_visible[n], rf_state[n], reason[n],
  flags)`, con `rf_state ∈ {open, transition, blocked}` (regola di `snapshot.link_state`).
- Funzioni pure: `rf_link(geo, terrain, p) -> RfLink`; dentro: `link_sum_db(...)` forma chiusa per un passo,
  la stessa che lo specchio TS riproduce.
- Somma (dB), una sola: `M(R_b) = P_t + G_t + G_r − L_pt − FSPL(d_vera) − L_misc − J(ν) − T(m,n) + G_2 − N_0 −
  (E_b/N_0)_req − 10 log10 R_b`, con `N_0 = k + 10 log10 T_sys` oppure G/T della stazione dal registro (una sola
  forma, D2). FSPL con la distanza vera di S1, non 384 400 km.
- Diffrazione, politica già decisa (validation.md, «Politica (implementata)»): correzione predefinita
  `max(T(m,n), 0)` di P.526-9 §4.2 con d1, d2 e λ reali; tabella split-step **solo confronto**; incertezza
  `max(incertezza della tabella, |ITU − split-step|)`, mai sommata; fuori griglia (ν > 3) banda saturata e
  segnalata; raggio non risolto → incertezza ≥ |correzione|.
- Multipath: solo dove applicabile (punto speculare prima dell'ostacolo, ψ > 0), altrimenti 0 dB con
  `non applicabile` dichiarato.
- Antenna: guadagno da diametro ed efficienza; montaggio `tracking` (errore fisso), `fixed` (escursione), `gimbal`
  (binario C `servo_ctrl_c/bin/gimbal_tracker`, stato ignoto se il binario manca: oggi `GimbalUnavailable`).
- Bit rate: `chosen_rate = max{R ∈ RATES : M_pred − kσ ≥ 0}` (B17).
- Ignoto: `terrain_reason ≠ ok` → margine ignoto (mai «aperto»).

### 2.9 S6 Visibilità DSN e disponibilità senza pianificazione

- Uscite: `Dsn(complex_visible[3][n], any_visible[n], station_class, reason[n])`.
- Funzione: `dsn(geo, p) -> Dsn`: Luna sopra `ground_station_min_elevation_deg` (6°, V) da almeno un complesso.
- Classe 18 m: nessuna lista di stazioni verificata → `any_visible = None` (`unknown_station`), come oggi in
  `coupled`. Nessuna pianificazione, nessuna assegnazione d'antenna: è disponibilità geometrica, e il testo lo dice.

### 2.10 S7 Stato di missione e obiettivi

- Uscite: `Mission(link_usable[n], state[n], useful[n], limiting[n], metrics)`; `metrics`: ore utili, ore ignote,
  ore per stato, frazioni del fattore limitante (energia, link, visibilità, più cause), SOC minimo (sui passi
  noti, dichiarato), tempo al primo blackout, finestre (inizio, fine, motivo di chiusura), dati consegnati.
- Regole: `link_usable = margin_db ≥ required_margin_db ∧ dsn.any_visible` (D3); `useful = state == operational ∧
  link_usable`; stati `operational`, `comms_only`, `survival`, `dark`, `unknown` (definizioni di `coupled.py`).
- Finestre: bordi raffinati per bisezione sugli stadi S1-S3 e S5 (forma chiusa) a 1 s dopo il campionamento a
  passo fisso (requisito «verifica temporale» di DA; oggi assente, R18). È la sola aggiunta di calcolo in S7.

### 2.11 Classifica unica

`ranking.rank(evals: list[Evaluation], order: list[str]) -> Ranking`: componenti sempre restituite per ogni sito
(ore utili, ore ignote, ore reali di link, margine minimo e mediano sui passi con Terra sopra la maschera, SOC
minimo, tempo al primo blackout); ordinamento lessicografico sulla lista `order` scelta dall'utente (default D5),
parità risolte con l'id del sito, dichiarato. Nessuna media pesata, nessun numero unico. Siti con dati ignoti
non sono ordinati sopra siti noti per un componente ignoto: sono in un gruppo «non confrontabile» con il motivo.

### 2.12 Registro dei parametri

- Forma: `ParamSpec(key, stage, default, unit, lo, hi, tag: V|D|I, source, note, aliases, ui: hidden|advanced|
  learning)`, estensione dell'attuale `lunar.model.ParamSpec` (che già ha valore, unità, limiti, tag e fonte).
- Contenuto: unione di `lunar.model.PARAMS` e `grazing.model.PARAMS`, più le costanti oggi sparse (soglia DSN di
  `snapshot.py`, `RATES`, guadagni di stazione di `antenna.STATIONS`, intervalli di `linkModel.RANGES`,
  `MAST_RANGE`, Boltzmann, raggi). I nomi vecchi restano come `aliases` finché esistono gli adattatori.
- Consumatori: `resolve(overrides) -> ResolvedParams` (422 generico per chiave ignota, valore non finito o fuori
  intervallo, come oggi); `GET /api/raven/parameters`; file generato `contracts/raven_params.json` → tipi TS e
  costanti in `frontend/src/contracts/` tramite `contracts/gen.py` (che oggi genera già modelli Pydantic e tipi TS
  dagli schemi, con `--check` per la deriva); tabella dei documenti generata dallo stesso file.
- Ogni `Evaluation` riporta `registry_sha256` e `model_version` (`raven-core-1`): una demo precalcolata
  (decisione n. 9) è riproducibile e confrontabile.

### 2.13 Punto di ingresso unico e viste

- `pipeline.evaluate(scenario: Scenario, *, engine, dem, store) -> Evaluation`.
- `POST /api/raven/evaluate`, corpo `Scenario = {site: SiteRef, window: TimeWindow, parameters: {chiave: valore},
  options: {rates?, include_steps: bool}}`; risposta `Evaluation = {model_version, registry_sha256, site, window,
  parameters_used[{key, value, unit, tag, source}], steps: {time_unix, …una colonna per uscita di S1-S7…},
  summary: metrics di S7, inputs_state per stadio, stage_validation (da `validation.py`), declared_limits}`.
  Errori come oggi: 422 generico senza eco, 503 senza efemeridi o oltre il tetto di concorrenza, cache LRU.
- `POST /api/raven/compare`: lista di siti, stessa finestra e parametri → `Evaluation` sintetiche + `Ranking`.
- Viste di sola lettura (nessuna fisica propria): `GET /api/raven/snapshot?t=` (S1, S5, S6 a un istante, tutti i
  siti), `GET|POST /api/raven/scene` (S1, S2, S5 a un istante con patch 3D), `POST /api/raven/horizon` (S2, 72
  profili o maschera), `GET /api/raven/sky/*` (S1; gli attuali `/api/sky/*` restano invariati perché sono della
  base generica), `GET /api/raven/model` (stadi, stato di validazione, prove, frasi ammesse: alimenta la pagina
  «Model & Validation»).
- `GET|POST /api/raven/wave`: modulo di ricerca, risposta con `label: "illustrative physics, not the link engine"`.

### 2.14 Destino dei moduli speciali

- **Simulatore d'onda** (B22): resta in `raven/research/`, fuori dalla catena; serve a spiegare la diffrazione e a
  produrre la tabella split-step, che alimenta solo la banda d'incertezza di S5. UI: «fisica illustrativa
  (split-step scalare parassiale), non il motore del link».
- **Tabella split-step** (B23): confronto e incertezza, invariata finché non viene rigenerata con dx ≤ 0,125 m,
  dy ≤ 0,025 m e assorbitore (aperto in validation.md).
- **Modello TS per gli slider** (F1): `frontend/src/raven/mirror.ts`, specchio dichiarato della sola forma chiusa
  di S5 (`link_sum_db` con geometria manuale) e delle funzioni J(ν), ITU, T(m,n); default e intervalli importati
  dal registro generato; fixture di parità generate da S5 (`scripts/dump_link_parity.py` esteso) e verificate in
  CI con `--check`; tolleranza 0,01 dB come oggi. Non calcola mai S1-S4, S6, S7: per un sito reale la pagina chiama
  il backend. Testo in pagina: «anteprima immediata calcolata nel browser con le stesse formule di S5; il valore di
  riferimento è quello del server».
- **Vecchio modello lunare a orizzonte piatto** (B2, B5, B6): rimosso come motore; resta un oracolo di poche righe
  in `tests/` (limite a terreno piatto: maschera nulla ⇒ S3 coincide con il criterio piatto a meno del
  semidiametro, test di regressione su Apollo 11 e sui casi analitici attuali).
- **Classifica** (B5, B19): una implementazione (§2.11), componenti visibili.
- **What-if `terrain_energy`** (B7): assorbito in S3-S4; la «sensibilità» diventa una seconda `evaluate` con
  parametri diversi, non un calcolo a parte.

## 3. Matrice di validazione

Tipi di confronto (dalle etichette di validation.md): **R** riproduzione di una formula pubblicata letta sul testo;
**II** reimplementazione indipendente; **LL** confronto con dati indipendenti a parità di grandezza
(like-for-like); **NL** dati indipendenti, criterio non identico; **P** solo plausibilità; **—** nessuno.
Nessuna riga è una misura radio o di potenza sulla Luna.

| Stadio / gruppo | Cosa è verificato | Contro cosa (tipo) | Residuo | Cosa NON è validato | Chi potrebbe validarlo | Frase ammessa in UI e README |
|---|---|---|---|---|---|---|
| S0 coordinate | copia delle coordinate | IAU Gazetteer, NSSDCA, LROC (R) | — | non sono centri delle regioni Artemis; quota non presa dal sito | team (catalogo Artemis, PGDA 78/104) | «coordinates copied from the cited source (IAU feature centres), not Artemis region centres» |
| S1 Sole e Terra | az, el, distanza dal sito | JPL Horizons, fixture offline (LL) | 8,2e-7° el e 7 m (Sole); 1,2e-6° e 0,16 m (Terra) | UT1 dopo il 2027-01 predetto, incertezza non quantificata | — | «verified against JPL Horizons» |
| S1 DSN | elevazione della Luna dai complessi | `skyfield` indipendente, 1753 istanti (II); coordinate DSN 810-005/301 Tab. 5 (R) | 6,6e-5°; 1e-6° | nessuna pianificazione | — | «geometry verified; no DSN scheduling» |
| S1 Terra al polo | elevazione | formula geometrica indipendente (II) | 0,001° (poli), 0,006° (Apollo 11) | — | — | «verified against an independent formula» |
| S2 maschera | codice dell'endpoint | arbitro, stessa geometria (II) | 2,2e-9° e 0 stati diversi su 21 900 (profilo storico); maschera: ≤ 1 passo su 4380, orizzonte all'azimut del Sole 0,007-0,053° | DEM: errore verticale, rilievo sotto 20 m, terreno oltre 200 km, DEM a 5 m non integrati | ricercatore LOLA/PGDA | «horizon verified against an independent implementation» |
| S2 + S3 contro osservazioni | frazione di illuminazione vicino al polo | LROC WAC `WAC_POLE_ILL_TWI_SOUTH_100M` (NL) | r 0,954, RMS 4,2 punti (qualsiasi parte del disco); polo 46,0 % contro 26,7 % non spiegato | criterio radiometrico diverso; siti di Malapert, Haworth, Nobile fuori dalla copertura 88-90° S | — | «agrees with LROC WAC observations within 4-6 points RMS near the pole (criteria not identical)» |
| S2 orientamento DEM | convenzione di `dem.lock.json` | LROC ruotato di 180° (NL) | r scende a 0,237 | — | — | «DEM orientation confirmed by independent data» |
| S2 letteratura | illuminazione alla cresta Shackleton-de Gerlache | Barker et al., Tab. 2, 1° percentile (P) | arbitro sopra il 1° percentile in ogni RoI | valori nominali non pubblicati; Mazarico 2011 e Gläser 2014 non letti | — | «plausibility only» |
| S2 ostacolo RF | vertice ITU contro cima fisica | un caso analitico (II) | 0,007 dB | ostacolo singolo, raggio da adattamento su 20 m, nessuna diffrazione multipla | ingegnere RF | «single-obstacle model, not validated» |
| S3 disco | frazione contro segmento circolare | soluzione analitica (R) | 2e-5; disco endpoint/arbitro ≤ 0,021 | oscuramento al bordo | — | «verified analytically» |
| S4 energia | conservazione, casi analitici, batteria | soluzioni analitiche (II) | 1e-9 relativo | nessun caso reale; pannello, batteria e carichi tag I | ingegnere di potenza | «arithmetic verified; not validated (illustrative parameters)» |
| S5 spazio libero | FSPL, EIRP, C/N0, Eb/N0 | formula esatta e calcolo in unità lineari (II); `fspl_c` (R) | 1e-4 dB; offset costante +0,0022 dB del plugin | — | — | «verified» |
| S5 bilancio, controlli NASA | rapporti di rate con G/T e diametro | NASA/TM-2019-220203 Tab. 4, 10 (P differenziale) | −0,04 dB (tolleranza 0,1); 0,11 dB | margine assoluto non ricostruibile dalle fonti | ingegnere RF | «differential check against a NASA study; absolute margin not validated» |
| S5 aritmetica di potenza | somma della catena | NASA/TM-2020-220472 Tab. V, CADeT (R aritmetica) | 0,02 dB | non è un link lunare; rumore, Eb/N0, margine | — | «arithmetic check against a published budget» |
| S5 bordo a lama | J(ν) esatto, ITU eq. (27), ν, raggio di Fresnel | ITU-R P.526-9 eq. (2), (22)-(23), (26), (27) letta sul testo (R, II) | < 1e-7 dB; ITU ≤ 0,123 dB (−0,78 < ν ≤ 5) | versione P.526 in vigore (-15 o successiva) non letta | — | «formulas verified against ITU-R P.526-9» |
| S5 cresta arrotondata | T(m,n) | P.526-9 §4.2 eq. (28)-(32) (R, II); split-step raffinato (P) | ITU − split-step fino a 1,3 dB (ν = 3) e 2,4 dB (ν = 8), R = 400 m | nessuna misura; cilindro esatto (Mie/Fock) non calcolato | ingegnere RF, simulatore indipendente | «ITU-R P.526-9 formula; uncertainty band from an unvalidated simulation; not validated» |
| S5 multipath | coefficienti di Fresnel, rugosità | JPL 42-226 eq. (48)-(49) (R); errore dello script corretto (model.md §0) | — | coefficiente circolare co-polare «da memoria» (non verificato sulla fonte); suolo piano, parte coerente; regolite I | ingegnere RF | «not validated» |
| S5 antenna | G = η(πD/λ)²; costante 12,04 | CB79 §2.7 (R); derivazione (D) | — | HPBW 70 λ/D non verificato sulla fonte; guadagni di stazione I | ingegnere RF | «gain formula verified; beamwidth factor illustrative» |
| S5 specchio TS | uguaglianza con il Python | fixture generate (II) | ≤ 0,01 dB | — | — | «browser preview identical to the server formulas within 0.01 dB» |
| S5 compensatore | `Φ(−k)` e simulazione | formula gaussiana (R) | — | σ supposto noto e gaussiano | — | «statistical rule; σ is an assumption» |
| S6 | come S1 DSN, soglia 6° | DSN 810-005/301 Rev. P §2.2.2-2.2.3 (R) | — | nessun tracking reale; 18 m ignoto | operatore DSN | «geometric visibility only» |
| S7 | flag di passo, margini, SOC | reimplementazione scalare (II); regressione Malapert/Haworth | 1e-9 | definizione di ora utile = scelta di progetto (I) | — | «definitions are design choices, stated» |
| Tempo (finestre) | — | — | — | bordi oggi al passo; bisezione da fare (§2.10) | — | «window edges at the sampling step» finché manca la bisezione |

Controlli dichiarati nei documenti e non rieseguiti: Malapert con la Terra fino a 10,7° e tramonto di circa 8
giorni, relay 77 %/100 % (DT §4, §11; R17). Da rieseguire con `evaluate` prima di citarli.

### 3.1 Domande probabili della giuria (bozza della pagina «Model & Validation»)

1. **Quanti modelli usate?** Uno: sette stadi in catena, un registro di parametri; le pagine sono viste. Prova:
   `GET /api/raven/model`, questo documento §2.
2. **Da dove vengono le posizioni di Sole e Terra?** Efemeridi JPL DE440 (NAIF), scarto contro JPL Horizons
   8,2e-7° (Sole) e 1,2e-6° (Terra). `tests/backend/ephemeris/test_validation.py`.
3. **Il terreno è reale?** Sì, LOLA 20 m fino a 10 km e 240 m fino a 200 km, file con SHA-256 in `dem.lock.json`;
   nessun profilo inventato; un dato mancante resta «ignoto».
4. **Come sapete che l'orizzonte è giusto?** Un'implementazione indipendente concorda entro 1 passo su 4380 in un
   anno; contro le osservazioni LROC WAC vicino al polo r = 0,95, 4-6 punti RMS, con criteri non identici.
5. **Perché Haworth e de Gerlache risultano sempre al buio?** Sono centri di grandi crateri: la maschera a 200 km
   li tiene in ombra tutto il 2027; LROC dà 0 anche per de Gerlache. Le coordinate sono centri di feature, non zone
   di atterraggio.
6. **Il margine radio è validato?** No. Le formule di diffrazione sono quelle di ITU-R P.526-9 lette sul testo; il
   margine assoluto non è riproducibile da nessun bilancio lunare pubblicato trovato; i parametri radio sono
   illustrativi (tag I). Serve una revisione di un ingegnere RF.
7. **Perché la cresta arrotondata costa più dB che nei vostri documenti iniziali?** Usiamo ITU-R P.526-9 §4.2,
   fonte pubblicata e più conservativa; la simulazione split-step dà meno perdita, fino a 2,4 dB in meno, e la loro
   distanza è la banda d'incertezza mostrata.
8. **Cosa significa V, D, I?** V letto in una fonte primaria, D derivato con formula ripetibile, I illustrativo da
   sostituire con i dati del cliente. Ogni risposta dell'API riporta il tag di ogni parametro usato.
9. **L'energia è affidabile?** L'aritmetica sì (casi analitici, conservazione 1e-9); i numeri no: pannello,
   batteria e carichi sono illustrativi; nessun confronto con un lander reale.
10. **Che cosa vuol dire «ora utile»?** Stato operativo e margine sopra la soglia richiesta e Luna visibile da un
    complesso DSN da 34 m; le ore ignote sono contate a parte e mai come utili.
11. **Avete considerato la pianificazione DSN?** No: solo visibilità geometrica sopra 6°; la classe 18 m ha
    visibilità ignota.
12. **Il simulatore d'onda calcola il link?** No: è fisica illustrativa (split-step scalare parassiale) per
    spiegare la diffrazione; serve solo a stimare l'incertezza della correzione.
13. **Gli slider del browser sono un secondo motore?** No: sono uno specchio delle formule di S5, verificato
    contro il server entro 0,01 dB con fixture generate; per un sito reale il numero viene dal server.
14. **Come verificate gli orari delle finestre?** Oggi i bordi hanno la risoluzione del passo; il nucleo li raffina
    per bisezione a 1 s (passo di migrazione M9). Fino ad allora la UI dice «al passo di campionamento».
15. **Cosa non modellate?** Terreno oltre 200 km, diffrazione su più creste, oscuramento del bordo solare, codifica
    CCSDS, atmosfera e pioggia a terra, polvere e termica, ostruzione del lander. Elenco in `declared_limits` di
    ogni risposta.

## 4. Piano di migrazione

### 4.1 Strategia di regressione

- **Golden** (M0): prima di toccare il codice si congelano le uscite attuali di `/api/lunar/{mission, solar-terrain,
  analyze, timeline, horizon}` e `/api/grazing/{analyze, compare, snapshot, scene, antenna, compensation, wave}`
  su scenari fissi, in due insiemi: **sintetico** (profilo `synthetic`, `EarthSweep`, maschere sintetiche: gira
  sempre in CI) e **reale** (kernel e tile in cache: salta come i test attuali, `skipif` su kernel e tile). Se la
  CI scarichi i tile: **non verificato**; senza tile l'insieme reale non protegge in CI.
- **Uguali per costruzione** (tolleranza 1e-9 o identità dei JSON): geometria, maschera, disco, margini RF a
  parità di parametri, stati di `mission`, viste snapshot e scene.
- **Differenze intenzionali** (ognuna con test che fissa il nuovo valore e una riga in un registro
  `docs/domain/raven-changes.md`, da creare al momento del passo): timeline piatta → maschera (C1); set radio
  unificato (D2); soglia di link (D3); semidiametro solare dalla distanza invece di 0,27° (C11); Terra coperta da
  terreno lontano → «fuori modello» (D4); classifica senza punteggio (D5); fine della decimazione (D9).
- I test esistenti restano verdi a ogni passo; un test si sposta solo insieme al codice che pinna, nello stesso
  commit, con il motivo nel messaggio.

### 4.2 Passi (ognuno rilasciabile da solo)

| Passo | Contenuto | Test di accettazione | Sforzo |
|---|---|---|---|
| M0 | Golden: `scripts/raven_golden.py` scrive `tests/backend/domain/raven/golden/*.json` (sintetico + reale) | `pytest tests/backend/domain/raven/test_golden.py` verde sul codice attuale | S |
| M1 | Registro `raven/params.py`: unione di `lunar.model.PARAMS`, `grazing.model.PARAMS` e costanti sparse, **valori invariati**, alias per i nomi vecchi; `lunar.model` e `grazing.model` leggono dal registro | ogni chiave vecchia risolve allo stesso `ParamSpec`; `/api/lunar/defaults` e `/api/grazing/defaults` identici ai golden | M |
| M2 | Generazione: `contracts/raven_params.json` e tipi TS con `contracts/gen.py --check`; `GET /api/raven/parameters` | CI fallisce su deriva; `linkModel.ts` importa `RANGES` e default generati, fixture di parità invariata | M |
| M3 | Scheletro `backend/domain/raven/` con `known.py` e contratti `import-linter` (`raven-layers`, `raven-no-web`, `raven-research-isolated`) | `make lint` verde; test di `Known` (tabella di verità dell'ignoto) | S |
| M4 | S0-S3 come funzioni che avvolgono `geometry`, `horizon`, `disc_criteria`; S2 aggiunge `earth_horizon_deg` (solo uscita in più) | golden di `/solar-terrain` e `/mission` uguali; test nuovo: arbitro e S2 concordano anche nell'azimut della Terra | M |
| M5 | S5 estratto da `analysis.analyze` (`rf_link`, `link_sum_db`); `analyze` diventa adattatore; specchio TS rigenerato da `link_sum_db` | golden `/api/grazing/*` uguali a 1e-9; parità TS ≤ 0,01 dB | L |
| M6 | S4, S6, S7 da `coupled.evaluate_mission`; `pipeline.evaluate`; `/api/lunar/mission` diventa adattatore | golden `/mission` uguali; regressione Malapert/Haworth invariata | M |
| M7 | `POST /api/raven/evaluate`, `/compare`, `GET /api/raven/model`; schemi Pydantic e TS generati; servizio unico (C13) | test API sul modello di `test_lunar_mission_api.py` (422 generico, 503, cache, tetti) | M |
| M8 | Unificazione dei parametri e delle regole (D2, D3, D4, D7, D8, D9): differenze intenzionali con test e voce in `raven-changes.md` | test che fissano i nuovi valori; `test_lunar_knowledge.py` aggiornato insieme ai documenti di conoscenza | M |
| M9 | Bisezione dei bordi delle finestre in S7 | caso analitico (Sole sinusoidale) entro 1 s; golden reali con bordi entro un passo dai vecchi | S |
| M10 | Planner su `evaluate`: sparisce la timeline piatta; `rfDsnOverlap`, `objectives`, `sensitivity` leggono colonne di S6-S7 invece di combinare risposte | e2e `mission-planner.spec.ts`, `journey.spec.ts` aggiornati; unit test del Planner migrati; bundle ≤ 70 000 B | L |
| M11 | Confronto: `EnergyCompare` e `Compare` su `/api/raven/compare` e `ranking.rank`; `/api/lunar/analyze` e `/api/grazing/compare` adattatori | e2e `compare.spec.ts`, `siti-combined.spec.ts`; nessuna colonna «Punteggio» | M |
| M12 | Viste: snapshot, scene, horizon su `views.py` (soglia DSN dal registro); Lander legge `lit` di S3 o etichetta il criterio 1-3° come inquadratura | e2e `viewer-grazing*`, `lander*`; golden snapshot/scene uguali | M |
| M13 | Ricerca: `wave.py` e tabella in `raven/research/`, etichetta in risposta e in pagina | `test_wave.py` spostato; e2e `wave*.spec.ts`; testo presente in en e it | S |
| M14 | Pagina «Model & Validation» e sezione README da `GET /api/raven/model` (§3, §3.1), solo inglese e italiano | e2e nuova; test che ogni stadio abbia stato, prova e frase | M |
| M15 | Deprecazioni: `/api/lunar/coupled-sensitivity` e il calcolo piatto rimossi; `/api/lunar/*` e `/api/grazing/*` restano adattatori finché un client li usa, poi 410 con il nuovo percorso (D6); contratto `api-through-raven` attivato | `rg` senza chiamate dal frontend; oracolo piatto in `tests/` verde | S |

Ordine: M0 → M1 → M3 → M2 → M4 → M5 → M6 → M7 → M8 → M9 → (M10, M11, M12 in parallelo) → M13 → M14 → M15. M8 è il
solo passo che cambia numeri visibili: va dopo che il nucleo è stabile e prima delle pagine, così che le pagine
migrino una volta sola.

### 4.3 Mappa endpoint → nucleo

| Oggi | Nucleo | Fase |
|---|---|---|
| `POST /api/lunar/mission` | `evaluate` (un sito) | adattatore da M6, rimosso in M15 se nessun client |
| `POST /api/lunar/timeline`, `/analyze` | `evaluate` / `compare`; risposta tradotta | adattatore M7-M11, poi 410 |
| `POST /api/lunar/solar-terrain` | colonne S2-S4 di `evaluate` | adattatore |
| `POST /api/lunar/horizon` | vista `horizon` | vista M12 |
| `POST /api/lunar/coupled-sensitivity` | — | rimosso M15 |
| `GET /api/lunar/sites`, `/defaults`; `GET /api/grazing/status`, `/defaults` | S0, registro | adattatori di `GET /api/raven/parameters` |
| `POST /api/grazing/analyze`, `/compare`, `/antenna`, `/compensator`, `GET /compensation` | S5 e `compare` | adattatori |
| `GET /api/grazing/snapshot`, `GET|POST /scene` | viste | M12 |
| `GET|POST /api/grazing/wave` | ricerca | M13 |
| `GET /api/sky/*` | S1 (base generica, invariati) | — |

Pagine: Planner → `evaluate`; Confronto e Siti → `compare`; Analizza (`/analizza`, alias `/grazinglink`) →
`evaluate` con colonne RF; Simula → specchio + `scene`; Lander → `scene`; Viewer → `snapshot` e `/api/sky`;
Onda → `wave`; Home → specchio (dimostrazione etichettata).

### 4.4 Rischi

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Numeri visibili cambiano (M8) davanti alla giuria | alto | `raven-changes.md`, `model_version` e `registry_sha256` in ogni risposta; demo precalcolate rigenerate dopo M8 |
| Golden reali non eseguiti in CI (tile non in cache) | medio | insieme sintetico obbligatorio; prefetch in CI da valutare (dimensione 22,8 + 18,1 MB, method.md) |
| `evaluate` più lenta della timeline piatta (maschera, profili RF) | medio | maschere già in cache (0,2-0,5 s alla prima); profili per azimut quantizzato; tetto 1500 passi |
| Bundle oltre 70 000 B per i tipi e il registro generati | medio | tipi senza costo a runtime; costanti del registro caricate con la pagina che le usa, non nel bundle iniziale; `check-bundle.mjs` a ogni passo |
| Conflitti con il lavoro i18n parallelo | medio | testi nuovi solo in en e it, chiavi aggiunte in passi separati |
| Lo specchio TS diverge | basso | fixture generate e `--check` in CI |
| D4 rende ignoti molti passi RF in siti con terreno lontano alto | non verificato | misurarlo in M4 prima di decidere la regola definitiva |
| Regola del branch (core non modificato) | basso | tutto sotto `backend/domain/` e `backend/api/`; `scripts/check_core_unchanged.py` in CI |

Sforzo complessivo: 5 passi S, 9 M, 2 L (M5, M10).

## 5. Decisioni richieste all'utente

| # | Decisione | Default raccomandato |
|---|---|---|
| D1 | Posizione del pacchetto | `backend/domain/raven/` (rispetta la regola del branch); non `backend/raven/` |
| D2 | Set radio unico | valori V/D dove esistono: 8,425 GHz (DSN104Q), guadagno 34 m 68,29 dBi (DSN104Q Tab. 7) e Tsys 26,2 K (DSN104Q Tab. 9), cioè G/T 54,1 dB/K (D, come in method.md), Eb/N0 richiesto 9,6 dB non codificato (prudente) con preset «codificato» 2,5 dB tag I; valori I da GrazingLink (10 dBW, 15 dBi, perdite 3 dB), dichiarati come illustrativi |
| D3 | Soglia di «link utilizzabile» | `required_margin_db = 3 dB` (V, NASA/TP-2019-220391 §11); la UI mostra anche «margine ≥ 0» come confine fisico |
| D4 | Terra coperta da terreno oltre il profilo RF | stato `outside_model` (ignoto), non «bloccato» né «aperto»; rivedere dopo la misura in M4 |
| D5 | Ordine della classifica | lessicografico: ore utili, poi ore ignote (meno è meglio), poi margine minimo, poi id; l'utente può scegliere il primo componente; nessun punteggio |
| D6 | Vecchi endpoint | adattatori fino a M15, poi 410 con il percorso nuovo; gli alias delle pagine (`/grazinglink`) restano |
| D7 | Criterio booleano di «luce» | `disc_fraction > 0`; bordo superiore, centro, inferiore restano visibili come dettagli |
| D8 | Altezze | due parametri, `panel_height_m` (ex `observer_height_m`) e `antenna_height_m`, intervallo unico 0,1-100 m, default 2 m (I) |
| D9 | Tetti | 1500 passi per sito, 6000 totali, nessuna decimazione nella catena |

## 6. Studio opzionale di affidabilita' e protezione (9 novembre 2026)

`backend/domain/raven/reliability.py`, modello `raven-reliability-1`, aggiunge
aritmetica RAM condizionata tramite `POST /api/raven/report/reliability`.
Non sostituisce S0-S7, non attribuisce una qualifica ai componenti e non
trasforma il simulatore di sito in una simulazione di lancio/atterraggio.
`GET /api/raven/model` ne pubblica ambito ed endpoint.

Il profilo e' disabilitato e ignoto per default. Il preset dimostrativo viene
caricato solo con un'azione esplicita e dichiara tutti i valori come ipotesi I,
mai come dati NASA, misure o hardware reale. Fonte/metodo sono obbligatori.
Fino a cinque sottosistemi critici indipendenti in serie: pannello/conversione,
batteria, radio/antenna, computer/avionica, controllo termico. Non e' una
FMEA/FMECA completa: hardware non elencato, ridondanza e cause comuni mancano.

Catena cumulativa: sopravvivenza del veicolo a lancio, trasferimento e
atterraggio, moltiplicata per i fattori di sopravvivenza dei singoli componenti
agli shock. Le probabilita' del veicolo devono escludere questi ultimi rischi,
per evitare doppi conteggi. Non si deducono probabilita' da vibrazioni o dinamica
di volo non simulate.

Per la superficie, ogni componente dichiara tasso permanente lambda,
tasso di upset nu, probabilita' di recupero r e durata media del recupero d.
Il modello usa hazard assorbente `h = lambda + nu(1-r)`, transizione
recuperabile `k = nu*r` e recupero esponenziale `mu = 1/d`.
Con tutti i componenti inizialmente attivi dopo gli shock:
`A_i(t) = mu/(k+mu) + k/(k+mu)*exp(-(k+mu)*t)`.
Un recupero di durata esplicitamente zero e' istantaneo, senza indisponibilita'.
I processi di guasto assorbente e recupero sono indipendenti: non e' una
cronologia di eventi realizzati. Probabilita'/conteggi degli upset recuperabili
sono riferiti all'esposizione pianificata completa, non al tempo effettivo in
vita di un veicolo gia' perso.

Le perdite frazionarie di prestazione al lancio e all'atterraggio si compongono
moltiplicativamente; il decadimento continuo e' esponenziale su trasferimento
piu' superficie. Il primo superamento della soglia minima dichiarata interrompe
l'operativita' condizionata, non la sopravvivenza fisica dell'hardware.
L'indicatore e' aggregato: non e' una legge di degrado qualificata di guadagno RF,
efficienza solare o capacita' della batteria.

L'engine integra esattamente la miscela di esponenziali della catena per le ore
attese disponibili/non disponibili e sulle singole finestre `useful` di S7.
Per campioni ignoti produce un limite inferiore/superiore, non uno zero e non
un valore puntuale. La durata e' `n_steps * step_min / 60`, coerente col
campionamento della pipeline; l'eventuale coda richiesta ma non campionata resta
fuori dallo studio. I 129 punti dei grafici sono solo una rappresentazione,
non la discretizzazione usata per gli integrali o un intervallo di confidenza.
Le ore non disponibili includono anche la perdita prima della superficie e i
guasti permanenti; non sono la durata media di una singola interruzione.

Controlli ambientali separati:

- Termico: si confrontano gli estremi previsti del componente/giunzione
  **dopo le protezioni, lungo tutte le fasi**, con l'intervallo operativo
  qualificato dichiarato. Il margine e' il minimo dei due scarti. Non si usano
  temperature esterne lunari come temperature dell'elettronica.
- Radiazioni: `dose = dose_rate_krad_h * shield_transmission *
  (cruise_hours + surface_hours)`, in krad(Si); confronto con il limite TID
  dichiarato. Non si inferiscono trasmissione da spessore, spettro, danno da
  spostamento o cross section SEE. Il tasso di upset resta un input distinto.
- Margini mancanti sono ignoti; margini negativi sono avvisi espliciti, non
  probabilita' inventate di distruzione. Anche un margine positivo non e'
  una verifica indipendente. Le probabilita' operative restano condizionate
  al rispetto dell'inviluppo e non vanno lette come successo della missione.

Scelta passiva/attiva/combinata tracciata come metadato di progetto, con
spiegazioni di MLI, schermi, radiatori, riscaldatori, regolazione, ECC/watchdog
e componenti radiation-tolerant. Non dimensiona protezioni o regolatori.
Un carico termico **incrementale** continuo e' applicabile esplicitamente ai
carichi `survival_load_w` e `active_load_w` tramite gli override esistenti,
con controlli dei limiti del registro e nuova simulazione. I carichi base
includono gia' riscaldamento illustrativo: evitare il doppio conteggio.
Nessun COP, duty cycle termostatico o costo energetico del singolo riavvio
e' stimato senza un modello aggiuntivo.

Il profilo persiste in dossier/sessione/libreria; le vecchie selezioni del
report a venti voci migrano senza perdere spunte. I risultati si ricalcolano
in Python sulle valutazioni correnti, con cancellazione delle richieste
obsolete, errori espliciti e blocco dell'export durante il calcolo.
Il report ha una sezione selezionabile, grafici, margini, input/fonte completi
e dati JSON inclusi nel digest DEMO; schema 4 esteso in modo additivo.

Fonti di metodo e principi, **non validazione dei tassi del preset**:
[NIST, modello esponenziale](https://www.itl.nist.gov/div898/handbook/apr/section1/apr161.htm),
[NASA, Thermal Control](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/),
[NASA NEPP, componenti EEE e prove](https://nepp.nasa.gov/).

### Grafici comparativi

Tre curve comuni A/B di sopravvivenza, operativita' e prestazione residua
usano le **ore trascorse dall'atterraggio**, con scala percentuale comune,
linee continue/tratteggiate e interruzioni sui valori ignoti. Non allineano
artificialmente per indice o per data UTC scenari con periodi diversi.
Sette grafici a barre confrontano catena cumulativa, guasti per componente,
durata media di recupero, degrado per componente, margine termico,
dose A/B rispetto alla tolleranza TID individuale e ore attese.
Ipotesi termiche e tempi medi comuni sono etichettati come condivisi,
non presentati come differenze ambientali calcolate tra siti.

Il riepilogo generale del Planner usa anelli solo per la partizione completa
del tempo campionato: ore utili confermate, ore note non utili, ore ignote.
Le ore note non utili sono `known_steps * dt_h - useful_hours`, semplice
contabilita' delle metriche S7, non un nuovo modello. Totali mancanti,
incoerenti o nulli non vengono normalizzati in una torta al 100%.
Energia raccolta e domanda non soddisfatta, costi e CO2e sono invece grafici
a barre: non sono ripartizioni arbitrarie di un totale noto. Dati di energia
parziali, costi/emissioni dichiarati e valori ignoti mantengono il proprio
ambito. Tutti i grafici del report rispettano la selezione esistente.
