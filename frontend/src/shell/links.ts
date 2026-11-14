// SPDX-License-Identifier: Apache-2.0

/**
 * Se il click va gestito dal router restituisce il nuovo URL (path+query+hash, base inclusa),
 * altrimenti null e il browser gestisce il link (hash in-page, esterni, nuova scheda, ecc.).
 */
export function linkTarget(
  e: MouseEvent,
  loc: Pick<Location, 'origin' | 'pathname' | 'search'>,
): string | null {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return null;
  const a = (e.target as Element | null)?.closest?.('a');
  if (!a) return null;
  const target = a.getAttribute('target');
  if (target && target !== '_self') return null;
  if (a.hasAttribute('download')) return null;
  if (a.relList.contains('external')) return null;
  if (a.origin !== loc.origin) return null;
  // Differisce solo per hash: frammento in-page (skip link), lo gestisce il browser.
  if (a.hash && a.pathname === loc.pathname && a.search === loc.search) return null;
  return a.pathname + a.search + a.hash;
}
