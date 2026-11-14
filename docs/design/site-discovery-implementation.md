# Ricerca automatica dei siti: implementazione economica e licenze

Completa `site-discovery-plan.md`. Data: 12 nov 2026. Obiettivo: lavoro veloce, poco costoso (in token e in calcolo), ottimizzato.
Non e' una consulenza legale: fanno fede i testi delle licenze.

## 1. Licenze: la regola da sapere prima
**Con MIT, BSD e Apache-2.0 non si puo' omettere l'attribuzione.** Obbligano a conservare l'avviso di copyright e il testo della licenza nelle
copie ridistribuite (Apache-2.0 anche il file NOTICE e l'indicazione delle modifiche; BSD-3 anche il divieto di usare il nome dell'autore per
promuovere il prodotto). Non obbligano a metterli nel README, nel codice o nelle pagine di marketing: basta un file di avvisi
(`THIRD_PARTY_NOTICES`) distribuito col progetto e la pagina `/licenses` che gia' esiste. E' il modo normale e conforme di non "esporre" gli autori.
**Senza alcun obbligo di attribuzione** sono solo le licenze equivalenti al pubblico dominio: 0BSD, Unlicense, CC0 (e MIT-0). Dati NASA (LOLA,
SVS, kernel JPL) sono pubblico dominio ma i crediti del progetto restano per correttezza scientifica.
Da evitare: Llama (licenza propria: "Built with Llama", nome del modello, limite a 700 M utenti), Gemma (termini propri), qualunque GPL/AGPL
(contagio del codice del progetto), modelli "research only". Verificare **sempre** la scheda del singolo modello prima di includerlo (una ricerca
ha dato risposte contrastanti per Qwen2.5 da 3B: non lo usiamo).

## 2. Cosa c'e' gia' nel progetto (nessuna nuova dipendenza)
| Serve | Gia' disponibile | Licenza | Nota |
|---|---|---|---|
| Processo gaussiano, alberi con quantili, clustering | `scikit-learn==1.9.1` (extra `ml`) | BSD-3 | `GaussianProcessRegressor`, `GradientBoostingRegressor(loss="quantile")`, `DBSCAN`/`KMeans` |
| Campionamento Sobol, statistica | `scipy==1.18.1` (extra `ml`/`sky`) | BSD-3 | `scipy.stats.qmc` per la propagazione dei parametri di tag I |
| Schema e validazione del brief | `pydantic>=2` | MIT | gia' usato da tutte le rotte |
| Lavori asincroni, cache, limiti | `RavenService` in `raven_routes.py` | del progetto | niente Celery |
| Provider LLM | assistente RAVEN SI (estrattivo, Groq, compatibile OpenAI) | del progetto | l'utente puo' puntarlo a un server locale |
| Heatmap, legenda, pannello | `OverlayController`, `OverlayPanel`, shader della Luna 3D | del progetto | livello "idoneita'" = un layer in piu' |
| Elenco, componenti, ordine | `ranking.py`, Compare, `RangeChart`, `ReportEstimates` | del progetto | gia' N siti nel Compare |
| SBOM e licenze | `cyclonedx-bom`, `pip-licenses` (extra `dev`) | Apache-2.0 / MIT | generano `THIRD_PARTY_NOTICES` |

Scelta consigliata: **niente librerie nuove** per il predittore. Intervalli con conformal prediction "split" scritta a mano (circa 15 righe),
acquisizione (UCB o miglioramento atteso) scritta a mano (circa 40 righe) sul processo gaussiano di scikit-learn. Si evitano MAPIE, scikit-optimize,
BoTorch (richiede torch, enorme) e Optuna (non da' l'incertezza sulla nuvola).

