<!-- SPDX-License-Identifier: Apache-2.0 -->
# GrazingLink: modello fisico scritto e verificato (fase 1)

> Nome storico: il prodotto si chiama **RAVEN**; "GrazingLink" e' il nome del prototipo di ricerca descritto qui.
> Il modello attuale e' in `docs/domain/raven-model.md`.

Stato: fase 1 del piano `docs/domain/grazinglink-plan.md`. Solo documentazione e verifica: nessun codice applicativo.
Data della verifica: 2026-10-26.

Materiale esaminato (cartella `research papers, scripts and planning/`, non modificata):
`antenna_directivity.py`, `compensation_demo.py`, `onda_3d_bozza.py`, `BozzaDescrizioneProgettoNASA.md`,
`Bibliografia_GrazingLink.xlsx`, `42-226D.pdf`, `ManualeEquazioniRiferimentoNASA.pdf`.

Abbreviazioni delle fonti:
- **JPL226** = M. Sanchez Net, "Simulation of Multipath Reflections from Planetary Bodies: Theory and Application to
  the Lunar South Pole", IPN Progress Report 42-226, 15 agosto 2021 (`42-226D.pdf`, 53 pagine). **Letto.** La
  numerazione stampata coincide con quella del PDF (pagina 1 = pagina 1 del PDF).
- **CB79** = R. K. Crane, D. W. Blood, "Handbook for the estimation of microwave propagation effects: link
  calculations for earth-space paths (path loss and noise estimation)", ERT Technical Report No. 1, P-7376-TR1,
  NASA GSFC, giugno 1979 (`ManualeEquazioniRiferimentoNASA.pdf`, 92 pagine). **Letto nelle parti citate.** La
  numerazione stampata è sfalsata di 12: pagina stampata 43 = pagina 55 del PDF. Qui cito "p. stampata (PDF n)".
  Le equazioni sono numerate da capo in ogni sottosezione, per cui cito "sez. x.y, eq. (n)".
- **P526** = Raccomandazione ITU-R P.526 "Propagation by diffraction". Non letta nella fase originale del 26 ottobre;
  la versione -9 (2005) è stata **letta sul testo** il 2026-11-04 per §2.1, §2.7, §4.1 e §4.2 (eq. (2), (6)-(7b),
  (22)-(32)): vedi la sezione «Validazione radio (2026-11-04)» qui sotto e in `docs/domain/validation.md`.
  Le note «memoria, non verificato sulla fonte» riferite a P526 nelle sezioni 2.3, 2.4 e T2/T4 sono superate.
- **ASSUMP** = `docs/domain/assumptions.md` del repository (fase A): contiene valori V già estratti dai moduli DSN
  810-005 e dai fact sheet NSSDC. Quando lo riprendo lo scrivo; non ho riaperto quei documenti in questa fase.

Etichette dei parametri (regola 1 del piano): **V** = letto in una fonte con pagina; **D** = derivato con formula;
**I** = ipotesi illustrativa (gli script stessi dichiarano illustrativi i parametri radio).

### Verifica aggiuntiva della fonte P.526 (2026-10-29)

