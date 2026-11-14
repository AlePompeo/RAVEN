# Ricerca automatica dei siti migliori: piano (bozza per la tua revisione)

Stato: **piano, nessun codice scritto**. Data: 12 nov 2026. Richiesta dell'utente: un algoritmo che trova da solo una "nuvola" di siti
con le migliori stime probabilistiche per lo scopo di una missione scelta, che combini algoritmi predittivi, il RAVEN core, i dati ricavati
dalle sovramappe e agenti LLM, e che l'utente possa guidare con un prompt (RAVEN SI) i cui contenuti diventano variabili del motore.
Assorbe anche il punto aperto "confronto di N siti" (oggi il planner e il report sono A contro B).

## 1. Regole che non si toccano
- **L'ignoto resta ignoto.** Un sito senza terreno, senza maschera o fuori dal modello non riceve un punteggio: va in `not_comparable` con il motivo
  (come `ranking.py`). Mai un valore riempito per far quadrare la nuvola.
- **Nessun numero unico nascosto** (decisione D5): ordine lessicografico sulle componenti scelte dall'utente, componenti sempre visibili.
  La "probabilita' di soddisfare gli obiettivi" e' una delle componenti, non un voto che le sostituisce.
- **Il core decide, i predittori propongono.** Ogni sito mostrato nei risultati e' stato ricalcolato dal RAVEN core (`/api/raven/evaluate`);
  un predittore (surrogato) serve solo a scegliere dove guardare. Cio' che non e' ricalcolato e' etichettato "stima del predittore" con il suo intervallo.
- **L'LLM non produce numeri.** Traduce il prompt in un brief strutturato (validato da schema e confermato dall'utente) e commenta risultati usando solo
  i numeri restituiti dal motore, con i tag V/D/I. Senza LLM il sistema funziona con il modulo.
- Tag: le stime del predittore e le probabilita' sono **I** (stima), anche se gli ingressi sono D. Fonti e limiti nel risultato.
- Solo inglese e italiano, solo Linux, nessun segreto nei file, download solo con il consenso gia' esistente.

## 2. Che cosa esiste gia' e si riusa
| Pezzo | Dove | Ruolo |
|---|---|---|
| Valutazione di un sito/finestra | `backend/domain/raven/pipeline.py` (`evaluate`), `/api/raven/evaluate` | verita' di terra: ore utili, SoC minimo, margine RF, DSN |
| Ordine lessicografico e `not_comparable` | `backend/domain/raven/ranking.py` | politica di ordinamento |
| Obiettivi di missione | `frontend/src/pages/planner/objectives.ts` (`priority`, `minSunPercent`, `minRfPercent`) | prime variabili del brief |
| Sovramappe globali (0,5 gradi) e polari (2 km) | `overlays_global.py`, `overlays.py`, `backend/assets/overlays/` | caratteristiche per cella: quota, pendenza regionale, quota di Sole, quota di Terra, copertura DEM |
| Terreno e maschere | `custom_terrain.py` (`TerrainStore`), `prefetch_global.py` | un sito fuori dal 20 m si valuta a 237 m se le tessere sono in cache |
| Classi di missione e stime | `economics.py`, `landing_stats.py`, `fresnel_estimates.py` | priori degli ingressi di tag I |
| Assistente RAVEN SI | `backend/assistant/`, `assistant_routes.py`, `raven_report.py` | canale del prompt; provider locale estrattivo, Groq, compatibile OpenAI |
| Catalogo siti | `backend/domain/data/sites.json` (51 siti) | candidati nominati e riferimento per la nuvola |

## 3. Il brief (le variabili)
`MissionBrief` (JSON con schema versionato, ogni campo opzionale, `null` = non specificato):
finestra di date; priorita' (`sun`, `earth`, `radio`, `balanced`); soglie minime di Sole e di radio in percento; classe di missione
(massa, pannello, batteria, antenna, stazione DSN, bit rate); fascia di latitudine o regioni permesse; pendenza regionale massima;
distanza minima fra siti proposti; K (quanti siti), budget di calcolo. Campi che il motore non conosce (per esempio "vicino all'acqua")
**non diventano variabili**: l'agente li segnala come non supportati.
Il prompt libero ("lander da 300 kg, 14 giorni da aprile 2027, almeno il 60 % di Sole, radio a 100 kbit/s, vicino al polo") produce un brief;
l'utente lo vede come modulo precompilato e lo conferma prima di calcolare.

