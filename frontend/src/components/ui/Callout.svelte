<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Nota in evidenza dentro il flusso. kind: 'note' (informazione) | 'warning' (rischio per l'utente).
  Non è una regione live: per messaggi dinamici usare role="status"/"alert" nel chiamante.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    kind = 'note',
    title,
    id,
    children,
  }: { kind?: 'note' | 'warning'; title?: string; id?: string; children: Snippet } = $props();
</script>

<div class="callout" data-kind={kind} {id}>
  {#if title}<p class="callout-title">{title}</p>{/if}
  <div class="callout-body">{@render children()}</div>
</div>

<style>
  .callout {
    border-inline-start: 3px solid var(--c-link);
    background: var(--c-raised);
    border-radius: 0;
    border-start-end-radius: var(--radius-md);
    border-end-end-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    margin: 0 0 var(--space-4);
  }
  .callout[data-kind='warning'] {
    border-inline-start-color: var(--c-power);
  }
  .callout-title {
    font-weight: 600;
    margin: 0 0 var(--space-1);
  }
  .callout-body :global(p:last-child) {
    margin-bottom: 0;
  }
</style>
