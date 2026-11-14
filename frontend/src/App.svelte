<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import type { Component } from 'svelte';
  import { router, BASE } from './registry';
  import { setTitle, focusMainHeading, announce, scrollBehavior } from './shell/a11y';
  import { navPages, normalizePath, redirectTo, withBase } from './shell/router';
  import { linkTarget } from './shell/links';
  import { pageIdFor } from './shell/pageContext.svelte';
  import { t, syncLangFromUrl, ensurePages } from './i18n/i18n.svelte';
  import type { PageModule } from './shell/router';

  const titleOf = (p: PageModule) => (p.titleKey ? t(p.titleKey) : (p.title ?? ''));

  // percorso corrente; una vecchia rotta (alias) viene sostituita nell'URL dalla nuova, query e hash conservati
  function current(): string {
    const r = router.resolve(location.pathname)?.redirect;
    if (r) history.replaceState(history.state, '', withBase(redirectTo(r, location.search, location.hash), BASE));
    return normalizePath(location.pathname, BASE);
  }
  let path = $state(current());
  let Current = $state<Component<any> | null>(null);
  let GlobalNav = $state<Component<{ pages: PageModule[]; path: string; base: string; open?: boolean }> | null>(null);
  let navPromise: Promise<void> | null = null;
  function loadNav(): Promise<void> {
    navPromise ??= import('./shell/GlobalNav.svelte').then((module) => { GlobalNav = module.default; }).catch((error: unknown) => {
      navPromise = null;
      throw error;
    });
    return navPromise;
  }
  let ExplainButton = $state<Component<{ pageId: string; inert?: boolean; dark?: boolean }> | null>(null);
  let explainFailed = $state(false);
  const explainLoaded = import('./shell/ExplainButton.svelte')
    .then((module) => { ExplainButton = module.default; })
    .catch(() => { explainFailed = true; });
  let failed = $state(false);
  let attempt = $state(0);
  let first = true;
  let announcer: HTMLElement | undefined = $state();
  let main: HTMLElement | undefined = $state();

  let menuOpen = $state(false);
  // segnale di prontezza per i test: true dopo il primo rendering concluso della rotta (nessun focus né annuncio prima)
  let routeReady = $state(false);

  // RAVEN SI is available on every known route, including /chat.
  const pageId = $derived(pageIdFor(path));
  const showExplain = $derived(!!router.resolve(path));

  const mainPages = navPages(router.pages(), 'main');
  const legalPages = navPages(router.pages(), 'legal');

  $effect(() => {
    attempt; // dipendenza per il "Riprova"
    const page = router.resolve(path);
    let cancelled = false;
    failed = false;
    if (!page) {
      Current = null;
      return;
    }
    // il chunk della pagina e le stringhe inglesi delle pagine (en.pages.json) in parallelo; ensurePages non rifiuta mai
    Promise.all([page.load(), ensurePages(), explainLoaded, loadNav()])
      .then(async ([m]) => {
        if (cancelled) return;
        Current = m.default;
        await tick();
        afterRender(titleOf(page));
      })
      .catch(() => {
        if (cancelled) return;
        Current = null;
        failed = true;
        void tick().then(() => afterRender(t('shell.loadErrorTitle')));
      });
    return () => {
      cancelled = true;
    };
  });

  // titolo del documento: segue la rotta e la lingua (effetto separato: il cambio di lingua non ricarica la pagina)
  $effect(() => {
    const page = router.resolve(path);
    setTitle(page ? titleOf(page) : t('shell.notFoundTitle'));
  });

  // un link interno con ?lang= vince sulla scelta in memoria (come ?mode=)
  $effect(() => {
    path;
    untrack(() => void syncLangFromUrl());
  });

  function afterRender(label: string) {
    if (first) {
      first = false;
      routeReady = true;
      return;
    }
    let anchor: HTMLElement | null = null;
    try {
      anchor = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    } catch {
      // Un frammento non valido non impedisce la navigazione.
    }
    if (anchor) {
      anchor.scrollIntoView?.({ behavior: scrollBehavior() });
      anchor.focus();
    } else {
      window.scrollTo?.({ top: 0, left: 0, behavior: scrollBehavior() });
      focusMainHeading(main);
    }
    announce(t('shell.pageAnnounce', { title: label }), announcer ?? null);
  }

  function navigate(url: string) {
    const cur = location.pathname + location.search;
    const next = new URL(url, location.origin);
    const same = next.pathname + next.search === cur;
    if (!same) history.pushState({}, '', url);
    const before = path;
    path = current();
    // stessa rotta con un'altra query (es. /compare?site= dalla scheda Globo di /siti): la pagina la rilegge (Hub)
    if (!same && path === before) dispatchEvent(new PopStateEvent('popstate'));
    // stessa pagina: l'effetto non riparte, quindi solo scroll
    if (same) window.scrollTo?.({ top: 0, left: 0, behavior: scrollBehavior() });
  }

  function onClick(e: MouseEvent) {
    const url = linkTarget(e, location);
    if (url === null) return;
    e.preventDefault();
    navigate(url);
  }
