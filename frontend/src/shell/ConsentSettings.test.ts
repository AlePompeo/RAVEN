// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/svelte';
import ConsentSettings from './ConsentSettings.svelte';
import { loadScript, grant, isGranted } from './consent';
import { useCatalog } from '../i18n/i18n.svelte';
import en from '../i18n/en.pages.json';
import itCatalog from '../i18n/it.json';
import { tick } from 'svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  grant('analytics'); // azzera la revoca di sessione tra i test
  localStorage.clear();
  document.head.innerHTML = '';
  useCatalog('it', itCatalog, en);
});

describe('ConsentSettings', () => {
  it('aggiorna etichette e messaggio al cambio lingua senza modificare il consenso', async () => {
    render(ConsentSettings);
    await fireEvent.click(screen.getByLabelText('Statistiche di utilizzo'));
    useCatalog('en', {}, en);
    await tick();
    expect(screen.getByLabelText('Usage analytics')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe('Choice saved.');
    expect(isGranted('analytics')).toBe(true);
  });
  it('se lo storage fallisce lo stato resta non attivo e compare un messaggio status', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('negato');
    });
    render(ConsentSettings);
    const box = screen.getByLabelText('Statistiche di utilizzo') as HTMLInputElement;
    await fireEvent.click(box);
    expect(box.checked).toBe(false);
    expect(screen.getByRole('status').textContent).toMatch(/non e stato possibile salvare/i);
  });
  it('revoca non salvata: messaggio onesto, checkbox sullo stato salvato, script rifiutati', async () => {
    render(ConsentSettings);
    const box = screen.getByLabelText('Statistiche di utilizzo') as HTMLInputElement;
    await fireEvent.click(box);
    expect(box.checked).toBe(true);
    expect(loadScript('analytics', 'https://example.org/a.js')).not.toBeNull();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('negato');
    });
    await fireEvent.click(box);
    const msg = screen.getByRole('status').textContent ?? '';
    expect(msg).toMatch(/non e stata salvata/i);
    expect(msg).toMatch(/ancora attivo/i);
    expect(msg).not.toMatch(/consenso non e attivo/i);
    expect(box.checked).toBe(true);
    expect(document.querySelectorAll('script').length).toBe(0);
    expect(loadScript('analytics', 'https://example.org/a.js')).toBeNull();
  });
  it('due revoche non salvate di fila: messaggio e stato coerenti', async () => {
    render(ConsentSettings);
    const box = screen.getByLabelText('Statistiche di utilizzo') as HTMLInputElement;
    await fireEvent.click(box); // granted salvato
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('negato');
    });
    await fireEvent.click(box); // revoca non salvata, checkbox resta "attivo"
    await fireEvent.click(box); // seconda revoca, ancora non salvata
    const msg = screen.getByRole('status').textContent ?? '';
    expect(msg).toMatch(/non e stata salvata/i);
    expect(msg).toMatch(/ancora attivo/i);
    expect(msg).not.toMatch(/consenso non e attivo/i);
    expect(box.checked).toBe(true); // stato salvato, come dichiara il messaggio
    expect(isGranted('analytics')).toBe(false);
    expect(loadScript('analytics', 'https://example.org/a.js')).toBeNull();
  });
  it('dopo la revoca indica che serve ricaricare', async () => {
    render(ConsentSettings);
    const box = screen.getByLabelText('Statistiche di utilizzo') as HTMLInputElement;
    await fireEvent.click(box);
    expect(box.checked).toBe(true);
    await fireEvent.click(box);
    expect(box.checked).toBe(false);
    expect(screen.getByRole('status').textContent).toMatch(/ricarica/i);
  });
});
