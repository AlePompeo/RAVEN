# Completamento dei campi "non forniti" del report: engine, IA, dati del titolare

Analisi del 10 nov 2026 (dal codice; il PDF reale e gli e2e non sono stati riletti: "non verificato"). Decisione dell'utente in
`docs/process/BACKLOG.md` ("Decisione del 10 nov"): l'engine fa le stime dei dati non certi ma stimabili; l'assistente IA fa
solo testo e contenuti più incerti; i dati che ha solo il titolare restano "da completare".

## 1. Che cosa fa davvero l'IA (RAVEN SI) nel report
- Chiama solo `POST /api/raven/report/narrative` e produce 7 paragrafi (chiavi 0, A..F, massimo 1600 caratteri), marcati
  `unreviewed_si_proposal` e salvati a parte come `si_proposal`.
- Non compila nessuno dei 35 campi di fase, né costi, CO2e o affidabilità. Il prompt vieta di inventare numeri; il backend
  controlla forma e lunghezza, **non** l'assenza di numeri (`guard.py` non letto: non verificato).
- Il presupposto "il bot completa i parametri" è falso nel codice. La SI serve a ritoccare il testo. Il resto è lavoro
  deterministico che oggi manca oppure richiede dati del titolare.

## 2. Classi
A = già calcolabile dall'engine con risultati esistenti (da rendere automatico). B = stimabile con un modello parametrico da
pochi ingressi dichiarati. C = servono dati che ha solo il titolare. D = solo testo (IA utile).

| Classe | Fasi | Economia | Legale | CO2e | ESG | Affidabilità | Totale |
|---|---|---|---|---|---|---|---|
| A | 9 | 0 | 0 | 0 | 0 | 0 | **9** |
| B | 4 | 11 | 0 | 7 | 1 | 10 | **33** |
| C | 20 | 6 | 7 | 2 | 7 | 14 | **56** |
| D | 2 | 0 | 0 | 0 | 0 | 0 | **2** |
(100 slot: 35 campi di fase, 17 economia, 7 legale, 9 CO2e, 8 ESG, 24 affidabilità, contati una volta per tipo.)

- **A (9):** high_level_requirements, technical_feasibility, risk_register, schedule, space_and_ground_segments,
  hardware_selection, drawings_and_software_baselines, operations_and_ground_services, contingencies. Sette sono già
  popolati da `reportCompletion.ts` quando ci sono valutazioni (non high_level_requirements né contingencies).
- **B fasi:** economic_feasibility; mass_and_power_budgets (la potenza c'è già, manca la massa); orbit_or_landing (solo ordine
  di grandezza dei Delta-v, decisione utente); environmental_footprint.
- **B economia:** le prime 8 voci di costo con relazioni di stima pubbliche (NASA SSCM, Aerospace USCM); contingency_percent,
  incertezza per voce, cash flow.
- **B CO2e:** 7 fasi con fattori DESNZ (persone-mese; massa per materiale per la fase D). Per la fase E (lancio) non è
  verificato che esista una fonte aperta adeguata: resta ignota.
- **B ESG:** solo il pilastro E, tramite l'indicatore CO2e.
- **B affidabilità:** probabilità di lancio, trasferimento e atterraggio da statistiche pubbliche, cruise_hours, thermal_load_w
  (derivato dai carichi, senza doppio conteggio), failure_rate (MIL-HDBK-217F), degradation_rate, dose_rate.
- **D (2):** verification_plan e ait_plan, oggi bozze da modello.
- **C (56):** obiettivi, stakeholder, architettura, interfacce, progetto dettagliato, prove, lancio, commissioning, smaltimento,
  protezione planetaria, assicurazione, finanziamenti, valuta, anno base, metodo, imposte, tutto il legale, ESG S e G con i
  metadati, perimetro e metodo della CO2e, 12 tipi di campo di affidabilità da datasheet (più protezione e base).

## 3. Regole di onestà per le stime dell'engine
Forma separata "Stima RAVEN": id del metodo, fonte, tag D/I, intervallo min-tipico-max, ingressi usati, limiti di validità,
data della fonte. Mai sovrascrive un valore dell'utente (si affianca e si usa con azione esplicita). Esclusa dai totali finché
non è accettata. Mai presentata come preventivo, LCA, progetto o previsione. Se manca un ingresso obbligatorio non si produce;
fuori dal campo di validità nessuna stima.

## 4. Piano a passi (ordine per valore/costo; ogni passo con test e criterio)
1. Registro dei rischi e contingenze generati dai risultati dell'engine (RF ignota, terreno lontano `outside_model`, copertura
   batteria, stati survival/dark/unknown, stadi non validati). S. Criterio: ogni voce cita il campo del risultato.
2. Requisiti e matrice di verifica deterministici da `objectives` e metriche, al posto della bozza SI. S. Criterio: ogni riga
   cita metrica e soglia.
3. Calendario operativo dalla finestra valutata; le date di sviluppo restano dichiarate dall'utente. S. Criterio: nessuna data
   inventata.
4. Bilancio di potenza e massa dalla configurazione energia/RF con densità dichiarate (tag I). M. Criterio: senza densità il
   valore resta ignoto.
5. Banda di costo parametrica con relazione pubblica (SSCM), in forma separata e accettabile voce per voce. L. Criterio:
   i totali restano invariati finché la stima non è accettata.
