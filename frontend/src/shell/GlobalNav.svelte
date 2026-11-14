<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Barra globale nera da 44px. Sotto 834px i link passano in un pannello a tutto schermo aperto dal
  pulsante "Menu" (aria-expanded/aria-controls, Esc chiude e ridà il focus, il resto della pagina è inert
  tramite `open` legato dalla shell).
-->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import type { PageModule } from './router';
  import { normalizePath, withBase } from './router';
  import { t } from '../i18n/i18n.svelte';
  import LanguageSwitch from './LanguageSwitch.svelte';
  import { scenarioStore, withScenario, type Scenario } from './scenario';
  import ravenMark from '../assets/media/raven-mark.webp?no-inline';
  import ravenWordmark from '../assets/media/raven-wordmark.webp?no-inline';

  let {
    pages,
    path,
    base = '/',
    open = $bindable(false),
  }: { pages: PageModule[]; path: string; base?: string; open?: boolean } = $props();

  const MOBILE = '(max-width: 833px)';
  let toggle: HTMLButtonElement | undefined = $state();
  let list: HTMLUListElement | undefined = $state();
  const store = scenarioStore();
  let scenario = $state<Scenario>(store.reload());
  $effect(() => store.subscribe((s) => (scenario = s)));
  $effect(() => {
    path;
    untrack(() => store.reload());
  });
  function reloadScenario() {
    store.reload();
  }

  async function setOpen(next: boolean, restoreFocus = true) {
    if (open === next) return;
    open = next;
    document.documentElement.classList.toggle('menu-open', next);
    await tick();
    if (next) list?.querySelector('a')?.focus();
    else if (restoreFocus) toggle?.focus();
  }

  // chiude alla navigazione (cambio di percorso) senza rubare il focus all'h1 della nuova pagina
  $effect(() => {
    path;
    untrack(() => void setOpen(false, false));
  });

  $effect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(MOBILE);
    const onChange = () => {
      if (!mql.matches) void setOpen(false, false);
    };
    mql.addEventListener('change', onChange);
    return () => {
      mql.removeEventListener('change', onChange);
      document.documentElement.classList.remove('menu-open');
    };
  });

  function onKeydown(e: KeyboardEvent) {
    if (open && e.key === 'Escape') {
      e.preventDefault();
      void setOpen(false);
    }
  }
</script>

<svelte:window onkeydown={onKeydown} onpopstate={reloadScenario} />

