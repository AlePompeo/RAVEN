<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Banda a tutta larghezza (<section> se ha un nome, altrimenti <div>). tone: 'auto' (segue prefers-color-scheme), 'alt' (superficie alternata dello
  schema), 'dark' (sempre scura). width: colonna di testo, larga, o piena (nessun contenitore interno).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    tone = 'auto',
    width = 'text',
    flush = false,
    labelledby,
    label,
    id,
    class: extra = '',
    children,
  }: {
    tone?: 'auto' | 'alt' | 'dark';
    width?: 'text' | 'wide' | 'full';
    /** Senza padding verticale (per media a filo). */
    flush?: boolean;
    labelledby?: string;
    label?: string;
    id?: string;
    class?: string;
    children: Snippet;
  } = $props();

  const cls = $derived(
    ['tile', tone === 'alt' ? 'tile--alt' : '', tone === 'dark' ? 'tone-dark' : '', flush ? 'tile--flush' : '', extra]
      .filter(Boolean)
      .join(' '),
  );
</script>

{#snippet body()}
  {#if width === 'full'}
    {@render children()}
  {:else}
    <div class="container" class:container--wide={width === 'wide'}>
      {@render children()}
    </div>
  {/if}
{/snippet}

<!-- <section> solo se etichettata (landmark region con nome), altrimenti <div>. Niente <svelte:element>:
     trascinerebbe nel chunk iniziale il runtime degli attributi dinamici. -->
{#if labelledby || label}
  <section {id} class={cls} data-tone={tone} aria-labelledby={labelledby} aria-label={label}>{@render body()}</section>
{:else}
  <div {id} class={cls} data-tone={tone}>{@render body()}</div>
{/if}
