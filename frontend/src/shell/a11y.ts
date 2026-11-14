// SPDX-License-Identifier: Apache-2.0
export const SITE_NAME = 'RAVEN';

export function setTitle(title: string): void {
  document.title = `${title} | ${SITE_NAME}`;
}

/** Sposta il focus sull'h1 dentro `root` (tabindex=-1 per renderlo focalizzabile). */
export function focusMainHeading(root: ParentNode = document): boolean {
  const h1 = root.querySelector('h1');
  if (!h1) return false;
  if (!h1.hasAttribute('tabindex')) h1.setAttribute('tabindex', '-1');
  h1.focus({ preventScroll: true });
  return true;
}

const timers = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>();

/** Annuncia un messaggio in una regione aria-live: svuota e riscrive per forzare la lettura. */
export function announce(message: string, region: HTMLElement | null = document.getElementById('announcer')): void {
  if (!region) return;
  const pending = timers.get(region);
  if (pending !== undefined) clearTimeout(pending);
  region.textContent = '';
  timers.set(
    region,
    setTimeout(() => {
      region.textContent = message;
      timers.delete(region);
    }, 50),
  );
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function scrollBehavior(): ScrollBehavior {
  return prefersReducedMotion() ? 'auto' : 'smooth';
}
