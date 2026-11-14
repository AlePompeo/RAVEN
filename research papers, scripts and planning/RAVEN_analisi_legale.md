# RAVEN: analisi legale pragmatica

Data: 5 novembre 2026. **Non è un parere legale e io non sono un avvocato.** È un'analisi tecnico-giuridica preliminare, fatta sulla repo che mi hai dato, sui documenti del progetto e su fonti pubbliche (elencate in fondo). Non conosco la vostra giurisdizione né la forma con cui vi organizzerete: dove serve assumo Italia/UE e lo dico. Prima di firmare contratti o di vendere, fatela rivedere a un avvocato che conosca software e spazio.

---

## 1. Il giudizio in breve

**Il progetto è fattibile e la base è sana.** Licenza Apache-2.0 su tutta la repo, dati pubblici (NASA/JPL NAIF, LOLA), nessun tracciamento, assistente locale di default, pagine di privacy e cookie già strutturate, un controllo automatico delle licenze delle dipendenze e il font con il testo della licenza. Non ho trovato nulla che vieti di costruirlo o di venderlo.

**Ma cinque cose possono costarvi caro, in quest'ordine:**

1. **Il modello commerciale si scontra con le regole dell'hackathon.** I termini (versione 2025, da riverificare per il 2026) chiedono che ciò che sottoponete sia libero o open source e non accettano materiale che promuove prodotti o servizi commerciali. La pagina Piani e il business plan nella repo vanno contro questo.
2. **Nella repo c'è una cartella interna che non deve diventare pubblica**: business plan con i prezzi e PDF di terzi.
3. **Il nome RAVEN è affollato**: marchio statunitense attivo in classe 9 di un'azienda aerospaziale e un software con lo stesso nome del laboratorio INL. Nessuna ricerca ufficiale è stata fatta.
4. **La privacy è un modello da completare**: manca il titolare del trattamento, e la pagina Contatti pubblica dati personali.
5. **Quando venderete, la responsabilità è vostra**: per un tool che influenza decisioni su missioni costose servono condizioni d'uso, tetto di responsabilità, assicurazione e un controllo sull'export. In più, la licenza di SPICE vi fa indennizzare Caltech e NASA per pretese di terzi nate dal vostro uso.

**Cosa fare prima del 14 novembre (hackathon):** punti 1, 2 e 4 nella versione minima (sezione 6), disclaimer di non affiliazione NASA e attribuzioni. **Prima del primo cliente:** punti 3 e 5.

---

## 2. Tabella dei rischi

| # | Area | Cosa ho trovato | Livello | Azione principale |
|---|---|---|---|---|
| 1 | Regole hackathon | Soluzioni libere o open source; niente promozione commerciale; originalità; export control a vostro carico | **Alto** | Separare il pacchetto da sottoporre da quello commerciale |
| 2 | Cartella interna | `research papers, scripts and planning/` con business plan, listino, PDF di terzi, vecchio zip del codice | **Alto** | Rimuovere dalla repo pubblica e dalla storia |
| 3 | Nome e marchio | "RAVEN" già usato (marchio US classe 9, software INL) | **Alto** | Ricerca di anteriorità professionale prima di investire nel brand |
| 4 | Pagina Piani | Prezzi e "Purchase not yet available" nella UI | **Medio-Alto** | Nascondere nella build sottoposta |
| 5 | Privacy | "Modello da completare" senza titolare; Contatti con nome, foto, LinkedIn | **Medio** | Titolare, contatti, base giuridica, consensi scritti |
| 6 | Licenze di terzi | `licenses.json` è un elenco vuoto nella copia ricevuta; nessun `NOTICE` | **Medio** | `make licenses`, aggiungere `NOTICE` |
| 7 | Dati e immagini NASA | Uso consentito se fattuale e con fonte; il logo NASA no; nessun patrocinio sottinteso | **Medio** | Disclaimer di non affiliazione, controllo immagine per immagine |
| 8 | SPICE | Uso commerciale gratuito; indennizzo verso Caltech/NASA | **Medio** | Contratti con limitazione di responsabilità |
| 9 | Responsabilità verso i clienti | Risultati usati per decidere su missioni costose | **Medio-Alto** (alla vendita) | Condizioni d'uso, tetto, assicurazione, pilot scritto |
| 10 | Controllo esportazioni | Dati pubblici e codice aperto: rischio probabilmente basso, ma non verificato | **Medio** (incerto) | Classificazione con un consulente prima dei contratti esteri |
| 11 | Contenuti generati con IA | Banner e logo sembrano generati; codice assistito | **Basso-Medio** | Titolarità incerta: ridisegno umano, traccia dell'apporto |
| 12 | Assistente LLM esterno | Opzionale; di default locale | **Basso** | Informativa e accordo col fornitore solo se lo attivate |
| 13 | Accordo tra soci | Copyright "Hackathon Base contributors", nessun accordo visibile | **Medio** | Scrittura su titolarità del codice, quote, nome |
| 14 | Dichiarazioni | "radio validata", "Artemis III" | **Basso-Medio** | Linguaggio da stima di pianificazione |

