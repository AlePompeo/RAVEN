<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Status chip of the printed report: a word, an icon and a colour, never the colour alone. The icon sits in its own
     inline-block with a margin, so it can never overlap the text or the number next to it (PDF and browser alike).
     Drawn with explicit SVG attributes (no classes, no var()). English only: the report is not translated. -->
<script lang="ts">
  import { rt } from './reportText';
  type ChipKind = 'known' | 'knownno' | 'unknown' | 'verified' | 'plausible' | 'notvalidated' | 'estimated' | 'provided';
  let { kind }: { kind: ChipKind } = $props();
</script>

<span class={`rp-chip rp-chip-${kind}`}><span class="rp-chip-icon"><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
  {#if kind === 'known' || kind === 'verified' || kind === 'provided'}<circle cx="6" cy="6" r="5" /><path d="M3.2 6.2 5.2 8.2 8.9 4.1" />
  {:else if kind === 'plausible' || kind === 'estimated'}<circle cx="6" cy="6" r="5" /><path d="M3 6.6C4 4.8 5 4.8 6 6.4S8 8 9 6.2" />
  {:else if kind === 'notvalidated'}<path d="M6 1.2 11 10.6H1Z" /><path d="M6 4.8V7.4M6 9V9.1" />
  {:else if kind === 'knownno'}<circle cx="6" cy="6" r="5" /><path d="M3.9 3.9 8.1 8.1M8.1 3.9 3.9 8.1" />
  {:else}<circle cx="6" cy="6" r="5" stroke-dasharray="2 2" /><path d="M4.5 4.7A1.6 1.6 0 1 1 6.6 6.2C6.1 6.5 6 6.8 6 7.3M6 9V9.1" />{/if}
</svg></span><span class="rp-chip-text">{rt(`chip.${kind}`)}</span></span>
