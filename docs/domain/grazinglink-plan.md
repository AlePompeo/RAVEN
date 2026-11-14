# GrazingLink: piano di integrazione (branch `hackathon/nasa-lunar`)

Fonte: cartella `research papers, scripts and planning/` (bozza `BozzaDescrizioneProgettoNASA.md`, script
`antenna_directivity.py`, `compensation_demo.py`, `onda_3d_bozza.py`, bibliografia `Bibliografia_GrazingLink.xlsx`,
JPL IPN PR 42-226 `42-226D.pdf`, handbook Crane & Blood `ManualeEquazioniRiferimentoNASA.pdf`).

Decisione dell'utente: questa ricerca diventa il nucleo scientifico del ramo lunare. Le schede già fatte (Confronto
siti, Contatti, visualizzatore con data e ora, API `/api/lunar`, `/api/sky`) restano. Il modello energetico e il
link budget "illustrativo" precedente non si estendono: i nuovi calcoli seguono la ricerca.

## Identità del sito (decisione successiva dell'utente)
Sul ramo `hackathon/nasa-lunar` il sito NON è più "una base con pagine lunari": **è GrazingLink**, e la ricerca è il suo
contenuto. Conseguenze, da realizzare nella fase 4/6:
- Home (hero cinematografico già esistente) racconta il problema GrazingLink: Terra a 0,5°–1,5° dall'orizzonte al polo
  Sud, perché la geometria binaria non basta, cosa aggiunge la fisica d'onda; i pulsanti principali portano a GrazingLink,
  Onda 3D, Scena lander. Titolo, descrizione, nome nella barra e nel piè di pagina: "GrazingLink".
- Navigazione: GrazingLink (analisi del link) prima, poi Onda 3D, Scena lander, Visualizzatore (Luna/Terra/Sole/Marte con
  data e ora), Confronto siti, Telemetria, Assistente, Contatti. Nulla di quanto già fatto si elimina.
- Confronto siti e il visualizzatore restano, ma usano il margine di link GrazingLink (diffrazione, multipath, antenna) al
  posto del solo link in spazio libero; il vecchio modello energetico/link "illustrativo" resta dichiarato tale e non è più
  il centro del sito.
- L'assistente (Learning Assistant) si basa sui documenti `grazinglink-*.md`: formule, metodo, limiti, soluzione.
- README, `docs/`, pagina Privacy/Licenze: citano le fonti della ricerca (JPL 42-226, Crane & Blood, ITU-R P.526 come
  riferimento non verificato). Il ramo `template-base` resta generico: l'identità GrazingLink vive solo sul ramo lunar.

## Ruolo del visualizzatore 3D su questo ramo (decisione dell'utente)
Il visualizzatore resta con **Luna e Terra** (Sole e Marte escono dal selettore dei corpi su questo ramo; il ramo
`template-base` li conserva; il Sole resta come sorgente di luce reale). Entrambi i corpi hanno un ruolo GrazingLink:
- **Luna (lato sito):** siti analizzabili (coperti da DEM LOLA, lat <= -85) selezionabili; direzione della Terra dal sito con
  elevazione e azimut reali (parallasse e librazione), linea sito-Terra con l'angolo scritto ("Terra a 0,9° sull'orizzonte");
  marker colorati per stato del link (aperto / transizione / bloccato / fuori copertura DEM), sempre con testo oltre al colore,
  stato calcolato con una sola richiesta in cache; scorrere data e ora muove la Terra e la librazione; pulsante "Apri scena
  lander" verso `/lander`; link "Analisi completa" verso `/grazinglink` con sito e istante preselezionati.
- **Terra (lato stazione):** stazioni DSN usate nei calcoli (34 m e 18 m: Goldstone, Madrid, Canberra, coordinate da
  `docs/domain` con la fonte) evidenziate; quale stazione vede la Luna all'istante scelto; distanza Terra-Luna del momento
  e la sua variazione sulla perdita in spazio libero (circa -0,49/+0,46 dB rispetto ai 384.400 km fissi); linea stazione-Luna.
- Contesto in pagina: un pannello "Perché GrazingLink" breve (Terra radente al polo Sud, perché la diffrazione conta) e
  sempre l'avviso dei limiti (copertura DEM, ostacolo singolo, parametri radio illustrativi).
