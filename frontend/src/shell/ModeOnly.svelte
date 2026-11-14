<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Mostra il contenuto solo nella modalità indicata: <ModeOnly mode="avanzato">...</ModeOnly>. Non cambia i numeri. -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { Mode } from './mode';
  import { modeNow } from './modeState.svelte';

  let { mode: want, children }: { mode: Mode; children: Snippet } = $props();
</script>

{#if modeNow.current === want}{@render children()}{/if}
