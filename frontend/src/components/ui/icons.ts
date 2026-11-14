// SPDX-License-Identifier: Apache-2.0
// Un solo set di icone: griglia 24, tratto 1.5, estremi e giunti arrotondati, nessun riempimento.
// Disegnate per questo progetto (nessun set di terzi). Resa a 20px (24px in modalità TV).
export const ICONS = {
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13ZM15.5 15.5 20 20',
  close: 'M6 6l12 12M18 6 6 18',
  play: 'M8 5.5v13l10.5-6.5L8 5.5Z',
  pause: 'M8.5 5.5v13M15.5 5.5v13',
  expand: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5',
  collapse: 'M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5',
  left: 'M14 6l-6 6 6 6',
  right: 'M10 6l6 6-6 6',
  up: 'M6 14l6-6 6 6',
  down: 'M6 10l6 6 6-6',
  reset: 'M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v4h4',
  spin: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4',
  pin: 'M12 21s6.5-5.6 6.5-11a6.5 6.5 0 1 0-13 0c0 5.4 6.5 11 6.5 11ZM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  pulse: 'M3 12h4l2.5-6 5 12 2.5-6h4',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  orbit: 'M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM20.5 12c0 2.2-3.8 4-8.5 4s-8.5-1.8-8.5-4 3.8-4 8.5-4 8.5 1.8 8.5 4Z',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM9.7 9.4a2.4 2.4 0 1 1 3.4 2.2c-.7.4-1.1.9-1.1 1.6M12 16.8h.01',
  chat: 'M5 18.5V6.5A1.5 1.5 0 0 1 6.5 5h11A1.5 1.5 0 0 1 19 6.5v8a1.5 1.5 0 0 1-1.5 1.5H8L5 18.5Z',
  external: 'M14 5h5v5M19 5l-8 8M17 14v4.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5v-11a.5.5 0 0 1 .5-.5H10',
  chevronUp: 'M6 15l6-6 6 6',
  chevronDown: 'M6 9l6 6 6-6',
  alert: 'M12 9v4.5M12 17h.01M10.3 4.3 2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z',
} as const;

export type IconName = keyof typeof ICONS;