## 3. Pezzi esterni opzionali con licenza permissiva (da verificare alla scheda)
| Pezzo | Licenza | Uso | Quando |
|---|---|---|---|
| llama.cpp (runtime locale, grammatiche GBNF per JSON valido) | MIT | parser del brief senza rete | solo se si vuole un LLM locale incluso |
| Phi-4-mini (3,8 B) | MIT (confermata da una ricerca) | modello locale per il parser | opzionale, scaricato su richiesta, non all'installazione |
| ~~Qwen3~~ | escluso: provenienza (Alibaba) | - | - |
| SmolLM2 1,7 B | Apache-2.0 (confermata per la taglia 1,7 B) | il piu' leggero | opzionale |
| gpt-oss 20B/120B | Apache-2.0 | troppo grande per un PC comune | solo server dedicato |
| SALib (analisi di sensibilita' Sobol) | MIT | alternativa a `scipy.stats.qmc` | non serve |
Un modello locale pesa da circa 1 a 3 GB: **non** entra nell'installazione obbligatoria (rallenterebbe quanto appena ottimizzato). Resta un passo
opzionale; di base funzionano il parser a regole e il provider gia' configurato.

## 4. Piano di implementazione a costo minimo
Regole di lavoro per risparmiare token (valgono per ogni fase): lavoro in chat senza agenti; leggere solo gli intervalli di righe che servono
(`grep` e `sed -n`); un file di script per modifica; riuso dei modelli di codice esistenti; un commit per fase; si eseguono solo i test toccati e
un giro completo alla fine; nessun polling.

**Fase 0 - misura (mezza giornata, poco codice).** Script che misura il costo di `evaluate` per un sito, su 20 siti, con e senza maschere in cache.
Da questo numero si fissa il budget (quante valutazioni in 60-120 s). Senza il numero il resto e' una scommessa. Output: una riga nel piano.
**Fase 1 - brief e N siti.** `MissionBrief` (pydantic), parser a regole (parole chiave in IT/EN per date, percentuali, bit rate, massa, K), modulo
nell'interfaccia. Il Compare accetta gia' N siti: si collega il brief. Test: parser a tabella, schema.
**Fase 2 - caratteristiche per cella.** Si leggono gli asset gia' spediti (`global-*.json`, quelli polari) con numpy; matrice (cella, caratteristiche);
filtri duri; cluster `DBSCAN`. Si precalcola e si spedisce (come `terrain_plans.json`) per non ricalcolare a ogni richiesta.
**Fase 3 - predittore.** `GaussianProcessRegressor` (kernel Matern, ARD) sulle valutazioni reali, campione iniziale di Sobol, acquisizione UCB, conformal
sui residui tenuti fuori. Test: funzione sintetica con verita' nota (copertura degli intervalli vicina al 90 %), determinismo con seme.
**Fase 4 - probabilita'.** `scipy.stats.qmc.Sobol` sugli intervalli di tag I; il core valuta un sottoinsieme; P(obiettivi) con intervallo e quota di
incertezza per fonte. Cache per hash di (sito, finestra, parametri, versione).
**Fase 5 - API e interfaccia.** `POST /api/raven/discover` + stato; layer "suitability" nel pannello delle sovramappe; lista con "Usa come A/B";
blocco nel report con lo stesso `RangeChart`. e2e: un brief, risultato, tratteggio dell'ignoto, assenza di numeri fuori dal risultato.
**Fase 6 - agenti LLM.** Parser, spiegatore, critico: prompt brevi (schema + 3 esempi), uscita JSON validata da pydantic, spiegatore che riceve solo il
JSON compatto dei primi K siti. Cache per hash del brief. Test con prompt di riferimento e controllo che ogni numero citato esista nel risultato.

## 5. Dove si risparmia davvero
- **Calcolo:** il core gira su poche decine di siti (non su migliaia), la nuvola e' del predittore; asset precalcolati; cache per hash.
- **Token dell'utente (LLM):** parser a regole per i prompt semplici (zero token), prompt da poche righe, niente catene di ragionamento, l'LLM non rilegge
  mai le sovramappe ne' i grafici: vede un JSON da pochi KB.
- **Token di sviluppo:** nessuna nuova libreria da imparare, modelli di codice gia' nel repo, fasi piccole con test prima del resto.
- **Licenze:** zero codice di terzi copiato; solo dipendenze gia' presenti, quindi nessun nuovo avviso da gestire; avvisi generati da `pip-licenses` e dall'SBOM.

## 6. IA online via API: conviene? (verificato il 12 nov 2026)
**Si', come secondo livello, non come unico.** Il progetto la supporta gia': `backend/assistant/cloud.py` (Groq, chiave `GROQ_API_KEY` letta dall'ambiente del server),
`discovery.py` (qualunque endpoint compatibile OpenAI, chiave `ASSISTANT_LLM_API_KEY`) e un filtro a lista bianca dei campi numerici inviati
(`report_technical_profile`). Quindi non serve nuovo codice di integrazione, solo i tre compiti (parser, spiegatore, critico).
- **Ordine di chiamata:** 1) parser a regole (zero token, offline); 2) se il prompt non e' coperto, il provider configurato; 3) se non c'e' rete o chiave,
  il sistema risponde "serve il modulo" senza inventare. Il core e il predittore non usano mai l'LLM.
