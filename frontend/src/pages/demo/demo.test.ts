// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import Demo from './Demo.svelte';

afterEach(cleanup);

it('shows a video placeholder rather than the previous guided sections', () => {
  render(Demo);
  expect(screen.getByRole('img', { name: /Video dimostrativo di circa 30 secondi/ })).toBeTruthy();
  expect(screen.queryAllByRole('link')).toHaveLength(0);
});
