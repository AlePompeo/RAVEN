# Design system — Hackathon Base

Piano di design (scritto PRIMA del codice, poi rivisto contro il brief) e regole operative.
Fonte dei token: `frontend/src/styles/tokens.css`. Il contrasto di ogni coppia di token è verificato da
`frontend/src/styles/contrast.test.ts` (fallisce sotto 4.5:1 per il testo, 3:1 per bordi/indicatori UI).

## 0. Piano v2 (ottobre 2026): da "artigianale" a strumento

Riferimenti studiati e principi adottati: `references.md`. Provenienza e licenze di ogni immagine: `credits.md`.

### 0.1 Perché la v1 sembra fatta a mano (diagnosi concreta)

| Sintomo nella v1 | Dove | Correzione v2 |
| --- | --- | --- |
| Luna **procedurale** (rumore + crateri ad anello): si riconosce subito come finta | palco home, visualizzatore 2D | mappe NASA LROC (colore) + LOLA (rilievo), luce dal Sole con terminatore; stesso dato in WebGL e Canvas 2D |
| Visualizzatore WebGL = sfera grigia liscia con anello blu e due palline colorate | `threeViewport.ts` | shader con mappa colore, rilievo da altimetria, cielo stellato reale, Sole emissivo da SDO |
| Icone disegnate caso per caso (tratti 1.8/2, misure 18/22/24, terminazioni miste) | toolbar, home, nav | un solo set inline SVG: griglia 24, tratto 1.5, `round`, resa a 20px (`components/ui/Icon.svelte`) |
| Raggi ed elevazioni casuali (5/8/11/18/pill, ombre e vetri diversi) | pannelli, toolbar, tile | scala a 3 raggi (`--r-inner 6px`, `--r-panel 14px`, pill/cerchio) e 2 superfici (piatta, vetro HUD) |
| Hover generici (solo cambio colore), nessuno stato `disabled`/`active` disegnato | pulsanti, chip | stati progettati: hover (+6% luce), pressione (scala .96), focus (anello unico 2px + 2px), disabilitato (40%, nessun hover) |
| Nessuno stato di caricamento/vuoto/errore: aree bianche o pagine che "saltano" | telemetria, simulazioni, assistente, visualizzatore | scheletri a dimensione riservata, stati vuoti che dicono cosa fare, errori con causa e rimedio |
| Nessuna sensazione di strumento: barra di 6 pulsanti testuali sotto la Luna | visualizzatore | HUD: pannello "Esplora" (ricerca, chip, luoghi), cifra chiave con fonte, LIVE, scheda ultimo campione, selettore di data e ora UTC (luce reale dal punto subsolare) con riproduzione, zoom rotondi, schermo intero, attribuzione |
| Gerarchia debole nelle dashboard (quattro numeri uguali, grafico senza contesto) | telemetria | un valore primario + secondari, unità e formati locali, tempo dell'ultimo campione |
| Numeri senza formato coerente (`103.5 W`, `6.0 dB`) | ovunque | `Intl.NumberFormat('it-IT')`, cifre tabulari, unità con spazio fine |

### 0.2 Token v2 (in aggiunta ai §2-4)

- **Colore**: invariati Vuoto `#000000`, Regolite, Uplink (unico interattivo). Nuovo uso dell'ambra Luce solare:
  anche per il cursore della luce (è un dato: la direzione del Sole). Vetro HUD = nero al 72% + sfocatura, filo
  `rgb(255 255 255 / .16)`; sotto ogni testo su cielo/immagine c'è vetro o scrim (contrasto AA misurabile).
- **Tipo**: HB Sans invariato. Le etichette HUD sono 12–14px in minuscolo con iniziale maiuscola, colore muted,
  **mai** maiuscolo tracciato; le cifre HUD in peso 300, `tabular-nums`, unità a 0.5em.
- **Forme**: `--r-inner 6px`, `--r-panel 14px`, `--r-pill`; pulsanti icona rotondi da 44px (56px in TV).
- **Movimento**: dissolvenza incrociata + carrello di camera 480ms al cambio di corpo; con reduced motion,
  cambio istantaneo.

### 0.3 Layout del visualizzatore