- **Costo:** una ricerca usa circa 3.000 token (parser circa 600, spiegatore circa 2.000 con il JSON dei primi K siti). Con gpt-oss-20b su Groq i prezzi
  riportati da fonti secondarie sono 0,075 USD per milione di token in ingresso e 0,30 in uscita: meno di un millesimo di dollaro a ricerca. Il piano
  gratuito riportato e' 200.000 token al giorno e 8.000 al minuto (circa 60 ricerche al giorno): sufficiente per demo e giuria. **I limiti variano per fonte e
  data: confermarli sulla pagina ufficiale di Groq prima di contarci.**
- **Cosa non e' verificato:** se gpt-oss-20b su Groq supporti l'uscita con schema JSON vincolato. Si assume di no: si valida con pydantic e si ripete una volta.
- **Privacy e consenso:** il prompt dell'utente e il JSON dei risultati escono dal computer. Serve un consenso esplicito e visibile ("questa funzione invia il testo
  a un servizio esterno"), come per il resto di RAVEN SI; niente coordinate di siti personalizzati, niente chiavi nel repository, la chiave resta nell'ambiente del server.
- **Affidabilita':** un servizio puo' cambiare modello, prezzi o limiti: il modello e' un parametro (`MODEL_RE` gia' valida l'identificatore), la risposta e' sempre
  validata e controllata (ogni numero citato deve stare nel risultato), e il funzionamento di base non dipende da lui.
- **Quando preferire un modello locale:** demo senza rete o dati che non devono uscire; vedi la tabella al punto 3 (passo opzionale).

## 7. Decisioni prese dall'utente (12 nov 2026) e IA locale
1. **Nessuna nuova dipendenza** per il predittore: confermato.
2. **Selezione automatica dell'IA:** se e' configurata un'IA online (chiave API nell'ambiente del server) si usa quella; altrimenti il sistema passa da solo a un LLM
   locale **piccolo**, scelto per RAM e CPU minime, abbastanza affidabile e veloce; se l'LLM locale basta, il sistema puo' funzionare solo con quello.
   Ordine: parser a regole -> IA online configurata -> LLM locale -> modulo senza LLM.
3. **Il LLM locale fa un solo lavoro: il parser del brief.** Spiegazione dei risultati e proposte di rilassamento sono deterministiche (modelli di testo e
   ricalcolo del core a soglie rilassate): zero RAM, zero allucinazioni, zero token. Cosi' "solo locale" e' realistico.
