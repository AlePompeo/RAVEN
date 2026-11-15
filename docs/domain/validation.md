<!-- SPDX-License-Identifier: Apache-2.0 -->
# Validazione dell'analisi lunare (Fase C)

## Sensibilità esplorativa ai DEM LOLA (15 novembre 2026)

Non è una validazione indipendente del terreno. A Shackleton (centro di feature,
−89,67°, 129,78° Est), `scripts/compare_lola_resolution.py` confronta il mosaico NASA
[LOLA 5 m](https://pgda.gsfc.nasa.gov/products/81) con i prodotti PDS 20 m e 240 m
indicati nel lock del progetto. Tutti usano LOLA e riferimenti correlati.
Il 240 m è confrontato qui **entro 10 km solo per sensibilità**; in produzione serve
per la parte 10–200 km. Non si è confrontato l'orizzonte completo né il suo effetto
sulle finestre.

Metodo: quattro azimut cardinali; 500 distanze per azimut, da 20 m a 10 km ogni
20 m, più il sito; interpolazione bilineare, osservatore 2 m sopra la quota di
ciascun DEM, curvatura su sfera di raggio 1 737 400 m. La maschera di produzione
usa un passo vicino di 10 m, più azimut e terreno lontano: questi massimi non sono
la sua uscita. Le label dei DEM 20 m e 240 m dichiarano ME/asse polare DE421;
NASA dichiara MOON_ME DE421 per il 5 m. Il GeoTIFF 5 m dichiara pixel-as-area,
scala 5 m e origine angolo (−100 000, 100 000) m; i centri sono a mezzo pixel.
Un controllo con PROJ al sito concorda sulla proiezione a meno di 2e-10 m;
questo non quantifica eventuali differenze geodetiche tra prodotti.

| Azimut | Massimo 5 m | Massimo 20 m | Massimo 240 m | 5 m − 20 m |
|---|---:|---:|---:|---:|
| 0° | 19,290352° | 19,291508° | 19,276465° | −0,001156° |
| 90° | 21,938266° | 21,938153° | 21,894769° | +0,000113° |
| 180° | 22,586064° | 22,592136° | 22,491782° | −0,006073° |
| 270° | 20,502873° | 20,500804° | 20,458806° | +0,002069° |

Quote del sito: −2788,9673 m (5 m), −2788,9680 m (20 m), −2785,9299 m (240 m).
Sui 2001 punti campionati, 5 m − 20 m ha media +0,661 m, RMS 2,114 m e massimo
assoluto 9,631 m; nessuna quota mancante. La mappa NASA `ldec` dei ritorni,
campionata sui quattro pixel circostanti ciascun punto, ha rispettivamente
**1340, 573, 85, 3 e 0** punti con 0, 1, 2, 3 e 4 pixel con conteggio positivo.
Tutti i punti hanno quindi almeno un pixel senza ritorni nel supporto bilineare:
il prodotto riempie i vuoti per interpolazione. Il conteggio non è una stima
dell'errore verticale e i risultati non si possono generalizzare ad altri siti.

Riproduzione: installare separatamente `tifffile==2026.9.9` e
`imagecodecs==2026.1.14`, predisporre le tile 20/240 m in cache, poi eseguire
`python -m scripts.compare_lola_resolution`. Il test HTTP verifica stato 206,
dimensioni, `Content-Range` ed ETag, e fallisce su tile mancanti. I GeoTIFF 5 m
non sono stati scaricati integralmente: per l'insieme ordinato di indice e byte
compressi delle tile lette, gli SHA-256 sono rispettivamente
`33ec4fa2a874ff1ff30550e44a67d46958d5d752fb4fa4bb5a7bf248a5e703cb` (quota) e
`76e8d27fddcb31528cc011fa8da59d95332be0b675a3f8274887a2d9b41537d5` (conteggi).
Sono hash dei soli intervalli letti, **non** degli interi prodotti. Le tile PDS
20/240 m sono quelle della cache verificata dal lettore, non è stato rieseguito
il download integrale. L'ETag è debole e non è un checksum crittografico.
La libreria segnala che il tag GDAL NoData `nan` del file di conteggi uint8 non
è interpretabile; i valori usati sono i conteggi grezzi, non un'asserzione di
copertura completa. Fonte: Barker et al., 2021,
[doi:10.1016/j.pss.2020.105119](https://doi.org/10.1016/j.pss.2020.105119).

## Ricerca di osservazioni e misure hardware (15 novembre 2026)

**LROC:** il [catalogo immagini ufficiale](https://data.lroc.im-ldi.com/lroc/search)
ha restituito 332 CDR WAC_MONO per la ricerca bounding box 128–131° E,
89,8–89,5° S, dal 21 settembre al 23 ottobre 2010. Un candidato verificabile è
[M142511439MC](https://data.lroc.im-ldi.com/lroc/view_lroc/LRO-L-LROC-3-CDR-V1.0/M142511439MC):
inizio 2010-10-23 22:16:11 UTC, fine 22:22:45 UTC, pixel nominale circa 60 m,
centro −89,47°, 137,69° E. Il [CDR](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-3-CDR-V1.0/LROLRC_1005/DATA/SCI/2010296/WAC/M142511439MC.IMG)
è accessibile (46 573 568 byte). È **solo un candidato**, non una validazione:
il filtro spaziale non dimostra che il pixel di Shackleton sia incluso, né che
sia illuminato. La label incorporata è stata letta con una richiesta parziale:
indica CDR v1.9, filtro 643 nm e `DATA_QUALITY_ID = 4`; il significato dei bit
di qualità, in particolare la soglia per pixel sotto-saturati, va verificato
nel SIS prima di usare un pixel scuro come ombra. L'immagine non è stata
scaricata integralmente, proiettata o confrontata. Servono la label,
kernel/pointing, calibrazione, georeferenziazione e incertezza, tempo del pixel
(l'acquisizione dura diversi minuti), criterio radiometrico e altezza al suolo
comparabili; la media WAC già descritta sotto non è uno stato istantaneo.

**Energia:** il progetto NASA [PILS](https://www.nasa.gov/history/solar-power-investigation-to-launch-on-lunar-lander/)
prevedeva misure di corrente e tensione delle celle sulla superficie, ma
[Peregrine Mission One non è allunata](https://www.nasa.gov/news-release/nasa-science-astrobotic-peregrine-mission-one-concludes/).
Non abbiamo acquisito una serie di celle, carichi e stato di carica comparabile:
il progetto o i dati raccolti in volo non costituiscono una prova di energia sul
suolo lunare. L'[archivio Apollo PDS](https://pds-geosciences.wustl.edu/missions/apollo/index.htm)
è un'altra fonte da esplorare, ma qui non è stata identificata una traccia
fotovoltaico/batteria adatta.

**Radio:** il [DSN Telecommunications Link Design Handbook](https://deepspace.jpl.nasa.gov/dsndocs/810-005/)
documenta proprietà e interfacce di progetto, non è da solo una serie misurata
di un link di superficie. Non è stato reperito un caso completo con misure
sincrone, geometria, antenna, EIRP, G/T, perdite, rate e incertezze. Restano
validi i controlli aritmetici NASA documentati sotto, non una qualificazione
assoluta S5. Le soglie e i protocolli di promozione restano quelli della sezione
«Acceptance protocol» in fondo: S2/S4/S5 non sono promossi.

## Aggiornamento RAVEN: parita' browser e contratti (6 novembre 2026)

La voce `s5.browser_mirror` della matrice `/api/raven/validation` e' **verificata come parita'
d'implementazione**, non come validazione fisica. `scripts/dump_link_parity.py` rigenera 30 casi con
`s5_rf.unified_link_inputs`; la fixture `frontend/src/pages/simula/fixtures/link_parity.json` e' invariata.
`linkModel.test.ts` confronta FSPL, Fresnel, cresta, multipath, puntamento e margini per rate:
tolleranza 0,01 dB, lama esatta 1e-6 dB, geometria relativa 1e-9. Non valida terreno, multipath,
parametri illustrativi, margine radio assoluto o batteria.

La telemetria confronta il CSV con le serie S5 non decimate di `/api/raven/evaluate` (`rf_series`,
margini per rate; `steps.chosen_rate_bps`, rate scelto dal compensatore). I null restano null:
niente estrapolazione, nessun ponte fra campioni ignoti e nessuna previsione per rate non supportati.
k rende conservativa la scelta del rate; non altera il margine fisico a rate fisso.

`/api/lunar/*`, `/api/grazing/*` e `/api/sky/*` sono ritirate con 410, non reindirizzate a un altro
modello. Le prove storiche descritte sotto usano l'app-oracolo isolata in `scripts/raven_reference/`;
gli snapshot golden non sono stati rigenerati. Il sito usa `/api/raven/*`: onda didattica in `/wave`,
cielo nel servizio condiviso `/sky/*`, esperimenti RF dichiarati in `/experiments/*`. Il cambio
di namespace non rende la simulazione d'onda o l'esperimento a ostacolo singolo una previsione di missione.

Le richieste di default del client usano 7 giorni a 10 minuti (1008 passi, sotto il tetto 1500);
il wizard usa 7 giorni a 60 minuti (168 passi), come il default HTTP di `evaluate`.

## Evidenze storiche della fase C

Data: 2026-10-20. Test in `tests/backend/domain/`. Misure riproducibili con i kernel in `build/ephemeris` (`make ephemeris`).

## Validato

| Cosa | Come | Risultato |
|---|---|---|
| Geometria Sole/Terra dai siti | motore `backend.ephemeris` vs JPL Horizons (Fase B, `docs/ephemeris.md`) | 8.2e-7 deg el, 7 m (Sole); 1.2e-6 deg, 0.16 m (Terra) |
| Luna vista dai complessi DSN | confronto con `skyfield` `wgs84.latlon` indipendente, 3 stazioni, 1753 istanti in un anno | errore massimo 6.6e-5 deg |
| Coordinate DSN | copiate da DSN 810-005/301 Rev. P Tab. 5, test sulle conversioni gradi-minuti-secondi | uguali a 1e-6 deg |
| Elevazione della Terra (Apollo 11) | formula geometrica indipendente `tan(el) = (d cos(theta) - R)/(d sin(theta))` dal punto sub-Terra | max 0.006 deg di differenza su un anno; banda 57.96-73.17 deg (attesa 57.5-75 da libreria +/- 8 deg) |
| Elevazione della Terra (poli) | stessa formula | max 0.001 deg |
| Frazione di Terra visibile ai poli | modello `el ~ c cos(dlon) - beta(t)`, beta ampiezza 6.8 deg: Malapert atteso 0.70, misurato 0.676; Shackleton atteso ~0.5, misurato 0.461 (anno 2027) | nelle bande dei test (+/-0.06, +/-0.05) |
| Sole a Apollo 11 | 12 finestre da 29.53 d in un anno: giorni di Sole 14.79-14.88, media 14.83 | atteso 14.77 +0.04 d per il semidiametro 0.27 deg; tolleranza test 0.35 d (finestra media vs mese vero, +/-0.3 d) |
| Maschera Sole 5 deg | differenza di frazione di Sole | 0.0282 misurata, 10/360 = 0.0278 attesa |
| FSPL | identita' con fspl-c su griglia 40x30 e con il binario compilato: offset costante 0.00222 dB; esempio 210.994 dB (plugin) / 210.992 dB (esatta) | **NON entro 1e-3 dB**: la costante 92.45 e' arrotondata da 92.44778 |
| Margine e proprieta' | -6.02 dB al raddoppio della distanza, +3.01 dB al raddoppio della potenza, -3.01 dB al raddoppio del rate; calcolo indipendente in unita' lineari | entro 1e-4 / 0.01 dB (k = -228.6 vs 228.599) |
| Energia | analitica: Sole allo zenit, SOC lineare di notte, rendimento di andata e ritorno, conservazione dell'energia su serie casuali (rel. 1e-9) | passano |
| Ore utili | reimplementazione scalare indipendente (solo il motore e' condiviso), 14 d, 2 siti, passo 4 h, soglia di margine a meta' intervallo | flag di passo identici, margini 1e-9, SOC minimo 1e-9 |
| API | 422 generici senza eco, NaN, cache, tetti di punti, 503 senza kernel e a tetto di concorrenza, kernel reali | test `test_lunar_api.py` |
| Esempi dei documenti di conoscenza | uguali all'uscita del codice | `test_lunar_knowledge.py` |

## Ricerca di un riferimento per Sole e terreno

Il [prodotto NASA LOLA AVGVISIB_85S_060M_201608](https://pgda.gsfc.nasa.gov/products/69)
e' una mappa modellata della frazione di istanti illuminati su circa 18.6 anni, non una
misura istantanea. La [label PDS corrente](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/extras/illumination/img/avgvisib_85s_060m_201608.lbl)
descrive pixel a 60 m, int16 little-endian e fattore 0.00004. Il prodotto rappresenta la
visibilita' di una qualsiasi frazione del disco solare, mentre il nostro test confronta il
solo bordo superiore nell'azimut centrale. Entrambi usano dati LOLA, ma DEM e risoluzioni
diverse: non sono osservazioni indipendenti.

Il 2026-11-03 e' stato eseguito un **controllo esplorativo, non una validazione**.
Con la stessa convenzione di orientamento del DEM del progetto e il pixel piu' vicino alle
coordinate di catalogo, il valore NASA era zero per de Gerlache, Haworth e Shackleton.
Una richiesta a `/api/lunar/solar-terrain` per ciascuno, inizio `2027-04-07T00:00:00Z`,
10 giorni e passo 60 minuti, ha prodotto 240 campioni `upper_below_profile` per sito,
senza campioni mancanti. Questo non dimostra l'accordo: la media NASA non ha la stessa
finestra temporale e un pixel di 60 m non coincide necessariamente con il punto interpolato
nel DEM a 20 m; anche gli stati e il disco solare non sono equivalenti.

Le label presentano una discordanza: la label corrente indica `CENTER_LONGITUDE = 0`, mentre la
[label della release 2016](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/extras/illumination/release_2016/img/avgvisib_85s_060m_201608.lbl)
indica 180 gradi. Gli IMG delle due directory riportavano lo stesso ETag
`"b8bdbb825fd21:0"`, ma le label hanno ETag diversi. Assumendo invece una rotazione
di 180 gradi, il pixel di de Gerlache passa da 0 a 0.15168: la discordanza non e'
trascurabile e la sua origine storica non e' stata chiarita.

Il 2026-11-03 e' stato trovato un ulteriore riferimento per l'orientamento:
il [GeoTIFF NASA dello stesso prodotto](https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_85S_060M_201608.TIF),
descritto dalla [pagina NASA](https://pgda.gsfc.nasa.gov/products/69) come conversione dell'IMG.
Il GeoTIFF dichiara proiezione stereografica polare lunare sud, meridiano centrale 0 gradi,
raggio 1737400 m e pixel di 60 m. Il confronto integrale delle matrici int16 con l'IMG
PDS corrente ha dato **25 583 364 pixel uguali su 25 583 364**. I due file sono quindi
la stessa mappa, non due osservazioni indipendenti; la georeferenziazione NASA sostiene
la lettura a 0 gradi, ma non spiega perche' la label della release 2016 indichi 180 gradi.

Applicando la georeferenziazione del GeoTIFF alle coordinate di catalogo:

| Centro di feature | Riga, colonna zero-based | Valore grezzo | Frazione (scala 0,00004) |
|---|---:|---:|---:|
| de Gerlache (−88,48°, −88,34°) | 2506, 1761 | 0 | 0 |
| Haworth (−87,45°, −5,17°) | 1245, 2412 | 0 | 0 |
| Shackleton (−89,67°, 129,78°) | 2635, 2657 | 0 | 0 |

Il GeoTIFF scaricato ha SHA-256
`ccf67d4f39e0a970c111196da7d6551ffcf50d075470b93067fb3904c0b05806`;
l'IMG PDS corrente ha SHA-256
`82dadf321dee28f1947c1fed81858d4cf50fe8eb2aa405aae114e8ab21c1efe1`.
Con `rasterio` e `numpy`, il confronto si ripete leggendo la banda 1 del GeoTIFF e
confrontandola con l'IMG interpretato come `'<i2'` di forma `(5058, 5058)`, quindi
trasformando le coordinate dalla sfera lunare di raggio 1737400 m al CRS del GeoTIFF
e usando l'indice del pixel contenente il punto. Non sono stati usati livelli overview.
Questo risolve un'ambiguita' pratica nella lettura del prodotto NASA, **non** la
validazione Sole–DEM: la mappa resta una media pluriennale e i criteri non coincidono.

Un ulteriore riferimento NASA, [NExSyS: Validation of Rendered Natural and Artificial
Lighting Environments](https://ntrs.nasa.gov/citations/20220009839), descrive il
confronto di immagini Apollo con ambienti simulati e la necessita' di tecniche diverse
al polo sud. Il testo disponibile non fornisce una serie numerica georeferenziata di
illuminazione, con sito, istante e criterio equivalenti a questo endpoint. E' un
riferimento sul metodo di validazione, non un risultato confrontabile.

Per ripetere il controllo: la label corrente aveva SHA-256
`33decce957d5d4d9608557d8d969d1e1b94056a159b2563624ade4b528a0c917`;
l'IMG ha 5058 colonne e 5058 righe, 51 166 728 byte. Con la convenzione del DEM locale,
de Gerlache (-88.48, -88.34 gradi Est) corrispondeva a riga 2506, colonna 1761
zero-based, offset byte 25354218; con rotazione 180 gradi a riga 2551, colonna 3296.
Il DEM locale utilizzato era `ldem_85s_20m_float`, SHA-256
`bbfd0295c7ae0759dd7b2513e1ebd61fd5e3d304e35b3fa2ae9e6840054d9b7a`.
I tile necessari devono essere in cache: un risultato `missing_dem` non e' confrontabile.

La [visualizzazione NASA SVS 4930](https://svs.gsfc.nasa.gov/4930/) offre invece frame
ogni due ore per il 2023-2030. Il frame `sp_illum.1153.tif` della sequenza 2027 mostra
`07 Apr 2027 00:00 UT`, ma non sono stati trovati metadati sufficienti per assegnare con
certezza un pixel a un sito e distinguere quantitativamente luce e ombra. Anche questo
prodotto e' un rendering basato su LOLA, non una misura osservativa indipendente.
Servono dati georeferenziati, istanti e criteri comparabili o immagini osservate con
incertezze note; fino ad allora Sole-DEM e l'eventuale accoppiamento energetico rimangono
non validati.

## NON validato

- **Nessun margine assoluto di link budget pubblicato e' stato riprodotto.** NASA/TP-2019-220391 non riporta i guadagni d'antenna: il suo margine non e' ricalcolabile. La catena e' verificata con un calcolo indipendente in unita' lineari e con il controllo differenziale qui sotto.
- Terreno e orizzonte locale: nessun confronto numerico con Mazarico et al. 2011 (testo non accessibile). Confronti eseguiti il 2026-11-04 nella sezione "Validazione Sole-terreno" in fondo: l'endpoint a profilo di 10 km sbaglia dentro i grandi crateri.
- Energia e batteria: nessun confronto con un caso reale; tutti i parametri di pannello, batteria e carico sono illustrativi.
- Coordinate dei siti polari: centri di feature IAU, non centri delle regioni Artemis III.
- Guadagno di codifica CCSDS, perdite atmosferiche e di pioggia, dipendenza di G/T dall'elevazione: non modellati.
- Tracking DSN reale (programmazione, concorrenza con altre missioni): non modellato.
- UTC oltre il 2027-01 usa UT1 predetto (incertezza non quantificata).

## Confronto differenziale con uno studio radio NASA

Lo studio [NASA/TM-2019-220203](https://ntrs.nasa.gov/citations/20190033430),
sezione 2.3 e tabelle 4 e 10, fornisce uno scenario **simulato**, non una misura
radio: ritorno superficie lunare–Terra, distanza 390 000 km, banda X 8,475 GHz,
potenza mantenuta fissa, BPSK e LDPC 1/2. Per le antenne di ricezione da 18 e
34 m riporta rispettivamente G/T di 33,48 e 39,02 dB/K. Le coppie di velocita'
minime sono 6,28 e 22,72 Mbit/s; le massime 100,55 e 363,53 Mbit/s.

Assumendo che i due estremi corrispondenti mantengano uguali tutti gli altri
termini, l'aumento di G/T e' 5,54 dB, mentre `10 log10(rate_34/rate_18)` e'
circa 5,58 dB per entrambe le coppie. Il motore lunare restituisce dunque
una differenza di margine di circa −0,04 dB; il controllo e' riproducibile nel
test `test_nasa_lunar_return_rate_scaling_with_ground_gt`, con tolleranza 0,1 dB.
La differenza include eventuali arrotondamenti e ipotesi o perdite non identiche
fra le stazioni. La pubblicazione riassume gli estremi ma non specifica tutti i
termini necessari a ricostruire il margine assoluto per una singola riga: il
confronto **non valida il margine completo, il codice LDPC, il terreno o il
comportamento operativo della DSN**.

Un secondo controllo usa [NASA/TM-2020-220472](https://ntrs.nasa.gov/citations/20200000817),
tabella V: collegamento TDRS-12–stazione CADeT a 22,6795 GHz, non un collegamento lunare.
La tabella riporta FSPL 211,35 dB, perdita atmosferica 0,50 dB e guadagno della catena
polarizzatore–LNA 53,29 dB. Con EIRP/guadagno d'antenna ideali 64,00/58,10 dB, il
totale riportato e' −36,46 dBW; con i valori misurati 63,30/55,55 dB e' −39,71 dBW.
Il test `test_nasa_cadet_forward_power_budget` riproduce entrambi a 0,02 dB, usando
`cn0_dbhz` e una temperatura fittizia di 100 K che viene eliminata nel passaggio inverso
alla potenza. La FSPL e la perdita atmosferica sono inserite dalla tabella, non verificate
indipendentemente; l'amplificazione LNA e' aggiunta esternamente. Si verifica la coerenza
aritmetica del bilancio di potenza con valori pubblicati, **non** temperatura di rumore,
Eb/N0, margine, condizioni lunari o prestazioni del collegamento reale.

## Validazione radio (2026-11-04)

Etichette dei confronti: **R** = riproduzione esatta di una formula pubblicata (testo letto);
**II** = reimplementazione indipendente; **P** = solo plausibilità. Nessuno di questi confronti è una misura.

### Fonte ITU-R P.526-9 letta sul testo

Testo: Raccomandazione ITU-R P.526-9 (2005), copia locale `docs/sources/itu-p526-9.pdf` **fuori da git**: il
documento non contiene una nota di licenza che ne permetta la ridistribuzione, quindi si cita solo per
paragrafo, equazione e pagina ([pagina ITU](https://www.itu.int/rec/R-REC-P.526-9-200508-S/en)). È una
versione superata, non quella in vigore.

| Paragrafo / equazione (pagina) | Contenuto | Codice | Esito | Test |
|---|---|---|---|---|
| §2.1 eq. (2) (p. 2) | R_n = sqrt(n λ d1 d2 / (d1 + d2)), raggio dell'ellissoide di Fresnel | `fresnel_zone_radius_m` | R | `test_nu_forms_p526_eq22_eq23_and_zone_eq2` |
| §2.7 eq. (6), (7a), (7b) (p. 4) | C, S con cos/sin(π s²/2) | `scipy.special.fresnel` (stessa convenzione) | R, II (quadratura) | `test_exact_knife_edge_equals_p526_eq26_by_quadrature` |
| §4.1 eq. (22)-(23) (p. 14) | ν = h sqrt(2/λ (1/d1 + 1/d2)) = θ sqrt(2/(λ (1/d1 + 1/d2))); h < 0 sotto la congiungente, θ con il segno di h, θ < circa 0,2 rad | `nu_from_geometry`, `nu_from_angle` | R | idem |
| §4.1 eq. (26) (p. 16) | J esatto = −20 log10( sqrt((1−C−S)² + (C−S)²) / 2 ) | `knife_edge_loss_db` (forma JPL226 eq. 38, algebricamente uguale) | R, II: scarto < 1e-7 dB | idem |
| §4.1 eq. (27) (p. 16) | J ≈ 6,9 + 20 log10( sqrt((ν−0,1)² + 1) + ν − 0,1 ), **solo per ν > −0,78** | `itu_knife_edge_db` (0 dB sotto −0,78: scelta del codice, non della fonte) | R | `test_itu_approx_is_p526_eq27` |
| §4.2 eq. (28)-(32) (p. 17) | A = J(ν) + T(m,n); T = 7,2 m^½ − (2 − 12,5 n) m + 3,6 m^³⁄₂ − 0,8 m² per mn ≤ 4 (30a); T = −6 − 20 log10(mn) + 7,2 m^½ − (2 − 17 n) m + 3,6 m^³⁄₂ − 0,8 m² per mn > 4 (30b); m = R ((d1+d2)/(d1 d2)) / (πR/λ)^⅓ (31); n = h (πR/λ)^⅔ / R (32) | `p526_rounded_term_db` | R, II (formula scalare nel test) | `test_p526_term_matches_independent_formula`, `test_p526_term_limits` |

Cosa dice la fonte sui limiti di §4.2: h, d1, d2 vanno misurati al **vertice** delle tangenti proiettate; «per
un'ostruzione ν è positivo e l'eq. (27) è valida»; «quando R tende a zero anche T tende a zero»; il raggio è quello
della parabola adattata alla cima entro una quota dell'ordine del raggio della prima zona di Fresnel (eq. 33-34);
i dati valgono quando la lunghezza d'onda è piccola rispetto agli ostacoli (f > 30 MHz, §4). **Non** fissa
un intervallo di validità per m e n e non dice nulla sulla polarizzazione. La formula T che il codice usava
«da memoria» era già quella del testo: nessuna correzione numerica è stata necessaria, solo le etichette.

### Cresta arrotondata: tre fonti a confronto

Geometria della tabella: λ = 0,0357 m, d1 = 2000 m, Terra all'infinito (onda piana). Correzione in dB oltre il
bordo a lama esatto (`scripts/study_splitstep_convergence.py`, circa 2 minuti):

| R (m) | ν | ITU T(m,n) | split-step tabella (dy 0,1, dx 2 m) | split-step raffinato (dy 0,0125, dx 0,0625, assorbitore) | JPL226 |
|---|---|---|---|---|---|
| 20 | 0 / 1 / 3 / 8 | 0,21 / 0,66 / 1,56 / 3,81 | 0,03 / 0,19 / 0,55 / 1,26 | 0,15 / 0,38 / 0,96 / 2,57 | 0 |
| 100 | 0 / 1 / 3 / 8 | 0,35 / 1,12 / 2,66 / 6,52 | 0,13 / 0,46 / 1,33 / 3,82 | 0,28 / 0,69 / 1,74 / 4,70 | 0 |
| 400 | 0 / 1 / 3 / 8 | 0,55 / 1,78 / 4,22 / 10,34 | 0,33 / 0,91 / 2,43 / 6,78 | 0,48 / 1,14 / 2,88 / 7,90 | 0 |

Studio di convergenza dello split-step (R = 400 m salvo indicazione):
- **finestra e bordo assorbente**: N = 2^14 → 2^16 (finestra 1,6 → 6,5 km) e strato cos² del 15 % cambiano
  il residuo di < 0,002 dB con dy = 0,1 m. Con dy ≤ 0,025 m l'assorbitore (e passi di 25 m dopo la cresta)
  è **necessario**: senza, le frequenze spaziali alte si ripiegano nella finestra periodica e il residuo
  oscilla di ±0,3 dB;
- **passo trasversale dy**: con assorbitore, 0,025 → 0,0125 m cambia ≤ 0,013 dB; il bordo a lama (R = 0)
  scende da 0,07 a 0,009 dB di errore;
- **profondità di troncamento** 20 → 40 m: ≤ 0,05 dB per R ≥ 20 m (0,1 dB per R = 5 m);
- **passo di marcia dx sulla cresta**: **non convergente** nella tabella. A ν = 3, R = 400 m: con dy = 0,1 m, dx 2 / 1 /
  0,5 / 0,25 m danno 2,43 / 2,69 / 2,82 / 2,89 dB; con dy = 0,0125 m e assorbitore, dx 0,25 / 0,125 / 0,0625 /
  0,031 m danno 2,75 / 2,83 / 2,88 / 2,92 dB. Gli incrementi si riducono di circa 0,7 per dimezzamento:
  limite estrapolato circa 3,0 dB (estrapolazione geometrica, non dimostrata). Il mascheramento ripetuto converge lentamente a una condizione di Dirichlet
  (cilindro «morbido»);
- **onda piana o sferica**: la sorgente lato Terra è a 3,8e8 m, quindi l'onda piana è esatta per
  l'incidenza; il ricevitore a 2 km è a distanza finita nella simulazione (reciprocità scalare). Non ho
  simulato un'onda sferica: non serve per questa geometria.

Esito (P, non validazione): la tabella è **sottostimata** di circa 0,1-0,2 dB a ν = 0 e fino a 0,5 dB a
ν = 3 (R = 400 m) per il passo dx = 2 m. Anche raffinato e estrapolato, lo split-step resta circa il
**55-95 % di T**: rapporto ≈ 0,9 a ν = 0, ≈ 0,6-0,8 per 1 ≤ ν ≤ 8; scarto ITU − split-step raffinato fino a
1,3 dB a ν = 3 e 2,4 dB a ν = 8 (R = 400 m). Le due **non concordano entro 0,5 dB** nel regime d'uso
(0 ≤ ν ≤ 3, R ≤ 400 m); concordano sul segno, sulla crescita con R e con ν, e entro circa il 45 % relativo.

JPL 42-226 eq. (35)-(38), p. 15-16 (riletto sul PDF): L_A ≈ −20 log10|1 + m Ψ(m)| con «m = f^⅓ ψ» e Ψ
integrale di Airy; per d2 ≫ d1 «ψ tende a zero» e quindi L_A ≈ 0. Quel parametro **non contiene il raggio**
della cresta (e ha f in Hz senza scala): così come è scritto non può descrivere la dipendenza da R, che sia ITU
sia lo split-step mostrano. Non ho letto Crysdale (1958) né Rice (1954), quindi non posso dire quale fosse il
parametro originale; l'affermazione di JPL226 non viene usata.

**Politica (implementata).** `compensation.ridge_correction` e `linkModel.ts`:
1. correzione predefinita = max(T(m,n), 0) di ITU-R P.526-9 §4.2 con d1, d2 e λ reali (non più limitata alla
   griglia della tabella né a d1 = 2000 m); per ν < 0 T può diventare negativo (fuori dal caso di ostruzione
   descritto dalla fonte): si tronca a 0;
2. la tabella split-step resta, invariata, come **confronto**: serie `ridge_correction_splitstep_db`, variante
   «Cresta arrotondata (lama + tabella split-step, confronto)» nel pannello Avanzato di Simula;
3. incertezza = max(incertezza della tabella, |ITU − split-step|), mai sommata alla correzione; fuori dalla
   griglia della tabella (ν > 3) la banda è saturata e segnalata.
Perché ITU: è una fonte pubblicata e verificata sul testo; è più conservativa (margine più basso) dello
split-step; lo split-step è una simulazione scalare parassiale con ostacolo assorbente, non validata, il cui
errore numerico va nella direzione di avvicinarsi a ITU. Lo split-step resta utile per la forma della
transizione e per le oscillazioni a ν < −0,78 (dove ITU non dice nulla).

**Effetto sui risultati** (fixture di parità Simula, `scripts/dump_link_parity.py`): cresta R = 100 m, ν = 1,1:
correzione 0,50 → 1,20 dB (margine −0,70 dB); R = 400 m, ν = 8,0: 2,43 (saturata) → 10,29 dB (margine −7,86 dB);
R = 200 m, ν = 18,6: 1,79 (saturata) → 18,49 dB; per R = 0 la correzione passa da 0,02-0,07 dB (errore
numerico del bordo nello split-step) a 0. Parità TS/Python entro 0,01 dB mantenuta.

### Margine lunare assoluto: riferimento indipendente

Cercato (WebSearch/WebFetch, 2026-11-04): NASA/TM-2019-220203, NASA/TM-2020-220472 (CADeT), JPL 42-226 (nessun
bilancio di collegamento nel testo), HLS-CONOP-008 Rev A (nessuna tabella numerica). **Nessun bilancio
lunare superficie–Terra con tutti gli ingressi pubblicati è stato trovato**; i risultati del web erano
progetti di studenti, non usati.
- NASA/TM-2019-220203 Tab. 10 (banda X, 8,475 GHz, 390 000 km, LDPC 1/2, perdita di implementazione 3 dB,
  margine 3 dB, G/T di Tab. 4): **mancano** potenza trasmessa del lato lunare, Eb/N0 richiesto, perdite
  lato luna e efficienza d'antenna per questa sezione. Riprodotti solo rapporti: G/T 18 → 34 m (scarto
  −0,04 dB, test esistente) e antenna lunare 6 → 23,7 pollici (residuo 0,11 dB: la tabella usa un rapporto
  16,0 = 12,04 dB, i pollici danno 11,93 dB; probabile arrotondamento 0,15/0,60 m;
  `test_nasa_lunar_return_rate_scaling_with_lunar_dish`). Con η = 0,55 il motore richiede che
  P_tx[dBW] − perdite non elencate − Eb/N0 richiesto valga 14,6-14,9 dB in tutte le sei righe (P: coerente,
  non una verifica: con 100 W resterebbero circa 5 dB per perdite ed Eb/N0).
- Residuo assoluto in dB: **non determinabile** con le fonti raggiunte.

### Aperti

- Validazione sperimentale della cresta arrotondata: nessuna misura (né lunare né terrestre) confrontata.
- Soluzione esatta del cilindro (serie di Mie o teoria di Fock, polarizzazioni morbida/dura) non calcolata:
  sarebbe il riferimento indipendente fra ITU e split-step.
- Rigenerare la tabella con dx ≤ 0,125 m, dy ≤ 0,025 m e assorbitore (non fatto: la tabella è versionata e
  resta come confronto; la sua sottostima allarga la banda di incertezza).
- Vertice ITU contro cima fisica sui profili LOLA: verificato in un solo caso analitico (0,007 dB).
- P.526 in vigore (versione -15 o successiva) non letta.

## Validazione Sole-terreno (2026-11-04)

Strumento: `scripts/solar_horizon_arbiter.py` (arbitro), test analitici in
`tests/backend/domain/grazing/test_solar_horizon_arbiter.py`. L'arbitro condivide con l'API
solo il lettore di tile `LolaDem` e il motore di efemeridi (gia' confrontato con JPL Horizons);
proiezione, interpolazione, raggi (rotazione di vettori 3D), angoli (differenze cartesiane
sulla sfera di 1737,4 km) e criteri del disco sono riscritti. Maschera completa: 3600 azimut
(720 per i confronti con la letteratura), LDEM_85S_20M a passo 10 m fino a 10 km (5 km per la
letteratura), poi LDEM_75S_240M a passo 120 m fino a **200 km** (limite dichiarato: terreno
oltre 200 km non modellato; a quella distanza la curvatura abbassa di ~1,6 gradi un rilievo di
6 km). Disco solare: semidiametro da distanza reale, integrato a 64 strisce verticali contro la
maschera. Nessuna rifrazione, nessun oscuramento al bordo. Il LDEM_75S_240M e' scaricato a tile
via `LolaDem` (ETag e dimensione verificati, label SHA-256
`8ad7ed746f0944762d249281db50667d4e1e9a0059eb836b4003909c1a5b336a`; hash dell'intero file non
calcolato). Nei 5 siti le quote 20 m e 240 m coincidono entro 12 m.

Per ripetere: `.venv/bin/python -m scripts.solar_horizon_arbiter --mode api` (API) e
`--mode references --grid-radius-km 15` (letteratura e LROC). Scarica i tile mancanti.

### Algoritmo dell'arbitro (verificato con soluzioni analitiche)

Sfera piatta (abbassamento d/2R esatto a 1e-9 gradi; dip `acos(R/(R+h))` a 1e-6 gradi con
osservatore a 100 m), bordo di cratere circolare (angolo analitico a 1e-7 gradi), cresta a lama
rettilinea a 2 km con azimut 45-120 gradi (trigonometria sferica, entro 1e-3 gradi), frazione del
disco contro il segmento circolare esatto (2e-5), maschera a gradino (meta' disco), frazioni
temporali con Sole sinusoidale contro le formule `1/2 - asin(H/A)/pi` per bordo superiore,
centro, bordo inferiore, qualsiasi parte e disco intero (1e-4), dati ignoti contati e mai
trattati come cielo libero.

### Confronto con `/api/lunar/solar-terrain`

Stessi siti e istanti: 2027-01-01T00:00Z, 365 giorni, passo 120 min, 4380 passi per sito, tutti
con stato noto (nessun `missing_dem`). Osservatore al suolo (0 m) salvo dove indicato.

| Sito | API bordo sup. | Stessa geometria API (esatta) | Arbitro 10 km, maschera 0,1 gradi | Arbitro 200 km: sup. / centro / inf. / disco medio | Differenza dall'API |
|---|---:|---|---:|---|---:|
| Malapert | 31,85 % | max 7,0e-10 gradi, 0 passi diversi | 31,76 % (4 passi) | 31,76 / 31,00 / 30,30 / 31,02 % | 480 min |
| Haworth | 22,67 % | max 1,5e-9 gradi, 0 passi | 22,65 % (1 passo) | 0 / 0 / 0 / 0 % | 119 160 min (82,8 d) |
| Nobile rim | 35,83 % | max 6,9e-10 gradi, 0 passi | 35,69 % (5 passi) | 27,45 / 26,53 / 25,56 / 26,52 % | 36 240 min (25,2 d) |
| de Gerlache | 35,11 % | max 2,2e-9 gradi, 0 passi | 35,11 % (0) | 0 / 0 / 0 / 0 % | 184 560 min (128,2 d) |
| Shackleton | 0 % | max 3,5e-10 gradi, 0 passi | 0 % | 0 / 0 / 0 / 0 % | 0 |

- **Riproduzione esatta** (colonna 3): con lo stesso azimut, passo 20 m e 10 km, l'arbitro
  riproduce l'orizzonte dell'API entro 2,2e-9 gradi e tutti i 21 900 stati. L'implementazione
  dell'API e' quindi corretta *per cio' che dichiara*.
- **Reimplementazione indipendente** (colonna 4): maschera a 0,1 gradi interpolata e passo 10 m;
  differenze di orizzonte fino a 0,93 gradi (media da +0,001 a +0,14 gradi) per l'interpolazione in
  azimut e il campionamento piu' fitto del terreno vicino; 0-5 passi diversi per sito.
- **Discrepanze di modello** (colonne 5-6): tutte nella stessa direzione (API illuminata, arbitro
  in ombra) e dovute al **terreno oltre 10 km**. Haworth e de Gerlache sono centri di grandi
  crateri: il profilo non raggiunge il bordo, mentre la maschera completa li tiene in ombra
  tutto l'anno anche a 10 m di altezza. A Nobile la maschera e' dominata dal terreno lontano nel
  64 % degli azimut. A Malapert pesa solo per 4 passi.
- **Criterio del bordo**: tra bordo superiore e centro la differenza e' 0,8-0,9 punti
  percentuali (65-80 h/anno); tra bordo superiore e disco intero 1,5-1,9 punti a Malapert/Nobile.
- **Altezza dell'osservatore**: Malapert, disco medio 31,0 % a 0 m, 33,0 % a 2 m, 45,9 % a 10 m;
  Nobile 26,5 / 26,5 / 26,6 %; gli altri restano a 0.
- Coordinate: centri di feature IAU del catalogo, **non** i punti piu' illuminati; Haworth,
  de Gerlache e Shackleton sono fondi di cratere. Le frazioni non descrivono le zone di atterraggio.

### Confronto con dati osservativi indipendenti (LROC WAC)

Riferimento: prodotto PDS `WAC_POLE_ILL_TWI_SOUTH_100M` v1.3 (LROC, Speyerer e Robinson 2013,
Icarus 222, 122-136), SHA-256 `dfecc026012fe24f67ca70ed21a09a1723ca0750bf3ec120f1a4ed2c4604717b`,
float32 1214x1214, 100 m/pixel, 88-90 gradi S. E' la frazione di immagini WAC in cui il pixel
risultava illuminato (soglia globale "conservativa", valore non pubblicato), 15/02/2010-05/02/2011,
pesata nel tempo. E' **ottico e indipendente da LOLA** (ma proiettato su un DEM LOLA di 30 m).

Arbitro: stesso periodo, passo 1 h, osservatore a 0 m, 29 punti su griglia di 5 km entro 15 km
dal polo, valore LROC come media 3x3 pixel.

| Criterio dell'arbitro | r | Scarto medio (arbitro - LROC) | RMS | Entro 10 punti |
|---|---:|---:|---:|---:|
| Qualsiasi parte del disco | 0,954 | -0,0 punti | 4,2 punti | 28/29 |
| Frazione media del disco | 0,952 | -1,6 punti | 4,6 punti | 28/29 |
| Disco intero | 0,946 | -3,2 punti | 5,8 punti | 28/29 |
| Qualsiasi parte, LROC ruotato di 180 gradi | 0,237 | -0,0 punti | 17,0 punti | 7/29 |

Sui 21 punti non nulli: r = 0,919, RMS 4,9 punti; esclusi il polo RMS 2,6 punti, massimo 7,5.
L'unico scarto grande e' il **polo** (0, 0): LROC 46,0 % (pixel 49,9 %), arbitro 26,7 % per
qualsiasi parte del disco. Causa non verificata: pixel di 100 m all'origine della proiezione,
soglia ignota, luce diffusa, rilievo sotto la risoluzione del DEM a 20 m. La rotazione di 180 gradi
peggiora tutto: anche la convenzione di orientamento del DEM (`dem.lock.json`) e' confermata da dati
indipendenti.

Questo e' un **confronto indipendente, ma non esattamente like-for-like**: il periodo, le coordinate
e l'osservatore al suolo coincidono; il criterio (soglia radiometrica su un pixel di 100 m invece
della geometria al centro del pixel) no. Non tocca i siti a Malapert, Haworth e Nobile, che sono
fuori dalla copertura 88-90 gradi S. Per de Gerlache e Shackleton (centri) LROC e arbitro danno 0;
l'API da' 35,11 % per de Gerlache nel 2027 (anno diverso, ma la differenza non e' spiegabile con
la variazione interannuale).

### Letteratura

| Fonte | Numeri letti | Confronto | Tipo |
|---|---|---|---|
| Barker et al., *Planetary and Space Science*, doi:10.1016/j.pss.2020.105119 (manoscritto NTRS 20205009660), Tabella 2 | Sito 1 (cresta Shackleton-de Gerlache), 7 RoI (X/Y km), 01/01/2024-01/01/2026, passo 1 h, dz 1 m e 5 m; 1° percentile su 100 cloni della media di illuminazione (frazione visibile del disco, con oscuramento al bordo, disco tagliato orizzontalmente all'orizzonte nell'azimut del centro). Righe A (media RoI) e C (pixel migliore) | Arbitro ai centroidi, stesso periodo e altezze: dz 1 m 74,3-85,7 % (A: 67,4-71,2; C: 77,3-86,8); dz 5 m 83,4-91,4 % (A: 82,8-89,3). Ogni valore dell'arbitro e' sopra il 1° percentile A | **Plausibilita'**: 1° percentile e non valore nominale; DEM di 5 m contro 20 m; RoI contro centroide; nessun oscuramento al bordo nell'arbitro |
| Gläser et al. 2014, Icarus 243, 78-90 | Solo da un riassunto di ricerca web del record DLR (non verificato sul testo): 92,27 % (2 m) e 95,65 % (10 m), 19 anni, cresta di collegamento | Non eseguito: coordinate non lette (articolo non accessibile) | Nessuno |
| Mazarico et al. 2011, Icarus 211, 1066-1081 | Solo dal riassunto della pagina NTRS (non verificato sul testo): ~240 giorni/anno presso il bordo di Shackleton | Non eseguito: Tabella 3 non accessibile | Nessuno |
| Bussey et al. 2005/2010, NASA Artemis III | Non consultati | Non eseguito | Nessuno |

La convenzione X/Y di Barker e' **dedotta**, non dichiarata: solo (-X, -Y) nella convenzione di
`dem.lock.json` cade su una cresta (+1,95 km, lon -137,15 gradi); le altre 3 scelte di segno
cadono tra -0,6 e -1,1 km. A dz 1 m, i valori nominali dell'arbitro tra A e C sono compatibili.

### Esito

- **Verificato like-for-like**: il codice dell'API (riproduzione esatta a 2,2e-9 gradi) e
  l'algoritmo dell'arbitro (casi analitici).
- **Verificato con dati indipendenti, criterio non identico**: l'illuminazione dell'arbitro contro
  LROC WAC entro 4-6 punti RMS (r 0,95) vicino al polo e l'orientamento del DEM.
- **Solo plausibilita'**: Barker et al. (1° percentile, DEM diverso).
- **Non validato, e risultato errato**: il profilo di 10 km dell'endpoint come stima di illuminazione.
  Nei centri di Haworth e de Gerlache segna il bordo superiore sopra il profilo nel 22,7 % e nel
  35,1 % dei passi, contro lo 0 % della maschera completa (de Gerlache 0 % anche in LROC). Il testo
  di API e Planner ora lo dichiara; l'endpoint espone anche `centre_above_profile` e
  `lower_above_profile` (campi aggiuntivi, compatibili) e `assumptions.observer`.
  **Corretto lo stesso giorno**: l'endpoint usa ora la maschera a 200 km (sezione seguente) e
  concorda con l'arbitro entro 1 passo su 4380 nei cinque siti.

### Endpoint con maschera d'orizzonte (2026-11-04, dopo la correzione)

`/api/lunar/solar-terrain` ora usa `backend/domain/grazing/horizon.py`: maschera per sito in
cache (memoria e `build/lola/horizon/`), 1440 azimut, LDEM_85S_20M a passo 10 m fino a 10 km e
LDEM_75S_240M a passo 120 m fino a 200 km (prodotto ora in `dem.lock.json`, con SHA-256
dell'intero file calcolato in streaming il 2026-11-04:
`82f40337cf42b3d478b255f22e6fce06d7273ff3bd4ac879b0f1ea4712dc280c`), curvatura, altezza
dell'osservatore esplicita (`observer_height_m`, default 2 m, tag I), semidiametro solare dalla
distanza reale, criteri bordo superiore / centro / bordo inferiore e frazione visibile del disco
(48 strisce). Formulazione diversa dall'arbitro (punti del raggio con la formula del punto di
destinazione, angolo per trigonometria piana nel piano del cerchio massimo, orientamento dal lock);
in comune solo `LolaDem` ed efemeridi. Costo misurato: 0,2-0,5 s per maschera alla prima
richiesta, poi da cache.

Test (`tests/backend/domain/grazing/test_horizon.py`): soluzioni analitiche (sfera, bordo di
cratere, frazione del disco contro il segmento circolare, frazioni temporali), arbitro e
produzione sullo stesso rilievo sintetico entro 1e-8 gradi, Malapert reale entro 1e-6 gradi a
parita' di griglia ed entro 0,02 gradi (media 1e-3) contro l'arbitro a 3600 azimut, dati mancanti
come stato ignoto. Con passo 20 m / 240 m (prima prova) la maschera di Malapert risultava fino a
1,2 gradi piu' bassa (media 0,14) dell'arbitro a 10 m / 120 m: il massimo cadeva tra i campioni;
da qui il passo a meta' pixel.

Rifatto il confronto del 2027 (stessi istanti della tabella sopra: 2027-01-01T00:00Z, 365 giorni,
passo 120 min, 4380 passi per sito, tutti con stato noto), endpoint contro arbitro a maschera
completa (3600 azimut), percentuali dei passi:

| Sito | h | Endpoint sup. / centro / inf. / disco medio | Arbitro sup. / centro / inf. / disco medio | Passi diversi (sup.) | Max scarto disco |
|---|---:|---|---|---:|---:|
| Malapert | 0 m | 31,76 / 31,00 / 30,30 / 31,02 | 31,76 / 31,00 / 30,30 / 31,02 | 0 | 0,021 |
| Malapert | 2 m | 33,68 / 32,97 / 32,35 / 32,98 | 33,65 / 32,97 / 32,35 / 32,98 | 1 | 0,018 |
| Malapert | 10 m | 48,33 / 46,16 / 43,36 / 45,94 | 48,33 / 46,16 / 43,36 / 45,94 | 0 | 0,007 |
| Haworth | 0 / 2 / 10 m | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 | 0 |
| Nobile rim | 0 m | 35,64 / 34,50 / 33,38 / 34,51 | 35,62 / 34,50 / 33,38 / 34,51 | 1 | 0,005 |
| Nobile rim | 2 m | 35,64 / 34,50 / 33,42 / 34,52 | 35,64 / 34,50 / 33,40 / 34,52 | 0 | 0,005 |
| Nobile rim | 10 m | 35,66 / 34,57 / 33,49 / 34,57 | 35,66 / 34,57 / 33,49 / 34,57 | 0 | 0,005 |
| de Gerlache | 0 / 2 / 10 m | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 | 0 |
| Shackleton | 0 / 2 / 10 m | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 | 0 |

Orizzonte all'azimut del Sole: scarto massimo 0,007-0,053 gradi. Residuo: risoluzione in azimut
(1440 contro 3600, interpolazione lineare) e semidiametro (distanza Sole-centro della Luna
nell'endpoint, distanza topocentrica nell'arbitro); 1 passo su 4380 al massimo, nessun sito con
discrepanza di modello. Haworth e de Gerlache sono ora in ombra tutto l'anno, come l'arbitro.

**Nobile, numero precedente non riprodotto.** La tabella del confronto precedente riportava per
Nobile, arbitro a 200 km, 27,45 / 26,53 / 25,56 / 26,52 % (0 m) e 26,5 / 26,5 / 26,6 % di disco
medio a 0 / 2 / 10 m. Rieseguito oggi lo stesso arbitro (`--mode api --sites nobile-rim
--heights 0`, stessi tile in cache, nessun dato ignoto, terreno lontano dominante nel 64,3 % degli
azimut come allora) da' 35,62 / 34,50 / 33,38 / 34,51 %. Gli altri quattro siti si riproducono
esattamente. Causa non trovata: il codice dell'arbitro e' invariato salvo formattazione; i tile in cache
superano il controllo SHA-256 per tile al caricamento, ma gli hash al momento della prima
esecuzione non erano registrati, quindi non si puo' escludere che allora fossero letti dati
diversi. Il valore di riferimento valido e' quello rieseguito; quello precedente va
considerato non verificato.

Aperti: punti LROC con piu' campioni e lontani dal polo; testo integrale di Mazarico 2011 e Gläser 2014
per un confronto alle loro coordinate; sensibilita' all'incertezza del DEM (Barker: errore
verticale RMS mediano ~0,3-0,5 m); oscuramento al bordo; anni diversi dal 2027 (ciclo di 18,6 anni).

## Audit mirato del modello corrente (2026-11-08)

Il modello corrente e' `raven-core-1.1`. L'hash del registro identifica i parametri, non il codice:
per riaprire un risultato come corrente occorre anche la stessa versione del modello. Gli archivi
storici mantengono l'identita' originale e non vengono ricalcolati o promossi a risultati correnti.

**Correzione geometrica multipath.** Il limite numerico di 0,05 gradi, illustrativo e usato nel
termine di campo coerente, veniva applicato anche alla distanza del punto speculare. A 0,01 gradi
e con antenna a 2 m il punto reale e' a 11 459,155786 m, non a 2291,830599 m: un crinale a 5000 m
esclude la riflessione nel modello dichiarato, mentre prima veniva applicata una correzione
di circa -4,39 dB. Ora l'applicabilita' usa l'angolo geometrico originale. Il limite nel campo
rimane esplicito e non validato fisicamente. Regressione Python e TypeScript; due vettori aggiunti
alla parita' S5 (32 in totale), uno escluso e uno applicabile sotto il limite. Gli oracoli
numerici storici non sono stati rigenerati.

**Energia S4.** Aggiunte sei verifiche del percorso RAVEN corrente con soluzioni chiuse,
senza chiamare i suoi helper di generazione o integrazione come oracolo: pannello tracking a
1/2 AU, disco visibile 0,5/1, carica con efficienza 0,9, scarica in buio con efficienza 0,8,
esaurimento con SOC non negativo e domanda non servita di 0,4 Wh. Tolleranza relativa 1e-9.
Sono verifiche dell'aritmetica discreta sotto parametri dichiarati, non osservazioni indipendenti
di hardware lunare. S4 resta `not_validated`.

**Ignoti nell'interfaccia.** Quando non esiste un prefisso energetico noto, energia raccolta,
domanda non servita e minimo SOC possono essere `null`: il contratto frontend e il lettore dei
calcoli ora li conservano, invece di rifiutare una risposta valida o inventare un totale zero.
I riepiloghi di energia/SOC con intervalli ignoti dichiarano il loro ambito (solo prefisso noto).
La conversione alla vecchia vista energetica non produce piu' una sensibilita' «available» con
stati della batteria mancanti. Registri incompatibili e versioni obsolete restano espliciti.

**Edizione ITU.** Il [catalogo ufficiale ITU](https://www.itu.int/rec/R-REC-P.526/en), consultato
l'8 novembre 2026, indica P.526-16 (11/2025) in vigore e P.526-9 superata. In questo audit e'
stata verificata l'identita' dell'edizione corrente, non il suo testo: la conformita' delle
formule implementate resta riferita alla P.526-9 gia' letta, non alla -16.

| Ambito | Evidenza disponibile | Evidenza ancora necessaria |
|---|---|---|
| RF assoluto | FSPL e somma del budget verificati; confronti NASA differenziali di plausibilita' | Caso indipendente completo e riproducibile: geometria, EIRP, G/T, perdite, codifica, bitrate e margine |
| Multipath e crinale arrotondato | Coefficienti TE/TM e rugosita' confrontati con JPL; geometria speculare corretta; formula ITU e confronto split-step | Fonte primaria per la convenzione circolare co-polare; misura o soluzione elettromagnetica indipendente; proprieta' reali del terreno |
| Energia | Soluzioni analitiche sul motore corrente e bilancio dei helper condivisi | Tracce di generazione/carico/SOC con parametri misurati e condizioni termiche/della polvere dichiarate |
| Sole/terreno | Effemeridi indipendenti e controlli geometrici; LROC WAC solo plausibilita' con criterio diverso | Confronto osservativo like-for-like, incertezza DEM, oscuramento al bordo e spiegazione dello scarto al polo |

Riproduzione: `.venv/bin/python -m pytest tests/backend/domain/raven/test_s4_s6_s7.py
tests/backend/domain/grazing/test_multipath.py` e `cd frontend && npm test --
src/pages/simula/linkModel.test.ts src/pages/planner/journey.test.ts`.
La matrice `/api/raven/model` cita queste prove senza elevare le ipotesi fisiche a «verified».

## Primary-reference closure audit (2026-11-08)

This section supersedes the *missing reference* statements in the preceding audit, not its
physical-validation limits. No production calculation, parameter default or model version changed.
Six new regression cases check two published design budgets and the lossless circular basis.

### Absolute lunar design budget: Surveyor

Primary source: [NASA CR-69102, NTRS 19660005264](https://ntrs.nasa.gov/citations/19660005264),
Surveyor Lunar Roving Vehicle Phase I, Volume III Book 2, Table 10-3 (PDF p.215,
printed III/2 10-8). The explanatory formulas are on PDF pp.276-277, printed 10-69/10-70.
This is a **1964 preliminary design**, not a flight measurement or a validation of current DSN defaults.
Downloaded PDF SHA256: `9d05827939ddc96c9ab3dc7eed069ac979d5c87231289d35771b58a125a3d4a1`.

The nominal budget supplies 2295 MHz, 3.0 dBW transmitter power, 2.6 dB transmitter circuit loss,
211.4 dB space loss, 61.0 dBi receive gain, 0.3 dB receiver loss, 215 K system noise temperature
and 4.1 dB subcarrier modulation loss. The telemetry transmitter gain is -3.0 dBi; television
gain is 17.0 dBi. System noise is nominal: the report gives 215 +/- 15 K, not an observed time series.
The required 8.3 dB Eb/N0 **already includes** 1.5 dB detector loss over the ideal 6.8 dB threshold.
Do not subtract detector loss again.

| Design channel | Published rate (bit/s) | Published received power (dBW) | Published margin (dB) | Recomputed nominal margin (dB) |
|---|---:|---:|---:|---:|
| Telemetry | 960 | -153.3 | 9.8 | 9.752903070 |
| Television | 122880 | -133.3 | 8.7 | 8.680803374 |

Noise density recomputes to -205.275615401 dBW/Hz versus the rounded -205.3; subcarrier C/N0
is 47.875615401/67.875615401 dBHz. Maximum margin residual is **0.047096930 dB**, below the
0.1 dB test tolerance for the published one-decimal design inputs. This closes the absence of
a complete published lunar **absolute budget arithmetic** reference.

The report calls the range "207,400 miles" without defining the unit. At 2295 MHz, nautical
miles give 384104.8 km and 211.3524 dB; statute miles give 333777.9456 km and 210.1326 dB.
The former is consistent with the reported loss, but this is an inference, not an independently
specified distance. Both tests therefore **supply the published 211.4 dB loss**. The S5 test
constructs an equivalent free-space range solely to inject this input; it is not an independent
check of FSPL or lunar range.

`test_surveyor_published_absolute_design_budget` checks received power, noise and both margins.
`test_current_s5_against_surveyor_absolute_design_budget` runs **current RAVEN S5**, with an explicit
synthetic unobstructed limit (`nu = -infinity`), zero pointing error and disabled rounded-ridge
and multipath contributions. This is a test boundary condition, never a fallback for missing DEM.
Because 960 and 122880 bit/s are not in the production catalogue, its 10000 bit/s margin is rebased
by `10 log10(10000 / source_rate)`; the catalogue is unchanged.
Unlisted environmental terms and blank pointing entries are not measurements of zero loss.
Only the reported nominal received-power/budget sum is reconstructed.

Matrix row: `s5.surveyor_absolute_arithmetic = verified`; flight/terrain/modern-station performance
remains unvalidated.

### Primary lossless circular-polarization basis

Primary source: Simpson & Tyler, [NASA CR-119032, NTRS 19710019588](https://ntrs.nasa.gov/citations/19710019588),
Explorer 35 bistatic-radar studies, Part 2, printed pp.13-14 (PDF pp.20-21).
Downloaded PDF SHA256: `ea2f269da97fa285ca8a27442d02b62867e4c08dd4fb07aa9c84052793c712e8`.
The source uses `exp(-j omega t)`, defines circular vectors from its vertical/horizontal basis,
and assumes **real** reflection coefficients. For pure circular input its printed component
power ratio reduces to `(rho_v + rho_h)^2 / (rho_v - rho_h)^2`.

`test_lossless_circular_power_against_explorer35_basis` constructs incidence and refraction
angles independently using Snell's law, then checks the incident-normalized power of RAVEN's
half-sum against that ratio and total reflected power. Two real permittivities (3.7 and 5.0,
test inputs, **not measured soil**) and six grazing angles cover grazing, Brewster vicinity
and normal incidence. Relative tolerance is 1e-12; absolute tolerance 1e-15 handles cancellation
near normal incidence. The half-sum amplitude is derived from the source's power/basis algebra,
not a quoted measured amplitude.

This closes the missing **lossless circular power algebra** reference. It does not establish
complex lossy phase, actual TX/RX antenna coupling, regolith parameters or a coherent multipath
observation. A hardware handedness claim needs the propagation axes, reflected local basis,
receiver sensitivity and direct-path basis specified together. The source does not supply that
mapping; no claim that a smooth dielectric always reverses helicity is made.
Matrix row `s5.circular_basis = verified`; aggregate `s5.multipath` stays `not_validated`.

### Current ITU edition actually compared

Primary source: [ITU-R P.526-16 (11/2025)](https://www.itu.int/rec/R-REC-P.526-16-202511-I/en),
official English PDF, SHA256 `7647c3cb3873dc0389a7007f487728359551ed82468a5677b7cd09430875f23d`.
Section 4.1 equations (30)-(31) retain the exact/approximate J(nu) expressions of P.526-9
(26)-(27). Section 4.2 equations (32)-(36) retain the rounded-obstacle expressions of
P.526-9 (28)-(32), including both `mn <= 4` / `mn > 4` branches and the self-consistent
units of m and n. Existing independent-formula and zero-radius-limit tests apply unchanged:
six T(m,n) cases, absolute tolerance 1e-9 dB. No numeric migration is justified.

The current text still requires height/distances at the **projected-ray vertex**, a curvature
fit near the apex over a first-Fresnel-zone-scale region, and an obstructing positive nu for
the stated approximate J expression. The terrain peak is not generally the projected vertex.
The implementation's tip approximation, nonnegative correction policy and unconverged split-step
band therefore do **not** become physically validated by this edition comparison.
`s5.rounded_ridge_formula = verified` is separate from `s5.rounded_ridge = not_validated`.
This is a comparison of these expressions, not certification against every method in P.526-16.

### Physical qualification: genuinely blocked, not relabelled as complete

The reproducible reference work above is complete. **The requested independent physical
qualification is not complete.** Numerical tests cannot manufacture observations or an equivalent
independent electromagnetic solution. Remaining acceptance gates are:

| Scope | Required independent evidence | Acceptance protocol before promotion |
|---|---|---|
| Absolute operational RF | Measured or independently qualified EIRP, receiver G/T, modulation/coding, losses, geometry and received C/N0 for the same configuration | Fix units/conventions and uncertainty first; predict before examining measurements; compare absolute C/N0/Eb/N0 and window classifications, not only ratios |
| Multipath / rounded lunar ridge | Measured material/roughness and geometry; complex field observation, or independently converged full-wave solution with matching boundary conditions | Map polarization/phase bases; use actual projected vertex; demonstrate numerical/domain convergence and residuals with uncertainty; no fit of soil parameters to the comparison being called validation |
| Real S4 hardware | Independent usable battery Wh, efficiencies and synchronized solar-generation/load/SOC or independent battery-state measurements | Hold parameters fixed on a separate calibration set; compare withheld charge, depletion and unserved-energy cases; declare thermal/dust scope and sampling error |
| Sun / terrain | Georeferenced observations with the same location, height, UTC, horizon and finite-disk criterion, plus DEM uncertainty | Match criteria before comparing; explain the existing polar discrepancy, quantify boundary/DEM effects; never tune a global offset to hide it |

The [NASA Ames battery-aging metadata](https://data.nasa.gov/dataset/li-ion-battery-aging-datasets)
describes measured voltage/current/temperature and discharge capacity in Ah; it does not supply
independently measured instantaneous SOC and equivalent lunar solar illumination in its documented
fields. Its linked legacy Dashlink resource was not retrievable in this audit. Even obtaining those
curves would not justify deriving usable Wh from the same curve and then calling its integration
independent SOC validation. This lead is **not equivalent evidence**, not proof that no dataset exists.
Previously investigated LROC WAC / AVGVISIB / SVS references retain the limitations recorded above.

No new source closes those four physical gates. No unsupported value is filled with zero, no
tolerance is chosen to pass a physical mismatch, and no overall mission-qualification claim is made.
Further work requires those inputs or an explicitly scoped, funded measurement/full-wave programme.

Reproduction: `.venv/bin/python -m pytest tests/backend/domain/test_lunar_link.py
tests/backend/domain/raven/test_s5.py tests/backend/domain/grazing/test_multipath.py
tests/backend/domain/grazing/test_compensation.py tests/backend/domain/grazing/test_diffraction.py
tests/backend/domain/raven/test_s4_s6_s7.py tests/backend/domain/raven/test_validation.py -q`
(105 passed). Source PDFs remain research artifacts outside the repository; hashes/links and the
independently written factual checks above are the committed evidence.

## Incremental S2-S5 validation and S3 correction (2026-11-08)

Model for this block: **raven-core-1.2**. Earlier evidence remains historical evidence; archived 1.1
reports must not be reopened as 1.2. Registry defaults and RF formulas are unchanged.

Starting with the shortest independent checks, the matrix now distinguishes S4's verified
arithmetic from its unvalidated hardware performance, and TE/TM/reflection algebra from the
unvalidated coherent lunar multipath model. No physical stage is promoted by this separation.

- **S4:** existing closed charge/discharge/depletion cases are exposed as
  `s4.energy_arithmetic = verified`; `s4.energy` still means unvalidated physical performance.
  A new independent circular-segment/energy balance checks that a very thin illuminated crescent
  produces nonzero generation, harvested Wh and battery charge. Relative tolerance 1e-9.
- **S5:** complex TE/TM coefficients retain the independent JPL 42-226 equations (48)-(49)
  comparison (1e-12 absolute). Four new cases compare the roughness field factor to numerical
  integration of the characteristic function of a Gaussian height-induced path phase
  (`q = 4 pi sigma sin(psi) / lambda`), 1e-10 absolute tolerance. This validates the algebra
  **conditional on Gaussian heights**, not the material, lossy circular antenna phase or an
  observed lunar reflection. `s5.reflection_formulas = verified`; multipath remains unvalidated.
- **S2:** three independent Cartesian dot-product cases check sampled ridge projection, signed
  height, both path distances and the selected maximum Fresnel parameter: 1e-8 m absolute,
  1e-9 relative for nu. `s2.rf_geometry = verified`; the actual DEM uncertainty, radius fit and
  single-obstacle assumption remain unvalidated.
- **S3, actual error corrected:** the former midpoint rectangles missed a crescent at a flat
  horizon with solar semidiameter 0.27 degrees and centre elevation -0.26999 degrees:
  upper limb visible, but fraction zero and therefore `lit = false`. Across 10001 uniformly
  spaced flat-horizon elevations, maximum absolute fraction error was **0.000773109883**.
  The earlier 2e-5 residual for another analytic implementation was not a valid bound for
  current terrain-disc quadrature.

S3 now integrates the **actual circular area inside each of the same 48 strips**, cut by its
midpoint horizon, using the circular antiderivative. A sweep across 1001 flat-horizon offsets
agrees with the independent circular-segment formula within 2e-15 absolute fraction; three
variable-horizon cases agree with independent adaptive strip quadrature within 1e-9.
The thin crescent remains positive; with incomplete terrain it is **unknown**, not a
numerically rounded known zero. Invalid solar semidiameters remain explicitly unknown.
S4 automatically uses this corrected fraction through the existing single pipeline.

### Harder numerical comparison on real terrain

Repeated S3 against the independent arbiter's refined disc integration, using **the same
production mask** to isolate the area algorithm from terrain and azimuth-grid errors.
Five cached catalogue sites, observer 2 m, 200 km mask, 2027-01-01 through 365 days,
6-hour steps (1460 instants per site); no data downloads. Arbiter 1024 and 2048 columns,
128 instants per batch to bound memory:

| Site | Current mean disc fraction | Maximum absolute residual vs 2048 columns | 1024-to-2048 refinement | Different lit steps |
|---|---:|---:|---:|---:|
| Malapert | 0.329535501 | 0.000011854016 | 0.000004471869 | 0 |
| Haworth | 0 | 0 | 0 | 0 |
| Nobile rim | 0.344357214 | 0.000012725051 | 0.000002998001 | 0 |
| de Gerlache | 0 | 0 | 0 | 0 |
| Shackleton | 0 | 0 | 0 | 0 |

The two illuminated sites are regression cases in `test_s2_s3_real.py`; their numeric
acceptance tolerances are 2e-5 fraction against the reference and 1e-5 for its refinement.
This is a sampled integration comparison, **not** proof of convergence for every terrain,
continuous window-edge accuracy or an observational illumination validation. The shared
mask is explicitly not an independent terrain source. Earlier two-hour/year numbers
must not be compared to this six-hour sampling as if the criteria and sampling were identical.

**Still not physically validatable from the available evidence:** the four acceptance gates
in the preceding closure audit remain open. In particular, exact strip area does not resolve
variation of terrain within a strip, angular mask discretization, DEM errors, limb darkening,
or the LROC polar discrepancy. No new matching observation or hardware trace has been obtained,
and no claim is made that the LROC residual improved. These are not silently replaced by an
assumed uncertainty or by zero. Overall states remain S2 not validated, S3 plausibility only,
S4 not validated, S5 not validated; illustrative parameter tags are unchanged.

Model/Validation displays per-stage verified-check counts separately from its conservative
stage status, and the missing independent evidence in both EN and IT. Counts are evidence
inventory, not a mission-qualification percentage.

Reproduce with `.venv/bin/python -m pytest tests/backend/domain/raven
tests/backend/domain/grazing/test_horizon.py tests/backend/domain/grazing/test_terrain.py
tests/backend/domain/grazing/test_multipath.py -q`.

## Remaining-stage arithmetic and applicability corrections (2026-11-08)

Current model: **raven-core-1.3**, unchanged parameter registry. Archived 1.2 results
remain historical; their matching registry does not make their calculations current.
The matrix contains **21 verified checks, 4 plausibility-only, 6 not validated and
1 unknown**. No missing observational or hardware evidence has been manufactured.

| Stage | Reproduced error and correction | Independent or regression check | Scope still not qualified |
|---|---|---|---|
| S2 | Absolute-height polynomial fitting gave resolved radii around 1e18 m on perfectly constant negative relief. Fit relative heights instead. | Four constant elevations must be unresolved; analytic 400 m parabola at three vertical offsets agrees within 1e-9 relative. `s2.ridge_fit_arithmetic` verified. | Real DEM curvature, fit-window adequacy, projected-ray vertex and single-obstacle representativeness. |
| S4 | Minimum SOC excluded the initial state and could exceed a charging mission's initial SOC. Include the initial SOC and known interval endpoints. | Initial SOC 0.2 remains the minimum of a known charging prefix; no known interval still gives an unknown minimum. | Hardware load/generation, usable battery energy and measured SOC. |
| S5 | Missing obstructing curvature silently disabled rounded correction despite that correction being enabled. Positive nu with nonfinite radius now gives `outside_model` and null margin/rate, unless sharp-edge-only mode is explicitly selected. | Synthetic missing radius, explicit sharp mode, unaffected gimbal steps and precedence of a known far-terrain block; real Shackleton historical budget reproduced only within its appropriate sharp-only scope. | Matching RF observations, ridge propagation, equivalent antenna/material and coherent reflection measurements. |
| S7 | Unknown RF/DSN was counted as a definite failure cause, falsely producing “multiple”. Attribute a cause only to an explicit false. | Independent nine-case three-valued RF/DSN truth table; `s7.rule_arithmetic` verified. | Mission thresholds and operational policies, not qualified by truth-table arithmetic. |

At 2027-04-07 00:00 UTC, de Gerlache and Shackleton now have an unknown RF margin
where the obstructing radius is absent. This is an intentional correction, not a
new RF measurement or a fabricated fitted radius. Malapert remains calculable;
a known far-terrain block remains a known no even without a numerical margin.

Scene responses carry authoritative `model.margin_db` and `model.rf_reason`.
Uncomputable aggregate RF terms are null, not legacy finite margins or implicit
zero corrections. The client renders actual geometry and pointing while preserving the renderer and camera,
with a neutral unknown state and explicit notice. Pointing cannot turn a null
margin into zero; text alternatives and exports preserve null. Simula with real
terrain hides its numerical gauge/chart/tables/export when the RF result is
unavailable instead of reporting its didactic fallback as current.

Model/Validation cards show **Verified** only if every recorded check for that
stage is verified. Unknown or unsupported statuses cannot become Verified.
Refresh and window focus reload the report; changed model/registry identity
invalidates cached parameters, and mismatched responses are rejected explicitly.
Hypothetical future reports test the open-to-Verified-to-unknown UI transition;
they do not change production validation evidence.

Overall S2/S4/S5 remain not validated and S3 plausibility only. The four physical
acceptance gates above still require equivalent independent data. S6's existing
DSN geometry checks and S3's earlier numerical checks remain unchanged.

Reproduce: `.venv/bin/python -m pytest tests/backend/domain/raven
tests/backend/domain/grazing/test_terrain.py tests/backend/api/test_raven_api.py -q`;
frontend Model/Lander tests and `e2e/tests/{model,lander,lander-no-webgl,simula}.spec.ts`.

Final checks: **2201 backend passed, 49 skipped; 826 frontend passed; 48 final scoped
frontend checks passed; 73 selected Chromium E2E passed**. Svelte has no errors or
warnings; Ruff, mypy, generated contracts and import contracts passed. Both build
bases pass the 70,000-byte initial-JS budget (68,509 / 68,517 bytes).
This is not an all-E2E or cold-start guarantee: the previously observed cold
Planner HTTP503 and preceding CI failure have not been claimed fixed.

## S2/S3 closure attempt and numerical corrections (2026-11-08)

Model **raven-core-1.4**, unchanged registry. The owner requested complete
S2/S3 Verified status; the existing physical gates have not been redefined or
removed to force that outcome. There are **22 verified checks, 4 plausibility-only,
6 not validated and 1 unknown**. Overall S2 is still not validated and S3 is
still plausibility-only.

| Correction | Evidence | Remaining limit |
|---|---|---|
| S2 polar bearings | Eight failing regressions reproduced the polar/near-polar mask and profile error. Shared Cartesian rotation matches an independent horizon oracle at both poles within 1e-8 deg and analytic south-pole meridians within 1e-8 deg. | Spherical coordinate arithmetic, not independent measured relief. Horizon algorithm v2 invalidates old cached masks. |
| S2 unsupported crest | Linear relief with slope 0.1 fabricated a resolved radius of 1.156e18 m. The fitted apex must now lie strictly inside its sampled window. Three monotone linear profiles remain unresolved; known parabolic fits are preserved. | The 20 m fit-depth choice, real DEM curvature, projected-ray vertex and single-obstacle representativeness remain unqualified. |
| S3 tilted horizon | A unit-disc slope-1 horizon at sqrt(2)+1e-5 returned 0.0002138627 illumination despite complete occultation. Integrate exact area above the piecewise-linear horizon, splitting the 48 base strips at interpolation knots. | Uniform disc and tangent-plane azimuth projection, not a radiometric surface model. |
| S3 coverage/projection | Include every crossed bin pair, including bins skipped by old high-Sun midpoint samples. Unsupported near-zenith partial-disc projection returns unknown rather than allocating an unbounded grid or inferring light. | Missing terrain is not filled with guessed heights. |

Tilted horizons of five slopes, at three seam/ordinary azimuths, have absolute
error below 2e-13 against independently rotated circular-segment solutions.
Strictly fully hidden cases are exactly zero; exact tangency uses the stated
floating-point tolerance rather than a threshold that deletes small crescents.
Continuous variable-horizon adaptive quadrature agrees within 1e-9.
Across five actual masks and 1460 instants per site in 2027, the largest
2048-column independent-disc residual was 1.4545e-6 fraction (Nobile);
1024-to-2048 refinement was at most 4.4719e-6 and no lit/dark decision differed.
This comparison shares the mask/DEM and is therefore numerical, not independent
terrain or illumination qualification.

The primary LROC image is available at the migrated NASA PDS archive:
`https://pds.mcp.nasa.gov/data/store/img/lunar_reconnaissance_orbiter/pds4/lroc/lro-l-lroc-5-rdr/LROLRC_2001/DATA/BDR/WAC_POLE/WAC_POLE_ILL_TWI_SOUTH/WAC_POLE_ILL_TWI_SOUTH_100M.IMG`.
Its 5,904,896 bytes match the existing pinned SHA-256. The attached label confirms
100 m/pixel and a time-weighted radiometric observation product. The pole pixel
is 49.9359%, its 3x3 mean 46.0477%; the earlier geometric arbiter value 26.7%
and the historic 29-point residual have not been silently recomputed or erased.
Spatial support and observation criterion still differ from the pointwise
geometric model. Archive migration was an access problem, not evidence that
observational data do not exist.

Barker's improved regional **5 m** LOLA products and quoted errors
(NASA NTRS [20205009660](https://ntrs.nasa.gov/citations/20205009660))
do not establish uncertainty for the locked **20 m / 240 m** products used here.
To close the physical gates requires equivalent independent terrain/curvature
with uncertainty and a like-for-like illumination comparison at matching
location, height, time, spatial support and criterion. Those requirements remain
visible in Model/Validation; passing arithmetic does not satisfy them.

Final checks: **273 scoped backend tests, 826 frontend tests and 17 selected
Chromium E2E passed**; Svelte has zero errors/warnings and both build bases pass
the 70,000-byte initial-JS budget. Lint, formatting, types and contracts pass.
The first full backend run passed 2257 tests, skipped 49 and found two failures:
all-unknown custom/catalogue margin comparison and legacy golden dependencies
using the corrected current terrain fit. The final scoped run includes both
corrected tests and the current scientific tests after the historical fixture.
Unknown margins must match explicitly, including their NaN locations.
Archived endpoints use isolated pre-1.4 terrain dependencies in their test
fixture; production and current scientific tests do not import them. Every
golden number and provenance record remains unchanged. No new complete
backend rerun or all-E2E/cold-start guarantee is claimed.