```
┌ nav (testo, punto sotto la voce attiva) ··········· [UTC 09:41:07  margine 6,1 dB] ┐
│ Luna                                  ← titolo h1                 384.400 km      │
│ [Luna|Terra|Sole|Marte]  (tablist)                   distanza media dalla Terra    │
│                                                                   (fonte NSSDC)    │
│                   ●Apollo 11                              ┌─ Esplora ───────────┐  │
│          ╭──── corpo (mappa NASA, luce vera) ────╮        │ [cerca luoghi]      │  │
│          │   ● Tycho                              │        │ (Tutti)(Allunaggi)  │  │
│          ╰────────────────────────────────────────╯        │ Apollo 11  0,67° N… │  │
│   (+)(−)  (⤢)                                             └─────────────────────┘  │
│ ── Luce solare ════════●══════════  ▶  │ LIVE  ultimo campione 09:41:05 UTC         │
│ Mappe NASA LROC e LOLA; stelle NASA SVS. Trascina per ruotare.        raggio 1.737,4 km │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Sotto 834px il pannello Esplora diventa un foglio dal basso (chiuso: maniglia + titolo; aperto: 60svh).

### 0.4 Dispositivi

Tipo e spazi fluidi con `clamp()`, `dvh/svh`, `env(safe-area-inset-*)`, regole `pointer: coarse` (target ≥ 44px,
nessuna affordance solo-hover), larghezza massima per ultrawide, **modalità TV** (≥1920px senza puntatore fine
oppure `?tv=1`): rem scalato, margini di overscan 5%, anello di focus spesso, navigazione spaziale con le frecce
(`shell/spatialNav.ts`, senza dipendenze), Esc/Back chiude, cursore nascosto dopo inattività. Livelli di qualità
(`viewports/quality.ts`): core, memoria, Save-Data → mappe 1k, DPR massimo 1.5, niente strati di stelle.

### 0.5 Revisione contro le regole della skill frontend-design

- *Cifra grande + etichetta piccola* è un default: la teniamo **una sola volta** per corpo (la distanza), perché è il
  dato con fonte che orienta la scala; i fatti secondari sono una riga a filo, non card.
- *Etichetta maiuscola sopra ogni titolo* (SpaceX, earth.): scartata, etichette in tono normale.
- *Attribuzione con punti centrali* (earth.): scartata, frasi con punto e virgola.
- *Chip di filtro identici* rischiano il kit SaaS: sono solo dove filtrano davvero un elenco (tipi di luogo).
- *Nero tinto*: lo sfondo resta `#000`; il cielo stellato è un dato (mappa SVS), non un gradiente.

## 1. Soggetto, pubblico, compito

- **Soggetto**: una base modulare per hackathon spaziali — un sito sulla Luna che invia telemetria (potenza,
  margine del collegamento verso la Terra, posizione di Sole e Terra), più simulazioni, un visualizzatore della
  Luna e un assistente.
- **Pubblico**: team in gara che partono da questo template e giurie che guardano una demo proiettata su un
  computer qualsiasi (anche senza GPU).
- **Compito della pagina principale**: far capire in 10 secondi che la piattaforma è *viva* (Luna che gira, dati
  che arrivano) e portare con un clic alle demo.

## 2. Palette (6 colori con nome)

| Nome | Hex | Ruolo |
| --- | --- | --- |
| Vuoto | `#000000` | palco (stage), barra di navigazione, tile scure. Nero vero, non un quasi-nero colorato. |
| Basalto | `#1d1d1f` | inchiostro su chiaro; superficie rialzata nello schema scuro |
| Regolite | `#f5f5f7` | tile chiare (pergamena), sfondo dei pannelli di lavoro |
| Altopiano | `#ffffff` | pagina e pannelli in chiaro |
| Uplink | `#0066cc` su chiaro / `#2997ff` su scuro | l'UNICO colore interattivo (link, pulsante primario, focus `#0071e3`) |
| Luce solare | `#b25000` su chiaro / `#ffb340` su scuro | SOLO dati: serie della potenza (energia solare) e marcatore del Sole |

Il blu è il colore della Terra e del collegamento radio; l'ambra è la luce che alimenta i pannelli. I due colori
compaiono insieme solo nei grafici, dove codificano davvero potenza e collegamento. Nessun gradiente decorativo.

Schemi: `prefers-color-scheme` cambia le tile "auto" (chiaro: Altopiano/Regolite; scuro: Vuoto/Basalto). Le tile
`tone-dark` (palco della home, visualizzatore, capitolo foto, capitolo telemetria) restano scure in entrambi gli schemi.

## 3. Tipografia

Una sola famiglia: **HB Sans**, sottoinsieme latino di *Mona Sans* (SIL OFL 1.1, variabile `wght` 300–700,
`wdth` 100–125), auto-ospitato (`frontend/src/assets/fonts/hb-sans-latin.woff2`, 67 KB, `font-display: swap`,
fallback `system-ui`). Rinominato perché *Mona* è un Reserved Font Name e l'OFL vieta di usarlo per versioni
modificate (il sottoinsieme lo è). Testo OFL in `frontend/src/assets/fonts/OFL.txt`.

Perché questo carattere: l'asse di larghezza. La mossa tipografica è il titolo del palco composto in **larghezza
espansa (wdth 125)**, come le scritte sugli scafi e sulle strumentazioni; tutto il resto è a larghezza normale.
Un solo carattere con un asse in più invece di due famiglie. Scartati: Instrument Sans (non ha il peso 300, si
stringe ma non si allarga), stack di sistema (su Linux/Windows cambia faccia e metriche da macchina a macchina:
la demo deve sembrare uguale ovunque; il font pesa 67 KB < 120 KB di budget).

