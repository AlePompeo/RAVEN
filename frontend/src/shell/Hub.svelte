<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Contenitore con schede (Simula, Siti): carica in modo lazy la pagina esistente della scheda attiva (?tab=) e
  passa titolo e schede alla sua SubNav via contesto (un solo h1, l'interruttore di modalità sempre nello stesso
  posto). Cambiare scheda aggiorna ?tab= con replaceState e conserva gli altri parametri (scenario, mode).
-->
<script lang="ts">
  import { setContext, tick, untrack } from 'svelte';
  import type { Component } from 'svelte';
  import SubNav from '../components/ui/SubNav.svelte';
  import { focusMainHeading } from './a11y';
  import { HUB_KEY, pickTab, searchWithTab, type HubCtx, type HubTab } from './hub';

  let { title, label, tabs, loading }: { title: string; label: string; tabs: readonly HubTab[]; loading: string } = $props();

  let active = $state(untrack(() => pickTab(location.search, tabs)));
  const tab = $derived(tabs.find((t) => t.id === active) ?? tabs[0]!);
  let Current = $state.raw<Component<any> | null>(null);
  let failed = $state(false);
  let refocus = false;

  $effect(() => {
    const t = tab;
    let cancelled = false;
    Current = null;
    failed = false;
    t.load()
      .then(async (m) => {
        if (cancelled) return;
        // l'h1 provvisorio può avere il focus dato dalla shell dopo la navigazione: passa al nuovo h1
        const onH1 = document.activeElement?.tagName === 'H1';
        Current = m.default;
        await tick();
        if (refocus) {
          refocus = false;
          document.getElementById(`hub-tab-${t.id}`)?.focus();
        } else if (onH1) focusMainHeading(document.getElementById('main') ?? document);
      })
      .catch(() => {
        if (!cancelled) failed = true;
      });
    return () => {
      cancelled = true;
    };
  });

  function select(id: string) {
    if (id === active || !tabs.some((t) => t.id === id)) return;
    refocus = true;
    active = id;
    try {
      history.replaceState(history.state, '', `${location.pathname}${searchWithTab(location.search, id)}${location.hash}`);
    } catch {
      /* ambiente senza History API */
    }
  }

  const ctx: HubCtx = {
    get title() {
      return title;
    },
    get label() {
      return label;
    },
    get tabs() {
      return tabs;
    },
    get active() {
      return active;
    },
    select,
  };
  setContext(HUB_KEY, ctx);
</script>

<!-- un link interno verso la stessa rotta con un'altra query (la shell emette popstate), o Indietro/Avanti -->
<svelte:window onpopstate={() => (active = pickTab(location.search, tabs))} />

{#if Current}
  {#if tab.header}<SubNav title={tab.title} learn={tab.learn} />{/if}
  <div class="hub-panel" data-tab={tab.id}><Current /></div>
{:else}
  <SubNav title={tab.title} learn={tab.learn} />
  <div class="container container--wide hub-wait">
    {#if failed}<p role="alert">{loading}</p>{:else}<p role="status">…</p>{/if}
  </div>
{/if}

<style>
  .hub-wait {
    padding-block: var(--space-5);
  }
</style>
