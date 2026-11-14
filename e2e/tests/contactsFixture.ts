// SPDX-License-Identifier: Apache-2.0
// Fixture della pagina Contatti: membri compilati iniettati via window.__HB_TEAM__ (passano dalla stessa validazione
// del runtime) e foto servita da una route di Playwright. Nessun dato personale: tutto è inventato per i test
// e NON fa parte di team.json.
import type { Page } from '@playwright/test';

export const FILLED = [
  {
    id: 'test-ada',
    firstName: 'Ada',
    lastName: 'Esempio',
    role: 'Ruolo di prova',
    bio: 'Presentazione di prova per i test automatici.',
    photo: '/team/test-ada.png',
    linkedin: 'https://www.linkedin.com/in/test-ada',
  },
  {
    id: 'test-bo',
    firstName: 'Bo',
    lastName: 'Esempio',
    role: 'Altro ruolo',
    bio: 'Senza foto e con un link non valido.',
    linkedin: 'https://linkedin.com.evil.com/in/test-bo',
  },
];

// PNG 8x8 grigio
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFklEQVR4nGNgGAWjYBSMglEwCkbBYAAABQgAAZbJ0NEAAAAASUVORK5CYII=',
  'base64',
);

export async function useFilledTeam(page: Page): Promise<void> {
  await page.addInitScript((team) => {
    (window as unknown as { __HB_TEAM__: unknown }).__HB_TEAM__ = team;
  }, FILLED);
  await page.route('**/team/test-ada.png', (r) => r.fulfill({ status: 200, contentType: 'image/png', body: PNG }));
}