| Ruolo | Dimensione | Peso / larghezza | Uso |
| --- | --- | --- | --- |
| display | clamp(44px → 104px) | 700 / wdth 125, tracking −0.03em | solo il titolo del palco della home |
| h1 | clamp(36px → 56px) | 600 / wdth 112 | titolo delle pagine documento |
| h2 / capitolo | clamp(28px → 48px) | 600 / wdth 112 | titoli dei capitoli |
| h3 | 21px | 600 | titoli di pannello |
| subnav title | 21px | 600 / wdth 112 | h1 delle pagine strumento (sotto-barra) |
| lead | clamp(19px → 24px) | 400 | paragrafo d'apertura |
| body | 17px / 1.47 | 400 | testo corrente, misura ≤ 68ch |
| small | 14px / 1.43 | 400 / 600 | etichette, didascalie, nav |
| micro | 12px | 400 | crediti delle immagini (minimo assoluto: niente 10px, troppo piccolo per AA pratico) |
| readout | clamp(32px → 48px) | 300, `tabular-nums` | valori di telemetria |

Pesi ammessi: 300 / 400 / 600 / 700 (niente 500). Nessun MAIUSCOLO tracciato, nessun monospazio per le etichette:
i numeri usano `font-variant-numeric: tabular-nums` della stessa famiglia.

## 4. Layout

Unità 8px; padding dei capitoli 80px (48px sotto i 480px). Colonna di testo 980px max, dashboard 1200px.
Allineamento: **tutto a sinistra** su un'unica linea di colonna (titoli, testo, pulsanti). Niente titoli centrati.
Breakpoint: 480 / 640 / 734 / 833 / 1068 / 1440. Navigazione globale nera da 44px, che sotto 834px diventa un
pulsante "Menu" con pannello a tutto schermo.

Home (scorrimento come racconto, tile a tutta larghezza alternate scuro/chiaro):

```
┌──────────────── nav 44px nero ─────────────────────────────┐
│ ◐ Hackathon Base     Home Telemetria Simulazioni Vis. Ass. │
├────────────────────────────────────────────────────────────┤
│ PALCO (Vuoto, 100svh-44)                    ╭──────────────│  Luna canvas 2D, diametro ~1.5x
│ HACKATHON          ░ scrim ≥ 0.6 ░        ╭╯   LUNA        │  l'altezza, esce in basso a destra,
│ BASE  (128px, espanso)                    │   (terminatore │  sale dal nero all'ingresso e si
│ lead              [Apri la telemetria]    │    e crateri)  │  avvicina nei primi 100vh di scroll
├────────────────────────────────────────────────────────────┤
│ CAP. 1 (alt) "Un sito lunare, quattro strumenti"           │
│  ◠ Telemetria │ ⚙ Simulazioni │ ◍ Visualizzatore │ ▭ Ass.  │  striscia di 4 colonne con icona
├────────────────────────────────────────────────────────────┤
│ CAP. 2 FOTO A TUTTO SCHERMO (100svh): Earthrise, cover      │  zoom legato allo scroll (view())
│ titolo + testo sul cielo nero, scrim ≥ 0.6   ● Terra        │  vignettatura in basso
│ ▁▁▁▁▁ orizzonte lunare ▁▁▁▁▁▁▁▁▁▁▁▁▁   credito NASA (micro)  │
├────────────────────────────────────────────────────────────┤
│ CAP. 3 (Vuoto) Telemetria dal vivo                         │
│  103.5 W | 6.0 dB | 35° | 25°  (cifre 44-72px, tabulari)   │
│  traccia della potenza 220px con area sotto la linea       │
├────────────────────────────────────────────────────────────┤
│ CAP. 4 Prova le demo: tile scura con falce lunare + righe  │
├──────────────── footer: Licenze Privacy Cookie ────────────┤
```

Pagine strumento (Telemetria, Visualizzatore, Simulazioni, Assistente):

```
┌ nav 44px ─────────────────────────────────────────────────┐
├ sotto-barra smerigliata (sticky): h1 21px  ·········· stato┤
│ area di lavoro (Regolite):                                │
│  ┌ pannello bianco r18 ┐ ┌ pannello ┐                     │
```

Visualizzatore: il palco occupa tutta la finestra sotto le barre; i comandi stanno in una barra flottante
traslucida in basso (pulsanti pieni su vassoio sfocato), descrizione testuale sotto il palco.

Pagine documento (Licenze, Privacy, Cookie, 404): tile chiara con h1 grande, testo a 68ch, tabelle con righe
sottili (hairline) e intestazioni allineate a sinistra.

## 5. Principi

1. **La Luna è l'unico spettacolo.** L'audacia sta solo nel palco della home (Luna procedurale a tutto schermo,
   titolo espanso). Tutto il resto è quieto: un colore interattivo, un carattere, superfici piatte.
2. **Testo su media solo sopra uno scrim garantito.** Dove il testo si sovrappone a canvas o foto (palco,
   capitolo Earthrise) c'è uno scrim nero ≥ 60% (`--scrim-min`, `--scrim-strong`) e il testo usa solo
   `--c-text`: `contrast.test.ts` verifica ≥ 4.5:1 anche sopra un pixel bianco. axe non può calcolare lo sfondo
   di quei nodi e li riporta come "incomplete" (atteso, elencato nel report); altrove il testo sta su colori
   pieni e axe lo misura. (Prima versione: niente sovrapposizione; cambiato su richiesta di regia, vedi §11.)