---

## 3. Dettaglio, area per area

### 3.1 Regole dell'hackathon (rischio alto)
**Trovato.** Nei termini dei partecipanti 2025 (aggiornati a marzo 2025; **i termini 2026 non li ho verificati**): le soluzioni devono essere liberamente disponibili o open source (licenza OSI) e, se non indicate, NASA le distribuisce con Apache-2.0; le soluzioni con materiale che promuove prodotti o servizi commerciali non vengono accettate né pubblicate; i materiali non NASA devono essere pubblici o open source; l'assenza di informazioni soggette a controllo delle esportazioni (ITAR/EAR) è responsabilità vostra; il partecipante garantisce di avere i diritti e manleva gli organizzatori; i video devono essere originali, senza terzi coperti da copyright. Nel modulo di invio 2025 si doveva confermare che tutto il lavoro è originale.
**Perché conta.** Tutto ciò che sottoponete diventa riusabile da chiunque, concorrenti compresi: non è un segreto industriale. E se la sottomissione "fa pubblicità" può essere rifiutata.
**Cosa fare.**
- Strategia open-core: motore e interfaccia restano Apache-2.0; il valore commerciale sta in dati preparati e validati, servizio ospitato, report su misura, supporto, marchio e relazioni.
- Nel pacchetto sottoposto: niente business plan, niente listini, niente "Request a pilot", niente prezzi. Il materiale commerciale vive in un sito e in una repo separati.
- Lavoro preesistente: non ho trovato una regola 2026 in merito. Leggete la guida di sottomissione (annunciata per il 13 novembre) e, finché non lo sapete, elencate cosa è preesistente e con quale licenza. Non scrivete "tutto fatto durante l'evento" se non è vero.

### 3.2 Cartella interna nella repo (rischio alto)
**Trovato.** `research papers, scripts and planning/` contiene il business plan con i prezzi, descrizioni interne, `42-226D.pdf` e `ManualeEquazioniRiferimentoNASA.pdf` (PDF di terzi, di cui non conosco la licenza), la bibliografia, script di prova e una copia del vecchio backend.
**Cosa fare.** Spostatela fuori dalla repo, aggiungetela a `.gitignore` e, se la storia git la contiene, riscrivetela (per esempio con `git filter-repo`) prima di rendere pubblico il codice. Per i PDF di terzi tenete il riferimento bibliografico, non il file, salvo licenza che lo permetta.

### 3.3 Nome RAVEN (rischio alto)
**Trovato.** Directory di marchi di terze parti indicano per Raven Industries una registrazione statunitense "RAVEN" attiva in classe 9 (apparecchi elettronici e informatici), e profili commerciali la collocano nel settore aerospaziale/difesa. Esiste poi un software open source "RAVEN" (Risk Analysis Virtual ENvironment) del laboratorio nazionale INL. **Sono ricerche su siti di terzi, non una ricerca ufficiale**; non ho consultato EUIPO, UIBM né WIPO.
**Perché conta.** Se vendete software per lo spazio con quel nome rischiate contestazioni e un rebranding quando avrete già clienti, domini e materiali.
**Cosa fare.**
- Ricerca di anteriorità professionale in classi 9, 42, 41 e 35 (EUIPO TMview, USPTO, WIPO Global Brand Database) prima di spendere in brand.
- Fino all'esito: non stampate materiali, non registrate domini a pagamento in massa, non investite nel logo.
- Tenete pronto un nome alternativo. L'acronimo "Radio Analysis, Visibility, Energy and Networks" è descrittivo e quindi debole come marchio.

