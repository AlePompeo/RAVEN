// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { CATEGORIES, grant, revoke, isGranted, isStoredGranted, loadScript, STORAGE_KEY } from './consent';

beforeEach(() => {
  localStorage.clear();
  document.head.innerHTML = '';
});
afterEach(() => vi.restoreAllMocks());

describe('consent', () => {
  it('di default nessuna categoria non essenziale e attiva', () => {
    for (const c of CATEGORIES) expect(isGranted(c)).toBe(false);
  });

  it('grant salva nel localStorage con timestamp', () => {
    grant('analytics');
    expect(isGranted('analytics')).toBe(true);
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    expect(stored.analytics.granted).toBe(true);
    expect(Number.isNaN(Date.parse(stored.analytics.at))).toBe(false);
  });

  it('loadScript senza consenso non inietta lo script', () => {
    expect(loadScript('analytics', 'https://example.org/a.js')).toBeNull();
    expect(document.querySelectorAll('script').length).toBe(0);
  });

  it('loadScript con consenso inietta, revoke rimuove', () => {
    grant('analytics');
    const el = loadScript('analytics', 'https://example.org/a.js');
    expect(el).not.toBeNull();
    expect(document.querySelectorAll('script[src="https://example.org/a.js"]').length).toBe(1);
    revoke('analytics');
    expect(document.querySelectorAll('script').length).toBe(0);
    expect(isGranted('analytics')).toBe(false);
  });

  it('non duplica lo stesso script e rifiuta schemi non http(s)', () => {
    grant('analytics');
    loadScript('analytics', 'https://example.org/a.js');
    loadScript('analytics', 'https://example.org/a.js');
    expect(document.querySelectorAll('script').length).toBe(1);
    expect(loadScript('analytics', 'javascript:alert(1)')).toBeNull();
  });

  it('rifiuta http: cross-origin, accetta same-origin relativo', () => {
    grant('analytics');
    expect(loadScript('analytics', 'http://example.org/a.js')).toBeNull();
    expect(loadScript('analytics', '/vendor/a.js')).not.toBeNull();
  });

  it('host non in allowlist rifiutato, in allowlist accettato', () => {
    grant('analytics');
    const opts = { allowedHosts: ['cdn.example.org'] };
    expect(loadScript('analytics', 'https://evil.example.com/a.js', opts)).toBeNull();
    expect(loadScript('analytics', 'https://cdn.example.org/a.js', opts)).not.toBeNull();
  });

  it('imposta integrity, crossorigin e referrerpolicy', () => {
    grant('analytics');
    const el = loadScript('analytics', 'https://example.org/a.js', { integrity: 'sha384-abc' });
    expect(el?.integrity).toBe('sha384-abc');
    expect(el?.getAttribute('crossorigin')).toBe('anonymous');
    expect(el?.getAttribute('referrerpolicy')).toBe('no-referrer');
  });

  it('dedupe per URL assoluto normalizzato', () => {
    grant('analytics');
    loadScript('analytics', 'https://example.org/a/../a.js');
    loadScript('analytics', 'https://EXAMPLE.org/a.js');
    expect(document.querySelectorAll('script').length).toBe(1);
  });

  it('grant/revoke riportano se la scelta e stata salvata', () => {
    expect(grant('analytics')).toBe(true);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('x');
    });
    expect(grant('media')).toBe(false);
    expect(revoke('analytics')).toBe(false);
  });

  it('revoke con storage che fallisce toglie comunque script e consenso in memoria', () => {
    grant('analytics');
    loadScript('analytics', 'https://example.org/a.js');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('x');
    });
    expect(revoke('analytics')).toBe(false);
    expect(document.querySelectorAll('script').length).toBe(0);
    expect(isGranted('analytics')).toBe(false);
    expect(loadScript('analytics', 'https://example.org/b.js')).toBeNull();
  });

  it('revoke fallita poi grant fallito: isGranted e loadScript restano bloccati, stored resta true', () => {
    grant('analytics');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('x');
    });
    expect(revoke('analytics')).toBe(false);
    expect(grant('analytics')).toBe(false);
    expect(isStoredGranted('analytics')).toBe(true);
    expect(isGranted('analytics')).toBe(false);
    expect(loadScript('analytics', 'https://example.org/a.js')).toBeNull();
  });

  it('revoke di una categoria non tocca le altre', () => {
    grant('analytics');
    grant('media');
    loadScript('media', 'https://example.org/m.js');
    revoke('analytics');
    expect(document.querySelectorAll('script').length).toBe(1);
  });

  it('se localStorage lancia, equivale a nessun consenso', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('negato');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('negato');
    });
    expect(() => grant('analytics')).not.toThrow();
    expect(isGranted('analytics')).toBe(false);
    expect(loadScript('analytics', 'https://example.org/a.js')).toBeNull();
    expect(() => revoke('analytics')).not.toThrow();
  });

  it('un valore corrotto vale come nessun consenso', () => {
    localStorage.setItem(STORAGE_KEY, '{non json');
    expect(isGranted('analytics')).toBe(false);
    localStorage.setItem(STORAGE_KEY, '{"analytics":{"granted":"si"}}');
    expect(isGranted('analytics')).toBe(false);
  });
});