4. **Vincolo di provenienza (12 nov 2026): solo soluzioni occidentali.** Esclusi modelli, codice e servizi di organizzazioni affiliate a Cina o Russia (Qwen/Alibaba,
   DeepSeek, GLM/Zhipu, Kimi/Moonshot, Yi, InternLM, Baichuan, MiniMax, GigaChat/Sber, YandexGPT e simili). Vale anche per l'IA online: il nome del modello configurato
   viene confrontato con un elenco di esclusione e rifiutato (un servizio occidentale puo' ospitare modelli cinesi). Vale anche per i modelli suggeriti da altri.
   Esclusi per licenza e non per provenienza: Llama (obbligo di "Built with Llama"), Gemma (termini propri), Ministral (licenza di ricerca).
5. **Candidato locale:** **IBM Granite 4.0 Nano** (IBM, USA): Apache-2.0 e italiano nell'elenco delle lingue (da una ricerca sulle schede dei modelli; da
   riconfermare sulla scheda ufficiale), versioni da 350 M e 1 B di parametri, supportate da llama.cpp (MIT), con grammatica GBNF **piatta** (la grammatica
   garantisce la sintassi, non il significato). Si prova prima il 350 M e si sale a 1 B solo se non supera i criteri. Dimensione dei file GGUF e velocita' su CPU:
   **non trovate, da misurare**. Riserve occidentali: Phi-4-mini 3,8 B (Microsoft, MIT da una ricerca; italiano non confermato; piu' pesante) e SmolLM3 3 B
   (Hugging Face; licenza e lingue non confermate: leggere la scheda).
6. **Criteri di accettazione** (da misurare su 50 prompt di riferimento in italiano e inglese, prima di dichiarare il locale sufficiente): accuratezza per campo almeno 95 %;
   latenza p95 al massimo 10 s su 4 core senza GPU; memoria residente al massimo 2 GB; nessun campo inventato (un campo non capito resta vuoto). Il brief
   resta confermato dall'utente: e' la rete di sicurezza contro gli errori del modello piccolo.
7. **Rete di sicurezza per le risorse:** il modello non e' caricato finche' non serve; un controllo della memoria libera (Linux, `/proc/meminfo`) lo impedisce sotto
   una soglia (propongo 3 GB liberi); si scarica dopo 5 minuti di inattivita'; gira in un processo separato, quindi non rallenta l'applicazione.

## 8. Decisioni
1. Conferma di "nessuna nuova dipendenza" per il predittore (consigliato) oppure si accettano librerie permissive aggiuntive.
2. LLM locale incluso come passo opzionale (llama.cpp + un modello MIT/Apache) oppure solo provider esterno gia' configurato.
3. Le 6 decisioni gia' elencate in `site-discovery-plan.md` punto 8.

## 9. Risposte dell'utente alle decisioni (12 nov 2026)
Tutte e sei approvate: nuvola come livello di probabilita' **e** K siti; budget circa 90 s (tetto 180 s) con avanzamento e risultati parziali; griglia globale a 15 km con
raffinamento a 2 km vicino al polo sud; LLM online se configurato altrimenti locale piccolo; variabili del brief come proposte (acqua e ghiaccio non supportati);
planner e report restano A contro B, con N siti nel Compare e nella dashboard.
**Indicazione di metodo:** usare il piu' possibile i dati combinati del RAVEN engine, l'interpretazione delle sovramappe della dashboard e algoritmi progettati nel
modello predittivo, che deve essere affidabile e leggero. L'LLM resta confinato al brief; i numeri vengono dal motore, dalle sovramappe e dal predittore.

## 10. Modello di decisione al posto (o accanto) dell'LLM; ML, deep learning, reinforcement (analisi, non misurata)
**Brief.** Compilare ~10 campi e' soprattutto estrazione di numeri/unita' (regole) e scelta fra poche classi (classificazione). Cascata proposta, si ferma al primo
livello che basta: 1) regole (numeri, date, unita', parole chiave IT/EN); 2) classificatore leggero per i campi a scelta (priorita', regione, classe di missione): per
esempio un encoder di frasi multilingue piccolo con prototipi per classe, o regressione logistica su n-grammi; 3) LLM piccolo (Granite 4.0 Nano 350 M) solo per
cio' che resta; 4) modulo. Ipotesi **da misurare** sui 50 prompt di riferimento: regole piu' classificatore coprono la gran parte dei casi e l'LLM serve di rado.
Licenze dei checkpoint (encoder di frasi, eventuali estrattori di entita'): da leggere uno per uno; alcuni hanno licenze non permissive.
**Predittore.** Il termine corretto e' *surrogato/emulatore* con *apprendimento attivo* (ottimizzazione bayesiana). Tecniche: GP e alberi con quantili (adatti a pochi
dati tabellari, con incertezza, leggeri) = si'; reti profonde = solo se i GP/alberi falliscono il test di calibrazione (su dati tabellari piccoli raramente vincono,
richiedono torch o ONNX e insiemi per l'incertezza); reinforcement learning = no per la ricerca (la scelta della prossima cella e' un problema di bandit/BO con soluzione
a formula e senza addestramento; RL e' piu' costoso, senza garanzie e meno spiegabile).
**Cosa conviene davvero (idee progettate per questo problema):** (a) *fedelta' multiple*: il surrogato = stima fisica dalle sovramappe + correzione appresa dai risultati
del core (servono meno dati e meno parametri); (b) nuovi strati precalcolati dalla stessa griglia di orizzonti: **coincidenza Sole e Terra** (quota del tempo con entrambi
sopra l'orizzonte, il vero proxy delle ore utili: le sovramappe attuali sono marginali) e **durata massima senza Sole** (critica per la batteria) e **senza Terra**;
(c) *pre-addestramento offline* su molte celle valutate dal core una volta sola (modello da pochi KB, in ONNX o puro numpy) piu' correzione online per il brief; (d) vincoli di
monotonia (piu' Sole non puo' dare meno energia); (e) validazione con **blocchi spaziali** (celle vicine non stanno nello stesso gruppo di prova, altrimenti l'errore e' sottostimato).
Parlare di "deep learning" o "reinforcement" senza che aggiungano valore sarebbe etichetta e non sostanza: il testo del progetto dira' "surrogato statistico con apprendimento attivo".
