<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Palco a tutta larghezza, sempre scuro. Slot `media` (canvas, immagine, video) e contenuto (titolo, testo,
  una CTA).
  layout:
   - 'overlay' (predefinito): il media riempie il palco e il testo gli sta sopra; uno scrim nero (≥ 60% di
     opacità sotto tutto il testo: vedi --scrim-* in tokens.css e contrast.test.ts) garantisce AA anche se
     sotto c'è un pixel bianco. axe segnala questo testo come "incomplete" (sfondo non calcolabile): la
     garanzia è il test sui token, non axe.
   - 'split' / 'stack': media accanto o sopra al testo, senza sovrapposizione (contrasto misurato da axe).
  fx: 'drift' = il media si avvicina e sale nei primi 100vh di scroll; 'recede' = si allontana uscendo.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { scrollFx } from './scrollFx';

  let {
    labelledby,
    layout = 'overlay',
    height = 'full',
    scrim = true,
    fx = 'drift',
    align = 'center',
    class: extra = '',
    media,
    children,
  }: {
    labelledby: string;
    layout?: 'overlay' | 'split' | 'stack';
    height?: 'full' | 'tall';
    /** overlay: scrim sotto il testo; split/stack: sfumatura del bordo del media verso il testo. */
    scrim?: boolean;
    fx?: 'drift' | 'recede' | 'none';
    /** overlay su schermi larghi: testo al centro verticale o in basso (titolo in basso a sinistra). */
    align?: 'center' | 'end';
    class?: string;
    media?: Snippet;
    children: Snippet;
  } = $props();
</script>

<section class="hero tone-dark {extra}" aria-labelledby={labelledby} data-layout={layout} data-height={height} data-scrim={scrim} data-align={align}>
  {#if media}
    <div class="hero-media" use:scrollFx={{ mode: fx === 'none' ? 'none' : 'recede' }}>
      <div class="hero-media-inner" class:fx-recede={fx === 'recede'} class:fx-drift={fx === 'drift'}>{@render media()}</div>
    </div>
  {/if}
  {#if layout === 'overlay' && scrim}<div class="hero-scrim" aria-hidden="true"></div>{/if}
  <div class="hero-content">{@render children()}</div>
</section>

<style>
  .hero {
    position: relative;
    display: grid;
    grid-template-columns:
      [full-start] minmax(var(--gutter), 1fr)
      [content-start] minmax(0, var(--content-wide))
      [content-end] minmax(var(--gutter), 1fr)
      [full-end];
    grid-template-rows: minmax(0, 1fr) auto;
    min-height: calc(100svh - var(--nav-h));
    background: #000;
    color: var(--c-text);
    overflow: hidden;
    isolation: isolate;
  }
  .hero[data-height='tall'] {
    min-height: min(80svh, 760px);
  }
  .hero-media {
    grid-column: full;
    grid-row: 1;
    position: relative;
    min-height: 0;
  }
  .hero-media-inner {
    position: absolute;
    inset: 0;
    transform-origin: 60% 100%;
  }
  .hero-content {
    position: relative;
    grid-column: content;
    grid-row: 2;
    padding-block: var(--space-4) var(--space-6);
  }

  /* ---- overlay: media a tutto palco, testo sopra con scrim ---- */
  .hero[data-layout='overlay'] {
    grid-template-rows: minmax(0, 1fr);
  }
  .hero[data-layout='overlay'] .hero-media {
    position: absolute;
    inset: 0;
  }
  .hero[data-layout='overlay'] .hero-content {
    grid-row: 1;
    align-self: center;
    padding-block: var(--space-7);
  }
  .hero[data-layout='overlay'][data-align='end'] .hero-content {
    align-self: end;
    padding-block: var(--space-7) clamp(var(--space-6), 8svh, var(--space-7));
  }
  .hero-scrim {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(
      to right,
      var(--scrim-strong) 0%,
      var(--scrim-strong) 30%,
      var(--scrim-min) 62%,
      transparent 82%
    );
  }
  @media (max-width: 833px) {
    .hero[data-layout='overlay'] .hero-content,
    .hero[data-layout='overlay'][data-align='end'] .hero-content {
      align-self: start;
      padding-block: var(--space-6) var(--space-5);
    }
    .hero-scrim {
      background: linear-gradient(
        to bottom,
        var(--scrim-strong) 0%,
        var(--scrim-strong) 34%,
        var(--scrim-min) 54%,
        transparent 66%
      );
    }
  }

  /* ---- stack / split: nessuna sovrapposizione ---- */
  .hero[data-layout='stack'][data-scrim='true'] .hero-media,
  .hero[data-layout='split'][data-scrim='true'] .hero-media {
    -webkit-mask-image: linear-gradient(to bottom, #000 72%, transparent);
    mask-image: linear-gradient(to bottom, #000 72%, transparent);
  }
  @media (min-width: 1068px) {
    .hero[data-layout='split'] {
      grid-template-columns:
        [full-start] minmax(var(--gutter), 1fr)
        [content-start] minmax(0, calc(var(--content-wide) * 0.46))
        [media-start] minmax(0, calc(var(--content-wide) * 0.54))
        [content-end] minmax(var(--gutter), 1fr)
        [full-end];
      grid-template-rows: minmax(0, 1fr);
    }
    .hero[data-layout='split'] .hero-media {
      grid-column: media-start / full-end;
      grid-row: 1;
    }
    .hero[data-layout='split'][data-scrim='true'] .hero-media {
      -webkit-mask-image: linear-gradient(to right, transparent, #000 18%);
      mask-image: linear-gradient(to right, transparent, #000 18%);
    }
    .hero[data-layout='split'] .hero-content {
      grid-column: content-start / media-start;
      grid-row: 1;
      align-self: end;
      padding-block: var(--space-7);
      padding-inline-end: var(--space-5);
    }
  }
</style>
