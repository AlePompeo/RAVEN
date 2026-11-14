# Riferimenti studiati (UI v2)

Screenshot a 1440x900 (prima vista e dopo uno scroll) di otto siti scelti dall'utente. Li abbiamo **studiati**
per estrarre principi; non riusiamo loghi, testi, caratteri, impaginazioni 1:1 né immagini. Le immagini della
v2 sono solo NASA/USGS verificate (vedi `credits.md`).

| Sito | Cosa abbiamo osservato | Principio adottato (non copiato) |
| --- | --- | --- |
| SpaceX | Nero assoluto, nav solo testo, **un solo elemento vivo nella nav** (conto alla rovescia), titolo enorme in basso a sinistra con data sopra, pulsante fantasma, zero cornici. Pianeta in controluce che sfuma nel nero. | Nav testuale minima con **un** elemento vivo (orologio UTC della missione + margine del collegamento). Titolo del palco in basso a sinistra. Corpi celesti illuminati di taglio che si perdono nel nero, senza alone decorativo. |
| Portal | Foto a tutto schermo (lembo terrestre), titolo grande e corto, testo breve, link sottolineati. | Palco cinematografico con un'immagine vera; titolo corto; poco testo. |
| NASA Eyes on the Earth | UI da applicazione: etichette sugli oggetti, barra dei livelli in basso, indicatore LIVE, scheda "dati osservati il", pulsante schermo intero, titolo sovrapposto a sinistra. | Il visualizzatore diventa uno **strumento**: marcatori etichettati (veri pulsanti), indicatore LIVE legato allo stato della telemetria, scheda "ultimo campione", schermo intero. |
| Moon 3D Map | Luna fotografica con marcatori, pannello laterale destro (ricerca, filtri a chip, elenco luoghi con dettaglio), riga di attribuzione in basso. | Pannello "Esplora" a destra (foglio dal basso su telefono) con ricerca, chip di filtro, elenco di luoghi con coordinate citate; attribuzione sempre visibile. |
| earth. (ethanplus) | Ibrido editoriale/app: titolo grande leggero, Luna fotorealistica illuminata da una direzione solare reale con terminatore, cifra chiave in alto a destra, chip di funzione, cursore "Sunlight", Play, zoom rotondi, divisori sottili, attribuzione "NASA LRO imagery + LOLA terrain". | Mappe NASA LROC + LOLA con luce solare guidata da un dato; **una** cifra chiave con fonte; cursore della luce + riproduzione del giorno lunare; zoom rotondi; divisori a filo. Diverso: titolo in larghezza *espansa* (non leggero), etichette in maiuscolo/minuscolo (non tracciate), nessuna numerazione "01 /". |
| Viewtec | Pagina prodotto con globo in un riquadro, barra di strumenti verticale a icone. | Solo come contro-esempio: il globo in una scatola con cornice e cookie banner sembra "template". Noi teniamo il corpo a tutta finestra. |
| Tembrica | Elenco di strumenti in barra laterale, molti banner. | Contro-esempio di densità; nessun principio ripreso. |
| Trek | Solo schermata di caricamento catturata. | Ignorato. |

## Principi della v2 (sintesi)

1. **Immagini vere, luce vera.** Niente più superficie procedurale: mappe NASA, terminatore dalla direzione del
   Sole (telemetria o cursore). Il Sole è emissivo (immagine SDO), mai "illuminato".
2. **Strumento, non pagina.** HUD a vetro sottile: cifre tabulari con unità, un indicatore vivo, attribuzione.
3. **Una sola audacia per schermata.** Nella home il titolo espanso sul palco; nel visualizzatore il corpo celeste.
   Tutto il resto è disciplinato (stesse icone, stessi raggi, stessi stati).
4. **Evitare i "segni" da generato** (skill frontend-design): nessuna etichetta in MAIUSCOLO tracciato, nessuna
   numerazione 01/02, nessuna stringa con punti centrali, nessun monospazio per le etichette, nessuna freccia "→"
   in coda ai link, niente nero tinto al posto del nero.
