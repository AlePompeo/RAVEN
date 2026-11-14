// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import RavenCompare from './RavenCompare.svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import itCatalog from '../../i18n/it.json';
import enPages from '../../i18n/en.pages.json';
import { raven, type RavenComparison } from '../../shell/ravenApi';
import { modeStore } from '../../shell/mode';
import { DEFAULT_ORDER, orderFrom, rankRows, rankingLine } from './ravenRanking';

const fx = <T>(n: string): T => JSON.parse(readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), `../../shell/fixtures/raven/${n}.json`), 'utf8')) as T;
const cmp = fx<RavenComparison>('compare');

describe('ranking helpers', () => {
  it('asks for the chosen criterion first, then the default ones not yet used', () => {
    expect(orderFrom('useful_hours')).toEqual([...DEFAULT_ORDER]);
    expect(orderFrom('min_soc')).toEqual(['min_soc', 'useful_hours', 'unknown_hours', 'margin_min_db']);
    expect(orderFrom('margin_min_db')).toEqual(['margin_min_db', 'useful_hours', 'unknown_hours']);
  });
  it('keeps every component visible and never invents a score', () => {
    const rows = rankRows(cmp.ranking);
    expect(rows.map((r) => r.site_id)).toEqual(cmp.ranking.ranking.map((r) => r.site_id));
    expect(rows[0]!.components).toMatchObject({ useful_hours: expect.any(Number), margin_min_db: expect.any(Number), min_soc: expect.any(Number) });
    expect(cmp.ranking.score).toBeNull();
    expect(JSON.stringify(rows)).not.toMatch(/score/);
    expect(rankingLine(cmp.ranking, (c) => c, (d) => d)).toContain('useful_hours (desc) > unknown_hours (asc)');
  });
});

describe('RavenCompare', () => {
  afterEach(() => { modeStore().set('learning'); cleanup(); vi.unstubAllGlobals(); raven.clear(); sessionStorage.clear(); useCatalog('it', itCatalog, enPages); });

  function stub(compare: RavenComparison) {
    const sites = cmp.sites.map((e) => ({ ...e.site, dem_covered: true }));
    const params = fx<Record<string, any>>('parameters');
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/raven/sites') return new Response(JSON.stringify({ model_version: compare.model_version, sites, dem: { available: true, cached_tiles: 1, product: { id: 'p', coverage: '', coverage_north_limit_deg: -85, credit: '', url: '' } }, ephemeris: { available: true }, disclaimer: '' }));
      if (url === '/api/raven/parameters') return new Response(JSON.stringify(params));
      if (url === '/api/raven/compare') { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(compare)); }
      return new Response('', { status: 404 });
    }));
    return bodies;
  }

  it('shows the components, the declared tie-break, the model version and the unknown sites apart with the reason', async () => {
    const withUnknown: RavenComparison = {
      ...cmp, ranking: { ...cmp.ranking, not_comparable: [{ site_id: 'apollo11', components: {}, reasons: ['margin_min_db unknown'] }] },
    };
    const bodies = stub(withUnknown);
    modeStore().set('avanzato');
    render(RavenCompare);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confronta con RAVEN' })).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: 'Confronta con RAVEN' }));
    const table = await screen.findByTestId('rank-table');
    expect(table.querySelectorAll('tbody tr')).toHaveLength(cmp.ranking.ranking.length);
    const heads = [...table.querySelectorAll('th[data-component]')].map((h) => h.getAttribute('data-component'));
    expect(heads).toEqual(['useful_hours', 'unknown_hours', 'margin_min_db', 'margin_median_db', 'min_soc']);
    expect(table.querySelector('thead')!.textContent + table.querySelector('tbody')!.textContent).not.toMatch(/punteggio|score/i);
    expect(screen.getByTestId('rank-stamp').textContent).toContain(cmp.model_version);
    expect(screen.getByTestId('ranking-rule').textContent).toContain('site id');
    expect(screen.getByTestId('not-comparable').textContent).toContain('margin_min_db unknown');
    expect(bodies[0]).toMatchObject({ days: 7, step_min: 10, order: ['useful_hours', 'unknown_hours', 'margin_min_db'] });
  });

  it('Learning shows the default-order components and hides the technical fields; Advanced shows all', async () => {
    stub(cmp);
    render(RavenCompare);
    await screen.findByRole('button', { name: 'Confronta con RAVEN' });
    expect(screen.queryByLabelText('Passo (minuti)')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'Confronta con RAVEN' }));
    const table = await screen.findByTestId('rank-table');
    expect([...table.querySelectorAll('th[data-component]')].map((h) => h.getAttribute('data-component'))).toEqual(['useful_hours', 'unknown_hours', 'margin_min_db']);
    expect(table.querySelectorAll('tbody tr:first-child td.num')).toHaveLength(4);
  });

  it('explains a too large window before calling the model', async () => {
    const bodies = stub(cmp);
    modeStore().set('avanzato');
    render(RavenCompare);
    const days = (await screen.findByLabelText('Durata (giorni)')) as HTMLInputElement;
    await fireEvent.input(days, { target: { value: '30' } });
    await waitFor(() => expect(document.getElementById('g-size-err')?.textContent).toMatch(/1.?500/));
    await fireEvent.click(screen.getByRole('button', { name: 'Confronta con RAVEN' }));
    expect(bodies).toHaveLength(0);
  });
});
