// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { useCatalog } from '../../i18n/i18n.svelte';
import en from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import fixture from '../../../../tests/backend/domain/golden/real.json';
import type { AnalysisResult } from './grazing';
import TabTime from './TabTime.svelte';
import TabWindows from './TabWindows.svelte';
import TabCompensator from './TabCompensator.svelte';
import GrazingLink from './GrazingLink.svelte';
import { modeStore } from '../../shell/mode';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); modeStore().set('learning'); useCatalog('it', itCatalog, en); });

describe('analysis localization', () => {
  it('updates network errors after a language change', async () => {
    useCatalog('en', en, en);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(GrazingLink);
    expect((await screen.findByRole('alert')).textContent).toContain('Server unreachable');
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Server non raggiungibile'));
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeTruthy();
  });

  it('keeps unknown rate samples out of the declared-link percentage in both languages', async () => {
    useCatalog('en', en, en);
    const result = structuredClone(fixture.outputs.grazing_analyze_shackleton.response) as AnalysisResult;
    result.series_time_unix = [1, 2, 3];
    result.series.chosen_rate_bps = [1000, 0, null];
    render(TabCompensator, { result });
    expect(screen.getByText(/Link declared in 50\.0 % of 2 known samples\. Samples with unknown rate: 1/)).toBeTruthy();
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByText(/Link dichiarato nel 50,0 % di 2 campioni noti\. Campioni con velocità ignota: 1/)).toBeTruthy());
  });

  it('reports an entirely unknown rate series without inventing a percentage', () => {
    useCatalog('en', en, en);
    const result = structuredClone(fixture.outputs.grazing_analyze_shackleton.response) as AnalysisResult;
    result.series_time_unix = [1, 2];
    result.series.chosen_rate_bps = [null, null];
    render(TabCompensator, { result });
    expect(screen.getByText('No known rate samples. Samples with unknown rate: 2.')).toBeTruthy();
  });

  it('updates the analysis setup and empty state after a language change', async () => {
    modeStore().set('learning');
    useCatalog('en', en, en);
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.endsWith('/status')
        ? { sites: [{ id: 's', name: 'Site', lat_deg: -89, lon_deg_east: 0, dem_covered: true }],
          dem: { available: true, product: { coverage: '85°S' } },
          limits: { max_profile_points: 1500 }, disclaimer: '' }
        : { parameters: [], stations: [{ key: 'dsn34', name: 'DSN' }], rates_bps: [100000] };
      return new Response(JSON.stringify(body), { status: 200 });
    }));
    render(GrazingLink);
    await screen.findByRole('button', { name: 'Run analysis' });
    expect(screen.getByLabelText('Where (south polar site)')).toBeTruthy();
    expect(screen.getByText('1 of 1 sites are covered by the DEM (85°S); the others require your own profile.')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Results' })).toBeTruthy();
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Esegui analisi' })).toBeTruthy());
    expect(screen.getByLabelText('Dove (sito al polo Sud)')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Risultati' })).toBeTruthy();
  });

  it('updates advanced result tabs without rerunning the analysis', async () => {
    modeStore().set('avanzato');
    useCatalog('en', en, en);
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/status')) return new Response(JSON.stringify({
        sites: [{ id: 's', name: 'Site', lat_deg: -89, lon_deg_east: 0, dem_covered: true }],
        dem: { available: true, product: { coverage: '85°S' } },
        limits: { days_max: 90, step_min_min: 1, max_profile_points: 1500, max_samples: 5000 }, disclaimer: '',
      }), { status: 200 });
      if (url.endsWith('/defaults')) return new Response(JSON.stringify({
        parameters: [], stations: [{ key: 'dsn34', name: 'DSN' }], rates_bps: [100000],
      }), { status: 200 });
      if (url.endsWith('/analyze')) return new Response(JSON.stringify(fixture.outputs.grazing_analyze_shackleton.response), { status: 200 });
      return new Response('', { status: 500 });
    }));
    render(GrazingLink);
    await screen.findByRole('button', { name: 'Run analysis' });
    expect(screen.getByText('Terrain profile (optional)')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Use a synthetic test ridge' }));
    expect(screen.getByText(/Profile loaded:/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));
    await screen.findByRole('tab', { name: 'Margin over time' });
    expect(screen.getByRole('tab', { name: 'Diffraction' })).toBeTruthy();
    expect(screen.getByText(/^Analysis complete:/)).toBeTruthy();
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Margine nel tempo' })).toBeTruthy());
    expect(screen.getByRole('tab', { name: 'Diffrazione' })).toBeTruthy();
    expect(screen.getByText(/^Analisi completata:/)).toBeTruthy();
    expect(screen.getByText('Profilo del terreno (facoltativo)')).toBeTruthy();
    expect(screen.getByText(/Profilo caricato:/)).toBeTruthy();
  });

  it('updates charts, summaries and export controls when the language changes', async () => {
    useCatalog('en', en, en);
    const result = fixture.outputs.grazing_analyze_shackleton.response as AnalysisResult;
    render(TabTime, { result });
    expect(screen.getByText('Earth and ridge elevation')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Download CSV' })).toBeTruthy();
    expect(screen.getByLabelText('Transmission rate legend')).toBeTruthy();
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByText('Elevazione della Terra e della cresta')).toBeTruthy());
    expect(screen.getByRole('button', { name: 'Scarica CSV' })).toBeTruthy();
    expect(screen.getByLabelText('Legenda delle velocità')).toBeTruthy();
  });

  it('explains the estimated window in both languages', async () => {
    useCatalog('en', en, en);
    const result = fixture.outputs.grazing_analyze_shackleton.response as AnalysisResult;
    render(TabWindows, { result });
    expect(screen.getByText('Geometric versus estimated link window')).toBeTruthy();
    expect(screen.getByTestId('windows-summary').textContent).toContain('estimated link');
    useCatalog('it', itCatalog, en);
    await waitFor(() => expect(screen.getByText('Finestra geometrica contro finestra del link stimato')).toBeTruthy());
    expect(screen.getByTestId('windows-summary').textContent).toContain('link stimato');
  });
});
