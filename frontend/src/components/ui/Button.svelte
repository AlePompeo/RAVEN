<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Nessuno spread di attributi ({...rest}) di proposito: costerebbe ~7 KB di runtime nel chunk iniziale.
  Pulsante a pillola. Con `href` è un link (navigazione), senza è un <button> (azione).
  variant: 'primary' (pieno, una sola azione principale per vista) | 'ghost' (bordo).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    variant = 'primary',
    size = 'md',
    href,
    type = 'button',
    disabled = false,
    pressed,
    class: extra = '',
    onclick,
    describedby,
    children,
  }: {
    variant?: 'primary' | 'ghost';
    size?: 'md' | 'lg';
    href?: string;
    type?: 'button' | 'submit' | 'reset';
    /** Reso come aria-disabled: il pulsante resta focalizzabile e annunciato. */
    disabled?: boolean;
    pressed?: boolean;
    class?: string;
    onclick?: (e: MouseEvent) => void;
    /** id dell'elemento che descrive il pulsante (aria-describedby). */
    describedby?: string;
    children: Snippet;
  } = $props();

  const cls = $derived(['btn', variant === 'primary' ? 'btn--primary' : 'btn--ghost', size === 'lg' ? 'btn--lg' : '', extra].filter(Boolean).join(' '));

  function handle(e: MouseEvent) {
    if (disabled) {
      e.preventDefault();
      return;
    }
    onclick?.(e);
  }
</script>

{#if href}
  <a class={cls} {href} {onclick} aria-describedby={describedby}>{@render children()}</a>
{:else}
  <button class={cls} {type} aria-disabled={disabled ? 'true' : undefined} aria-pressed={pressed} aria-describedby={describedby} onclick={handle}
    >{@render children()}</button
  >
{/if}
