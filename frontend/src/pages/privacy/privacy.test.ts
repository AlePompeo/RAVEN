// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import Privacy from './Privacy.svelte';
import Cookies from '../cookies/Cookies.svelte';
import Terms from '../terms/Terms.svelte';

afterEach(() => { cleanup(); useCatalog('it', itCatalog, en); });

it.each(['en', 'it'] as const)('privacy dichiara i limiti reali del prototipo in %s', (language) => {
  useCatalog(language, language === 'it' ? itCatalog : {}, en);
  render(Privacy);
  expect(screen.getByText(language === 'en' ? /not a completed legal privacy notice/ : /non un'informativa legale completa/)).toBeTruthy();
  expect(screen.getByText(language === 'en' ? /does not guarantee IP truncation/ : /non garantisce troncamento degli IP/)).toBeTruthy();
  expect(screen.getByRole('link', { name: language === 'en' ? 'Manage calculation history' : 'Gestisci la cronologia dei calcoli' }).getAttribute('href')).toBe('/dashboard');
});

it('cookie documenta la cronologia, la compatibilita e il limite del backup senza cancellare dati', () => {
  localStorage.setItem('hb.planner-journey.history.v1', '{"keep":true}');
  render(Cookies);
  expect(screen.getByText('hb.planner-journey.history.v1')).toBeTruthy();
  expect(screen.getByText(/hb.mission-timeline.v1/)).toBeTruthy();
  expect(screen.getByText(/non offre backup cloud automatico/)).toBeTruthy();
  expect(localStorage.getItem('hb.planner-journey.history.v1')).toBe('{"keep":true}');
  localStorage.removeItem('hb.planner-journey.history.v1');
});

it('condizioni non presenta il prototipo come contratto commerciale approvato', () => {
  render(Terms);
  expect(screen.getByRole('heading', { name: "Condizioni d'uso", level: 1 })).toBeTruthy();
  expect(screen.getByText(/Non sono un contratto commerciale approvato/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Modello e validazione' }).getAttribute('href')).toBe('/model');
});
