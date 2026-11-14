<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Controllo "Sito personalizzato", uguale in ogni pagina che sceglie un sito. Qui solo il pulsante (pochi byte); il pannello
  con i campi, il globo e la stima del terreno e' un chunk caricato al primo clic.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../i18n/i18n.svelte';
  import { customSites } from './customSites';

  let { onadd }: { onadd?: (id: string) => void } = $props();
  let shown = $state(false);
  let n = $state(customSites.get().length);
  onMount(() => {
    return customSites.subscribe((l) => { n = l.length; });
  });
</script>

<div class="cs-control">
  <button type="button" class="cs-toggle" aria-expanded={shown} aria-controls="custom-panel-host" onclick={() => (shown = !shown)} data-testid="custom-toggle">
    {t('custom.toggle')}{n > 0 ? ` (${n})` : ''}
  </button>
  <div id="custom-panel-host" hidden={!shown}>
    {#if shown}
      {#await import('./CustomSitePanel.svelte')}
        <p role="status">{t('custom.loading')}</p>
      {:then m}
        <m.default {onadd} />
      {:catch}
        <p role="alert">{t('custom.loadFailed')}</p>
      {/await}
    {/if}
  </div>
</div>

<style>
  .cs-control { display: grid; gap: 0.5rem; margin: 0.5rem 0; }
</style>
