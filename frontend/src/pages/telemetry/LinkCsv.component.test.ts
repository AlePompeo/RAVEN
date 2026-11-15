// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { setLang, useCatalog } from '../../i18n/i18n.svelte';
import enPages from '../../i18n/en.pages.json';
import itCatalog from '../../i18n/it.json';
import LinkCsv from './LinkCsv.svelte';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useCatalog('it', itCatalog, enPages);
});

it('updates a displayed CSV error when the language changes', async () => {
  useCatalog('it', itCatalog, enPages);
  vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 503 })));
  render(LinkCsv, { onContext: () => {} });
  const file = { size: 12, text: async () => 'invalid\n' };
  await fireEvent.change(screen.getByLabelText('Scegli un file CSV'), { target: { files: [file] } });
  await waitFor(() => expect(screen.getByText('Intestazioni CSV obbligatorie mancanti o duplicate.')).toBeTruthy());
  await setLang('en', { persist: false, url: false });
  await waitFor(() => expect(screen.getByText('Missing or duplicate required CSV headers.')).toBeTruthy());
});