### 3.4 Privacy e dati personali (rischio medio)
**Trovato (nella repo).** La pagina Privacy dice di essere un "modello da completare a cura del titolare del trattamento (nome, contatti, base giuridica) prima della messa in produzione". Il resto è buono: nessun cookie non essenziale né tracciamento, `localStorage` documentato, log con IP troncati, assistente locale di default che non invia dati a terzi, e un avviso prima dell'invio se usate un provider esterno.
**Cosa fare.**
- Indicate il titolare (persona fisica o ente), un contatto, le basi giuridiche, la conservazione e i diritti degli interessati.
- Pagina Contatti: pubblicate nome, foto e LinkedIn di un membro solo con il suo consenso scritto (e con attenzione particolare se è minorenne).
- Se aggiungerete un modulo "Request a pilot" o account, serviranno informativa, base giuridica e tempi di conservazione per le email.
- Se attivate l'assistente con un LLM esterno: informativa, accordo con il fornitore (DPA) e valutazione dei trasferimenti extra-UE. Trattatelo come funzione disattivata finché non serve.
- Evitate script e font da terzi. Il font Orbitron è locale (con licenza OFL), ed è la scelta giusta.

### 3.5 Licenze di terzi e attribuzioni (rischio medio)
**Trovato.** `frontend/public/licenses.json` è un elenco vuoto nella copia ricevuta (la pagina Licenze mostrerebbe nulla); non c'è un file `NOTICE`; `REUSE.toml` attribuisce il copyright a "Hackathon Base contributors".
**Cosa fare.** Eseguite `make licenses` prima di pubblicare; aggiungete un `NOTICE` (Apache-2.0, sezione 4) con le attribuzioni principali (NASA/JPL NAIF SPICE, LOLA/PDS, le librerie incluse); sostituite "Hackathon Base contributors" con i nomi reali o con una dicitura concordata tra i soci.

### 3.6 Dati, immagini e nome NASA (rischio medio)
**Trovato.** Le linee guida NASA permettono di usare i contenuti NASA in modo fattuale, citando la fonte e senza suggerire patrocinio. Insegne, logo e sigillo NASA non sono di pubblico dominio e non si usano; nei materiali promozionali non si usano identificativi NASA né l'espressione "NASA" abbinata a un nome di prodotto. Non tutte le immagini sul sito di NASA sono di NASA. La home già cita crediti per Luna, SVS e Blue Marble: è la pratica giusta.
**Cosa fare.** Aggiungete in vista "RAVEN è un progetto indipendente, non affiliato né approvato da NASA". Controllate la licenza di ogni immagine. "Artemis" e "CLPS" restano riferimenti descrittivi, mai parte del nome o del logo.

### 3.7 SPICE (rischio medio)
**Trovato.** NAIF consente l'uso commerciale di SPICE senza canoni. Il testo della licenza dice che chi lo riceve si assume il rischio e **indennizza Caltech e NASA** per le pretese di terzi derivanti dalle proprie azioni nell'uso del software. SPICE è classificato come tecnologia e software pubblicamente disponibili ai fini dell'export.
**Cosa fare.** Nei vostri contratti con i clienti limitate la responsabilità (sezione 3.8) e valutate un'assicurazione. Non ridistribuite il toolkit modificato; i kernel NAIF si scaricano, non si ridistribuiscono alterati (la repo già li scarica con verifica dello SHA-256: è corretto).

