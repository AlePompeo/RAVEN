---
id: page-pricing
title: Pagina Piani
kind: page
summary: >-
  La pagina Piani (/pricing) presenta tre piani, Free, Premium ed Enterprise, e sotto una tabella di confronto con i
  piani in colonna e le funzionalita' in riga (spunta = incluso, croce = non incluso, sempre con il testo "Incluso" o
  "Non incluso"). Le funzionalita' non ancora implementate portano l'etichetta "Prevista". I prezzi sono ipotesi del
  business plan, IVA esclusa e da validare; gli acquisti restano disattivati finche' non e' configurato un indirizzo
  di checkout HTTPS; l'acquisto non attiva automaticamente l'accesso; il prodotto non e' qualificato per decisioni
  operative di missione.
tags: [pagina, piani, prezzi, Free, Premium, Enterprise, tabella di confronto, prevista, checkout, VITE_PREMIUM_CHECKOUT_URL, VITE_ENTERPRISE_CHECKOUT_URL, ipotesi commerciali]
applies_to: [pricing]
related: [page-model]
level: principiante
lang: it
last_verified: 2026-11-08
sources:
  - {ref: frontend/src/pages/pricing/Pricing.svelte, supports: "tre schede, tabella di confronto con regione scorrevole da tastiera, intestazione fissa, stato dell'acquisto"}
  - {ref: frontend/src/pages/pricing/plans.ts, supports: "righe della tabella per gruppo, piani che le includono ed etichetta 'prevista'"}
  - {ref: frontend/src/pages/pricing/checkout.ts, supports: "il checkout si abilita solo con un URL HTTPS senza credenziali"}
  - {ref: research papers, scripts and planning/Business_Plan_Revenue_Plan.md, supports: "livelli Community, Education, Professional, Mission License ed Enterprise, prezzi ipotetici (par. 6.1) e funzionalita' (par. 2.2)"}
  - {ref: docs/design/commercial-launch-plan.md, supports: "gap reali, distinzione storico locale/cloud e PDF browser/server, fasi e criteri di lancio senza attivare vendite"}
---
## Piani

**Free** corrisponde al livello Community del business plan: siti predefiniti, geometria di Sole e Terra, confronto di
siti e date, apprendimento guidato. **Premium** corrisponde al livello Professional (indicativo 199 euro al mese per
utente o piccolo team): scenari personalizzati, analisi RF avanzata, confronto multi-scenario, esportazione CSV e JSON.
**Enterprise** riunisce Mission License (10.000-30.000 euro per studio), Enterprise (30.000-100.000+ euro l'anno) e le
licenze didattiche istituzionali del livello Education: e' su preventivo. L'uso individuale Education resta in Free.

## Tabella di confronto

Le righe sono raggruppate in Analisi, Dati terreno e apprendimento, Report ed esportazione, Supporto e licenza. Ogni
cella ha il simbolo e il testo "Incluso" o "Non incluso". L'etichetta **Prevista** indica una funzionalita' non
ancora implementata: relay what-if, strumenti per la classe, report
dedicato, account e attivazione della licenza, misura dell'uso, supporto standard e prioritario, accesso multiutente,
API con chiavi e quote, installazione dedicata. Oggi ogni funzionalita' implementata e' disponibile a tutti senza
account: la divisione tra i piani e' una proposta.

Le righe `pdf` e `history` sono ancora marcate "Prevista" nella tabella, ma il prodotto offre gia'
report strutturato stampabile/salvabile in PDF dal browser e cronologia locale della Dashboard.
Queste funzioni non sono un renderer PDF server o uno storico cloud sincronizzato: il
[piano commerciale](../design/commercial-launch-plan.md) richiede di separare le promesse e
riallineare la tabella prima di vendere. Questa pianificazione non modifica il comportamento gratuito.

## Acquisto e limiti

I prezzi sono ipotesi, IVA esclusa, da validare con interviste e progetti pilota. Il pulsante di checkout compare solo
se all'avvio della compilazione e' impostato `VITE_PREMIUM_CHECKOUT_URL` o `VITE_ENTERPRISE_CHECKOUT_URL` con un URL
HTTPS; altrimenti la scheda dice che l'acquisto non e' ancora disponibile. L'acquisto non attiva automaticamente
l'accesso. RAVEN e' un prototipo di ricerca e formazione, senza validazione con dati di volo.
