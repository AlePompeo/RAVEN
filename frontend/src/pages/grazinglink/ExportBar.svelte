<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { downloadText } from './grazing';
  import { t } from '../../i18n/i18n.svelte';

  let { name, csv, json }: { name: string; csv: () => string; json: () => string } = $props();
</script>

<p class="export">
  <button type="button" onclick={() => downloadText(`${name}.csv`, 'text/csv', csv())}>{t('analysis.downloadCsv')}</button>
  <button type="button" onclick={() => downloadText(`${name}.json`, 'application/json', json())}>{t('analysis.downloadJson')}</button>
</p>

<style>
  .export {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
  }
</style>
