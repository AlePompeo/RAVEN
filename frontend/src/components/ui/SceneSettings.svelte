<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { t } from '../../i18n/i18n.svelte';

  let { children }: { children: Snippet } = $props();
  let open = $state(window.matchMedia('(min-width: 900px)').matches);
  const id = 'scene-settings-panel';
  let root: HTMLElement;
  let toggle: HTMLButtonElement;

  onMount(() => {
    const wide = window.matchMedia('(min-width: 900px)');
    const resize = (e: MediaQueryListEvent) => {
      if (!e.matches) open = false;
    };
    wide.addEventListener('change', resize);
    return () => wide.removeEventListener('change', resize);
  });

  function onKey(e: KeyboardEvent) {
    if (e.defaultPrevented || e.key !== 'Escape' || !open || !root.contains(document.activeElement)) return;
    e.preventDefault();
    open = false;
    toggle.focus();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="scene-controls" data-open={open ? 'true' : 'false'} bind:this={root}>
  <div class="scene-drawer-clip">
    <div class="scene-drawer" id={id} inert={!open} aria-hidden={!open}>
      <h2 class="scene-drawer-title">{t('scene.controls')}</h2>
      {@render children()}
    </div>
  </div>
  <button type="button" class="scene-drawer-toggle" aria-label={t('scene.controls')} aria-expanded={open} aria-controls={id} onclick={() => (open = !open)} bind:this={toggle}>
    <span aria-hidden="true">☰</span>
  </button>
</div>
