<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { downloadText } from './grazing';

  let { name, csv, json }: { name: string; csv: () => string; json: () => string } = $props();
</script>

<p class="export">
  <button type="button" onclick={() => downloadText(`${name}.csv`, 'text/csv', csv())}>Scarica CSV</button>
  <button type="button" onclick={() => downloadText(`${name}.json`, 'application/json', json())}>Scarica JSON</button>
</p>

<style>
  .export {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
  }
</style>
