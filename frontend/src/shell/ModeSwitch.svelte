<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Interruttore "Learning | Avanzato" (docs/design/grazinglink-ux.md): due pulsanti con aria-pressed in un gruppo
  etichettato "Modalità", frecce sinistra/destra per passare dall'uno all'altro, bersagli da 44 px, annuncio del
  cambio nella regione aria-live della shell (#announcer). Larghezza fissa: il cambio non sposta nulla intorno.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { MODES, modeStore, type Mode } from './mode';
  import { t } from '../i18n/i18n.svelte';

  const label = (m: Mode) => t(m === 'learning' ? 'mode.learning' : 'mode.advanced');
  import { modeNow } from './modeState.svelte';
  import { announce } from './a11y';

  const mode = modeStore();

  let group: HTMLElement | undefined = $state();

  // un link con ?mode= (anche dentro l'app, senza ricaricare) vince sulla scelta in memoria
  onMount(() => void mode.sync());

  function pick(m: Mode) {
    if (m === mode.get()) return;
    mode.set(m);
    announce(t('mode.changed', { mode: label(m) }));
  }

  function onKey(e: KeyboardEvent) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    // due soli pulsanti: ogni freccia passa all'altro (vale anche in RTL)
    const m: Mode = mode.get() === 'learning' ? 'avanzato' : 'learning';
    pick(m);
    group?.querySelector<HTMLButtonElement>(`[data-mode="${m}"]`)?.focus();
  }
</script>

<div class="mode-switch" role="group" aria-label={t('mode.group')} bind:this={group} data-testid="mode-switch">
  {#each MODES as m (m)}
    <button type="button" data-mode={m} aria-pressed={modeNow.current === m} onclick={() => pick(m)} onkeydown={onKey}>{label(m)}</button>
  {/each}
</div>

<style>
  .mode-switch {
    display: inline-flex;
    flex: none;
    padding: 2px;
    border: 1px solid var(--c-hairline);
    border-radius: var(--radius-pill);
    background: var(--c-bg);
  }
  button {
    min-block-size: var(--target);
    min-inline-size: 5.25rem;
    padding-block: 0;
    padding-inline: 0.65rem;
    border: 0;
    font-size: var(--fs-small);
    color: var(--c-text);
  }
  button[aria-pressed='true'] {
    background: var(--c-text);
    color: var(--c-bg);
    font-weight: 600;
  }
  button:focus-visible {
    outline-offset: -3px;
  }
</style>
