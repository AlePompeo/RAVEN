# GrazingLink: Advanced Cislunar Communication & Terrain Diffraction Planning Engine

> **Traccia di riferimento:** NASA Space Apps Challenge – *CLPS Lunar Mission Browser*[cite: 2]
> **Ambito:** Telecomunicazioni spaziali, pianificazione di missione cislunare, elettromagnetismo applicato, modellazione multi-fidelity.

---

## 1. Executive Summary (Cos'è GrazingLink)

Al Polo Sud lunare, la Terra si trova a pochissimi gradi dall'orizzonte (tra $0.5^\circ$ e $1.5^\circ$)[cite: 5]. I tool esistenti per la pianificazione delle missioni (come *LunaHorizon* o *Sightline*) rispondono a una domanda binaria e geometrica: *«La Terra è visibile da questo cratere oppure il crinale la blocca?»*[cite: 3, 4]. 

**GrazingLink fa un salto di qualità fondamentale:** supera la geometria pura introducendo l'elettromagnetismo e la propagazione d'onda. Riconosce che quando un segnale radio rasenta un ostacolo montuoso (*grazing ray*), non si interrompe di colpo, ma subisce **diffrazione** (secondo il modello ITU-R P.526) e riflessioni al suolo (*multipath*)[cite: 3, 4, 5]. 
GrazingLink è una piattaforma software interattiva che calcola il **margine di link effettivo** in tempo reale, stimando se e a quale velocità (bit-rate) un lander o un rover lunare può comunicare con la Terra o con un satellite relay, anche quando la linea di vista geometrica è parzialmente ostruita[cite: 3, 4].

---

## 2. Obiettivi Principali del Progetto

1. **Prevedere le finestre di comunicazione reali:** Sostituire le stime geometriche binarie con un calcolo basato sulla fisica della diffrazione e sulla teoria delle zone di Fresnel[cite: 3, 4, 5].
2. **Ottimizzare il throughput dei dati (Bit-rate dinamico):** Consentire agli ingegneri di missione di sfruttare la "zona di transizione" delle onde radio per estendere le ore di trasmissione utile di dati scientifici pesanti o video HD[cite: 4, 8].
3. **Integrazione End-to-End con l'Hardware:** Collegare la pianificazione del segnale radio con i vincoli fisici e geometrici del rover di superficie (dimensionamento delle antenne in banda X e tolleranze di puntamento rispetto alla librazione terrestre)[cite: 4, 9].
4. **Modellazione Multi-Fidelity:** Correggere i modelli teorici ideali (bordo a lama) tenendo conto della curvatura e della rugosità reale dei crinali lunari tramite surrogate modeling basato su Processi Gaussiani[cite: 8].

---

## 3. Come Funziona: Architettura Scientifica e Moduli

Il sistema si compone di moduli analitici interconnessi che elaborano i dati topografici digitali (DEM LOLA della NASA) e le effemeridi spaziali[cite: 3, 4]:

### A. Modello Geometrico ed Effemeridi
* **Posizionamento della Terra:** Calcolato tramite le effemeridi SPICE e modelli di librazione lunare ($\pm 6.7^\circ$ in latitudine, $\pm 7.9^\circ$ in longitudine)[cite: 4].
* **Profilo del Terreno:** Estrazione del profilo altimetrico lungo l'azimut della Terra a partire dai dati altimetrici laser della sonda LRO (LOLA)[cite: 3, 4].

### B. Modello di Diffrazione & Multi-Fidelity (Correzione delle Creste Arrotondate)
* *Il limite teorico:* La formula classica del bordo a lama (*knife-edge*) assume ostacoli appuntiti perfetti. Nella realtà lunare, i crinali sono arrotondati[cite: 8].
* *La soluzione GrazingLink:* Utilizza una simulazione a onde piene (*split-step* di Fresnel) su creste con raggi di curvatura reali ($R$ da 0 a 400 m)[cite: 8]. Un **Processo Gaussiano (GPR)** apprende il "residuo" (la differenza di attenuazione tra la cresta reale e quella ideale), creando una tabella di compensazione robusta[cite: 8].

### C. Modello di Propagazione e Multipath (Two-Ray Model)
* Calcola le interferenze dovute alle riflessioni speculari sul regolite lunare (caratterizzato da una costante dielettrica nominale e un fattore di rugosità superficiale $\sigma$), cruciali quando la Terra è vicinissima all'orizzonte[cite: 8].

