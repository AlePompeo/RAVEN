// SPDX-License-Identifier: Apache-2.0
/**
 * Pagine navigabili (path, titolo del documento, h1 come sottostringa del nome accessibile, voce di navigazione, se ha
 * l'interruttore Learning | Avanzato). Fonte: frontend/src/pages/*\/index.ts. Le schede dei contenitori (Simula, Siti)
 * compaiono come pagine a sé con ?tab=, così ogni vista esistente resta coperta.
 */
export const PAGES = [
  { path: '/', title: 'Home | RAVEN', h1: 'RAVEN', nav: 'Home', mode: true },
  { path: '/explore', title: 'Explore | RAVEN', h1: 'Explore', nav: 'Explore', mode: false },
  { path: '/learn', title: 'Learn | RAVEN', h1: 'Learn', nav: 'Learn', mode: false },
  { path: '/pricing', title: 'Piani | RAVEN', h1: 'Una nuova prospettiva', nav: 'Piani', mode: false },
  { path: '/simula', title: 'Simula | RAVEN', h1: 'Simula – Simulatore', nav: 'Explore', mode: true },
  { path: '/simula?tab=onda', title: 'Simula | RAVEN', h1: 'Simula – Onda 3D', nav: 'Explore', mode: true },
  { path: '/analizza', title: 'Link budget | RAVEN', h1: 'Link budget', nav: 'Explore', mode: true },
  { path: '/siti', title: 'Siti | RAVEN', h1: 'Siti – Globo e classifica', nav: 'Explore', mode: true },
  { path: '/siti?tab=globo', title: 'Siti | RAVEN', h1: 'Siti – Globo e classifica', nav: 'Explore', mode: true },
  { path: '/siti?tab=classifica', title: 'Siti | RAVEN', h1: 'Siti – Globo e classifica', nav: 'Explore', mode: true },
  { path: '/laboratorio', title: 'Laboratorio | RAVEN', h1: 'Laboratorio', nav: 'Explore', mode: true },
  { path: '/telemetry', title: 'Telemetria | RAVEN', h1: 'Telemetria', nav: 'Explore', mode: true },
  { path: '/sims', title: 'Simulazioni | RAVEN', h1: 'Simulazioni', nav: 'Explore', mode: true },
  { path: '/chat', title: 'RAVEN SI | RAVEN', h1: 'RAVEN SI', nav: 'Learn', mode: false },
  { path: '/model', title: 'Modello e validazione | RAVEN', h1: 'Modello e validazione', nav: 'Modello e validazione', mode: true },
  { path: '/licenses', title: 'Licenze | RAVEN', h1: 'Licenze', nav: 'Licenze', mode: false },
  { path: '/privacy', title: 'Informativa sulla privacy | RAVEN', h1: 'Informativa sulla privacy', nav: 'Privacy', mode: false },
  { path: '/contacts', title: 'Contatti | RAVEN', h1: 'Il team', nav: 'Team', mode: false },
  { path: '/cookies', title: 'Cookie e archiviazione locale | RAVEN', h1: 'Cookie e archiviazione locale', nav: 'Cookie', mode: false },
  { path: '/terms', title: "Condizioni d'uso | RAVEN", h1: "Condizioni d'uso", nav: "Condizioni d'uso", mode: false },
] as const;

/** Vecchie rotte: restano valide e portano alla nuova pagina conservando la query. */
export const ALIASES = [
  { from: '/lander', to: '/simula', tab: 'sito' },
  { from: '/wave', to: '/simula', tab: 'onda' },
  { from: '/grazinglink', to: '/analizza', tab: null },
  { from: '/viewer', to: '/siti', tab: 'globo' },
  { from: '/compare', to: '/siti', tab: 'classifica' },
] as const;
