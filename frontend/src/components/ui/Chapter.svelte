<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Capitolo di un racconto a scorrimento: tile a tutta larghezza con titolo (h2), lead facoltativo, contenuto
  e uno slot `media` a filo sotto il testo (es. MediaFrame con fx="settle"). Il testo non si anima mai.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Tile from './Tile.svelte';

  let {
    id,
    title,
    lead,
    tone = 'auto',
    width = 'text',
    headingLevel = 2,
    children,
    media,
  }: {
    id: string;
    title: string;
    lead?: string;
    tone?: 'auto' | 'alt' | 'dark';
    width?: 'text' | 'wide';
    headingLevel?: 2 | 3;
    children?: Snippet;
    media?: Snippet;
  } = $props();
</script>

<Tile {tone} width="full" labelledby="{id}-h" {id} class="chapter{media ? ' chapter--media' : ''}">
  <div class="container" class:container--wide={width === 'wide'}>
    {#if headingLevel === 3}
      <h3 id="{id}-h" class="chapter-title">{title}</h3>
    {:else}
      <h2 id="{id}-h" class="chapter-title">{title}</h2>
    {/if}
    {#if lead}<p class="lead chapter-lead">{lead}</p>{/if}
    {#if children}{@render children()}{/if}
  </div>
  {#if media}
    <div class="chapter-media">{@render media()}</div>
  {/if}
</Tile>

<style>
  :global(.chapter--media) {
    padding-bottom: var(--space-5);
  }
  .chapter-title {
    font-size: var(--fs-h2);
    font-stretch: var(--wdth-heading);
    max-width: 18ch;
  }
  .chapter-lead {
    max-width: 44ch;
    margin-bottom: var(--space-5);
  }
  .chapter-media {
    margin-top: var(--space-5);
  }
</style>