## 4. Pipeline (fasi)
1. **Generazione dei candidati.** Dalle sovramappe: cella per cella, filtri duri soltanto dove il dato e' un limite sicuro (copertura, vincoli di
   regione e fascia). La pendenza regionale **non esclude** un sito (sottostima la pendenza locale): al piu' lo penalizza come componente. Le celle
   diventano una nuvola grezza di migliaia di punti con caratteristiche (lat, lon, quota, pendenza, quota di Sole, quota di Terra, statistiche
   dell'orizzonte, copertura).
2. **Predittore (surrogato).** Un modello veloce (processo gaussiano o insieme di alberi con intervalli) che stima le metriche del core
   (ore utili, SoC minimo, margine RF) dalle caratteristiche della cella. Si allena sulle valutazioni reali del core, parte da un campione
   spaziale stratificato e cresce per campionamento attivo (ottimizzazione bayesiana: celle promettenti **e** incerte). Seme fisso, versione del modello e
   hash del registro nel risultato.
3. **Valutazione reale a budget.** Il core valuta i candidati scelti (in lotti, con tetto di tempo e di numero). Il predittore si riaddestra.
   Si ferma quando i primi K non cambiano piu' o a budget esaurito.
4. **Probabilita'.** Per ogni candidato: distribuzione della metrica = valore del core dove calcolato, altrimenti media e intervallo del predittore,
   piu' propagazione dell'incertezza dei parametri di tag I (intervalli di `fresnel_estimates`, efficienza del pannello, guadagno d'antenna) con
   campioni Monte Carlo valutati dal core su un sottoinsieme. Risultato: P(soddisfa gli obiettivi) con intervallo, e quanta parte dell'incertezza
   viene dal sito e quanta dai parametri.
5. **Nuvola e proposte.** (a) Un nuovo livello di sovramappa "idoneita'" (P per cella, ignoto tratteggiato) sul globo 3D e sulla mappa polare.
   (b) Fino a K siti proposti: centroidi di cluster con distanza minima, ognuno con componenti, P, intervalli, motivi del non confrontabile e
   avvertenze (terreno a 237 m, orizzonte da celle di 15 km, ecc.). Ordine lessicografico a scelta dell'utente, con vista del fronte di Pareto.
6. **Agenti LLM** (tutti dietro strumenti a lista bianca, nessun accesso libero ai dati):
   - *Parser del brief*: prompt -> JSON validato; se un campo e' ambiguo chiede, non indovina.
   - *Spiegatore*: racconta il risultato con i soli numeri restituiti, citando fonte e tag; frase di limiti obbligatoria.
   - *Critico*: se la nuvola e' vuota o troppo piccola, propone quali vincoli rilassare e di quanto; la proposta e' un nuovo brief che l'utente conferma
     e il core riverifica (l'agente non dice mai "funzionera'").
   Provider: quello gia' configurato; senza provider un parser a regole copre i prompt semplici e dichiara cio' che non capisce.

## 5. API e interfaccia
- `POST /api/raven/discover` (brief) -> `202 {job_id}`; `GET /api/raven/discover/{job_id}` (stato, avanzamento, risultato parziale e finale).
  Cache per hash del brief e delle versioni; limiti di richieste e di tempo come le altre rotte RAVEN; un solo lavoro per volta per utente.
- Pagina o scheda "Trova siti" (vicino a Siti e al Mission Planner): a sinistra prompt e modulo, a destra Luna 3D con il livello di idoneita' e la lista;
  "Usa come A/B" porta due siti nel planner; "Confronta" apre il confronto N siti (anche la dashboard lo mostra).
- Report: sezione con il brief, il metodo (predittore, budget, seme), le incertezze e i limiti.

## 6. Validazione e onesta' dei numeri
- Il predittore si valuta su valutazioni del core **tenute fuori** (errore e copertura degli intervalli: l'intervallo al 90 % deve contenere il vero ~90 %).
  Se la copertura e' sotto soglia il risultato lo dice e allarga gli intervalli.
- Sensibilita' ai priori di tag I: ogni risultato mostra quanto cambia l'ordine se un parametro va ai suoi estremi.
- Limiti dichiarati: sovramappe regionali (celle da 15 km, luce dei terreni scabri sovrastimata), terreno a 237 m fuori dal 20 m, radio non validata da misure,
  nessuna validazione contro prodotti di illuminazione NASA. Nessuna affermazione di "sito migliore": solo "classificato cosi' sotto queste ipotesi".

## 7. Fasi di lavoro (ognuna testabile da sola)
1. **Brief e N-siti**: schema `MissionBrief`, parser a regole, confronto di N siti nel Compare e nella dashboard (senza ricerca automatica).
2. **Candidati e caratteristiche**: estrazione delle caratteristiche per cella dalle sovramappe, filtri duri e cluster; livello "idoneita'" provvisorio (solo caratteristiche, tag I).
3. **Surrogato e campionamento attivo** sul core, con la suite di validazione (dati sintetici con verita' nota, poi core reale).
4. **Probabilita' e propagazione dei parametri**; ordinamento lessicografico e fronte di Pareto.
5. **API a lavori + interfaccia** "Trova siti" + sezione del report.
6. **Agenti LLM** (parser, spiegatore, critico) con prompt di riferimento e verifica che non compaiano numeri fuori dal risultato.

## 8. Decisioni che servono da te
1. **Che cos'e' la "nuvola"**: un livello continuo di probabilita' per cella, un insieme di K siti discreti, o entrambi (proposta: entrambi).
2. **Budget di calcolo**: quanto aspettare (proposta: 60-120 s in un lavoro asincrono con avanzamento) e quante valutazioni del core (da misurare: il costo di una valutazione oggi non e' noto qui).
3. **Risoluzione dei candidati**: griglia globale da 15 km ovunque, con raffinamento a 2 km solo vicino al polo sud?
4. **LLM**: puo' essere il provider gia' configurato (anche senza rete: parser a regole) o vuoi un requisito minimo (modello locale)?
5. **Cosa vale come obiettivo**: oltre a Sole, Terra e radio, quali variabili entrano per forza (pendenza massima? distanza dal polo? vicinanza a un sito di riferimento)?
6. **Planner a N scenari**: fa parte di questo lavoro (fase 1) o resta A contro B con N solo nel confronto?

## 9. Rischi
- Il costo di una valutazione del core potrebbe rendere il budget troppo stretto: da misurare prima della fase 3.
- Un predittore addestrato su poche valutazioni puo' sembrare sicuro e sbagliare: per questo la copertura degli intervalli e' un test bloccante.
- Un agente che "consiglia" puo' essere letto come una garanzia: lo spiegatore ha una frase di limiti fissa e non puo' usare numeri fuori dal risultato.
