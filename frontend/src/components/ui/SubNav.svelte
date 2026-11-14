<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Sotto-barra smerigliata e sticky delle pagine strumento: h1 della pagina e, subito a destra, l'interruttore
  "Learning | Avanzato" (stessa posizione su ogni pagina; `mode={false}` dove non cambia nulla); stato/azioni a destra
  (slot `aside`). Dentro un contenitore con schede (shell/Hub.svelte) l'h1 è il titolo del contenitore ("Simula", con
  il titolo della pagina ospitata nel nome accessibile: "Simula – Scena lander") e sotto compaiono le schede. `learn`: la frase "Cosa stai
  guardando" mostrata sotto la barra solo in Learning. È l'unico posto, con la barra degli strumenti del
  visualizzatore, dove si usa il backdrop blur.
-->
<script lang="ts">
  import { getContext, type Snippet } from 'svelte';
  import ModeSwitch from '../../shell/ModeSwitch.svelte';
  import { t } from '../../i18n/i18n.svelte';
  import { modeNow } from '../../shell/modeState.svelte';
  import { HUB_KEY, type HubCtx } from '../../shell/hub';

  let {
    title,
    tone = 'auto',
    mode: withMode = true,
    learn,
    aside,
    toolbar,
  }: { title: string; tone?: 'auto' | 'dark'; mode?: boolean; learn?: string; aside?: Snippet; toolbar?: Snippet } = $props();

  const hub = getContext<HubCtx | undefined>(HUB_KEY);

  function onTabKey(e: KeyboardEvent) {
    if (!hub || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const btns = [...(e.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]')];
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    const rtl = getComputedStyle(e.currentTarget as HTMLElement).direction === 'rtl';
    const step = (e.key === 'ArrowRight') !== rtl ? 1 : -1;
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? btns.length - 1 : (i + step + btns.length) % btns.length;
    btns[next]?.focus();
  }
</script>

<div class="subnav" class:tone-dark={tone === 'dark'}>
  <div class="container container--wide subnav-inner">
    <div class="subnav-head">
      <h1 class="subnav-title">
        {#if hub}{hub.title}<span class="visually-hidden"> – {title}</span>{:else}{title}{/if}
      </h1>
      {#if withMode}<ModeSwitch />{/if}
    </div>
    {#if (hub && hub.tabs.length > 1) || toolbar}
      <div class="subnav-tools">
        {#if hub && hub.tabs.length > 1}
          <!-- svelte-ignore a11y_interactive_supports_focus -->
          <div class="hub-tabs" role="tablist" aria-label={hub.label} onkeydown={onTabKey}>
            {#each hub.tabs as t (t.id)}
              <button
                type="button"
                role="tab"
                id="hub-tab-{t.id}"
                aria-selected={hub.active === t.id}
                tabindex={hub.active === t.id ? 0 : -1}
                onclick={() => hub.select(t.id)}>{t.label}</button
              >
            {/each}
          </div>
        {/if}
        {#if toolbar}{@render toolbar()}{/if}
      </div>
    {/if}
    {#if aside}<div class="subnav-aside">{@render aside()}</div>{/if}
  </div>
</div>
{#if learn && !modeNow.advanced}
  <div class="learn">
    <div class="container container--wide"><p data-testid="learn-line"><strong>{t('mode.whatYouSee')}</strong> {learn}</p></div>
  </div>
{/if}

<style>
  .subnav {
    position: sticky;
    top: 0;
    z-index: 50;
    color: var(--c-text);
    background: var(--c-bg);
    border-bottom: 1px solid var(--c-hairline);
    box-shadow: 0 8px 26px rgb(0 0 0 / 0.12);
  }
  @supports ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
    .subnav {
      background: var(--c-frost);
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      backdrop-filter: saturate(180%) blur(20px);
    }
  }
  .subnav-inner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-3);
    min-height: var(--subnav-h);
    padding-block: var(--space-1);
  }
  .subnav-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-3);
    min-inline-size: 0;
  }
  .subnav-title {
    margin: 0;
    font-size: var(--fs-body);
    font-stretch: var(--wdth-heading);
    letter-spacing: -0.015em;
  }
  /* testo della barra solo in --c-text: la barra è traslucida e il contrasto deve reggere su qualunque
     sfondo scorra sotto (verificato in contrast.test.ts su nero e bianco) */
  .subnav-aside :global(.status-pill) {
    color: var(--c-text);
  }
  .subnav-aside {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
    margin-inline-start: auto;
  }
  .subnav-tools {
    display: flex;
    flex: 1 1 24rem;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
  }
  .hub-tabs {
    display: flex;
    flex: none;
    gap: var(--space-1);
  }
  .hub-tabs button {
    padding-inline: 0.75rem;
    white-space: nowrap;
    border-color: transparent;
    color: var(--c-text);
    font-size: var(--fs-small);
  }
  .hub-tabs button[aria-selected='true'] {
    background: var(--c-text);
    color: var(--c-bg);
    font-weight: 600;
  }
  .learn {
    background: var(--c-bg-alt);
    color: var(--c-text);
  }
  .learn p {
    margin: 0;
    padding-block: var(--space-1);
    font-size: var(--fs-small);
  }
</style>