3. **La luce è un dato.** Ambra = potenza (energia solare), blu = collegamento con la Terra. Mai decorazione.
4. **Gira su un computer qualunque.** Home senza WebGL (Canvas 2D, 13 KB), DPR ≤ 2, 20 fps massimi nel palco,
   animazione solo se visibile (IntersectionObserver + Page Visibility), qualità adattiva, nessuna dipendenza nuova.
5. **Il movimento risponde.** Un solo ingresso orchestrato al caricamento (la Luna passa da falce a gibbosa, poi
   compare il titolo); il resto del movimento è legato allo scroll dell'utente. Con `prefers-reduced-motion` tutto
   è statico (Luna ferma in fase finale, nessun effetto di scroll).

## 6. Regole di movimento

- Ingresso: 1 sequenza (fase lunare 1.6s ease-out, poi titolo/lead/CTA in 400ms, una volta sola per sessione di pagina).
- Scroll: `animation-timeline: view()` dentro `@supports (animation-timeline: view())`; senza supporto un
  IntersectionObserver con soglie (passi del 5%) scrive `--progress` sul capitolo; il CSS usa la stessa variabile.
  Effetti ammessi: solo `transform`/`opacity` (compositor), solo sul media (Luna che si allontana uscendo dal palco,
  foto che si stringe entrando). Il testo non si anima mai allo scroll.
- Rotazione della Luna: 4°/s, ferma fuori schermo, a scheda nascosta e con reduced motion.
- Pressione: `scale(.95)` 120ms sui pulsanti. Nessuna transizione su hover delle tile.
- `prefers-reduced-motion: reduce`: nessuna animazione, nessun effetto di scroll, rotazione disattivata.

## 7. Accessibilità (WCAG 2.2 AA)

- Contrasto: testo ≥ 4.5:1, bordi dei controlli/indicatori ≥ 3:1, verificato da test sui token reali e da axe
  (wcag2a/aa/21/22aa) su ogni pagina in entrambi gli schemi.
- Focus: anello 2px Focus Blue (`#0071e3` su chiaro, `#2997ff` su scuro), offset 2px; mai rimosso.
- Target ≥ 44×44px per pulsanti e voci di menu (24px minimo WCAG 2.5.8, qui più largo).
- Menu mobile: `aria-expanded`/`aria-controls`, Esc chiude e ridà il focus al pulsante, Tab resta nel pannello
  (resto della pagina `inert`), chiusura alla navigazione.
- Skip link, focus sull'h1 al cambio rotta, annuncio in regione live: invariati.
- Canvas sempre `aria-hidden` con equivalente testuale (descrizione della scena, tabella dei campioni).

## 8. Componenti riusabili (`frontend/src/components/ui/`)

`Hero` (palco a tutta larghezza con slot media e scrim), `Tile` (tone `light`/`dark`/`auto`), `Chapter`
(capitolo con effetto di scroll opzionale), `MediaFrame` (immagine responsiva con `<picture>` e riga di credito),
`Button` (pill `primary`/`ghost`, `<a>` o `<button>`), `Callout` (nota/avviso), `SubNav` (sotto-barra sticky).
Ognuno ha test Vitest.

## 9. Cosa NON si fa (deliberatamente)

- Niente griglie di card identiche, ombre morbide ovunque, gradienti decorativi.
- Niente etichette MAIUSCOLE sopra i titoli, niente numerazioni 01/02/03, niente "→" in coda ai link, niente
  stringhe con punti centrali, niente monospazio per le etichette.
- Niente fade-up a ogni sezione, niente parallax del testo, niente smooth-scroll JS (Lenis) né GSAP.
- Niente WebGL nella home: three.js (192 KB gzip) resta solo nel visualizzatore.
- Niente loghi o testi di terzi, niente font o immagini da CDN: tutto auto-ospitato.
- Nessuna dipendenza npm nuova.

## 10. Revisione del piano contro il brief (prima di costruire)

Prima stesura → revisione:

- *Titoli centrati come nel linguaggio di riferimento* → **allineati a sinistra**: il riferimento va imitato, non
  copiato; la colonna sinistra unica lega home, dashboard e documenti.
- *Tre card uguali per i moduli* (SaaS kit) → **elenco di definizioni** con righe sottili nel capitolo 1, e nel
  capitolo demo **una tile grande + righe-link** invece di una griglia uniforme.
- *Testo sovrapposto alla Luna con scrim a gradiente* → axe darebbe "incomplete" e il contrasto dipenderebbe dai
  pixel: **la Luna sfuma nel nero e il testo sta sul nero pieno**.
- *Instrument Sans* → **Mona Sans (rinominato HB Sans)**: serve il 300 e la larghezza espansa per il titolo.
- *Cifre grandi con etichetta piccola + accento a gradiente* (default da dashboard) → tenute solo nella telemetria,
  dove i valori SONO il contenuto, in peso 300 e senza gradienti.
- *Luna illuminata dal Sole della telemetria dal vivo* → scartata per il palco: con il Sole dietro la Luna il palco
  diventerebbe nero. Il palco è deterministico; i dati veri stanno nel capitolo 3 e nel visualizzatore.

