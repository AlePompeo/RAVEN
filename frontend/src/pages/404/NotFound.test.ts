// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import NotFound from './NotFound.svelte';

afterEach(cleanup);

describe('NotFound', () => {
  it('il link home resta sotto la base /app/', () => {
    render(NotFound, { base: '/app/' });
    expect(screen.getByRole('link', { name: 'Torna alla home' }).getAttribute('href')).toBe('/app/');
  });
  it('con base / punta a /', () => {
    render(NotFound, { base: '/' });
    expect(screen.getByRole('link', { name: 'Torna alla home' }).getAttribute('href')).toBe('/');
  });
});