### 3.8 Responsabilità verso i clienti (rischio medio-alto quando venderete)
**Perché conta.** RAVEN stima ore di luce e di collegamento di un sito lunare. Un cliente potrebbe basare una decisione su un numero e poi lamentare un danno. La licenza Apache-2.0 esclude garanzie sul codice, ma non vi protegge da un contratto di servizio o da affermazioni commerciali.
**Cosa fare.**
- Condizioni d'uso e contratto di pilot scritti: oggetto, consegne, esclusioni ("stima di pianificazione, non certificazione di garanzia della missione"), dati usati e loro limiti, tetto di responsabilità (tipicamente legato a quanto pagato in dodici mesi), riservatezza (NDA), titolarità dei risultati e diritto di citare il cliente.
- Se il contratto è sotto diritto italiano: le clausole che limitano la responsabilità o la decadenza, in condizioni generali predisposte da voi, vanno approvate specificamente per iscritto (artt. 1341-1342 c.c.), e non si può escludere la responsabilità per dolo o colpa grave (art. 1229 c.c.). Fatelo verificare.
- Assicurazione di responsabilità professionale e cyber dopo i primi contratti.

### 3.9 Controllo delle esportazioni (rischio medio, incerto)
**Cosa so.** Il codice open source pubblicato e i dati pubblici generalmente non ricadono sotto l'EAR statunitense, ma non è un automatismo (verificate "published" e "publicly available" e l'eccezione per la crittografia). Il software "specificamente progettato" per veicoli spaziali può rientrare nelle categorie ITAR o EAR 9x515. RAVEN usa dati pubblici e analisi generica, quindi il rischio è probabilmente basso, ma **non l'ho verificato**.
**Cosa fare.** Prima di contratti con clienti esteri o di una versione privata con funzioni su misura: classificazione con un consulente, controllo delle liste di sanzioni sui clienti e, nelle condizioni d'uso, il divieto di caricare dati tecnici soggetti a controllo. Per l'UE verificate l'Allegato I del Regolamento (UE) 2021/821 (categoria 9, aerospaziale) e le autorità nazionali competenti.

### 3.10 Contenuti generati con IA (rischio basso-medio)
Il banner e il logo del corvo sembrano generati con IA. La tutela del diritto d'autore su opere generate da IA è incerta in molte giurisdizioni (spesso serve un apporto creativo umano), quindi non potete contare su di essa come bene distintivo, e l'originalità richiesta dall'hackathon (video e materiali "originali") può diventare un problema. Fate ridisegnare logo e banner a una persona e tenete traccia dell'apporto umano nel codice e nei testi. Controllate le condizioni d'uso degli strumenti usati.

### 3.11 Accordo tra soci e titolarità (rischio medio)
Non vedo nulla che stabilisca chi possiede il codice e il nome. Scrivete un accordo tra i membri (fino a sei in squadra, secondo le regole viste): titolarità dei contributi, uso del nome, ripartizione, uscita di un membro. Se alcuni sono studenti o dipendenti, controllate le politiche dell'università o del datore di lavoro sulla proprietà intellettuale.

### 3.12 Dichiarazioni e linguaggio (rischio basso-medio)
Evitate "radio validata", "accurato", "certificato", "approvato da NASA". Il sito già dice che i piani sono proposte non garantite e che i parametri sono illustrativi: è la direzione giusta. Per Artemis scrivete "Artemis landing candidate regions": oggi Artemis III è un test in orbita terrestre e il primo allunaggio è previsto con Artemis IV (la nuova schermata iniziale già usa questa dicitura).

---

## 4. Cosa aggiungere

| Cosa | Perché | Quando |
|---|---|---|
| Disclaimer "progetto indipendente, non affiliato né approvato da NASA" | Nessun patrocinio sottinteso | Prima del 14 novembre |
| `NOTICE` e `licenses.json` generato | Obblighi delle licenze di terzi | Prima della pubblicazione |
| Privacy completa (titolare, contatto, basi giuridiche, conservazione) | Oggi è un modello | Prima della pubblicazione |
| Consensi scritti dei membri per Contatti | Dati personali | Prima della pubblicazione |
| Elenco "cosa è preesistente e con quale licenza" | Originalità richiesta dall'hackathon | Con la sottomissione |
| Condizioni d'uso e contratto di pilot con NDA | Responsabilità e riservatezza | Prima del primo cliente |
| Accordo tra soci | Titolarità del codice e del nome | Subito, non dopo il successo |
| Ricerca di marchio professionale | Il nome RAVEN è affollato | Prima di investire nel brand |
| Consulenza su export e classificazione | Rischio incerto | Prima dei clienti esteri |
| Assicurazione professionale e cyber | Responsabilità e SPICE | Dopo i primi contratti |

