<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 10 report: frontend shell, router, a11y

Status: DONE (con nota versioni).
- Stack: Vite 6.4.4, Svelte 5.57.2, vitest 4.1.11, jsdom 26.1.0 (vedi docs/versions.md; Vite 7/8 richiedono Node >=20.19).
- Router: createRouter/normalizePath/routerFromModules in src/shell/router.ts; auto-registrazione in src/registry.ts via import.meta.glob('./pages/*/index.ts').
- a11y: setTitle, focusMainHeading, announce, prefersReducedMotion, scrollBehavior; App.svelte con header/nav/main/footer, skip link, #announcer aria-live.
- CSS: token come custom properties, dark via prefers-color-scheme, focus visibile, reduced-motion.
- Verifiche: vitest 10/10 pass; npm run build OK; svelte-check 0 errori; npm audit 0.
- Concerns: shell non testata in browser reale (solo build); App.svelte senza test componente; Node 20.18.1 blocca Vite >=7.

## Fix round 1
- Skip link: shell/links.ts linkTarget ignora link solo-hash, target != _self, download, rel=external, origini diverse; main ha tabindex=-1.
- Base path: normalizePath(url, base)/withBase, BASE da import.meta.env.BASE_URL (registry.ts), usati per href, pushState, popstate.
- Navigazione: nessun pushState duplicato, scroll a inizio pagina con scrollBehavior(); timer announce() cancellati; 404 built-in; errore di import con "Riprova" e titolo aggiornato; warn dev sui duplicati; campo order.
- Verifiche: vitest 20/20, svelte-check 0 errori, build OK.
