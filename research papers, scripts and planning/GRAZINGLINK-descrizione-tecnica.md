# GrazingLink v3: descrizione e svolgimento del progetto

**Traccia:** NASA Space Apps 2026, CLPS Lunar Mission Browser (telecomunicazioni).

---

## 1. In breve

**GrazingLink** è uno strumento interattivo che, per un sito del Polo Sud lunare e una data, dice **quanto margine ha il collegamento radio con la Terra**. Non risponde "sì o no": calcola la perdita dovuta al crinale (diffrazione), le oscillazioni dovute al suolo (multipath), la direttività dell'antenna e l'altezza del mast, per ogni banda radio e per ogni stazione di terra. Poi propone un bit rate con un margine di sicurezza.

**Cosa è nuovo e cosa no (onestà).** La fisica di diffrazione e multipath al Polo Sud è già pubblicata da JPL (rapporti IPN 42-226 e 42-243A). La novità è portarla in uno strumento leggero, interattivo, per banda e mast, con la causa spiegata e un compensatore del bit rate. La validazione su dati di volo non esiste, e lo diciamo.

---

## 2. Cosa è cambiato in questa versione

| Novità | Perché | Stato |
|---|---|---|
| Multipath a due raggi dal suolo | I paper JPL e Gorham mostrano che il suolo riflette e crea frange | Calcolato e verificato analiticamente |
| Modulo antenna (guadagno, apertura del fascio, perdita di puntamento) | Serve per rispondere a "quanto direttiva?" | Calcolato (sezione 6) |
| Tabelle di compensazione con processo gaussiano | Correggere il modello veloce con uno più fedele e riempire celle vuote | Dimostrato su dati simulati (sezione 5) |
| Compensatore del bit rate | Raggiungere un obiettivo di interruzioni con un margine statistico | Dimostrato in simulazione (sezione 5.4) |
| Relay what-if (1–3 satelliti) | Cosa succede se la Terra non c'è | Opzionale, solo dopo il nucleo |
| Grafici d'onda 3D con strumenti open source | Spiegare la diffrazione a chi guarda | Esempio pronto (`onda_3d_diffrazione.png`) |

---

## 3. Architettura

```
[SPICE + LOLA]  --prepara_dati.py-->  ephemeris + DEM
        |
        v
  ENGINE C++/WebAssembly (da fare): orizzonte, profilo verso la Terra
        |
        v
  MODULI FISICI (JS o C++): diffrazione -> multipath -> antenna -> link budget
        |
        v
  COMPENSAZIONE: tabelle (LUT) + interpolazione + incertezza (GP) + segnalazione di anomalie
        |
        v
  DECISIONE: bit rate con margine statistico; relay what-if (opzionale)
        |
        v
  INTERFACCIA 3D (Three.js) + grafici d'onda + report esportabile
```

---

## 4. Moduli fisici e verifiche