## 5. Cosa togliere o cambiare

- **Togliere** dalla repo pubblica la cartella `research papers, scripts and planning/` e riscrivere la storia git.
- **Togliere** dal pacchetto sottoposto la pagina Piani con prezzi e pulsanti d'acquisto, e il business plan.
- **Togliere** i PDF di terzi se non avete la licenza di ridistribuirli.
- **Togliere** ogni uso del logo NASA e ogni frase che suggerisca approvazione.
- **Togliere** "validata/certificata" da testi e slide.
- **Cambiare** il nome o almeno sospendere l'investimento sul brand finché non c'è l'esito della ricerca.
- **Cambiare** il banner e il logo se generati con IA.
- **Cambiare** "Hackathon Base contributors" con i titolari reali.

---

## 6. Calendario pratico

**Entro il 14 novembre**
- [ ] Rimuovere la cartella interna dalla repo (e dalla storia)
- [ ] Nascondere Piani e materiale commerciale nella build da sottoporre
- [ ] Disclaimer di non affiliazione NASA
- [ ] Privacy: almeno titolare e contatto; consensi per Contatti
- [ ] `make licenses` e `NOTICE`
- [ ] Leggere i termini 2026 e la guida di sottomissione appena disponibili

**Con la sottomissione**
- [ ] Elenco del lavoro preesistente con le licenze
- [ ] Video senza materiale di terzi e senza persone minorenni
- [ ] Verifica che nessun dato controllato sia nel codice

**Prima del primo cliente**
- [ ] Ricerca di marchio e decisione sul nome
- [ ] Condizioni d'uso, contratto di pilot, NDA
- [ ] Accordo tra soci
- [ ] Classificazione export e controllo sanzioni

**Entro 90 giorni**
- [ ] Assicurazione professionale e cyber
- [ ] Revisione legale dei testi di vendita

---

## 7. Cosa non ho verificato

- La vostra giurisdizione, la forma societaria e l'esistenza di accordi tra soci.
- I termini dell'hackathon **2026**: ho letto la versione 2025.
- La storia git (la copia ricevuta non la mostra) e le licenze di ogni singola immagine.
- Il contenuto e la provenienza dei PDF di terzi nella cartella interna.
- Una ricerca di marchio ufficiale (EUIPO, UIBM, USPTO, WIPO).
- La classificazione di export di RAVEN.
- Le norme sull'intelligenza artificiale applicabili all'assistente se usate un LLM esterno.

---

## 8. Fonti

- Termini dei partecipanti Space Apps (versione 2025): https://spaceappschallenge.org/legal
- FAQ dei partecipanti (date e calendario 2026): https://www.spaceappschallenge.org/resources/participant-faqs/
- Guida di sottomissione: https://www.spaceappschallenge.org/resources/project-submission-guide/
- NAIF, regole d'uso di SPICE: https://naif.jpl.nasa.gov/naif/rules.html
- NAIF, uso commerciale di SPICE: https://naif.jpl.nasa.gov/pipermail/spice_announce/2005-October/000032.html
- Testo della licenza CSPICE (copia): https://lunaserv.im-ldi.com/naif-spice-docs/file.COPYING.html
- Linee guida NASA sui media: https://www.nasa.gov/multimedia/guidelines/index.html
- Linee guida NASA sulla pubblicità: https://www.nasa.gov/nasa-brand-center/advertising-guidelines/
- Marchi Raven Industries (directory di terzi): https://trademarkdir.com/owner/raven-industries e https://markinton.com/trademark/raven-73618360
- Software RAVEN del laboratorio INL: https://www.osti.gov/biblio/1235208
- EAR e software open source: https://bestpractices.linuxfoundation.org/export/ear-oss.html
- EAR, 15 CFR 734.7 (pubblicato): https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-734/section-734.7
- ECCN 9D515: https://open-gov.usebase.io/eccn/9/9D515

Le fonti sono state consultate con ricerca web e le pagine non sono state lette per intero: verificate il testo aggiornato prima di agire.
