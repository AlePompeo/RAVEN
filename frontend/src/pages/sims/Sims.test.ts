// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import Sims from './Sims.svelte';
import { setLang, useCatalog } from '../../i18n/i18n.svelte';
import itCatalog from '../../i18n/it.json';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useCatalog('it', itCatalog);
});

async function setup() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url === '/api/plugins'
        ? new Response(JSON.stringify({ plugins: [{ id: 's', kind: 'simulation' }] }))
        : new Response(JSON.stringify({ outputs: { y: 4 } })),
    ),
  );
  const r = render(Sims);
  await waitFor(() => expect(screen.getByLabelText('Nome ingresso 1')).toBeTruthy());
  return r;
}

describe('Sims', () => {
  it('errore di validazione: aria-invalid, aria-describedby e focus sul primo campo non valido', async () => {
    const { container } = await setup();
    await fireEvent.submit(container.querySelector('form') as HTMLFormElement);
    const val = screen.getByLabelText('Valore 1') as HTMLInputElement;
    await waitFor(() => expect(val.getAttribute('aria-invalid')).toBe('true'));
    const errId = val.getAttribute('aria-describedby') ?? '';
    expect(document.getElementById(errId)?.textContent).toMatch(/numero/i);
    expect(document.activeElement).toBe(val);
    // nessun alert annidato in una regione live
    for (const a of container.querySelectorAll('[role="alert"]')) expect(a.closest('[aria-live]')).toBeNull();
  });
  it('aggiungi sposta il focus sul nome della nuova riga', async () => {
    await setup();
    await fireEvent.click(screen.getByRole('button', { name: 'Aggiungi ingresso' }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Nome ingresso 2')));
  });
  it('rimuovi sposta il focus su un controllo esistente', async () => {
    await setup();
    await fireEvent.click(screen.getByRole('button', { name: 'Aggiungi ingresso' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Rimuovi ingresso 2' }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Aggiungi ingresso' })));
  });
  it('esecuzione riuscita mostra tabella e stato', async () => {
    const { container } = await setup();
    await fireEvent.input(screen.getByLabelText('Valore 1'), { target: { value: '2' } });
    await fireEvent.submit(container.querySelector('form') as HTMLFormElement);
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy());
    expect(screen.getByRole('status').textContent).toMatch(/completata/i);
  });
  it('traduce interfaccia ed errori già visibili quando cambia lingua', async () => {
    const { container } = await setup();
    await fireEvent.submit(container.querySelector('form') as HTMLFormElement);
    expect(screen.getByText('Inserisci un numero finito.')).toBeTruthy();
    await setLang('en', { persist: false, url: false });
    await waitFor(() => expect(screen.getByLabelText('Input name 1')).toBeTruthy());
    expect(screen.getByText('Enter a finite number.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Run' })).toBeTruthy();
  });
});
