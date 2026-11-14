<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Conferma del download del terreno: "Questo sito richiede circa X MB di dati di terreno". Nessun dato viene scaricato
  finche' l'utente non conferma; il server scarica solo le tessere vicine al sito, dall'URL fisso del nodo PDS.
-->
<script lang="ts">
  import { t } from '../i18n/i18n.svelte';
  import { modal } from './modal';
  import type { TerrainEstimate } from './ravenApi';

  let { estimate, decide }: { estimate: TerrainEstimate; decide: (yes: boolean) => void } = $props();
  const need = $derived(estimate.sites.filter((s) => s.tiles_to_download > 0));
  const num = (x: number | null, d = 0) => (x === null ? '' : x.toFixed(d));
</script>

<div class="overlay" role="presentation">
  <div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="tp-title" aria-describedby="tp-body" use:modal={{ onClose: () => decide(false) }} data-testid="terrain-prompt">
    <h2 id="tp-title">{t('custom.prompt.title')}</h2>
    <div id="tp-body">
      <p><strong data-testid="terrain-prompt-mb">{t('custom.prompt.total').replace('{mb}', estimate.mb_to_download.toFixed(1))}</strong></p>
      <ul>
        {#each need as s (s.id)}
          <li>{t('custom.prompt.site').replace('{name}', s.name).replace('{mb}', num(s.mb_to_download, 1)).replace('{res}', num(s.resolution_m))}</li>
        {/each}
      </ul>
      <p>{t('custom.prompt.how')}</p>
      <p>{t('custom.prompt.cache').replace('{max}', String(estimate.cache.max_mb))}</p>
    </div>
    <div class="buttons">
      <button type="button" data-autofocus onclick={() => decide(false)} data-testid="terrain-cancel">{t('custom.prompt.cancel')}</button>
      <button type="button" onclick={() => decide(true)} data-testid="terrain-confirm">{t('custom.prompt.confirm').replace('{mb}', estimate.mb_to_download.toFixed(1))}</button>
    </div>
  </div>
</div>

<style>
  .overlay { position: fixed; inset: 0; display: grid; place-items: center; background: rgba(0, 0, 0, 0.55); z-index: 1000; }
  .dialog { background: var(--bg, #fff); color: var(--fg, #111); padding: 1.2rem; max-width: 30rem; width: calc(100% - 2rem); border-radius: 0.5rem; display: grid; gap: 0.5rem; }
  .buttons { display: flex; gap: 0.6rem; justify-content: flex-end; }
</style>
