

## Learning Assistant: interfaccia (2026-10-19)

| Requisito | Test | Stato |
|---|---|---|
| Client SSE (meta/token/citations/warning/done/error, chunk a ogni byte, abort, tetti) | `frontend/src/pages/chat/assistant.test.ts` | verificato (unit) |
| Renderer markdown-lite sicuro, carichi XSS come testo, id ignoti mai link | `frontend/src/pages/chat/markdown.test.ts` | verificato (unit) |
| Pannello fonte: formula/variabili, focus trap, Esc, ritorno del focus, 404/errore | `frontend/src/pages/chat/SourcePanel.test.ts`, `e2e/tests/assistant.spec.ts` | verificato (unit + e2e) |
| Chat: stato, privacy fail closed, rifiuto, avvisi, stop, nuova conversazione, nessuna persistenza | `frontend/src/pages/chat/Chat.test.ts`, `e2e/tests/assistant.spec.ts` | verificato con backend reale e provider estrattivo |
| Spiega questa pagina: page_context da /sims e /viewer, Alt+A e ? opt-in, CLS | `frontend/src/shell/ExplainButton.test.ts`, `e2e/tests/assistant.spec.ts` | verificato |
| TV (D-pad su chat, chip, pannello, foglio), dispositivi, zoom 200/400%, axe in 2 schemi | `e2e/tests/tv.spec.ts`, `devices.spec.ts`, `ui-screens.spec.ts` | verificato in Chromium |
| Modalita llm, provider non locale, interruzione a meta, lettori di schermo reali | solo unit con risposte simulate | NON verificato con un LLM reale ne con lettori di schermo |

## Pagina Contatti (2026-10-20)

| Requisito | Test | Stato |
|---|---|---|
| Validazione dati del team: link LinkedIn solo https su linkedin.com (anche host simili e javascript:/data:), foto solo /team/*.ext locali, lunghezze, iniziali, testo senza HTML | `frontend/src/pages/contacts/contacts.test.ts` (legge anche `team.json`) | verificato (unit) |
| Due schede, nessuna richiesta fuori origine, fixture compilata (foto + link), tastiera, link nel piè di pagina, TV, Spiega, axe in 2 schemi, matrice dispositivi | `e2e/tests/contacts.spec.ts`, `devices.spec.ts`, `ui-screens.spec.ts`, `a11y.spec.ts`, `keyboard.spec.ts` | verificato in Chromium |
| Dati reali del team (nomi, foto, LinkedIn) | `frontend/src/data/team.json` contiene solo segnaposto | DA COMPILARE a cura del team |