<header class="global-nav tone-dark" data-open={open}>
  <div class="bar">
    <a class="brand" href={withBase('/', base)}>
      <img class="mark" src={ravenMark} alt="" width="44" height="22" />
      <img class="wordmark" src={ravenWordmark} alt="" width="882" height="99" />
      <span class="visually-hidden">RAVEN</span>
    </a>
    <button
      bind:this={toggle}
      class="menu-toggle"
      type="button"
      aria-expanded={open}
      aria-controls="global-nav-panel"
      onclick={() => setOpen(!open)}
    >
      <span class="menu-icon" aria-hidden="true"></span>
      {t('nav.menu')}
    </button>
    <!-- sotto 834 px il pannello a tutto schermo contiene i link e, in fondo, il selettore della lingua -->
    <div class="nav-panel" id="global-nav-panel">
      <nav aria-label={t('nav.main')}>
        <ul id="global-nav-list" bind:this={list}>
          {#each pages as p (p.path)}
            <li>
              <a href={withBase(p.path === '/' || p.path === '/contacts' || p.path === '/pricing' ? p.path : withScenario(p.path, scenario), base)} aria-current={normalizePath(p.path) === path ? 'page' : undefined}>{p.navKey ? t(p.navKey) : p.navLabel}</a>
            </li>
          {/each}
        </ul>
      </nav>
      <LanguageSwitch />
    </div>
  </div>
</header>

<style>
  .global-nav {
    position: relative;
    z-index: 100;
    background: linear-gradient(110deg, #03060c, #0b1422 55%, #03060c);
    color: var(--c-text);
    border-bottom: 1px solid rgb(139 185 231 / 0.18);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    height: var(--nav-h);
    max-width: calc(var(--content-wide) + 2 * var(--gutter));
    margin-inline: auto;
    padding-inline: var(--gutter);
  }
  a.brand {
    padding: 0;
    color: var(--c-text);
    display: inline-flex;
    align-items: center;
    gap: 0.7rem;
    margin: 0;
    margin-inline-end: auto;
    white-space: nowrap;
  }
  .mark {
    width: 44px;
    height: 22px;
    object-fit: contain;
    mix-blend-mode: screen;
  }
  .wordmark {
    display: block;
    width: 83px;
    height: auto;
  }
  .nav-panel {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-inline-size: 0;
  }
  ul {
    display: flex;
    gap: var(--space-1);
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li { display: flex; }
  a {
    display: inline-flex;
    align-items: center;
    min-height: var(--target);
    /* voci corte ("Siti"): bersaglio di almeno 44 px anche in larghezza (puntatore grossolano) */
    min-inline-size: var(--target);
    justify-content: center;
    padding: 0 0.75rem;
    color: #c9d4e1;
    font-size: var(--fs-small);
    text-decoration: none;
    white-space: nowrap;
  }
  a:hover {
    color: var(--c-text);
  }
  a {
    position: relative;
  }
  a[aria-current='page'] {
    color: var(--c-text);
  }
  /* voce attiva: un punto sotto il testo (non una sottolineatura) */
  a[aria-current='page']::after {
    content: '';
    position: absolute;
    left: 50%;
    bottom: 6px;
    width: 4px;
    height: 4px;
    margin-left: -2px;
    border-radius: 50%;
    background: #8bc7ff;
    box-shadow: 0 0 8px #65b6ff;
  }
  @media (max-width: 1199px) {
    /* sotto 1200 px le voci restano su una riga senza scorrere in orizzontale */
    .bar {
      gap: var(--space-3);
    }
    a {
      padding-inline: 0.5rem;
    }
  }
  a:focus-visible {
    outline-offset: -4px;
    border-radius: var(--radius-sm);
  }
  .menu-toggle {
    display: none;
  }

  @media (max-width: 833px) {
    .bar {
      gap: var(--space-3);
    }
    .menu-toggle {
      display: inline-flex;
      min-height: var(--target);
      margin-block: 0;
      white-space: nowrap;
      padding: 0 0.9rem;
      border: 0;
      color: var(--c-text);
      background: transparent;
      font-size: var(--fs-small);
      gap: 0.6rem;
    }
    .menu-toggle:focus-visible {
      outline-offset: 0;
    }
    .menu-icon {
      position: relative;
      width: 16px;
      height: 10px;
    }
    .menu-icon::before,
    .menu-icon::after {
      content: '';
      position: absolute;
      left: 0;
      right: 0;
      height: 1.5px;
      background: currentColor;
      border-radius: 1px;
      transition: transform var(--dur-ui) var(--ease-out);
    }
    .menu-icon::before {
      top: 1px;
    }
    .menu-icon::after {
      bottom: 1px;
    }
    [data-open='true'] .menu-icon::before {
      transform: translateY(3.5px) rotate(45deg);
    }
    [data-open='true'] .menu-icon::after {
      transform: translateY(-3.5px) rotate(-45deg);
    }
    .nav-panel {
      display: none;
    }
    [data-open='true'] .nav-panel {
      display: block;
      position: fixed;
      inset: var(--nav-h) 0 0 0;
      background: #080f1c;
      overflow-y: auto;
      padding: var(--space-4) var(--gutter) var(--space-6);
      animation: menu-in var(--dur-ui) var(--ease-out);
    }
    ul {
      flex-direction: column;
      gap: 0;
    }
    nav a {
      width: 100%;
      min-height: 56px;
      padding: 0;
      font-size: 1.75rem;
      font-weight: 600;
      font-stretch: var(--wdth-heading);
      letter-spacing: -0.02em;
      color: var(--c-text);
    }
    a[aria-current='page']::after {
      left: auto;
      inset-inline-end: 0;
      bottom: 50%;
      width: 8px;
      height: 8px;
      margin: 0 0 -4px;
    }
  }

  @keyframes menu-in {
    from {
      transform: translateY(-8px);
    }
    to {
      transform: none;
    }
  }
</style>
