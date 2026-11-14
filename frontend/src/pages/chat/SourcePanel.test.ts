// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import SourcePanel from './SourcePanel.svelte';
import { nextTrapTarget } from '../../shell/modal';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
  document.documentElement.classList.remove('modal-open');
});

const FSPL = {
  id: 'fspl', title: 'Perdita nello spazio libero', kind: 'formula', summary: 'Attenuazione in dB.', body: '## Come si usa\n\nRaddoppiare la distanza aggiunge 6 dB. Vedi [link budget](kb:link-budget).',
  level: 'intermedio', last_verified: '2026-10-15', origin: 'manual',
  sources: [{ ref: 'backend/plugins/fspl_c/fspl.c', supports: 'implementazione' }, { ref: 'https://example.org/x', supports: 'ext' }, { ref: 'javascript:alert(1)', supports: '' }],
  expression: 'FSPL_dB = 92.45 + 20*log10(d_km) + 20*log10(f_GHz)',
  variables: [{ symbol: 'd_km', name: 'distanza', unit: 'km', range: '> 0' }],
  assumptions: ['spazio libero'], limits: ['nessuna perdita atmosferica'],
  worked_example: { inputs: { distance_km: 384400 }, outputs: { fspl_db: 210.994 }, note: 'Terra-Luna' },
  derivation: ['passo uno', 'passo due'], anchors: [{ anchor: 'come-si-usa', heading: 'Come si usa' }],
};

function mount(fetchImpl: (u: string) => Promise<Response>, onClose = vi.fn()) {
  vi.stubGlobal('fetch', vi.fn(fetchImpl));
  const opener = document.createElement('button');
  opener.textContent = 'chip';
  document.body.appendChild(opener);
  opener.focus();
  const r = render(SourcePanel, { props: { id: 'fspl', anchor: 'come-si-usa', trigger: opener, onClose } });
  return { opener, onClose, ...r };
}

describe('SourcePanel', () => {
  it('mostra formula, tabella variabili, ipotesi, limiti, esempio, derivazione, fonti e data', async () => {
    mount(async () => new Response(JSON.stringify(FSPL)));
    await screen.findByText('FSPL_dB = 92.45 + 20*log10(d_km) + 20*log10(f_GHz)');
    expect(screen.getByRole('dialog', { name: 'Perdita nello spazio libero' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Unità' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'km' })).toBeTruthy();
    expect(screen.getByText('spazio libero')).toBeTruthy();
    expect(screen.getByText('nessuna perdita atmosferica')).toBeTruthy();
    expect(screen.getByText('384400')).toBeTruthy();
    expect(screen.getByText('210.994')).toBeTruthy();
    expect(screen.getByText('passo due')).toBeTruthy();
    expect(screen.getByText('2026-10-15')).toBeTruthy();
    expect(screen.getByText(/Passaggio citato: Come si usa/)).toBeTruthy();
    // solo gli URL http(s) diventano collegamenti; un percorso o uno schema pericoloso restano testo
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]!.getAttribute('href')).toBe('https://example.org/x');
    expect(links[0]!.getAttribute('rel')).toContain('noopener');
    // i collegamenti kb: del corpo diventano testo
    expect(screen.getByText(/Vedi link budget\./)).toBeTruthy();
  });

  it('focus sul pulsante Chiudi, Tab e Maiusc+Tab restano dentro, Esc chiude', async () => {
    const { onClose } = mount(async () => new Response(JSON.stringify(FSPL)));
    await screen.findByText(/FSPL_dB/);
    const dlg = screen.getByRole('dialog');
    const close = screen.getByRole('button', { name: /Chiudi/ });
    expect(document.activeElement).toBe(close);
    await fireEvent.keyDown(dlg, { key: 'Tab', shiftKey: true });
    expect(dlg.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(close); // da Chiudi (primo) con Maiusc+Tab si va all'ultimo
    await fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(close); // dall'ultimo si torna al primo
    await fireEvent.keyDown(dlg, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('il resto della pagina è inert mentre è aperto e il focus torna al chip alla chiusura', async () => {
    const root = document.createElement('div');
    root.id = 'app';
    const ann = document.createElement('div');
    ann.id = 'announcer';
    const main = document.createElement('main');
    root.append(main, ann);
    document.body.appendChild(root);
    const { opener, unmount } = mount(async () => new Response(JSON.stringify(FSPL)));
    await screen.findByText(/FSPL_dB/);
    expect(main.hasAttribute('inert')).toBe(true);
    expect(ann.hasAttribute('inert')).toBe(false); // gli annunci restano udibili
    expect(opener.hasAttribute('inert')).toBe(true);
    expect(document.documentElement.classList.contains('modal-open')).toBe(true);
    unmount();
    expect(main.hasAttribute('inert')).toBe(false);
    expect(opener.hasAttribute('inert')).toBe(false);
    expect(document.activeElement).toBe(opener);
    expect(document.documentElement.classList.contains('modal-open')).toBe(false);
  });

  it('fonte inesistente: messaggio onesto, nessun Riprova inutile', async () => {
    mount(async () => new Response('', { status: 404 }));
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toMatch(/non è più nel materiale/);
    expect(screen.queryByRole('button', { name: 'Riprova' })).toBeNull();
  });

  it('errore di rete: messaggio con istruzioni e Riprova che ricarica', async () => {
    let n = 0;
    mount(async () => {
      if (n++ === 0) throw new TypeError('offline');
      return new Response(JSON.stringify(FSPL));
    });
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toMatch(/connessione/);
    await fireEvent.click(screen.getByRole('button', { name: 'Riprova' }));
    await waitFor(() => expect(screen.getByText(/FSPL_dB/)).toBeTruthy());
  });

  it('documento senza campi opzionali: nessuna sezione vuota', async () => {
    mount(async () => new Response(JSON.stringify({ id: 'x', title: 'Solo titolo', kind: 'concept', summary: 's' })));
    await screen.findByText('s');
    expect(screen.queryByText('Variabili')).toBeNull();
    expect(screen.queryByText('Esempio svolto')).toBeNull();
    expect(screen.getByText(/non indica fonti esterne/)).toBeTruthy();
  });
});

describe('nextTrapTarget', () => {
  const mk = (n: number) => {
    const c = document.createElement('div');
    const items = Array.from({ length: n }, () => c.appendChild(document.createElement('button')));
    return { c, items };
  };
  it('cicla tra primo e ultimo, altrimenti lascia fare al browser', () => {
    const { c, items } = mk(3);
    expect(nextTrapTarget(items, items[2]!, false, c)).toBe(items[0]);
    expect(nextTrapTarget(items, items[0]!, true, c)).toBe(items[2]);
    expect(nextTrapTarget(items, items[1]!, false, c)).toBeNull();
    expect(nextTrapTarget([], null, false, c)).toBe(c);
    expect(nextTrapTarget(items, document.body, false, c)).toBe(items[0]); // focus fuori: rientra
  });
});