</script>

<svelte:window onclick={onClick} onpopstate={() => (path = current())} />

<a class="skip-link" href="#main" inert={menuOpen}>{t('shell.skip')}</a>

{#if GlobalNav}<GlobalNav pages={mainPages} path={router.resolve(path)?.section ?? path} base={BASE} bind:open={menuOpen} />{:else}<div class="nav-slot" aria-hidden="true"></div>{/if}

<main id="main" tabindex="-1" bind:this={main} inert={menuOpen} class:tone-dark={path !== '/'} class:interior={path !== '/'} data-route-ready={routeReady ? "1" : undefined}>
  {#if failed}
    <div class="doc tile">
      <div class="container">
        <h1>{t('shell.loadErrorTitle')}</h1>
        <p role="alert">{t('shell.loadErrorText')}</p>
        <button type="button" class="btn--primary" onclick={() => attempt++}>{t('shell.retry')}</button>
      </div>
    </div>
  {:else if Current}
    <Current />
  {/if}
  <!-- rotte inesistenti: la pagina /404 del registro (pages/404, chunk lazy), risolta da routerFromModules -->

</main>

<footer class="site-footer tile--alt" class:tone-dark={path !== '/'} inert={menuOpen}>
  <div class="container container--wide footer-inner">
    <nav aria-label={t('nav.legal')}>
      <ul>
        {#each legalPages as p (p.path)}
          <li>
            <a href={withBase(p.path, BASE)} aria-current={normalizePath(p.path) === path ? 'page' : undefined}>{p.navKey ? t(p.navKey) : p.navLabel}</a>
          </li>
        {/each}
      </ul>
    </nav>
    <p>{t('footer.license')}</p>
  </div>
</footer>

{#if showExplain && ExplainButton}<ExplainButton {pageId} inert={menuOpen} dark={path !== '/'} />
{:else if showExplain && explainFailed}<p role="status">{t('explain.fail')}</p>{/if}

<div id="announcer" class="visually-hidden" aria-live="polite" aria-atomic="true" bind:this={announcer}></div>

<style>
  /* riserva lo spazio della barra finché il suo chunk non arriva: l'inserimento non sposta contenuto e piè di pagina (CLS) */
  .nav-slot {
    height: calc(var(--nav-h) + 1px);
  }
  .site-footer {
    background: var(--c-bg-alt);
    color: var(--c-muted);
    font-size: var(--fs-small);
    border-top: 1px solid var(--c-hairline);
  }
  .site-footer.tone-dark {
    background: #080e19;
    border-color: #405268;
  }
  .footer-inner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-5);
    padding-top: var(--space-4);
    /* Reserve space for the persistent RAVEN SI launcher. */
    padding-bottom: calc(var(--target) + var(--space-4) + var(--space-3) + env(safe-area-inset-bottom));
  }
  .footer-inner p {
    margin: 0;
  }
  ul {
    display: flex;
    flex-wrap: wrap;
    list-style: none;
    margin: 0;
    margin-inline-start: -0.6rem;
    padding: 0;
  }
  a {
    display: inline-flex;
    align-items: center;
    min-height: var(--target);
    padding: 0 0.6rem;
    color: var(--c-text);
    text-decoration: none;
  }
  a:hover,
  a[aria-current='page'] {
    text-decoration: underline;
  }
</style>