1. **Orizzonte reale** da DEM LOLA, con curvatura lunare e altezza del mast (ray-marching per 360 azimut).
2. **Diffrazione a bordo a lama.** Parametro `ν = −Δ·√(2d/λ)` (Terra all'infinito); perdita esatta di Fresnel e approssimazione ITU-R P.526. Il rapporto JPL IPN 42-226 usa lo stesso parametro. **Verifica:** una simulazione d'onda indipendente concorda entro 0,07 dB con la formula esatta; l'approssimazione ITU entro 0,11 dB. A `ν = 0` la perdita è 6,02 dB.
3. **Multipath a due raggi** (metodo delle immagini): `Δr = 2h·sin ε`, coefficienti di Fresnel del regolite (ε = 3,7 − j0,01), fattore di rugosità di Gorham et al. **Verifica analitica:** con `R = −1` il primo massimo è a `sin ε = λ/(4h)` con +6,02 dB. A banda bassa le frange sono profonde (fino a circa −20 dB), in banda X la rugosità le attenua.
4. **Antenna:** guadagno `G = η(πD/λ)²`, apertura `HPBW ≈ 70 λ/D`, perdita di puntamento `≈ 12 (errore/HPBW)²` dB.
5. **Link budget:** Friis, rumore di sistema, Eb/N0 richiesto, margine di progetto 3 dB. I parametri radio sono ipotesi finché non si citano valori di un lander.
6. **Preset Artemis:** 36 kbps e 60 Mbps (requisiti NASA per i relay).
7. **Relay what-if (opzionale):** orbita ellittica di letteratura. Nel mio modello kepleriano un satellite copre circa il 77% del polo, due il 100%; Set Cover (ILP) conferma 2 come minimo. Nessuna perturbazione modellata.

**Controlli di coerenza con i paper:** a Mount Malapert il mio modello dà quota massima della Terra 10,7° e tramonto più lungo circa 8 giorni; JPL riporta "raramente sopra circa 12°" e "circa una settimana al mese".

---

## 5. Compensazione: reinforcement learning e deep learning sono applicabili?

### 5.1 Cosa intendi con "compensatore"
In teoria dei controlli un compensatore corregge un errore noto con una curva (esempio: l'equazione di Steinhart–Hart per linearizzare un termistore usa un logaritmo, `1/T = A + B·ln R + C·(ln R)³`; è una formula standard che non ho verificato in questa sessione). In GrazingLink ci sono due tipi di compensazione:
- **Correggere il modello:** un modello veloce (lama a bordo) più una correzione appresa da un simulatore più fedele.
- **Raggiungere un obiettivo:** scegliere bit rate e margine per ottenere una probabilità di interruzione voluta.

### 5.2 Applicabilità
| Idea | Applicabile? | Come | Rischio e sforzo |
|---|---|---|---|
| Tabelle di compensazione (LUT) con interpolazione | **Sì, subito** | Residuo = modello fedele − modello veloce, indicizzato per `ν`, raggio della cresta, banda, altezza del mast | Basso; la tabella vale solo quanto il simulatore fedele |
| Riempire celle vuote | **Sì** | Gerarchia: fisica → interpolazione (lineare o spline) → processo gaussiano con incertezza → rifiuto fuori dal dominio | Basso; per tabelle lisce basta l'interpolazione |
| Rilevare picchi e punti fuori regime | **Sì** | Residui dal modello liscio con soglia robusta (MAD); distinguere errori da fisica vera | Medio: i nulli del multipath e le oscillazioni di Fresnel **non vanno smussati** |
| Deep learning come **surrogato** | **Opzionale** | Rete che impara da migliaia di simulazioni costose (Kirchhoff su DEM, ray tracing) | Alto in 48 ore; per tabelle a poche dimensioni il GP è meglio |
| Reinforcement learning | **Non nel nucleo** | Possibile per adattare il rate con riscontro (ACK/NACK), puntamento o pianificazione dei contatti; esistono alternative classiche (tabelle di modulazione adattiva, Kalman, ILP) | Alto: senza dati reali si allena in simulazione e resta il divario con la realtà |

**Regola:** non si compensano i fenomeni fisici veri (nulli di multipath, ripple di Fresnel): si compensano solo gli **errori del modello**.

### 5.3 Risultati della dimostrazione (`compensation_demo.py`)
Simulatore fedele: propagazione d'onda split-step su una cresta **arrotondata** (raggi da 5 a 400 m) contro la lama a bordo esatta, banda X, cresta a 2 km.

| Raggio della cresta | Residuo medio | Residuo massimo |
|---|---|---|
| 0 (lama, controllo) | 0,04 dB | 0,07 dB |
| 50 m | 0,30 dB | 0,90 dB |
| 100 m | 0,45 dB | 1,33 dB |
| 400 m | 0,88 dB | 2,43 dB |

- La lama a bordo **sottostima** la perdita di una cresta arrotondata, fino a circa 2,4 dB. È una correzione piccola ma reale, che cresce con il raggio.
- **Celle mancanti** (182 su 728, scelte a caso): errore 0,68 dB senza compensazione; 0,01 dB con interpolazione lineare; 0,00 dB con il processo gaussiano. **Non** vuol dire che il GP sia migliore: la tabella è liscia e densa; il suo vantaggio è fornire l'incertezza quando i dati sono pochi.
- **Anomalie** (soglia 4 MAD): 18 punti su 728, di cui 12 con `ν < −0,78`, cioè le oscillazioni di Fresnel, che una curva liscia non cattura.
- **Limite:** la tabella corregge la differenza tra **due miei modelli**, non la realtà. Per una compensazione vera servono dati esterni (misure o simulazioni indipendenti).

### 5.4 Compensatore del bit rate
Scenario simile a Malapert, banda X, antenna da 15 dBi, cresta a 2 km e 0,9°, 30 giorni. Il modello usa il mast a 2,0 m; la "realtà" a 2,15 m più rumore di 1,5 dB.

| Margine di sicurezza | Interruzioni (% del tempo con link dichiarato) | Dati consegnati (relativi) |
|---|---|---|
| 0 | 1,6% | 1,00 |
| 1 σ | 0,6% | 1,00 |
| 2,33 σ | 0,1% | 0,99 |
| 3 σ | 0,0% | 0,99 |

Per un obiettivo di interruzioni sotto l'1%, servono circa 1 σ di margine, con un costo trascurabile in dati. **Non è reinforcement learning:** è un controllo predittivo con margine statistico. Un'estensione realistica è imparare il margine online da ACK e NACK con un algoritmo a banditi, dopo il nucleo.

---

## 6. Antenna del rover lunare: quanto direttiva?

**Dipende dal bit rate, dalla potenza e dalla stazione di terra.** Con 10 W, banda X, stazione da 34 m (68 dBi), Tsys 30 K, Eb/N0 2,5 dB, perdite 3 dB e margine 3 dB:

| Bit rate | Guadagno necessario | Tipo di antenna | Apertura |
|---|---|---|---|
| fino a 1 Mbps | circa −31 … −1 dBi | omnidirezionale o patch | quasi omni |
| 10 Mbps | circa 9 dBi | parabola equivalente D ≈ 4 cm | circa 56° |
| 100 Mbps | circa 19 dBi | D ≈ 14 cm | circa 18° |

Con una stazione da 18 m (ipotesi, circa 62,5 dBi) servono circa 5,5 dB in più: 10 Mbps a circa 15 dBi (apertura circa 30°), 100 Mbps a circa 25 dBi (circa 9°). Guadagno di una parabola in banda X: D = 0,1 m dà circa 16 dBi (25°); 0,3 m circa 26 dBi (8°); 1 m circa 36 dBi (2,5°).

**Cosa dicono le fonti sulla pratica** (da verificare nei testi primari):
- La Terra sottende circa 1,9° dalla Luna e la librazione la sposta di circa ±7°: un'antenna stretta richiede puntamento.
- Apollo: l'antenna ad alto guadagno del rover era in banda S, con guadagno nominale di circa 24 dB e puntamento entro pochi gradi (dato da una fonte secondaria che cita documenti NASA); il Lunar Surface Journal riporta che mantenere il puntamento in movimento si è rivelato difficile.
- VIPER: NASA Ames descrive un'antenna ad alto guadagno su gimbal, con più di 100 volte i dati di quella a basso guadagno.
- Chang'e-3: un rover con antenne a basso guadagno e ad alto guadagno orientabile (articolo IAC 2015).
- **Conseguenza per GrazingLink:** preset di antenna: omni/patch (0–8 dBi), media fissa (15–20 dBi, apertura 18–30°), alta su gimbal (25–30 dBi, 5–10°). Con antenne larghe il multipath dal suolo conta di più, perché il raggio riflesso resta nel fascio.

---

## 7. Strumenti open source per simulare e disegnare le onde

**Uso consigliato:**
- **Nel prodotto:** Three.js per la scena 3D e WebAssembly per il calcolo; superfici d'onda con Plotly o grafici statici con Matplotlib.
- **Per la verifica:** una simulazione d'onda (come lo split-step che ho usato) o openEMS/Meep per casi piccoli.
- Attenzione alle licenze GPL se distribuite con il codice: dichiaratele nel README.

Il file `onda_3d_diffrazione.png` mostra come appare un'onda diffratta da una cresta, ottenuta con strumenti open source.

---

## 8. Piano di svolgimento

**Prima dell'evento (verificate il regolamento e verificare questo svolgimento):**
1. Scaricare kernel e DEM, scrivere test su carta.
2. Alessio: prova di Emscripten e algoritmo dell'orizzonte.
3. Tu: parametri radio da fonti, tabella delle antenne, scelta dei siti.
4. Pitch e dichiarazione dei limiti.

**Durante le 48 ore (gate):**
| Ore | Cosa | Gate |
|---|---|---|
| 0–8 | Orizzonte (C++/WASM) e Terra nel browser per un sito reale | Gate 1 (ora 8) |
| 8–18 | Diffrazione, multipath, link budget | |
| 18–24 | Antenna (preset), stazione di terra, finestre | Gate 2 (ora 20): MVP |
| 24–34 | Compensatore del bit rate, tabelle di compensazione, spiegazione delle cause | |
| 34–44 | Scena 3D principale, grafico d'onda, validazione, video | Gate 3 (ora 36): blocco funzioni |
| 44–48 | Pitch, consegna | |
| Se avanza tempo | Relay what-if | |

**Ruoli da ricontrollare:** Alessio, motore C++/WASM, interfaccia e prestazioni; tu, dati, modelli, validazione e pitch.

**Definizione di "fatto":**
- [ ] Orizzonte reale e mast regolabile
- [ ] Diffrazione verificata (≤ 0,11 dB)
- [ ] Multipath a due raggi verificato
- [ ] Antenna con preset e perdita di puntamento
- [ ] Margine di link con valori radio citati
- [ ] Compensatore del bit rate con obiettivo dichiarato
- [ ] Tabella di compensazione con incertezza e avviso fuori dominio
- [ ] Scena 3D principale con dati veri
- [ ] Slide di validazione e dei limiti

---

## 9. Vista 3D

1. **Scena 1:** dal lander, il tubo di Fresnel verso la Terra, il crinale che lo taglia, **il cono dell'antenna** (apertura in gradi) e le **frange di multipath** al suolo che cambiano con il cursore del mast.
2. **Scena 2:** confronto tra finestra geometrica e finestra con margine; per ogni punto, causa (terreno, geometria, fading).
3. **Scena 3 (opzionale):** orbite relay e copertura.
4. **Pannello "onda":** superficie 3D dell'intensità dopo la cresta, come in `onda_3d_diffrazione.png`.

---

## 10. Prodotto, interlocutori e pitch
- **Chi compra:** operatori di lander e relay, gestori di stazioni di terra, e chi progetta il modulo abitabile italiano per il sito e il collegamento.
- **Modello (ipotesi):** licenza per missione più report.
- **Frase per la giuria:** "Sulla Luna il collegamento con la Terra non è acceso o spento: vicino all'orizzonte il crinale lo indebolisce e il suolo lo fa oscillare. Noi calcoliamo il margine reale e il bit rate sicuro."
- **Dichiarare sempre:** modello da letteratura JPL, validazione su dati di volo in sospeso.

---

## 11. Rischi e cosa non è verificato
- **Novità fisica limitata:** JPL ha già pubblicato i modelli.
- **Compensazione:** la tabella corregge differenze tra modelli, non la realtà; reinforcement learning e deep learning sono fuori dal nucleo.
- **Parametri radio, antenna e Tsys:** ipotesi da sostituire con valori di un lander o di una stazione reali.
- **Dati di Apollo e VIPER** sull'antenna: letti da fonti secondarie o divulgative; da confermare sui documenti.
- **Licenze** di alcuni strumenti: non verificate.
- **Regolamento:** controllare cosa si può preparare prima dell'evento.
- **Miller (60°N):** un dato dei paper allegati non si riproduce (vedi `paper-allegati/`).
