<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dati del team (pagina Contatti)

La pagina `/contacts` legge `team.json`. Per aggiungere o modificare un membro:

1. Modifica `team.json`. Ogni membro:

   | Campo | Obbligatorio | Note |
   | --- | --- | --- |
   | `id` | sì | minuscolo, cifre e trattini (`ada-rossi`); unico |
   | `firstName`, `lastName` | sì | max 40 caratteri; mostrati come testo |
   | `role` | sì | max 80 caratteri |
   | `bio` | sì | max 280 caratteri, solo testo (niente HTML) |
   | `photo` | no | percorso locale `/team/<id>.webp` (o `.jpg`, `.png`, `.avif`) |
   | `linkedin` | no | `https://www.linkedin.com/in/...` (o `/company/...`); altri indirizzi non diventano link |

2. Metti la foto in `frontend/public/team/` come `<id>.webp` o `<id>.jpg`: quadrata, 512x512, al massimo 150 KB.
   Solo file locali: niente URL esterni né immagini incorporate.
3. Finché il nome è `Nome Cognome` la scheda mostra "Profilo da completare". Senza foto compare un avatar con le
   iniziali; senza `linkedin` il pulsante non viene mostrato.

Valori troppo lunghi vengono troncati e quelli non validi scartati (`src/pages/contacts/team.ts`, con test).

**Privacy**: pubblica solo ciò che la persona ha acconsentito a rendere pubblico (nome, foto, presentazione,
profilo). Nessun dato personale senza il suo consenso.