È stata consultata la versione della bibliografia, [ITU-R P.526-9 (2005)](https://www.itu.int/rec/R-REC-P.526-9-200508-S/en),
disponibile dal sito ITU. È una versione superata, non la raccomandazione attualmente in vigore.

- La definizione di ν e il segno di h concordano con §4.1, p. 14, eq. (22) e relative definizioni.
  La formula approssimata J(ν) riportata sotto concorda con §4.1, p. 16, eq. (27), per ν > −0,78.
  Il valore zero assegnato dal codice per ν ≤ −0,78 non è stabilito da quell'equazione; la perdita esatta
  può oscillare nella zona illuminata.
- La forma delle espressioni T(m,n) riportate sotto concorda con §4.2, p. 17, eq. (28)–(32). Tuttavia
  la fonte definisce h, d1 e d2 rispetto al **vertice di intersezione dei raggi proiettati sopra l'ostacolo**,
  non semplicemente rispetto alla cima fisica della cresta. Il confronto numerico esistente non dimostra
  che le geometrie usate nei due modelli siano equivalenti: resta un confronto indicativo, non una
  validazione della tabella o una risoluzione della discrepanza con JPL226.
- Questa verifica riguarda le formule e le convenzioni citate sopra, non la validazione sperimentale né
  l'intera implementazione del modello arrotondato. Le indicazioni precedenti «da memoria» nelle sezioni
  seguenti descrivono lo stato della verifica originale del 26 ottobre.

### Validazione radio (2026-11-04)

Dettagli, numeri e test in `docs/domain/validation.md`, sezione omonima. In sintesi:
- **V (testo letto)**: P526-9 §2.1 eq. (2) zona di Fresnel; §2.7 eq. (6)-(7b) integrali di Fresnel; §4.1 eq.
  (22)-(23) ν e segno di h/θ; eq. (26) J esatto; eq. (27) approssimazione solo per ν > −0,78; §4.2 eq. (28)-(32)
  A = J + T(m,n) con m, n. Le formule del codice coincidevano già con il testo; i test le confrontano con una
  quadratura indipendente (eq. 26) e una reimplementazione scalare (eq. 30-32).
- **Politica della cresta arrotondata**: correzione predefinita = max(T(m,n), 0) di P526-9 §4.2 con d1, d2, λ
  reali; la tabella split-step resta come confronto e |ITU − split-step| è l'incertezza. Lo studio di
  convergenza (`scripts/study_splitstep_convergence.py`) mostra che la tabella non è convergente nel passo
  dx = 2 m (circa 0,5 dB sotto a ν = 3, R = 400 m) e che lo split-step raffinato resta al 55-95 % di T.
- **JPL226 eq. (35)-(38)**: «L_A → 0 per d2 ≫ d1» con m = f^⅓ ψ, parametro senza raggio: non usato.
- **Ancora non verificato**: nessuna misura; nessuna soluzione esatta del cilindro; P526 in vigore non letta.

#### Un caso analitico del vertice ITU

Per verificare quanto la differenza di vertice influisca **su un solo caso della tabella**, si considera
la geometria continua ideale del generatore: onda piana orizzontale incidente da sinistra, cresta
parabolica `y = -x²/(2R)` con cima in `(0, 0)`, ricevitore in `(D, -h)`, `D = 2000 m`,
`λ = 0,0357 m`, `R = 400 m` e `ν_cima = 3`. La prima tangente è orizzontale e passa per la cima;
la seconda passa per il ricevitore. Dalla condizione di tangenza si ricava
`x_t = D - sqrt(D² - 2Rh)` e il vertice delle due tangenti è `(x_t/2, 0)`. Questo è il caso limite
di sorgente all'infinito, non una dimostrazione per geometrie arbitrarie o per un profilo LOLA.

Con `h = ν_cima sqrt(λD/2) = 17,9248 m`, `x_t = 3,5882 m`; il vertice è spostato di
`1,7941 m` rispetto alla cima e la distanza lungo il raggio fino al ricevitore è `1998,2863 m`.
Usando tale distanza e la stessa quota `h` si ottiene `ν_vertice = 3,001286`. Per le eq. (27) e
(28)–(32) della P.526-9 la perdita totale indicativa è **26,646 dB**; usando ancora la cima e
`D = 2000 m` è minore di circa **0,007 dB**. Per confronto, la perdita costituita dal bordo
esatto più la tabella interpolata è **24,949 dB**: circa **1,697 dB** sotto il valore ITU con
vertice corretto. La differenza fra i soli termini arrotondati non coincide con quella fra le perdite
totali, perché qui l'approssimazione ITU del bordo e la soluzione esatta differiscono.

Il risultato suggerisce che lo spostamento del vertice **non spiega la discrepanza in questo caso**.
Non prova che la geometria sia equivalente in tutta la griglia, non quantifica gli errori numerici dello
split-step né risolve il confronto con JPL226 o la validazione sperimentale. In particolare il profilo
numerico è troncato 20 m sotto la cima e discretizzato; la costruzione qui è continua.

#### Sensibilità numerica del caso

Lo script `scripts/ridge_sensitivity.py` ripete il caso precedente con il propagatore del generatore
e varia un parametro alla volta; la perdita viene interpolata in dB come nella tabella. Non modifica
la tabella. Con i parametri originali (`dy = 0,1 m`, `dx = 2 m`, troncamento `20 m`, finestra
FFT `1638,4 m`) la perdita simulata a `ν = 3` è **24,9499 dB**.

| Variazione rispetto al caso originale | Perdita a ν = 3 | Differenza |
|---|---:|---:|
| `dx = 1 m` | 25,2100 dB | +0,2600 dB |
| `dx = 0,5 m` | 25,3375 dB | +0,3876 dB |
| `dy = 0,05 m`, stessa larghezza FFT | 24,8873 dB | −0,0626 dB |
| `dy = 0,025 m`, stessa larghezza FFT | 25,2060 dB | +0,2561 dB |
| troncamento a `10 m` / `40 m` sotto la cima | 24,9285 / 24,9633 dB | −0,0214 / +0,0133 dB |
| finestra FFT raddoppiata | 24,9499 dB | −0,0001 dB |

Il risultato dipende dalla discretizzazione e i valori al variare di `dy` non sono monotoni. Queste
prove **non stabiliscono un limite d'errore né la convergenza** e non equivalgono a una misura reale:
non si può attribuire con certezza la discrepanza ITU alla risoluzione. Cambiare il troncamento
modifica inoltre il profilo fisico, non solo il campionamento. I risultati riguardano solo questo
caso; la geometria ITU, il modello scalare/parassiale e la validazione sperimentale restano aperti.

---

## 0. Sintesi delle verifiche e dei problemi trovati

| # | Elemento | Esito | Dove |
|---|---|---|---|
| 1 | Perdita esatta del bordo a lama con gli integrali di Fresnel (`knife_exact_db`) | **Verificato su JPL226** | p. 16, eq. (38)-(39) |
| 2 | Parametro nu e convenzione del segno (nu > 0 se il crinale sta sopra la linea di vista) | **Verificato su JPL226** (nota 9 a p. 15: h < 0 se l'ostacolo non interseca la linea di vista) | p. 15-16, eq. (39) |
| 3 | Approssimazione ITU J(nu) = 6.9 + 20 log10(...) | Formula confrontata con P.526-9 §4.1 eq. (27), valida per nu > -0,78; scarto calcolato <= 0.123 dB per -0.78 < nu <= 5 | §2.3, test T2 |
| 4 | Correzione per cresta arrotondata | JPL226 eq. (35)-(38) p. 15-16 la riduce a zero per d2 >> d1 (parametro senza raggio); P526-9 §4.2 eq. (28)-(32) (**testo letto** 2026-11-04) e lo split-step danno una correzione non nulla, lo split-step raffinato al 55-95 % di T. **Politica**: T di P526 predefinita, split-step come banda di incertezza; non validata da misure | §2.4, «Validazione radio» |
| 5 | Coefficienti di Fresnel del regolite | **Verificato su JPL226** eq. (48)-(49) p. 20, a meno del segno (convenzione FSA: R_JPL = -Gamma_script, controllato numericamente). Lo script usa **solo la polarizzazione orizzontale**, mentre il collegamento di JPL226 è RCP | §2.6 |
| 6 | Snell in JPL226 eq. (50) p. 20 stampata come `eps1 sin(theta_i) = eps2 sin(theta_t)` | **Refuso della fonte**: la legge corretta usa gli indici n = sqrt(eps) | §2.6 |
| 7 | Fattore di rugosità dello script `exp(-(4 pi sigma sin psi / lambda)^2)` applicato all'**ampiezza** | **Sbagliato di un fattore 2 nell'esponente**: JPL226 eq. (87), (90), (94) p. 26-28 dà `exp(-(q_z s)^2)` sulla **potenza** coerente, con q_z s = 4 pi s sin psi / lambda; il fattore in ampiezza è quindi `exp(-(q_z s)^2 / 2)` (forma di Ament, da memoria) | §2.6, test T8 |
| 8 | Termine di fase del raggio riflesso `exp(-j 4 pi h sin psi / lambda)` | Corretto per suolo piano e Terra all'infinito (differenza di cammino 2 h sin psi). Limiti: nessuna curvatura lunare, punto speculare oltre il crinale per psi piccoli, raggio riflesso non diffratto separatamente | §2.6 |
| 9 | Perdita di puntamento 12 (err/HPBW)^2 dB | D: è il fascio gaussiano, costante esatta 10 log10(e) 4 ln 2 = 12.04. Valida fino a circa err = HPBW/2; a err = HPBW sottostima di 4.3 dB rispetto a un'apertura uniforme | §2.9, test T9 |
| 10 | HPBW ~ 70 lambda/D | Approssimazione per illuminazione rastremata (memoria, **non verificato sulla fonte**); apertura uniforme: 58.96 lambda/D (calcolato) | §2.9 |
| 11 | G ~ 30000/HPBW^2 | Formula grezza (lo script lo dice). Con eta = 0.55 e HPBW = 70 lambda/D la costante coerente è 26 599: scarto +0.52 dB | §2.9 |
| 12 | Efficienza d'antenna 0.55 | I. CB79 usa 0.56 nel suo modello di scintillazione (p. 46 (PDF 58)), come ipotesi del modello, non come dato di un'antenna da rover | §3 |
| 13 | Spazio libero e guadagno da apertura | **Verificato su CB79** sez. 2.7 eq. (1) p. 65 (PDF 77) e definizione di G_r p. 66 (PDF 78) | §2.10 |
| 14 | Distanza Terra 384 400 km fissa | I/D: è la distanza media. La FSPL varia di -0.49/+0.46 dB tra perigeo e apogeo (363 300 / 405 500 km da ASSUMP) | §2.10 |
| 15 | DSN 34 m 68 dBi, Tsys 30 K, Eb/N0 2.5 dB | 68 dBi implica eta = 0.704 ed è 0.2-0.3 dB sotto 68.21-68.29 dBi (DSN104Q Tab. 7 via ASSUMP); 30 K sta nell'intervallo 19.74-42.1 K (DSN104Q Tab. 9 via ASSUMP); 2.5 dB non verificato | §3 |
| 16 | Elevazione della Terra con librazione sinusoidale (`earth_el`) | Giocattolo: ignora la parallasse topocentrica (fino a 0.259 deg, confrontabile con il crinale a 0.9 deg) e la librazione fisica, fasi arbitrarie. Da sostituire con le effemeridi | §2.1 |
| 17 | Zona di Fresnel | **Verificato su CB79** sez. 2.3, eq. (2), p. 43 (PDF 55): F = sqrt(n lambda z), z = rho (L - rho) / L. Gli script non la calcolano | §2.5 |

---

## 1. Convenzioni comuni

- c = 299 792 458 m/s (costante esatta). f = 8.4 GHz (banda X), lambda = c/f = 0.035690 m (D). Gli script di
  diffrazione usano `LAM = 0.0357` m (arrotondato; JPL226 p. 3 scrive "3.57 cm" a 8.4 GHz: V).
- Angoli: elevazione `el` della Terra sull'orizzonte locale, in gradi; angolo radente `psi` = el per suolo
  orizzontale.
- Decibel: le perdite sono positive (J > 0 significa attenuazione). Un valore J < 0 è un guadagno (oscillazioni di
  Fresnel nella zona illuminata).
- Convenzione temporale e^{+j omega t} (JPL226, nota 13 p. 19): la permittività complessa si scrive
  eps_r = eps' - j eps''. Lo script usa `3.7 - 0.01j`, coerente.

---

## 2. Moduli

### 2.1 A. Geometria ed effemeridi (elevazione della Terra, librazione)

**(1) Equazioni degli script.** `compensation_demo.py`, funzione `earth_el(td, lat=-86.0, lon=0.12)`:

```
b(t) = 6.68 deg * sin(2 pi t / 27.21 + 1)      latitudine selenografica del punto sub-terrestre [rad]
l(t) = 7.9 deg  * sin(2 pi t / 27.55)          longitudine selenografica del punto sub-terrestre [rad]
e    = [cos b cos l, cos b sin l, sin b]       versore Luna -> Terra nel riferimento lunare fisso
n    = [cos p cos la, cos p sin la, sin p]     normale (zenit) del sito, p = lat, la = lon
el   = asin(e . n)                             elevazione [deg]
```
t in giorni (passo 15 min, 30 giorni). 27.21 e 27.55 d sono i periodi draconitico e anomalistico (memoria,
**non verificato sulla fonte**); la fase "+1" rad è arbitraria. `antenna_directivity.py` cita le ampiezze
"+-6.7 deg (lat) e +-7.9 deg (lon)" (bozza §3.A, stessi valori).

**(2) Verifica.** Le ampiezze di librazione ottica ~6.7 deg / ~7.9 deg sono valori di letteratura che ricordo, ma
la fonte in bibliografia (Copernicus AMT 2022, P3) **non è stata letta**: non verificato sulla fonte. JPL226 p. 35
(Fig. 9) mostra, per Mount Malapert e antenna a 10 m, una Terra che "almost never rises above 12 deg" e che
tramonta per circa una settimana al mese, calcolata con DEM e curvatura (nota 24): è un controllo qualitativo
utile, non una tabella di numeri. Problemi del modello giocattolo:
- **Parallasse topocentrica ignorata**: `el` è l'elevazione della direzione Luna-centro -> Terra-centro, non
  quella vista dal sito. Lo scarto arriva a asin(R_Luna/d) = asin(1737.4/384 400) = **0.259 deg** vicino
  all'orizzonte (D), cioè quasi un terzo dell'altezza del crinale assunto (0.9 deg). Non è trascurabile qui.
- Librazione fisica, variazione della distanza, inclinazione reale e fasi: assenti.
- Centro della Terra, non il disco (diametro 1.80-2.01 deg): parte del disco può essere visibile quando il
  centro non lo è.

Il motore (fase 2) userà `backend/ephemeris` (Skyfield + kernel NAIF, già nel repository): vettore sito -> Terra
in un riferimento lunare fisso, elevazione e azimut topocentrici. La sinusoide resta solo come riferimento per
confrontare gli output degli script.

### 2.2 A. Profilo del terreno

**(1) Script.** Nessun profilo: `compensation_demo.py` usa un ostacolo unico con altezza angolare fissa
`th_h = 0.9` deg a distanza `d_ridge = 2000` m (I).

**(2) Cosa si implementa (D, geometria).** Profilo LOLA lungo l'azimut della Terra, campioni (s_i, z_i) con s
distanza orizzontale e z quota sul riferimento. Angolo di elevazione apparente del punto i dall'antenna a quota
z_a, con curvatura lunare (R_m = 1737.4 km):

```
theta_i ~= atan( (z_i - z_a) / s_i ) - s_i / (2 R_m)          [rad]
```
(approssimazione per s << R_m; la forma esatta si ottiene con i vettori nel riferimento lunare fisso).
Ostacolo dominante = punto con nu massimo (§2.3), coerente con il limite "ostacolo singolo dominante".
Il raggio di cresta R per la correzione (§2.4) si stima con una parabola ai minimi quadrati attorno al massimo:
z(x) ~= z0 - x^2/(2R). Limite: con passo LOLA di 5-20 m (JPL226 p. 3 cita 5 m come risoluzione migliore; p. 2 usa
dati a 20 m e la Tab. 1 a p. 35 un DEM a 10 m) raggi sotto qualche decina di metri non sono risolvibili: va scritto in UI.
JPL226 p. 3 nota anche che i DEM lunari sono "electrically undersampled" alla lunghezza d'onda X (3.57 cm contro
5 m): la rugosità sotto il passo del DEM va modellata statisticamente (§2.6).

### 2.3 B. Diffrazione da bordo a lama

**(1) Script.** `compensation_demo.py`, `knife_exact_db`:

```
A(nu)   = (1/2 - C(nu)) - j (1/2 - S(nu))
F(nu)   = (1 + j)/2 * A(nu)                    campo diffratto / campo libero
J(nu)   = -20 log10 |F(nu)|                    [dB]
nu      = -(el - th_h) * (pi/180) * sqrt(2 d / lambda)
```
C, S: integrali di Fresnel `scipy.special.fresnel` (convenzione con pi t^2 / 2 nell'argomento). el, th_h in
gradi, d [m], lambda [m]. nu adimensionale.

**(2) Verifica.**
- JPL226 p. 16, **eq. (38)**: L_D ~= (1/2) |(1/2 - C(nu)) - j (1/2 - S(nu))|^2. Poiché |(1+j)/2|^2 = 1/2, lo
  script calcola esattamente -10 log10 di questa quantità: **verificato**. Nota: JPL226 chiama "loss" un
  rapporto di potenza lineare e poi scrive P_rx = P_los + L_D (eq. (40)) in dB: il segno va letto come
  guadagno negativo. Lo script usa la convenzione perdita positiva.
- JPL226 p. 16, **eq. (39)**: nu = h sqrt(2 (L1 + L2) / (lambda L1 L2)) ~= sqrt(2 d1 / lambda) theta per
  L2 >> L1 e theta piccolo; nota 9 (p. 15): h < 0 se l'ostacolo non interseca la linea di vista. Lo script ha
  theta = th_h - el (in rad) e quindi nu > 0 quando il crinale è sopra la linea di vista: **verificato**. JPL226
  eq. (39) nell'ultima forma omette il segno; theta va letto come l'angolo tra linea di vista e cima.
- P526, bordo a lama singolo (**V**: P.526-9 §4.1 eq. (22)-(23), (26), (27), testo letto 2026-11-04; lo «J = 0
  altrimenti» è una scelta del codice, la fonte non dà valori sotto −0,78): stessa forma esatta con C e S, stessa
  definizione di nu (nu = h sqrt(2/lambda (1/d1 + 1/d2)) = theta sqrt(2 d1 d2 / (lambda (d1 + d2)))), e
  l'approssimazione
  `J(nu) = 6.9 + 20 log10( sqrt((nu - 0.1)^2 + 1) + nu - 0.1 )` per nu > -0.78, J = 0 altrimenti.
  La bibliografia (riga P526, P1) dice "da confermare qui la mia approssimazione J(nu)": gli script **non**
  usano l'approssimazione, usano la forma esatta. Lo scarto calcolato (test T2) è al massimo 0.123 dB per
  -0.78 < nu <= 5; per nu < -0.78 l'approssimazione ignora le oscillazioni (da -1.37 a +1.09 dB tra nu = -3 e
  -0.78).
- CB79: non tratta la diffrazione da terreno (è un manuale Terra-spazio sull'atmosfera): non applicabile.

**Decisione.** Runtime: forma esatta (scipy). L'approssimazione J(nu) è solo un test di coerenza.

### 2.4 B. Cresta arrotondata

**(1) Script.** Nessuna formula chiusa: la "verità" è lo split-step (§2.7). La correzione è il residuo
`R(nu, raggio) = L_splitstep - J_esatto`.

**(2) Verifica e incoerenza aperta.**
- JPL226 p. 15-16, **eq. (35)-(37)** (da Crysdale): L_D = L_K + L_A, L_A ~= -20 log10 |1 + m Psi(m)|, m = f^(1/3) psi,
  Psi integrale con funzioni di Airy. JPL226 afferma che per d2 >> d1 psi -> 0 e quindi L_A ~= 0: per un
  collegamento verso la Terra la correzione di cilindro **sparisce**.
- P526, ostacolo arrotondato (**V**: P.526-9 §4.2 eq. (28)-(32), p. 17, testo letto 2026-11-04; la forma
  ricordata era corretta): A = J(nu) + T(m, n), con
  m = R ((d1 + d2)/(d1 d2)) / (pi R / lambda)^(1/3), n = h (pi R / lambda)^(2/3) / R,
  T = 7.2 m^(1/2) - (2 - 12.5 n) m + 3.6 m^(3/2) - 0.8 m^2 per m n <= 4,
  T = -6 - 20 log10(m n) + 7.2 m^(1/2) - (2 - 17 n) m + 3.6 m^(3/2) - 0.8 m^2 per m n > 4.
  Per d2 -> infinito, m -> R / (d1 (pi R/lambda)^(1/3)), che **non** tende a zero.
- Lo split-step degli script (onda piana, quindi d2 = infinito) dà residui fino a +2.43 dB a R = 400 m: anche
  lui non nullo.
- Confronto numerico split-step / T di P526 (memoria) a d1 = 2000 m (test T4): lo split-step dà circa il 40-60 %
  di T (es. R = 400 m, nu = 2: 1.63 dB contro 3.00 dB). Esito della verifica del 2026-11-04: la formula non era
  ricordata male; il troncamento a 20 m pesa ≤ 0,05 dB; il passo dx = 2 m sottostima fino a circa 0,5 dB; a passo
  fine lo split-step resta al 55-95 % di T (schermo assorbente scalare parassiale contro formula ingegneristica).

**Decisione (aggiornata 2026-11-04).** Correzione predefinita = max(T(m, n), 0) di P526-9 con d1, d2, λ reali
(`compensation.ridge_correction`); la tabella split-step resta come confronto e |ITU − split-step| è riportata
come incertezza (serie `ridge_correction_splitstep_db`, variante split-step in Simula). Il termine resta
opzionale (on/off) e non è validato da misure.

### 2.5 B. Zona di Fresnel

**(1) Script.** Non calcolata esplicitamente; compare solo come scala implicita sqrt(lambda d) nello split-step
(`yo = -nu * sqrt(LAM * DIST / 2)`) e nella scena 3D della bozza (tubo di Fresnel).

**(2) Equazione e verifica.**
```
r_n(d1) = sqrt( n lambda d1 d2 / (d1 + d2) )       [m],  d2 -> inf:  r_1 ~= sqrt(lambda d1)
```
**Verificato su CB79**, sez. 2.3, **eq. (2)**, p. 43 (PDF 55): F = sqrt(n lambda z), z = rho (L - rho)/L, con
rho posizione lungo il raggio e L lunghezza totale (stessa formula con d1 = rho, d2 = L - rho). Uso:
nu = sqrt(2) h / r_1 (D, dalle due definizioni). Il criterio "60 % della prima zona libera" è
**V** in P.526-9 §2.3 p. 3 (inizio della zona di diffrazione a una distanza pari al 60 % di R1; testo letto
2026-11-04); stessa formula R_n in §2.1 eq. (2). h = -0.6 r_1 dà nu = -0.6 sqrt(2) = -0.849, dove J esatto = -0.374 dB
(lieve guadagno, cioè perdita praticamente nulla; calcolato con lo stesso script del test T1). JPL226 p. 15 cita la prima zona di Fresnel come soglia qualitativa, senza formula.

### 2.6 C. Multipath a due raggi sul regolite

**(1) Script.** `compensation_demo.py`, `two_ray_db(eps_deg, h, lam, er=3.7-0.01j, sig=0.25)`:

```
s      = sin(psi),  q = sqrt(eps_r - cos^2 psi)
Gamma  = (s - q) / (s + q)                                   polarizzazione orizzontale (TE)
rho    = exp( -(4 pi sigma s / lambda)^2 )                   fattore di rugosità, applicato all'AMPIEZZA
r      = Gamma * rho
G2     = 20 log10 | 1 + r exp(-j 4 pi h s / lambda) | (+1e-9)   [dB]
```
psi = max(el, 0.05 deg); h = altezza dell'antenna (2.0 m modello, 2.15 m "realtà"); sigma = rugosità rms [m].

**(2) Verifica.**
- **eps_r = 3.7 - j0.01 e sigma = 0.25 m: V da JPL226 Tab. 1, p. 35** ("Lunar dielectric constant 3.7 - j0.01",
  "Lunar roughness 0.25 m", "Lunar roughness distance 1 m"). Attenzione: in JPL226 sono **parametri di
  simulazione in banda S (2.2 GHz)** per Mount Malapert, non misure; la tabella dà l'unità "F/m" alla costante
  dielettrica relativa, che è adimensionale (refuso). Restano quindi V come "valore usato da JPL", I come
  proprietà vera del regolite al sito.
- **Coefficienti di Fresnel: JPL226 eq. (48)-(49), p. 20**, in forma di impedenze. Con eta2 = eta1/sqrt(eps) e
  Snell corretta, R_perp(JPL) = -Gamma_h(script) e R_par(JPL) = -Gamma_v (controllo numerico a psi = 1 e 10 deg:
  moduli identici, segno opposto per la convenzione FSA). **Verificato** in modulo.
- **JPL226 eq. (50), p. 20 è stampata come `eps1 sin(theta_i) = eps2 sin(theta_t)`**: refuso, Snell vale con gli
  indici, sqrt(eps1) sin(theta_i) = sqrt(eps2) sin(theta_t). Ho controllato l'immagine della pagina, non solo il
  testo estratto.
- **Scelta della polarizzazione**: lo script usa solo Gamma_h. JPL226 Tab. 1 usa RCP in trasmissione e in
  ricezione (DSN). Per polarizzazione circolare il coefficiente co-polare (stesso senso dell'antenna di
  ricezione) è (Gamma_h + Gamma_v)/2 e quello incrociato (Gamma_h - Gamma_v)/2, con la convenzione in cui
  Gamma_h = -Gamma_v a incidenza normale (memoria, **non verificato sulla fonte**; JPL226 p. 20 dà RCP come
  alpha_h = 1/sqrt(2), alpha_v = j/sqrt(2) e p. 24 nota 18 il polarizzatore RCP, coerente ma non in questa
  forma). A psi = 1 deg: |Gamma_h| = 0.979, |Gamma_co| = 0.952 (test T7): differenza piccola al radente,
  grande sopra qualche grado. Angolo di Brewster radente 27.47 deg (D: atan(1/sqrt(3.7))).
- **Fattore di rugosità: errore.** JPL226 p. 26 eq. (87): q_z^2 s^2 = (4 pi^2/lambda^2)(cos theta_i + cos theta_s)^2 s^2;
  in riflessione speculare cos theta_i = cos theta_s = sin psi, quindi q_z s = 4 pi s sin psi / lambda.
  JPL226 eq. (90) p. 27 ed eq. (94) p. 28: la parte coerente di <|I|^2> (potenza) è moltiplicata per
  exp(-(q_z s)^2). Il fattore sul **campo** è dunque exp(-(q_z s)^2 / 2) = exp(-8 pi^2 s^2 sin^2 psi / lambda^2),
  che è la forma di Ament che ricordo (non verificata sulla fonte). Lo script mette exp(-(q_z s)^2) sul campo:
  l'esponente è doppio. A psi = 1 deg: 0.094 (script) contro 0.307 (corretto); l'escursione del multipath
  passa da -0.84/+0.77 dB a -3.11/+2.28 dB (test T8). Lo script quindi **sottostima** il multipath tra
  ~0.3 e ~2 deg. Inoltre JPL226 eq. (90) include il fattore (1 + 4 s^2/l^2) = 1.25 (s = 0.25, l = 1 m) che lo
  script non ha.
- **Termine di fase** `exp(-j 4 pi h sin psi / lambda)`: differenza di cammino 2 h sin psi tra raggio diretto e
  immagine, suolo piano, sorgente all'infinito (D, geometria). Corretto in queste ipotesi. Limiti:
  1. punto speculare a distanza h / tan psi: 2292 m a 0.05 deg, 1146 m a 0.1 deg con h = 2 m, cioè **oltre o
     vicino al crinale a 2 km**: lì il "suolo piano davanti all'antenna" non esiste più (test T8);
  2. orizzonte lunare per h = 2 m a sqrt(2 R_m h) = 2636 m: curvatura e fattore di divergenza ignorati;
  3. il raggio riflesso passa dallo stesso crinale ma con un nu diverso (antenna immagine a -h): lo script
     moltiplica J(nu) del raggio diretto per G2, cioè assume la stessa diffrazione per i due raggi;
  4. pendenza locale del DEM ignorata (psi = el sull'orizzontale);
  5. guadagno d'antenna verso il raggio riflesso (a -psi) uguale a quello diretto.
  JPL226 tratta invece la riflessione per faccette del DEM con parte coerente e non coerente e un canale di Rice
  (eq. (31)-(34) p. 13-14) e osserva che sotto ~5 deg domina la parte coerente (p. 36). Il modello a due raggi
  ne è il caso con una sola faccetta piana e solo la parte coerente.
- **Limite psi -> 0, suolo liscio**: Gamma_h -> -1 e la fase -> 0, quindi 1 + r -> 0 (cancellazione totale,
  -inf dB). Lo script evita il logaritmo di zero con il taglio psi >= 0.05 deg e +1e-9.
- CB79 sez. 2.4 (p. 52-57 (PDF 64-69)) parla di multipath **atmosferico** e di defocusing nella troposfera
  terrestre: si applica alla stazione di terra a bassa elevazione, non alla superficie lunare (che non ha
  atmosfera). Per elevazioni DSN sopra 5 deg il defocusing è "of the order of 0.1 dB" (CB79 p. 54 (PDF 66)):
  V, trascurabile con la maschera DSN di 6-10 deg (ASSUMP).

### 2.7 B. Simulazione ad alta fedeltà (split-step di Fresnel) e onda 3D

**(1) Script.** `compensation_demo.py`, `hi_fidelity_loss(R, dx=2.0)` e `onda_3d_bozza.py`:

```
propagatore parassiale:  E(x + dx, y) = IFFT{ FFT{E(x, y)} * exp(-j pi lambda dx f_y^2) }
ostacolo:                E = 0 per y < -x^2/(2R) (cresta parabolica), x in [-w, w], w = sqrt(2 R * 20 m)
                         R = 0: E = 0 per y <= 0 (lama)
perdita:                 L(y) = -10 log10( |E(y)|^2 / mean(|E|^2, 300 < y < 600 m) )
lettura a nu:            y_obs = -nu sqrt(lambda d / 2),  d = 2000 m dalla cima
```
N = 2^14 campioni, dy = 0.1 m (finestra 1638.4 m, periodica), lambda = 0.0357 m.
`onda_3d_bozza.py`: stessa propagazione da una lama, 100 passi da 20 m, |E|^2 per -40 <= y <= 40 m.

**(2) Verifica.** Metodo standard di ottica di Fourier (memoria). Controllo interno ottenuto: per R = 0 il
residuo split-step - esatto sta in [-0.04, +0.07] dB (output §6), quindi la discretizzazione è adeguata per
la lama. Ipotesi da dichiarare: 2D (cresta cilindrica infinita), scalare (nessuna polarizzazione), parassiale,
ostacolo perfettamente assorbente (non dielettrico né conduttore), cresta troncata a 20 m sotto la cima, onda
piana (Terra all'infinito). JPL226 non usa split-step (usa GO per faccette + bordo a lama): nessun confronto
diretto possibile.

### 2.8 B. Tabella di compensazione multi-fidelity e processo gaussiano

**(1) Script.**
```
griglia:   nu in [-1.5, 3.0] passo 0.05 (91 valori) x R in {0, 5, 10, 20, 50, 100, 200, 400} m = 728 celle
residuo:   Delta(nu, R) = L_splitstep(nu, R) - J_esatto(nu)          [dB]
feature:   x = (nu, log10(R + 1))
GP:        kernel C(1.0) * RBF([0.5, 0.8]) + White(1e-3), normalize_y = True, 1 restart
prova:     25 % delle celle tolte a caso (seed 3), RMSE di: residuo = 0, interpolazione lineare, GP
anomalie:  res = Delta - GP_tutte(x); MAD = 1.4826 median|res - median(res)|; anomalia se |res - median| > 4 MAD
uso:       L_corretta(nu, R) = J_esatto(nu) + Delta_tabella(nu, R)
```
**(2) Verifica.** Metodi standard (GP: scikit-learn; MAD con fattore 1.4826 per la normale, memoria). Nessuna
fonte del progetto li tratta. Osservazioni:
- la prova "25 % mancanti" è facile perché la griglia in nu è fitta (0.05) e il residuo è liscio: RMSE GP 0.00 dB
  e lineare 0.01 dB (output §6) **non** dimostrano capacità di estrapolazione in R o in nu;
- le anomalie sono soprattutto per nu < -0.78 (12 su 18): sono le oscillazioni di Fresnel, non errori;
- la "verità" è una simulazione con le ipotesi di §2.7, non una misura.
**Decisione** (piano): la tabella si genera offline (extra `[ml]`), si versiona con sha256, e a runtime si fa
solo interpolazione bilineare in (nu, log10(R+1)); fuori griglia si satura ai bordi e lo si segnala.

### 2.9 E. Antenna di bordo: guadagno, HPBW, puntamento

**(1) Script.** `antenna_directivity.py`:
```
G(D)    = 10 log10( eta (pi D f / c)^2 ),  eta = 0.55                [dBi]
HPBW(D) = 70 lambda / D                                              [deg]
L_p     = 12 (err / HPBW)^2                                          [dB]   (tabella: err = HPBW/2 -> 3.0 dB)
D(G)    = (lambda / pi) sqrt( 10^(G/10) / 0.55 )                     [m]
G(HPBW) ~ 10 log10( 30000 / HPBW^2 )                                 [dBi]  ("grezza", dichiarato)
theta_T = 12742 / 384400 rad = 1.90 deg                              diametro angolare della Terra
```
**(2) Verifica.**
- G = eta 4 pi A / lambda^2 con A = pi D^2/4 equivale a eta (pi D/lambda)^2: **verificato su CB79** sez. 2.7,
  p. 66 (PDF 78): G_r = 10 log10(4 pi A_e / lambda^2), A_e = eta A, "aperture efficiency factor".
- eta = 0.55: I. CB79 p. 46 (PDF 58) usa eta = 0.56 ("(eta)^(1/2) = 0.75 assumed in model") nel modello di
  scintillazione: conferma solo l'ordine di grandezza tipico.
- 70 lambda/D: approssimazione per apertura rastremata (memoria, **non verificato sulla fonte**). Apertura
  circolare uniforme (diagramma di Airy, calcolato): HPBW = 1.029 lambda/D rad = 58.96 lambda/D deg. eta = 0.55
  e 70 lambda/D sono due ipotesi indipendenti, non derivate dalla stessa illuminazione.
- 12 (err/HPBW)^2: fascio gaussiano, L = 10 log10(e) 4 ln 2 (err/HPBW)^2 = 12.04 (err/HPBW)^2 (D). Con apertura
  uniforme (test T9): uguale fino a err/HPBW = 0.5 (3.00 contro 3.01 dB), 6.75 contro 7.44 dB a 0.75, 12.0 contro
  16.3 dB a 1.0. La colonna "perdita a metà HPBW" dello script vale 3.0 dB per costruzione (12 x 0.25) e non
  dipende da D.
- 30000/HPBW^2: con eta = 0.55 e HPBW = 70 lambda/D la costante coerente è eta pi^2 70^2 = 26 599: la formula
  grezza dà +0.52 dB in più (test T9).
- Antenna da 15 dBi (scenario del compensatore): D = 0.0861 m, HPBW = 29.0 deg (D). Spostamento massimo della
  Terra per librazione circa hypot(6.7, 7.9) = 10.4 deg -> 12 (10.4/29)^2 = 1.53 dB con montaggio fisso (D,
  ampiezze non verificate): coerente con la frase dello script "con HPBW > ~30 gradi basta un montaggio fisso".

### 2.10 Link budget (somma)

**(1) Script.** `compensation_demo.py`, `margin(rate, h_mast)`:
```
M = P_t + G_t + G_r - L_fs - L_x - J(nu) + G2(psi, h) - N0 - 10 log10(R_b) - (Eb/N0)_req        [dB]
  = 10 + 15 + 68 - L_fs - 3 - J + G2 - (-228.6 + 10 log10 30) - 10 log10(R_b) - 2.5
L_fs = 20 log10( 4 pi d f / c ),  d = 384 400 km
```
`antenna_directivity.py` risolve la stessa somma per G_t con margine 3 dB e perdite 3 dB:
`G_t,req = 3 + 2.5 + 10 log10 R_b + N0 - 10 - G_r + L_fs + 3`.

**(2) Verifica.**
- Struttura della somma: **CB79 sez. 2.7, eq. (1), p. 65 (PDF 77)**:
  P_r' = P_t + G_t - L_b - L_atm - A_rain - L_scint - L_fade - L_focus - L_radome + G_div + G_r,
  con **L_b = 10 log10(16 pi^2 R^2 / lambda^2)** (identica a L_fs). **Verificato.** Margine CB79 sez. 2.7
  eq. (2)-(4) p. 66 (PDF 78).
- Rumore: P_N = k T B, k = 1.38e-23 W s/K (**CB79 sez. 3.1, eq. (4), p. 69 (PDF 81)**). 10 log10(1.380649e-23) =
  -228.599 dBW/K/Hz (D): la costante -228.6 dello script è corretta a 0.001 dB.
- Termini di CB79 assenti negli script: L_atm, A_rain, L_scint, L_fade, L_focus, L_radome (tutti al lato Terra).
  In banda X, alla maschera DSN, sono piccoli ma non nulli: dichiarati come non modellati.
- Termini assenti rispetto a un budget completo: perdita di puntamento (§2.9), perdita di polarizzazione,
  variazione della distanza Terra-Luna (FSPL 222.14-223.09 dB per 363 300-405 500 km, ASSUMP/MOONFACT; lo script
  usa 222.63 dB), elevazione della stazione DSN.
- Con J = 0 e G2 = 0 lo scenario ha C/N0 = 81.20 dB-Hz e margine +13.9 dB già a 3 Mbps (test T11): il
  compensatore lavora quasi sempre al rate massimo e le interruzioni dipendono solo dai passaggi radenti.

### 2.11 D. Compensatore del bit rate

**(1) Script.**
```
M_pred(t, R_b)  = margin(R_b, h = 2.0 m)                         modello
M_vero(t, R_b)  = margin(R_b, h = 2.15 m) + N(0, sigma),  sigma = 1.5 dB     "realtà" simulata
R_b*(t)         = max{ R_b in {1e4, 3e4, 1e5, 3e5, 1e6, 3e6} : M_pred(t, R_b) - k sigma >= 0 }
interruzione    = M_vero(t, R_b*) < 0 ;  volume = sum R_b* x 900 s sui passi non interrotti
k in {0, 1, 2.33, 3}
```
**(2) Verifica.** Non è un metodo di una fonte: è un controllo feedforward con margine statistico. Per un
errore gaussiano puro la probabilità di interruzione a ogni scelta è Phi(-k): 50 %, 15.9 %, 0.99 %, 0.13 % (D).
Le percentuali ottenute (1.6, 0.6, 0.1, 0.0 %, §6) sono molto più basse perché nella maggior parte dei passi il
margine al rate massimo è di decine di dB (§2.10) e l'errore conta solo vicino alla soglia. Il generatore
casuale è condiviso con la parte A (seed 3): i numeri dipendono dall'ordine delle chiamate.

### 2.12 G. Dimensione angolare della Terra e intervalli di librazione

```
theta_T = 2 atan(R_T / d) ~= 2 R_T / d,  R_T = 6371 km                               [rad]
```
Script: 12742/384 400 rad = 1.8992 deg; esatto 1.8991 deg (D). Tra perigeo e apogeo (ASSUMP: 363 300-405 500 km)
2.009-1.800 deg. Librazione: +-6.7 deg (lat) e +-7.9 deg (lon), **non verificato sulla fonte** (vedi §2.1).
Con le effemeridi (fase 2) gli intervalli si misurano dal motore e diventano D.

---

## 3. Tabella dei parametri

| Parametro | Valore negli script | Tag | Fonte / formula / nota |
|---|---|---|---|
| Frequenza portante | 8.4 GHz | I (scelta) | Banda X; JPL226 p. 3 usa 8.4 GHz come esempio. Allocazione DSN 8400-8450 MHz in ASSUMP |
| lambda | 0.0357 m (diffrazione), c/f nel resto | D | c/f = 0.035690 m; JPL226 p. 3: 3.57 cm (V) |
| Distanza Terra-Luna | 384 400 km | I | Distanza media; valori reali 363 300-405 500 km (ASSUMP/MOONFACT); da effemeridi in fase 2 |
| Raggio/diametro terrestre | 12 742 km | I (valore standard) | Non riletto; EARTHFACT in ASSUMP |
| Raggio lunare | 1737.4 km (solo in questo documento) | I (valore standard) | MOONFACT in ASSUMP, non riletto qui |
| Ampiezze di librazione | 6.68 deg lat, 7.9 deg lon | I | Non verificato sulla fonte (AMT 2022 non letto) |
| Periodi di librazione | 27.21 d, 27.55 d | I | Draconitico/anomalistico, memoria |
| Sito | lat -86.0 deg, lon 0.12 deg ("simile a Malapert") | I | JPL226 Tab. 1 p. 35 usa Mount Malapert, senza coordinate |
| Crinale | th_h = 0.9 deg, d = 2000 m | I | Ipotesi; in fase 2 dal DEM |
| Raggi di cresta | 0-400 m | I | Bozza §3.B; non misurati |
| Altezza antenna | 2.0 m (modello), 2.15 m (realtà) | I | JPL226 usa 10 m (Tab. 1) |
| eps_r regolite | 3.7 - j0.01 | V (valore di JPL226) / I (al sito) | JPL226 Tab. 1 p. 35, simulazione in banda S |
| Rugosità rms sigma | 0.25 m | V (valore di JPL226) / I | JPL226 Tab. 1 p. 35 ("Lunar roughness") |
| Lunghezza di correlazione | (non usata) | V (JPL226: 1 m) | JPL226 Tab. 1 p. 35 |
| Polarizzazione del riflesso | orizzontale | I (scelta discutibile) | JPL226 Tab. 1: RCP/RCP |
| Potenza trasmessa | 10 W (10 dBW) | I | Non verificato; ASSUMP cita 61 W (TP2019) come esempio |
| Guadagno rover | 15 dBi (compensatore) | I | D = 0.086 m, HPBW 29 deg (D) |
| Efficienza d'antenna | 0.55 | I | CB79 p. 46 (PDF 58) usa 0.56 nel suo modello |
| HPBW | 70 lambda/D | I (approssimazione) | Uniforme 58.96 lambda/D (D) |
| Perdita di puntamento | 12 (err/HPBW)^2 | D | Gaussiana, 12.04 |
| Guadagno da HPBW | 30000/HPBW^2 | I (grezza) | +0.52 dB rispetto a eta = 0.55, 70 lambda/D |
| DSN 34 m | 68 dBi | I (vicino a V) | DSN104Q Tab. 7 via ASSUMP: 68.21-68.29 dBi a 8425 MHz; 68 dBi implica eta = 0.704 |
| Stazione 18 m | 62.5 dBi | I | Lo script lo dichiara ipotesi; implica eta = 0.708 |
| Tsys | 30 K | I | Dentro 19.74-42.1 K (DSN104Q Tab. 9 via ASSUMP) |
| Boltzmann | -228.6 dBW/K/Hz | V / D | CB79 p. 69 (PDF 81): k = 1.38e-23; esatto -228.599 |
| Perdite varie | 3 dB | I | |
| Eb/N0 richiesto | 2.5 dB | I | Codice non specificato; non verificato |
| Margine (antenna_directivity) | 3 dB | I | ASSUMP: >= 3 dB da TP2019 (V là) |
| Rate | 1e4-3e6 bit/s | I | Bozza §3.D |
| sigma dell'errore non modellato | 1.5 dB | I | |
| k (backoff) | 0, 1, 2.33, 3 | I | Phi(-2.33) = 0.99 % (D) |
| Passo temporale / durata | 15 min / 30 d | I | |
| Split-step | N = 2^14, dy = 0.1 m, dx = 2 m, troncatura 20 m | I (numerico) | Controllo R = 0: errore <= 0.07 dB |
| GP | C*RBF([0.5, 0.8]) + White(1e-3), seed 3 | I | |
| Soglia anomalie | 4 MAD | I | |

---

## 4. Cosa si implementa, cosa si approssima, cosa no

**Si implementa esattamente** (entro la precisione numerica):
1. Perdita del bordo a lama con C(nu), S(nu) (JPL226 eq. (38)); nu con il segno di JPL226 eq. (39)/nota 9.
2. FSPL e guadagno da apertura (CB79 sez. 2.7 eq. (1) e p. 66), con la distanza vera dalle effemeridi.
3. Raggio della zona di Fresnel (CB79 sez. 2.3 eq. (2)).
4. Coefficienti di Fresnel h, v e circolari co/cross per eps_r complessa.
5. Somma del link budget in dB con tutti i termini elencati in §2.10, ciascuno con tag V/D/I.
6. Elevazione e azimut topocentrici della Terra con librazione reale (Skyfield + NAIF), quindi parallasse inclusa.

**Si approssima** (con l'errore quando lo conosco):
1. Ostacolo singolo dominante (massimo nu sul profilo): ignora la diffrazione multipla. Errore non stimato.
2. Cresta arrotondata con T(m, n) di P526-9 §4.2 (testo letto): errore ignoto rispetto alla realtà; lo
   split-step 2D assorbente (tabella) dà il 40-60 % di T, a passo fine il 55-95 %: lo scarto è l'incertezza.
3. Multipath con un solo riflesso speculare su suolo piano a pendenza locale, parte coerente con fattore
   exp(-(q_z s)^2/2) in ampiezza (corretto rispetto allo script); niente parte non coerente, niente curvatura
   (errore non stimato; JPL226 mostra che la parte coerente domina sotto ~5 deg, p. 36).
4. Raggio riflesso con la stessa perdita di diffrazione del diretto, salvo che in fase 2 si calcoli nu per
   l'antenna immagine (preferibile, costo trascurabile).
5. Perdita di puntamento gaussiana: errore <= 0.03 dB fino a err = HPBW/2, -4.3 dB a err = HPBW (T9).
6. ITU J(nu) solo come controllo: errore <= 0.123 dB per -0.78 < nu <= 5 (T2).
7. Il compensatore assume errore gaussiano a sigma noto.

**Non si implementa:**
1. Modello completo JPL226 a faccette con RCS polarimetrica, coerente e non coerente (eq. (5)-(133)),
   triangolazione, octree, Moller-Trumbore, ritardo e Doppler (eq. (137)-(144)).
2. Ray tracing 3D, GTD/UTD, diffrazione su più spigoli.
3. Integrali di Airy per il cilindro (JPL226 eq. (36)-(37)).
4. Atmosfera terrestre, pioggia, scintillazione, defocusing, radome (CB79 sez. 2.1-2.5): dichiarati assenti.
5. Apprendimento per rinforzo (lo script stesso lo esclude).

**Limiti dichiarati dalla bozza (§7), sempre visibili in UI:**
- ostacolo singolo dominante (bordo a lama corretto per raggio di curvatura);
- nessuna misura radio reale al polo Sud (anche JPL226 p. 40: "complete experimental validation of the model is
  still pending");
- parametri dielettrici e di rugosità del regolite da letteratura (qui: da JPL226 Tab. 1, che li usa come
  ingresso di simulazione).

---

## 5. Casi di prova di validazione (numeri calcolati)

Calcolati con `scipy.special.fresnel` e `scipy.special.j1` (SciPy 1.18.1, NumPy 2.5.4, Python del `.venv`),
script nella cartella temporanea del job (non nel repository). Tolleranza suggerita: 1e-3 dB per le formule
chiuse, 0.05 dB per i confronti con valori stampati.

**T1. Bordo a lama esatto**, J(nu) = -20 log10 |(1+j)/2 ((1/2 - C) - j(1/2 - S))|:

| nu | -3.0 | -2.0 | -1.5 | -1.0 | -0.78 | -0.5 | 0.0 | 0.5 | 1.0 | 1.5 | 2.0 | 2.4 | 3.0 | 5.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J esatto (dB) | -0.444 | 0.737 | -0.659 | -1.001 | -0.011 | 1.859 | 6.021 | 10.234 | 13.864 | 16.777 | 19.091 | 20.618 | 22.522 | 26.936 |

Valori chiave richiesti: **nu = -1: -1.001 dB; nu = 0: 6.021 dB; nu = 1: 13.864 dB; nu = 2.4: 20.618 dB**.
Asintoto 13 + 20 log10 nu: 20.604 dB a nu = 2.4, 26.979 a 5, 33.000 a 10 (esatto 32.954).

**T2. ITU J(nu) (P.526-9 eq. (27), testo letto 2026-11-04) meno esatto**: nu = -0.5: +0.101; 0: +0.012; 0.5: +0.054; 1: +0.062;
1.5: +0.007; 2: -0.048; 2.4: -0.079 (J_ITU = 20.539); 3: -0.106; 5: -0.123 dB. Massimo |scarto| su
(-0.78, 5]: 0.123 dB a nu = 4.571. Per nu = -1 la formula dà 0 contro -1.001 dB esatto.

**T3. nu dallo scenario dello script** (d = 2000 m, lambda = c/8.4 GHz): el - th = -0.5 deg -> nu = 2.922,
J = 22.29 dB; -0.2 -> 1.169, 14.92; -0.1 -> 0.584, 10.90; 0 -> 0, 6.02; +0.1 -> -0.584, 1.24; +0.2 -> -1.169,
-1.35; +0.5 -> -2.922, -0.04 dB.

**T4. Residuo split-step contro T(m, n) di P526** (P.526-9 eq. (30)-(32), testo letto 2026-11-04; split-step della tabella, dx = 2 m, non convergente: vedi «Validazione radio»; d1 = 2000 m, d2 infinito, lambda = 0.0357):

| R (m) | nu = 0: split / T | nu = 1 | nu = 2 | nu = 3 |
|---|---|---|---|---|
| 5 | -0.067 / 0.130 | -0.055 / 0.414 | -0.048 / 0.698 | -0.062 / 0.982 |
| 50 | 0.069 / 0.278 | 0.294 / 0.890 | 0.582 / 1.502 | 0.897 / 2.114 |
| 100 | 0.129 / 0.350 | 0.459 / 1.121 | 0.874 / 1.892 | 1.326 / 2.663 |
| 400 | 0.329 / 0.552 | 0.907 / 1.776 | 1.632 / 3.000 | 2.428 / 4.223 |

Atteso in fase 2: chiarire lo scarto (§2.4) prima di usare T come riferimento.

**T5. FSPL e geometria**: 8.4 GHz, 384 400 km: **222.629 dB**; 363 300 km: 222.139; 405 500 km: 223.093;
2.2 GHz a 384 400 km: 210.992 dB (coincide con `docs/domain/method.md`). Diametro angolare della Terra a
384 400 km: 1.8991 deg (script 1.8992). Parallasse lunare: 0.2590 deg.

**T6. Zona di Fresnel** r1 = sqrt(lambda d1 d2/(d1+d2)), d2 = 384 400 km, lambda = 0.035690 m:
d1 = 10 m: 0.597 m; 50: 1.336; 100: 1.889; 500: 4.224; 1000: 5.974; **2000: 8.449**; 5000: 13.358;
10 000: 18.891 m. Collegamento di superficie d1 = d2 = 1000 m: 4.224 m.

**T7. Coefficienti di Fresnel**, eps_r = 3.7 - j0.01, psi radente:

| psi (deg) | 0.1 | 0.5 | 1 | 2 | 5 | 10 | 30 | 45 | 90 |
|---|---|---|---|---|---|---|---|---|---|
| abs(Gamma_h) | 0.9979 | 0.9894 | 0.9790 | 0.9584 | 0.8994 | 0.8098 | 0.5491 | 0.4334 | 0.3159 |
| abs(Gamma_v) | 0.9922 | 0.9615 | 0.9244 | 0.8543 | 0.6723 | 0.4400 | 0.0371 | 0.1878 | 0.3159 |
| abs(Gamma_co circ.) | 0.9950 | 0.9754 | 0.9517 | 0.9064 | 0.7858 | 0.6249 | 0.2560 | 0.1228 | 0.0000 |

Limiti: psi -> 0: Gamma_h, Gamma_v -> -1; psi = 90 deg: abs = (sqrt(3.7) - 1)/(sqrt(3.7) + 1) = 0.3159.
Brewster: 27.47 deg radente.

**T8. Rugosità e due raggi** (sigma = 0.25 m, h = 2 m, polarizzazione h):

| psi (deg) | g = (4 pi sigma sin psi/lambda)^2 | exp(-g) (script) | exp(-g/2) (corretto) | G2 script (dB) | G2 corretto (dB) | inviluppo corretto (dB) | h/tan psi (m) |
|---|---|---|---|---|---|---|---|
| 0.05 | 0.0059 | 0.9941 | 0.9971 | -4.40 | -4.38 | -47.95 / +6.00 | 2292 |
| 0.1 | 0.0236 | 0.9767 | 0.9883 | +1.13 | +1.18 | -37.18 / +5.96 | 1146 |
| 0.2 | 0.0944 | 0.9099 | 0.9539 | +5.09 | +5.28 | -25.99 / +5.80 | 573 |
| 0.5 | 0.5901 | 0.5543 | 0.7445 | -6.69 | -10.79 | -11.59 / +4.79 | 229 |
| 1.0 | 2.3601 | 0.0944 | 0.3073 | -0.81 | -2.91 | -3.11 / +2.28 | 115 |
| 2.0 | 9.4375 | 0.0001 | 0.0089 | -0.00 | -0.06 | -0.07 / +0.07 | 57 |

Inviluppo dello script a 1 deg: -0.84 / +0.77 dB. Orizzonte lunare per h = 2 m: 2636 m; per h = 10 m: 5895 m.

**T9. Antenne in banda X** (eta = 0.55, HPBW = 70 lambda/D):

| D (m) | 0.05 | 0.10 | 0.20 | 0.30 | 0.50 | 1.00 | 34 |
|---|---|---|---|---|---|---|---|
| G (dBi) | 10.28 | 16.30 | 22.32 | 25.84 | 30.28 | 36.30 | 66.93 |
| HPBW (deg) | 49.97 | 24.98 | 12.49 | 8.33 | 5.00 | 2.50 | 0.073 |
| 30000/HPBW^2 (dBi) | 10.80 | 16.82 | 22.84 | 26.36 | 30.80 | 36.82 | 67.45 |

34 m ideale (eta = 1): 69.52 dBi; eta per 68 dBi: 0.704. 18 m con eta = 0.55: 61.40 dBi.
Perdita di puntamento, err/HPBW = 0.10 / 0.25 / 0.50 / 0.75 / 1.00: gaussiana 0.120 / 0.750 / 3.000 / 6.750 /
12.000 dB; apertura uniforme (Airy) 0.114 / 0.719 / 3.010 / 7.439 / 16.276 dB.

**T10. Rumore**: 10 log10(k) = -228.599 dBW/K/Hz; N0(30 K) = -213.828 dBW/Hz (script -213.829).

**T11. Link dello scenario** (10 dBW, 15 dBi, 68 dBi, 3 dB, 30 K, 384 400 km): C/N0 = 81.200 dB-Hz;
margine con J = 0, G2 = 0, Eb/N0 2.5 dB: 1e4: +38.70; 3e4: +33.93; 1e5: +28.70; 3e5: +23.93; 1e6: +18.70;
3e6: +13.93 dB; rate a margine zero 7.41e7 bit/s. `antenna_directivity.py`: G_t richiesto -0.70 dBi a 1 Mbit/s
e 19.30 dBi a 100 Mbit/s con 68 dBi; 4.80 e 24.80 dBi con 62.5 dBi.

**T12. Compensatore** (errore gaussiano): Phi(-k) = 0.5000 / 0.1587 / 0.0099 / 0.0013 per k = 0 / 1 / 2.33 / 3.

**T13. Elevazione giocattolo** (`earth_el`, lat -86, lon 0.12, 30 d, passo 15 min): min -2.690 deg,
max 10.670 deg; frazione del tempo con el > 0.9 deg: 0.592; con el > 0: 0.637. Da usare solo per riprodurre gli
script; il motore con effemeridi deve dare numeri diversi (parallasse, librazione vera).

**T14. Effemeridi (fase 2)**: su un anno il punto sub-terrestre deve stare entro circa +-6.7 deg in latitudine e
+-7.9 deg in longitudine (valori non verificati sulla fonte: tolleranza larga, 0.5 deg, finché non si legge una
fonte).

---

## 6. Output degli script eseguiti (riferimento per confronti)

Eseguiti una volta il 2026-10-26 in una copia nella cartella temporanea del job, mai nella cartella della ricerca.
`antenna_directivity.py` e `compensation_demo.py` con il Python del `.venv` (Python 3.14, SciPy 1.18.1,
scikit-learn 1.9.1, NumPy 2.5.4). `onda_3d_bozza.py` con `/usr/bin/python3` (3.10.8, NumPy 2.4.4) perché il `.venv`
non ha matplotlib. Nessun file generato è stato messo nel repository.

`antenna_directivity.py`:
```
1) D (m)  guadagno (dBi)  HPBW (gradi)  perdita a meta' HPBW (dB)
   0.10   16.3   25.0   3.0
   0.20   22.3   12.5   3.0
   0.30   25.8    8.3   3.0
   0.50   30.3    5.0   3.0
   1.00   36.3    2.5   3.0
2) 34 m (68 dBi): Gt necessario 1e3 -30.7, 1e4 -20.7, 1e5 -10.7, 1e6 -0.7 (omni/patch),
                  1e7 9.3 (parabola 0.04 m, HPBW 55.9), 1e8 19.3 (0.14 m, 17.7)
   18 m (62.5 dBi): 1e3 -25.2, 1e4 -15.2, 1e5 -5.2 (omni/patch), 1e6 4.8 (0.03 m, 93.8),
                  1e7 14.8 (0.08 m, 29.7), 1e8 24.8 (0.27 m, 9.4)
3) Terra circa 1.9 gradi; HPBW 10/20/30/60 -> 24.8/18.8/15.2/9.2 dBi (30000/HPBW^2)
```

`compensation_demo.py` (circa un minuto; due ConvergenceWarning di scikit-learn sul noise_level del GP, vicino
al limite 1e-5):
```
A) residuo per raggio: medio / minimo / massimo (dB)
   0 m:  0.04 / -0.04 / 0.07      5 m: -0.05 / -0.07 / 0.03     10 m: -0.15 / -0.27 / 0.07
  20 m:  0.18 / -0.05 / 0.55     50 m:  0.30 / -0.05 / 0.90    100 m:  0.45 / -0.08 / 1.33
 200 m:  0.64 / -0.11 / 1.79    400 m:  0.88 / -0.16 / 2.43
   celle mancanti 182 su 728; RMSE: residuo = 0 0.68 dB, lineare 0.01 dB, GP 0.00 dB
   anomalie (> 4 MAD): 18 su 728; nu < -0.78: 12; nu >= -0.78: 6
B) backoff  interruzioni (%)  dati (relativi)
   0          1.6   1.00
   1 sigma    0.6   1.00
   2,33 sigma 0.1   0.99
   3 sigma    0.0   0.99
```
CSV generato: `tabella_compensazione.csv`, 728 righe + intestazione
(`raggio_m,nu,residuo_simulato_dB,residuo_GP_dB`), sha256
`f8322975ca39ba5e35efd5795fa8340d69d89586f6e3f42d093fce9982c6f301` (dipende dalle versioni delle librerie).

`onda_3d_bozza.py`: `salvato onda_3d_diffrazione.png (50, 801)` (50 distanze da 40 a 2000 m, 801 quote
tra -40 e +40 m). La docstring dice `python onda_3d.py`, ma il file si chiama `onda_3d_bozza.py`.

---

## 7. Bibliografia (da `Bibliografia_GrazingLink.xlsx`, foglio "Bibliografia GrazingLink")

Colonna "Letto": **sì** solo per i due PDF presenti nella cartella. Tutto il resto non è stato aperto in questa fase.

| Pr. | Titolo | Fonte | Cosa estrarre (dal foglio) | Letto |
|---|---|---|---|---|
| P1 | Direct-with-Earth Links between a Planetary Body and an Earth Station (multipath su DTE a bassa elevazione) | JPL IPN PR 42-243A | Modello a raggi del multipath DTE a bassa elevazione con diversità spaziale; termine di incertezza | no (nota: il PDF nella cartella è 42-226, non 42-243) |
| P1 | LTE Coverage Analysis Using TEMPER and Wireless InSite | JHU APL, URSI NRSM 2021 | Confronto diffrazione / ray tracing 3D al polo Sud | no |
| P1 | Lunar Relay Services Requirements Document (SRD) | NASA LCRNS 2025 | Requisiti Artemis (36 kbps, 60 Mbps, Ka) come preset | no |
| P1 | Lunar Surface VHF Propagation Loss Model for Lunar Terrain (Apollo 15) | NASA 1979 | Diffrazione su ostacolo arrotondato; critica di Bullington | no |
| P1 | NASA's Lunar Communications and Navigation Architecture | NASA 2024 | DTE, NSN, DSN, ESTRACK | no |
| P1 | Path Loss Prediction Over the Lunar Surface Utilizing a Modified Longley-Rice Irregular Terrain Model (Foore, Ida) | NASA/TM-2007-214825 | Fade, margine, DEM analogo, validazione Apollo | no |
| P1 | RF Metrology of Lunar Highlands | NASA NTRS 20230013296 | Parametri elettrici del regolite; bande X/Ka DTE | no |
| P1 | Recommendation ITU-R P.526-9: Propagation by diffraction | ITU-R | Bordo a lama e ostacolo arrotondato; conferma di J(nu) | sì, solo formule e geometria indicate nella verifica aggiuntiva |
| P2 | Gateway Communications (ICSSC) | NASA NTRS 20210018935 | Sistemi S, X, Ka di Gateway e HLS | no |
| P2 | Joint Age and Coverage-Optimal Satellite Constellation Relaying in Cislunar Communications with Hybrid Orbits | arXiv 2411.05655 | Copertura di relay | no |
| P2 | Lunar Pole Illumination and Communications Maps Computed From Digital Elevation Models | JPL IPN 42-176 | Mappe di comunicazione da DEM (geometriche) | no |
| P2 | Lunar Surface Propagation (progetto NASA SCaN) | NASA Glenn | Motivazione: Terra bassa, riflessioni, richiesta dati | no |
| P2 | Lunar Surface Propagation Modeling and Effects on Communications (Hwu et al.) | NASA NTRS 20080015374 | Altezza d'antenna, frequenza, materiale | no |
| P2 | Multipath Fading and Soil Property Characterization at Lunar South Pole from Ground-based Observations (poster) | JPL 2020 | Multipath con DEM LOLA a 5 m | no |
| P2 | NASA 3GPP in Space | NASA NTRS 20220016752 | Architetture di superficie | no |
| P2 | NASA Lunar Base Wireless System Propagation Analysis | NASA NTRS 20070016709 | Terreno 3D e multipath | no |
| P2 | NASA SCaN at the Moon (SpaceOps 2023, paper 537) | SpaceOps 2023 | Tassi S/Ka, LTV fino a 10 km, DSN uplink Ka | no |
| P2 | Sub-6-GHz 5G Large-Scale Path Loss Model for Shoemaker Rim F | MDPI Telecom 2026 | Path loss di sito con DEM e ray tracing | no |
| P2 | The evolution of lunar communication (Farkasvolgyi) | Int. J. Satellite Comm. and Networking 2024 | Panoramica bande e tassi (solo abstract) | no |
| P2 | Tulip-Shaped Orbits for Lunar South-Pole PNT and Direct-to-Earth Relay Missions | arXiv 2607.10482 | Relay per il polo Sud | no |
| P3 | Characterizing the Radio Quiet Region Behind the Lunar Farside (Bassett) | NESS / Univ. Colorado 2019 | Diffrazione su topografia LOLA | no |
| P3 | Development of a tool for Ground to Space Link Budget Computation | PoliTo / Telespazio 2025 | Link budget e CCSDS | no |
| P3 | Handbook for the estimation of microwave propagation effects | NASA NTRS 19820004428 | Equazioni di riferimento | **sì** (= CB79, `ManualeEquazioniRiferimentoNASA.pdf`, sezioni 2.3, 2.4, 2.7, 3.1) |
| P3 | Libration of the Moon: Earth observations from the Moon surface (preprint) | Copernicus AMT 2022 | Ampiezze e periodi di librazione | no |
| P3 | Lunar Browser trajectory tool | NASA Ames NTRS 20240005553 | Finestre di comunicazione | no |
| P3 | Moonlight: LCNS and Lunar Pathfinder | UNOOSA ICG WG-B 2024 | Orbite ellittiche congelate | no |
| - | Simulation of Multipath Reflections from Planetary Bodies (Sanchez Net) | JPL IPN PR 42-226 (2021) | Non è nel foglio | **sì** (= JPL226, intero) |

Il foglio "Dashboard" contiene solo formule di conteggio (26 riferimenti: 8 P1, 12 P2, 6 P3).

**Letture prioritarie per chiudere i punti aperti:** P526 in vigore (la -9 è stata letta il 2026-11-04 per
J(nu), T(m, n) e stima del raggio dal profilo); Crysdale 1958 e Rice 1954 (parametro originale di JPL226 eq. 36); il
preprint AMT 2022 (librazione); RF Metrology of Lunar Highlands (eps_r e perdite del regolite in banda X);
JPL 42-243A (multipath DTE a bassa elevazione).
