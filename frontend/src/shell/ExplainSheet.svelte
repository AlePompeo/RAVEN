<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { modal } from './modal';
  import Chat from '../pages/chat/Chat.svelte';
  let { pageId, onClose }: { pageId: string; onClose: () => void } = $props();
</script>

<div class="overlay" role="dialog" aria-modal="true" aria-label="RAVEN SI" use:modal={{ onClose }}>
  <div class="scrim" role="presentation" onclick={onClose}></div>
  <div class="sheet"><Chat {pageId} embedded {onClose} /></div>
</div>

<style>
  .overlay { position: fixed; inset: 0; z-index: 180; }
  .overlay:focus { outline: none; }
  .scrim { position: absolute; inset: 0; background: #020712a8; backdrop-filter: blur(7px); }
  .sheet { position: absolute; inset: 3vh 1rem auto; margin-inline: auto; width: min(72rem, calc(100vw - 2rem)); height: min(54rem, 94dvh); background: #101725; color: #e8edf5; border: 1px solid #48617e; border-radius: 1.3rem; box-shadow: 0 20px 100px #0009; overflow: hidden; }
  .sheet:focus { outline: none; }
  @media (max-width: 650px) { .sheet { inset: 0; width: 100%; height: 100dvh; border: 0; border-radius: 0; } }
  @media print { .overlay { display: none !important; } }
</style>