- Limiti onesti: la fisica d'onda sta in `/wave`, `/lander`, `/grazinglink`; il globo dà solo il contesto geometrico.

## Integrazione delle altre pagine con GrazingLink (decisione dell'utente)
Principio: nessuna pagina del ramo lunar resta "a parte". Tutte leggono e scrivono lo stesso **scenario condiviso**
(sito, istante UTC, stazione di terra, antenna, bit-rate, k), tenuto in un piccolo store del frontend e riportato
nell'URL (`?site=&t=&station=...`), così un link tra pagine porta lo stesso caso. Nessuna riga o banda di rimando in testa alle pagine
(l'utente l'ha rifiutata): i collegamenti stanno nei pulsanti pertinenti (es. "Analisi completa" nel dettaglio del sito).
- **Confronto siti:** il ranking usa i risultati GrazingLink (ore di finestra geometrica contro ore reali con diffrazione,
  ore in zona di transizione, margine minimo e mediano, bit-rate sostenibile, interruzioni del compensatore) per i siti
  coperti dal DEM; gli altri siti restano nella tabella marcati "non confrontabile con GrazingLink (fuori copertura DEM)",
  mai riempiti con numeri inventati. Le colonne del vecchio modello energetico restano solo come blocco secondario
  etichettato "ipotesi illustrative", fuori dal punteggio principale. Esporta anche i parametri e i flag del terreno.
- **Telemetria:** diventa "Telemetria del link": accetta un CSV (istante, margine misurato o simulato, elevazione,
  bit-rate) e lo sovrappone alla previsione GrazingLink dello stesso sito e periodo, con residuo, eventi di interruzione
  e statistiche (RMSE, bias, copertura k·sigma). I dati dimostrativi sono generati dal modello più rumore e portano la
  scritta "simulati dal modello, non misure"; quando arriveranno dati veri (ad esempio SCaN o la sfida del 28 ottobre) si
  caricano nello stesso modo e servono a validare la previsione.
- **Simulazioni (`/sims`, plugin esistenti):** nuovo plugin di tipo simulation `grazinglink-link` (protocollo `exec:` /
  registry come gli altri) che espone il motore: margine di link per elevazione e raggio del crinale. Il plugin C `fspl-c`
  è usato come controllo incrociato del termine di spazio libero (confronto Python/C mostrato e testato). `servo-ctrl-c`
  diventa il gimbal dell'antenna: segue azimut ed elevazione della Terra con la librazione reale, l'errore di puntamento
  alimenta la perdita di puntamento (rapporto errore/HPBW) nel margine. Gli altri plugin restano com'erano.
- **Assistente:** documenti `grazinglink-*.md` (metodo, formule, limiti, soluzione hackathon); il pulsante "Spiega" di ogni
  pagina passa all'assistente lo scenario corrente e un riassunto dei risultati visibili (numeri veri della pagina), con
  citazioni; le risposte non ripetono mai numeri non presenti nelle fonti o nel riassunto.
- **Visualizzatore, Onda 3D, Scena lander:** leggono lo scenario condiviso (vedi sezioni sopra).
- **Contatti e pagine legali:** invariati, tranne i riferimenti alle fonti della ricerca (Licenze).

Ordine di realizzazione: (1) chiusura `/wave`; (2) store dello scenario condiviso + visualizzatore Luna e Terra;
(3) scena `/lander`; (4) Confronto siti; (5) Telemetria del link; (6) plugin e Simulazioni; (7) assistente e "Spiega";
(8) revisione, e2e completo, CI, allineamento del branch base dove generico, pubblicazione.

## Regole di onestà (valgono per ogni agente)
1. Ogni parametro porta l'etichetta V (da fonte, con citazione e pagina), D (derivato, con formula) o I (ipotesi
   illustrativa). Gli script della ricerca dichiarano loro stessi "ipotesi illustrative" per i parametri radio: restano I
   finché una fonte non li conferma.
2. Nessun dato inventato presentato come reale. Il terreno deve venire da LOLA (PDS) o da un file fornito
   dall'utente. Un profilo sintetico è ammesso solo per i test e in UI porta la scritta "profilo sintetico di prova".