### D. Compensatore Statistico del Bit-Rate
* Invece di un collegamento a velocità fissa, il sistema implementa un compensatore *feedforward* che stima la variabilità del canale e applica un margine di sicurezza statistico ($k \cdot \sigma$), selezionando dinamicamente il bit-rate massimo sostenibile (da 10 kbps a 3 Mbps) per prevenire interruzioni (*outage*) di missione[cite: 8].

### E. Dimensionamento dell'Antenna di Bordo e Vincoli di Puntamento
* Integra un modulo radiotecnico che calcola il guadagno, l'apertura del fascio ($\text{HPBW}$) e la dimensione dell'antenna parabolica in banda X necessaria sul rover per chiudere il link con stazioni di terra da 34 m (DSN) o 18 m (es. LEGS), valutando la necessità di sistemi di puntamento motorizzati (*gimbal*) per contrastare i movimenti di librazione terrestre[cite: 9].

---

## 4. Analisi dei Competitor e Differenziazione

| Feature / Capacità | Tool Esistenti (es. *LunaHorizon*, *Sightline*)[cite: 3, 4] | **GrazingLink (Il vostro progetto)** |
| :--- | :--- | :--- |
| **Tipo di analisi visiva** | 2D/3D geometrica (Sì / No)[cite: 3, 4] | 3D interattivo con visualizzazione della **Zona di Fresnel**[cite: 4] |
| **Effetti d'onda** | Ignorati[cite: 3, 4] | **Diffrazione del crinale** (ITU-R P.526)[cite: 3, 4, 5] |
| **Topografia reale** | Solo altezza geometrica[cite: 3, 4] | **Correzione multi-fidelity** per creste arrotondate (Processi Gaussiani)[cite: 8] |
| **Gestione del canale** | Nessuna[cite: 3, 4] | **Multipath sul regolite** e compensatore dinamico del bit-rate[cite: 8] |
| **System Engineering** | Limitato alla visibilità[cite: 3, 4] | Integrazione con **specifiche d'antenna del rover** e librazione[cite: 4, 9] |

---

## 5. Mercato, Stakeholder e Vendibilità (B2B / B2G)

GrazingLink non è un prodotto consumer, ma uno strumento industriale ad alto valore aggiunto per la **NewSpace Economy** e l'esplorazione cislunare[cite: 6]:

1. **Contractor Commerciali CLPS (NASA / Privati):** Aziende come *Intuitive Machines, Astrobotic, Blue Origin*. Hanno la necessità critica di validare i margini di comunicazione Direct-to-Earth per evitare la perdita di missioni da decine di milioni di dollari[cite: 6].
2. **Agenzie Spaziali (ESA, NASA, ASI):** Utile per la pianificazione a lungo termine delle infrastrutture di comunicazione del programma Artemis e delle costellazioni di relay (es. programma *ESA Moonlight*)[cite: 4, 6].
3. **Operatori di Stazioni di Terra e System Integrator:** Enti e aziende come *Telespazio / Centro Spaziale del Fucino* o grandi colossi aerospaziali che gestiscono i flussi di dati verso le antenne di deep space[cite: 6].

---

## 6. Stack Tecnologico Progettato

* **Backend di Calcolo (Engine):** Python / NumPy / SciPy / scikit-learn (per le elaborazioni di ottica di Fourier, la gestione delle funzioni di Fresnel e il training dei Processi Gaussiani)[cite: 7, 8]; moduli di calcolo geometrico predisposti per la conversione in **C++ / WebAssembly** per garantire fluidità in tempo reale[cite: 4].
* **Frontend / Visualizzazione 3D:** WebGL / Three.js[cite: 4]. 
  * *Scena principale:* Vista dal lander con luce radente, modello del terreno LOLA, e un **tubo traslucido 3D (la zona di Fresnel)** che parte dall'antenna, viene intersecato dal crinale e cambia colorazione (verde/rosso) in base al margine di link calcolato dinamicamente[cite: 4].
  * *Dashboard analitica:* Interfaccia a doppia barra per confrontare la finestra geometrica pura contro la finestra reale con margine di diffrazione[cite: 3, 4].

---

## 7. Trasparenza Scientifica e Limiti Dichiarati

* Viene modellato un **ostacolo singolo dominante** (bordo a lama corretto per raggio di curvatura)[cite: 3, 4, 5].
* Non sono inclusi dati di propagazione radio reali registrati al Polo Sud lunare (poiché, come confermato dai report NASA SCaN, non esistono ancora dataset pubblici di misurazioni radio in loco)[cite: 3, 4, 5].
* Gli effetti dielettrici del regolite si basano su stime parametriche standard di letteratura[cite: 8].