6. Poi: CO2e a bande, affidabilità per classe con fonti, ridondanza (parallelo e k-su-n con n e k dichiarati), cassa e inflazione.

## 5. Decisioni richieste all'utente (con default raccomandato)
1. Quali relazioni di stima e prezzi di lancio ammettere. Default: nessuna banda di costo finché l'utente non dichiara massa o
   classe del veicolo; poi SSCM con l'avviso che è calibrato su satelliti, non su lander lunari.
2. Statistiche storiche di lancio e atterraggio. Default: sì, come intervalli con fonte citata (tag D), al posto dei valori
   illustrativi attuali; senza fonte restano illustrativi.
3. Default di densità e margini. Default: valori dichiarati, tag I, sempre modificabili.
4. Fase E della CO2e (lancio). Default: resta ignota finché non c'è una fonte aperta adeguata.
5. Bozza SI per verification_plan e ait_plan. Default: ritirarla e generare il piano in modo deterministico dalla matrice
   requisiti (passo 2); la SI resta opzionale solo per la formulazione.
6. Stime accettate nel contesto inviato al cloud. Default: sì solo con l'opt-in già esistente e il contesto pubblico limitato.

## 6. Stato di implementazione (10 nov 2026)
Modello `EngineEstimate` in `frontend/src/pages/planner/estimates/` (types, risks, requirements, calendar, power, index,
render), salvato in `planning.estimates` con il dossier. Non sovrascrive mai un valore utente ed è fuori da totali e
conteggi finché non è accettato.

| Passo | Stato | Dove / note |
|---|---|---|
| 1 Registro rischi e contingenze | fatto | `risks.ts`; gravità per quota di finestra interessata (alta da 25 %), nessuna probabilità; causa = campo e valore; stadi non validati da `/api/raven/validation` |
| 2 Requisiti, matrice, verification_plan, ait_plan | fatto | `requirements.ts`; piani come modelli fissi sulla matrice; la bozza di riserva resta finché la stima non è accettata |
| 3 Calendario operativo | fatto | `calendar.ts`; solo la finestra valutata; date di sviluppo e lancio mai dedotte |
| 4 Potenza e massa | fatto | `power.ts`; potenza solo da numeri esistenti; massa solo con default dichiarati (tag I, modificabili), come intervallo, altrimenti ignota |
| 5 Banda di costo (SSCM) | da fare | richiede massa o classe del veicolo dichiarata |
| 6 CO2e a bande, affidabilità per classe, statistiche di lancio, ridondanza, cassa | da fare | |

Migrazione dei campi A: `risk_register`, `schedule` e `mass_and_power_budgets` hanno una stima corrispondente con gli
stessi numeri; le frasi `engine_result` esistenti restano invariate come riserva finché la stima non è accettata, poi
quella accettata le sostituisce (origine `engine_estimate`). Le altre cinque (technical_feasibility,
space_and_ground_segments, hardware_selection, drawings_and_software_baselines, operations_and_ground_services) ripetono
parametri e risultati senza stimare nulla: non migrate. Decisione 6: le stime non entrano nel contesto SI/cloud
(`estimates` e `massDefaults` esclusi). Non verificato: il PDF del server con il riquadro (l'e2e usa la stampa del browser).

## 6. Stato di implementazione (10 nov 2026)
Modello `EngineEstimate` in `frontend/src/pages/planner/estimates/` (tipi, risks, requirements, calendar, power, index, render), salvato in `planning.estimates` con il dossier; mai sovrascrive un valore utente; fuori da totali e conteggi finche' non accettato.

| Passo | Stato | Dove / note |
|---|---|---|
| 1 Registro rischi e contingenze | fatto | `risks.ts`; regola di gravita' documentata (quota di finestra, alta da 25 
## 7. Modalità Learn ed Expert (10 nov 2026)
Fatto: `reportMode` in `planning` (persistito; predefinito dalla modalità del sito alla prima apertura del Dossier), `learnReportSections()` (sintesi + fasi 0-F, il resto nascosto), `reportMode.ts` (campi essenziali, gruppi facoltativi con contatore, indicatore di completezza con stime accettate contate a parte). Learn: 4 domande (scopo da lista, dichiarazione, criteri di successo, titolare) + soglie lette dal passo Missione (sola lettura, per non invalidare il calcolo); report con paragrafo didattico per fase e conteggio fornito/calcolato/stimato/ignoto. Expert: tutti i 38 campi in gruppi chiusi. Slot vuoto `SCENARIO_SLOT` (`scenarioSlot` in ReportDossier) per il futuro cursore di scenari: nessuna UI. Non fatto: scelte al posto del testo libero per giurisdizione/autorità/piani (nessun elenco senza fonte), cursore di scenari.

## 8. Stime automatiche e cursore di classe (12 nov 2026)
Il report mostra le stime senza passo di accettazione (le non scartate sono incluse; il valore dell'utente prevale sempre). Codice: `frontend/src/pages/planner/estimates/missionClass.ts` (dati e fonti), `totals.ts` (totali su due righe), `MissionClassSlider.svelte`. Rischi: `estimates/risks.ts` (al massimo 5 righe unite fra A e B). Senza fonte letta non si produce nulla: CO2e di produzione, affidabilita' per componente, probabilita' di trasferimento, costo di rover. Elenco unico nel report: "Owner only, or no public source". Dettagli e limiti in `docs/process/BACKLOG.md` (stato del 12 nov).