## 11. Immagini: provenienza e licenza

| Campo | Valore |
| --- | --- |
| Soggetto | "Earthrise", la Terra sopra l'orizzonte lunare (nessuna persona ritratta) |
| ID NASA | `as08-14-2383` (AS08-14-2383), Apollo 8, 24 dicembre 1968, centro JSC |
| Sorgente | https://images.nasa.gov/details/as08-14-2383 ; file `https://images-assets.nasa.gov/image/as08-14-2383/as08-14-2383~orig.jpg` (3000x3000) |
| Metadati (metadata.json NASA) | Title "Apollo 8 Mission image, Earth over the horizon of the moon"; Center JSC; Keywords APOLLO 8, LUNAR PHOTOGRAPHS, EARTH LIMB…; campi Credit/Rights/Copyright vuoti; nessun fotografo o persona identificabile |
| Stato | Opera NASA, non protetta da copyright negli USA (linee guida NASA sull'uso dei media). Nessun logo NASA, nessuna formula che suggerisca approvazione |
| Riga di credito | "La Terra sorge sull'orizzonte lunare, Apollo 8, 24 dicembre 1968. Foto NASA, pubblico dominio." (home) e voce in Licenze |
| File | `frontend/src/assets/media/earthrise-wide-{1280,1920}.webp`, `earthrise-wide-1280.jpg`, `earthrise-portrait-860.webp` (20–41 KB), ciascuno con `.license` (REUSE), generati da `build-assets.py`; auto-ospitati, nessun hotlink |

Carattere: HB Sans da Mona Sans (OFL 1.1); `hb-sans-latin.woff2.license` e `OFL.txt` nella stessa cartella.

## 12. Prestazioni e budget

- JS iniziale (`check-bundle.mjs`): 51 012 B → 55 250 B raw (19.4 → 21.0 kB gzip); soglia invariata 64 000 B. Con il pulsante Spiega della shell: 63 670 B raw (24.6 kB gzip), 99.5% della soglia (foglio e chat sono chunk pigri).
  L'aumento è la barra globale (≈2.1 kB) e runtime Svelte condiviso. Spread di attributi e `<svelte:element>`
  evitati di proposito: da soli aggiungevano ≈7 kB al chunk iniziale (misurato con source map).
- Pagina Contatti (`/contacts`, 2026-10-20): scheda del team guidata da `frontend/src/data/team.json`, importato solo dal
  chunk lazy della pagina. Nel chunk iniziale entrano solo il registro e la voce nel piè di pagina: 63 670 → 64 112 B
  raw (+442 B), oltre la soglia di 64 000 B. Soglia alzata di 500 B a 64 500 B (+0.8%); nessun controllo spostato o
  disattivato. Layout: due schede affiancate da 760px, in colonna sotto; foto quadrata con `aspect-ratio` e
  `width`/`height` (nessun salto di layout); senza foto, avatar con iniziali dai token (bordo tratteggiato = segnaposto);
  link LinkedIn come pulsante ghost con icona SVG propria. Link nel piè di pagina (gruppo `legal`), non nella nav
  principale (larghezza). Validazione di link/foto in `pages/contacts/team.ts` (vedi `frontend/src/data/README.md`).
- Home "Il problema" (2026-10-27): navigazione TV corretta nella shell (`spatialNav.ts`: dalla barra la freccia giù
  porta al primo controllo della pagina, cioè la CTA; il pulsante fluttuante "Spiega questa pagina" è scelto solo se in
  quella direzione non c'è altro). JS iniziale 64 328 → 64 553 B raw (+225 B, 24.5 kB gzip), oltre la soglia di
  64 500 B. Soglia alzata di 500 B a 65 000 B (+0.8%, ben sotto il tetto concordato di 72 000 B): è codice di
  accessibilità della shell, che deve stare nel chunk iniziale perché vale su ogni pagina. Il resto della home è pigro.
- Lingue, fase A (2026-10-27): `t()` con segnaposto e plurali, risoluzione della lingua, catalogo inglese del primo
  rendering (`i18n/en.json`: barra, piè di pagina, interruttori, titoli, hero della home) e pulsante del selettore
  nella shell: 64 553 → 73 474 B raw. Compensazioni: navigazione spaziale TV (`spatialNav.ts`, 3,5 kB) caricata solo in
  modalità TV (il rilevamento resta in `tv.ts`), listbox del selettore in un chunk lazy (`LanguageMenu.svelte`),
  etichette italiane letterali tolte dai moduli delle pagine (ora `titleKey`/`navKey`), ripiego 404 duplicato tolto da
  `App.svelte` (la 404 è la pagina `/404` del registro), stringhe delle pagine in `i18n/en.pages.json` (lazy, caricato
  insieme al chunk della pagina). Misura finale 69 825 B raw (26.4 kB gzip). Soglia alzata a 70 000 B, il tetto
  concordato per questa fase: l'i18n deve stare nel chunk iniziale perché la barra è tradotta al primo rendering.
  L'italiano (unica lingua non inglese; hindi, cinese, arabo e coreano, aggiunti in seguito, sono stati rimossi) è un
  chunk lazy, caricato prima del montaggio solo se scelto. La fase B aggiunge
  stringhe solo in `en.pages.json` e nei cataloghi lazy, non nel chunk iniziale.
- Home: chunk `Home` ≈19 kB, mini-simulatore `MiniSim` ≈9 kB (caricato solo quando il passo 3 si avvicina allo schermo;
  modello condiviso con Simula), `canvas2dViewport` ≈13 kB, carattere 67 kB, foto 20–36 kB (lazy). three.js mai caricato.
- CPU rallentata 4x (CDP, `perf-cpu.spec.ts`): numeri nel report e in `e2e/test-results/ui/perf-cpu4x.json`.

## 12b. Verso del testo e scritture

Il sito è solo inglese e italiano (decisione dell'utente): scrittura latina, sempre `dir="ltr"`. Non ci sono stack di font
per scritture non latine, né specchiatura (RTL), né `--dir-x`. Le proprietà CSS logiche (`margin/padding-inline`,
`inset-inline`, `text-align: start`) già in uso restano: sono innocue e facilitano una futura lingua RTL (vedi
`docs/i18n.md`, "Aggiungere una lingua in futuro"). Verifica: `e2e/tests/i18n.spec.ts` (nessun overflow a 390 e 1440 in
en e it, axe pulito).

## 13. Changelog

- **v1** (piano §1–10): token, HB Sans, shell, componenti, home con Luna a destra e testo su nero pieno,
  restyle di tutte le pagine, QA a 3 larghezze x 2 schemi.
- **QA 1**: Home prima nella nav (era ultima: `order` assente); sotto-barra scura del visualizzatore su
  sfondo bianco → spostata dentro il contenitore scuro (contrasto); colonne della home allineate (container
  largo ovunque); tile demo invisibile nello schema scuro (#000 su #000) → Basalto; credito della foto
  allineato alla colonna; bordo della Luna scalettato → ritaglio anti-alias; crateri "ad anello" → bordi
  attenuati; anteprima telemetria vuota negli screenshot → connessione aperta subito.
- **QA 2**: pannelli invisibili nello schema scuro (raised = alt) → `--c-raised #2a2a2c`; fascia bianca tra
  area di lavoro e piè di pagina → `main` a colonna flessibile; grafico con un solo campione esteso su anni →
  finestra di ±30 s; credito della foto coperto dalla tile successiva → figura a colonna flessibile;
  `<select>` con freccia in background-image (axe "incomplete") → freccia nativa.
- **Regia (art direction)**: Luna dominante fuori bordo con ingresso dal nero e "drift" legato allo scroll
  (`animation-timeline: scroll()` + ripiego IO), titolo fino a 128px sopra scrim tokenizzato; Earthrise a tutto
  schermo con zoom di scroll e vignettatura (nuovo ritaglio verticale per telefoni); striscia dei quattro
  strumenti con icone; cifre di telemetria 44–72px e traccia 220px con area.
- **QA 3**: titoli degli strumenti non allineati → icona in alto senza margine automatico; falce della tile
  demo sfocata e sotto il titolo → falce nitida in alto a destra; Luna su telefono quasi tutta in ombra →
  centro più a sinistra e scrim più corto.
- **Assistente di apprendimento**: la pagina `/chat` (cartella `pages/chat`, etichetta di navigazione "Assistente",
  titolo "Assistente di apprendimento") diventa l'interfaccia del Learning Assistant (contratto: `docs/assistant.md`);
  nuovi: pannello fonte, foglio "Spiega questa pagina", scorciatoie, stato della modalità. Dettagli in §14.

## 14. Assistente di apprendimento (chat, fonti, "Spiega questa pagina")

Codice: `frontend/src/pages/chat/` (pagina, client SSE, renderer, pannello fonte) e `frontend/src/shell/`
(`ExplainButton`, `ExplainSheet`, `modal.ts`, `pageContext.svelte.ts`). Tutto usa i token esistenti
(`--c-raised`, `--c-link`, `--c-power`, `--space-*`, `--radius-*`), `SubNav`, `Callout` e i pulsanti globali; nessun
colore nuovo, nessuna ombra tranne quella del pulsante fluttuante e dei pannelli.

**Pagina `/chat`.** Sotto-barra con h1 "Assistente di apprendimento" e, a destra, lo stato (`.status-pill`):
verde "Risposte dal materiale del sito" (modalità estrattiva) oppure ambra "Risposte generate da un modello
(provider)". Una colonna di 52rem: nota di privacy (solo se serve), introduzione, cronologia, compositore (livello
principiante/intermedio/tecnico, lingua automatica/it/en, campo, Invia / Interrompi / Nuova conversazione), e SOTTO il
compositore le domande di partenza da `/api/assistant/suggestions` (arrivano da rete: sopra spingerebbero giù il
compositore e produrrebbero CLS). Domande dell'utente: bolla blu a destra; risposte: scheda `--c-raised` a tutta
larghezza. Il compositore NON è sticky (a 400% di zoom, in TV e su telefono copriva risposte e chip).

**Risposta.** Markdown-lite reso con elementi veri (nessun `innerHTML`/`{@html}`; test con carichi XSS): paragrafi
con a capo, **grassetto**, `codice`, elenchi, blocchi ``` ```, tabelle, la riga "Formula:" come blocco monospace con
bordo sinistro blu, l'elenco "Variabili:" come tabella (simbolo, significato, unità, intervallo) con cifre tabulari.
Le tabelle scorrono nella loro regione focalizzabile (mai parole spezzate lettera per lettera). I marcatori `[id]`
diventano chip focalizzabili solo se l'id è tra i documenti recuperati/citati; altrimenti restano testo (mai
collegamenti; nemmeno `[testo](url)`). Sotto la risposta: elenco "Fonti" (pulsanti da 44px con titolo e tipo),
avvisi dei `warning` tradotti in frasi che dicono cosa è successo, domande di approfondimento (`done.followups`),
"Copia la risposta". Rifiuto (`done.refused`): scheda calma "Non è nel materiale del sito" con tre cose da provare
e tre domande suggerite; nessun allarme rosso.

**Regione live.** Un solo `role="status"` visivamente nascosto, che cambia solo a fine risposta ("Risposta pronta, 3
fonti." / "Risposta pronta: non è nel materiale del sito." / "Risposta interrotta." / "Nuova conversazione."). I token
non sono mai in una regione live; durante lo streaming i token si riversano nel DOM al massimo una volta per
fotogramma. Gli errori sono un solo `role="alert"` che spiega cosa fare; il testo digitato resta nel campo (WCAG 3.3.7).
"Invia" resta sempre nel DOM (aria-disabled quando occupato) e "Interrompi" accanto a lui: se il pulsante premuto
sparisse, il focus finirebbe sul body e Esc non raggiungerebbe più il foglio.

**Privacy.** La conversazione vive solo in memoria (nessun localStorage/sessionStorage dei messaggi; test e2e).
Avviso "il testo viene inviato a un servizio esterno" (Callout ambra) quando la modalità è `llm` e lo stato non
dichiara `external: false` (o il provider non è uno stub locale noto), e anche quando lo stato non è raggiungibile o
la modalità è ignota (fail closed). Con la modalità estrattiva non compare. Un modello locale non dichiarato come tale
dal backend mostra comunque l'avviso, e il testo lo dice.

**Pannello fonte** (`SourcePanel.svelte`). Da 640px in su pannello laterale destro da 34rem; sotto, foglio dal basso
(max 88dvh, angoli superiori r18). Modale: il resto della pagina è `inert` (tranne `#announcer`), il focus entra su
"Chiudi" e resta intrappolato (Tab/Maiusc+Tab), Esc (o Indietro in TV) chiude e il focus torna al chip. Carica
`/api/assistant/knowledge/{id}` e mostra: tipo (badge), livello, data di verifica, sintesi, per le formule
l'espressione in blocco monospace, la tabella delle variabili, ipotesi, limiti, esempio svolto (ingressi e risultati con
cifre tabulari), derivazione numerata, testo completo (collassato per le formule) e "Dove è documentato": solo gli URL
https diventano collegamenti (`rel="noopener noreferrer"`), i percorsi del repository restano testo. Stati: caricamento,
404 ("non è più nel materiale del sito", senza Riprova), errore di rete (con Riprova), documento senza campi opzionali
(nessuna sezione vuota).

**"Spiega questa pagina".** Pulsante a pillola fisso in basso a destra (`position: fixed`: non sposta il layout, CLS 0),
su tutte le pagine tranne `/chat` e le rotte inesistenti; sotto 480px il testo visibile è "Spiega" (il nome accessibile
resta "Spiega questa pagina"). Il foglio è un chunk a parte caricato al primo uso (il pulsante pesa ≈3.9 kB nel JS
iniziale). Contiene lo stato, le domande suggerite per `page_id` (nome della cartella in `pages/`), un campo libero e
la riga "Con la tua domanda invio all'assistente ciò che vedi in questa pagina: ..." (trasparenza sul contesto). Ogni
domanda parte con `page_context {page_id, simulation_id?, params?}`: su `/sims` la simulazione scelta, i valori
numerici validi inseriti e l'ultimo risultato (`risultato_<uscita>`), su `/viewer` il corpo celeste (`body`) e il luogo
scelto (`place`); al più 16 scalari, chiavi di al più 40 caratteri (limiti del server).
- Scorciatoie: **Alt+A** apre il foglio da qualunque pagina (non si attiva se il menu è aperto); il tasto **?** apre il
  foglio solo se l'utente lo attiva con il pulsante "Apri anche con il tasto ?" nel foglio (WCAG 2.1.4: i tasti singoli
  devono poterli spegnere; la scelta vale fino alla chiusura della scheda e non si salva), e mai mentre si scrive in un
  campo. Il pulsante ha `aria-keyshortcuts="Alt+A"`.
- TV: il pulsante è `opacity: 0` finché non riceve il focus; si raggiunge con le frecce (nello stesso modo in cui si
  raggiunge ogni altro controllo), appare con l'anello di focus spesso e Invio apre il foglio. Dentro il foglio le
  frecce restano nel foglio (resto della pagina `inert`) e il tasto Indietro chiude.

**Verifiche** (tutte in `e2e/tests/`): `assistant.spec.ts` (backend reale, provider estrattivo fissato con
`ASSISTANT_PROVIDER=assistant-extractive` nella config di Playwright), `tv.spec.ts`, `devices.spec.ts` (matrice dei
dispositivi + reflow 200%/400% con `/sims#explain` e `/chat#answer`), `ui-screens.spec.ts` (3 dimensioni x 2 schemi con
axe su risposta, pannello fonte e foglio). Nota di misura: i chip `[id]` dentro il testo sono esentati dal controllo dei
44px (eccezione WCAG 2.5.8 per i bersagli in linea; il pseudo-elemento allarga l'area utile), ma la stessa fonte è
sempre anche nell'elenco "Fonti" con bersagli da 44px.

## 15. Stampa: il report del Mission Planner (PDF del server e stampa del browser)

Il report e' **solo in inglese** (decisione 10 nov 2026), con numeri e date in formato inglese; il sito resta inglese+italiano.
Struttura: parte 1 verdetto (titolo, frase unica con i numeri, schede A|B con barre noto-si / noto-no / ignoto, al massimo tre
punti), parte 2 quattro grafici sovrapposti A/B con una striscia noto/ignoto sotto ciascuno, parte 3 formule con variabili
nominate (legenda e valori della run nelle ultime colonne), parte 4 limiti e stato di validazione. Learn = parti 1-4; Expert
aggiunge le appendici A-F (solo quelle che hanno contenuto). Indice breve solo in Expert, con numeri di pagina nel PDF.

Sistema di stampa "carta bianca": frontend/src/pages/planner/reportPrint.css (palette e componenti rp-*, condiviso dal PDF del
server e dalla stampa del browser) e backend/assets/report-print.css (solo WeasyPrint: pagine, intestazione corrente,
piede "RAVEN · Preliminary study, not a certificate" e "Page X of Y", segnalibri, indice con puntini). Niente CSS grid ne' flex
(WeasyPrint 70 e' lento e fallisce): blocchi, tabelle, inline-block.
- **Palette**: inchiostro #1d1d1f, accento #0066cc (A), arancio #b25000 (B); ruoli con token --pp-<ruolo>-bg|fg|rule
  (test di contrasto WCAG AA sui token).
- **Stati**: noto-si = riempito col colore del sito, noto-no = bianco con bordo, ignoto = tratteggio grigio. Chip con colore +
  icona + parola (StatusChip.svelte): l'icona e' un inline-block a parte con margine, quindi non si sovrappone al testo.
  La legenda e' scritta una sola volta (riquadro nella pagina 1).
- **Formule**: righe con nomi di variabile (corsivo grassetto), legenda a tabella (nome, significato, unita', origine con tag
  V/D/I) e colonne "This run A / B". Registro unico reportFormulas.ts; nessun font matematico.
- **Grafici**: A blu continua, B arancio tratteggiata, assi comuni, due per riga, titolo = domanda, riga "come leggere" e riga
  formula.
- **Anti-slop**: test reportLint.test.ts (frasi <= 25 parole, nessuna frase ripetuta, legenda e disclaimer una volta,
  Learn <= 900 parole di corpo, Expert senza appendici <= 1600, niente parole italiane).
- **Accessibilita'**: h1-h4 reali nel PDF, th scope, lingua en, segnalibri, PDF con tag.

### Audit dei grafici A contro B (12 nov 2026)
Tutte le curve: asse y comune ad A e B, asse x in giorni dall'inizio di ciascun periodo (prima era il tempo assoluto: con inizi
diversi A e B finivano distanti; corretto), A continua blu, B tratteggiata arancio, striscia noto-si / noto-no / ignoto sotto il
grafico. Aggiunto un solo grafico, "How many useful hours add up over time?" (stato della missione nel tempo). Non aggiunti: finestre
DSN a parte (il motore da' solo si/no per passo e la visibilita' DSN e' gia' un fattore dell'ora utile); bande impilate dello stato
(ripetono la striscia "utile"). Daltonismo: colori scelti per contrasto e tratteggio, simulazione non eseguita.

| Variabile | Grafico | Unita' | Stato verificato |
|---|---|---|---|
| `sun_el_deg` | Sole | gradi con segno, riferimento 0 = orizzonte piatto | ignoto = linea interrotta, mai 0 |
| `lit`, `earth_visible`, `rf_closes`, `useful` | strisce | si/no/ignoto | tre stati distinti |
| `earth_el_deg` | Terra | gradi con segno, riferimento 0 | ignoto = linea interrotta |
| `margin_db` | link RF | dB; riferimenti 0 dB e margine richiesto | sito tutto ignoto: "no values (unknown)" |
| `soc` x 100 | batteria | % della capacita', asse fisso 0-100, linea di riserva | ignoto dal primo passo ignoto |
| ore utili cumulate (da `useful`) | cumulato (nuovo) | ore | si ferma al primo passo ignoto (null, non 0) |
| curve di affidabilita' | Appendice A (se abilitata) | probabilita' / ore | gia' presenti |
