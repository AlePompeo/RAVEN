// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import Learn from './Learn.svelte';

afterEach(() => { cleanup(); useCatalog('it', itCatalog, en); });

it('teaches all seven Planner steps and S0–S7, gates quizzes and preserves scenario links', async () => {
  useCatalog('en', {}, en);
  history.replaceState(null, '', '/learn?site=haworth');
  render(Learn);
  const next = () => screen.getByRole('button', { name: 'Next lesson' });
  expect((next() as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('link', { name: 'Open the corresponding Planner step' }).getAttribute('href')).toContain('site=haworth');
  expect(screen.queryByRole('link', { name: 'How it works' })).toBeNull();
  expect(screen.queryByRole('link', { name: 'Learning assistant' })).toBeNull();
  await fireEvent.click(screen.getByRole('radio', { name: 'It increases transmitter power automatically.' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Check answer' }));
  expect(screen.getByText(/Not yet/)).toBeTruthy();
  expect((next() as HTMLButtonElement).disabled).toBe(true);
  const checks = [
    ['mission', 'b'], ['sites', 'b'], ['period', 'a'], ['energy', 'a'],
    ['radio', 'c'], ['simulation', 'b'], ['report', 'c'],
    ['s0', 'a'], ['s1', 'b'], ['s2', 'c'], ['s3', 'b'], ['s4', 'c'],
    ['s5', 'b'], ['s6', 'a'], ['s7', 'c'],
  ] as const;
  for (const [i, [id, answer]] of checks.entries()) {
    expect(screen.getByRole('heading', { name: en[`course.${id}.title`], level: 3 })).toBeTruthy();
    expect(screen.getByText(en[`course.${id}.body`])).toBeTruthy();
    expect(screen.getByText(en[`course.${id}.example`])).toBeTruthy();
    await fireEvent.click(screen.getByRole('radio', { name: en[`course.${id}.${answer}`] }));
    await fireEvent.click(screen.getByRole('button', { name: 'Check answer' }));
    expect(screen.getByText(en[`course.${id}.explanation`], { exact: false })).toBeTruthy();
    if (i < checks.length - 1) {
      expect((next() as HTMLButtonElement).disabled).toBe(false);
      await fireEvent.click(next());
      expect(screen.getByRole('heading', { level: 3, name: en[`course.${checks[i + 1]![0]}.title`] })).toBe(document.activeElement);
    }
  }
  expect(screen.getByRole('heading', { name: 'Learning path completed' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Put the lessons into practice' }).getAttribute('href')).toContain('site=haworth');
});

it('updates Italian quiz and feedback in place without losing the answer', async () => {
  useCatalog('it', itCatalog, en);
  render(Learn);
  await fireEvent.click(screen.getByRole('radio', { name: 'Cambia il requisito con cui valutare il risultato.' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Verifica la risposta' }));
  expect(screen.getByText('Corretto.')).toBeTruthy();
  useCatalog('en', {}, en);
  await tick();
  expect((screen.getByRole('radio', { name: 'It changes the requirement used to assess the result.' }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole('button', { name: 'Next lesson' }) as HTMLButtonElement).disabled).toBe(false);
});