3. Limiti dichiarati dalla bozza (§7) restano visibili in UI: ostacolo singolo dominante, nessuna misura radio reale al
   polo Sud, regolite da stime di letteratura.
4. Le formule si controllano contro la fonte (ITU-R P.526, JPL 42-226, Crane & Blood), con i numeri di pagina e di
   equazione nel documento del modello. Dove non si riesce a verificare, lo si scrive.
5. Il nucleo (`backend/core`) non importa altri livelli (import-linter). Codice nuovo in `backend/domain/grazing/`.

## Moduli (dalla bozza §3) e dove vivono
| Modulo | Cosa fa | Riuso dell'infrastruttura esistente |
|---|---|---|
| A. Geometria | elevazione e azimut della Terra dal sito con librazione reale | `backend/ephemeris` (Skyfield+NAIF), non la sinusoide giocattolo dello script |
| A. Terreno | profilo altimetrico LOLA lungo l'azimut della Terra | cache tipo kernel (`build/`, sha256), non nel repository |
| B. Diffrazione | bordo a lama esatto (Fresnel), approssimazione ITU-R P.526, cresta arrotondata, zona di Fresnel | nuovo |
| B. Multi-fidelity | tabella di correzione R(nu, raggio) da split-step di Fresnel, completata con processo gaussiano, punti anomali | extra `[ml]` (scikit-learn) per generare; a runtime solo interpolazione della tabella versionata |
| C. Multipath | modello a due raggi sul regolite (eps, sigma) | nuovo; JPL 42-226 come riferimento per il termine coerente |
| D. Compensatore | rate massimo con margine previsto >= k*sigma, tradeoff interruzioni/dati | nuovo |
| E. Antenna | guadagno, HPBW, diametro, perdita di puntamento, necessità del gimbal | nuovo, parametri V/D/I |
| Link | sommatoria del margine con tutti i termini | `backend/domain/lunar/link.py` come base, estesa |
| API | `/api/grazing/*` | stesso schema di `lunar_routes.py` (cache, tetto di concorrenza, 422 generico, 503 senza dati) |
| UI | pagina GrazingLink con grafici nel tempo, doppia barra finestra geometrica vs reale, tabella di compensazione, antenna | design system, uPlot, SkyTime, pagina Confronto siti come modello |
| 3D | scena lander: terreno, crinale, tubo di Fresnel verde/rosso, modello di rover e antenna con cono HPBW, Terra con librazione, superficie d'onda 3D | `ViewportPort` (WebGL) e fallback Canvas 2D |
| Pagina "Onda 3D" (`/wave`, richiesta dell'utente) | grafico 3D interattivo della diffrazione: intensità |E|² di un'onda piana in banda X dopo una cresta (bordo a lama o arrotondata, raggio R), propagata con split-step di Fresnel (FFT) come in `onda_3d_bozza.py`. Controlli: frequenza o lunghezza d'onda, raggio della cresta, distanza, altezza sulla linea di vista; superficie 3D ruotabile, sezione 2D (profilo di intensità a distanza fissa) con la curva del bordo a lama esatto sovrapposta, animazione lungo la distanza. | motore di calcolo in `backend/domain/grazing/wave.py` (NumPy, griglia limitata e cache), API `/api/grazing/wave`, vista 3D con `ViewportPort` (WebGL) e ripiego Canvas 2D, stessa pagina e stesso design system, tastiera e touch |
| Assistente | documenti `docs/knowledge/grazinglink-*.md` | loader e test di knowledge esistenti |

## Fasi (una per volta nel worktree, commit a ogni passo)
1. Modello scritto e verificato: `docs/domain/grazinglink-model.md` (equazioni con fonte, parametri V/D/I, cosa si implementa e cosa no).
2. Motore: geometria con effemeridi, DEM LOLA, diffrazione, multipath. Test contro valori noti.
3. Tabella di compensazione + compensatore + antenna + API.
4. Pagina GrazingLink con grafici.
5. Scena 3D (Fresnel, antenna, rover, onda) con fallback.
6. Documenti per l'assistente, e2e, CI, revisione, allineamento del branch base dove generico.
