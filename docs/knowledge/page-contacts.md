---
id: page-contacts
title: Pagina Contatti
kind: page
summary: >-
  La pagina Contatti presenta il team con nome, ruolo, foto, breve presentazione e un collegamento
  LinkedIn; i dati stanno in frontend/src/data/team.json e nel modello sono segnaposto da completare. Si apre dalla
  voce "Contatti" della navigazione principale (rotta /contacts invariata), con risorse di aiuto self-service.
tags: [pagina, contatti, team, membri, LinkedIn, foto, team.json, segnaposto]
applies_to: [contacts]
level: principiante
lang: it
last_verified: 2026-11-08
sources:
  - {ref: frontend/src/pages/contacts/Contacts.svelte, supports: "pagina 'Il team' con una scheda per membro e nota di personalizzazione"}
  - {ref: frontend/src/pages/contacts/team.ts, supports: "validazione: limiti di lunghezza, link LinkedIn solo https su linkedin.com, foto solo locali sotto /team/"}
  - {ref: frontend/src/data/team.json, supports: "due membri segnaposto 'Nome Cognome' con i ruoli del team"}
  - {ref: frontend/src/data/README.md, supports: "come aggiungere un membro e requisiti della foto"}
---
## Cosa e'

Una pagina statica, raggiungibile dal collegamento "Contatti" della navigazione principale, che mostra le persone del
team. Non usa il backend e non fa richieste a siti esterni: la foto, se c'e', e' un file locale del sito.
Il collegamento LinkedIn si apre in una nuova scheda solo quando lo si seleziona.

Nel modello i due membri sono segnaposto ("Nome Cognome", "Profilo da completare"), con i ruoli
"Elettronica e telecomunicazioni" e "Informatica, robotica e AI". Non sono persone reali.

## Come si modifica

Si modifica `frontend/src/data/team.json` (nome, cognome, ruolo, presentazione fino a 280 caratteri,
foto e LinkedIn facoltativi) e si mette la foto quadrata 512x512 in `frontend/public/team/`. Senza foto
compare un avatar con le iniziali; senza LinkedIn il pulsante non compare. Un collegamento che non e'
`https://www.linkedin.com/in/...` (o `/company/...`) viene ignorato. Si pubblicano solo informazioni di cui
la persona ha dato il consenso.

## Aiuto e assistenza

La pagina offre ora collegamenti interni a Learn, Model e gestione dei dati locali, in EN/IT.
Non e' un servizio ticket: indirizzo pubblico di assistenza, contatto del titolare, tempi di
risposta e iscrizione al pilota non sono pubblicati o attivati. Il repository e' privato
e non viene presentato come canale pubblico. Non usare segnaposto o assistente per
richieste privacy e non inviare dati personali, credenziali o configurazioni riservate.
