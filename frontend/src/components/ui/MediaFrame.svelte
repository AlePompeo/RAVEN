<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Immagine responsiva con riga di credito. `sources` per art direction/formati (<picture>), `fade` sfuma i
  bordi del media nel colore pieno della tile (il testo non va mai sopra il media: vedi design-system.md §5).
  `fx="settle"`: leggero zoom legato allo scroll (CSS view() o fallback IntersectionObserver).
-->
<script lang="ts" module>
  export interface MediaSource {
    srcset: string;
    type?: string;
    media?: string;
    sizes?: string;
  }
</script>

<script lang="ts">
  import { scrollFx } from './scrollFx';

  let {
    src,
    alt,
    width,
    height,
    srcset,
    sizes = '100vw',
    sources = [],
    credit,
    fade = 'none',
    fx = 'none',
    fit = 'cover',
    loading = 'lazy',
    class: extra = '',
  }: {
    src: string;
    /** Testo alternativo; stringa vuota solo se l'immagine è decorativa. */
    alt: string;
    width: number;
    height: number;
    srcset?: string;
    sizes?: string;
    sources?: MediaSource[];
    credit?: string;
    fade?: 'none' | 'top' | 'bottom' | 'both';
    fx?: 'none' | 'settle';
    fit?: 'cover' | 'contain';
    loading?: 'lazy' | 'eager';
    class?: string;
  } = $props();
</script>

<figure class="media {extra}">
  <div class="frame" data-fade={fade} data-fit={fit} use:scrollFx={{ mode: fx }}>
    <picture class:fx-settle={fx === 'settle'}>
      {#each sources as s (s.srcset)}
        <source srcset={s.srcset} type={s.type} media={s.media} sizes={s.sizes ?? sizes} />
      {/each}
      <img {src} {srcset} {sizes} {alt} {width} {height} {loading} decoding="async" />
    </picture>
  </div>
  {#if credit}<figcaption class="credit">{credit}</figcaption>{/if}
</figure>

<style>
  /* se il chiamante fissa l'altezza della figura, il media si restringe e la didascalia resta dentro */
  .media {
    margin: 0;
    display: flex;
    flex-direction: column;
  }
  .frame {
    position: relative;
    overflow: hidden;
    flex: 1 1 auto;
    min-height: 0;
  }
  picture {
    display: block;
    height: 100%;
    transform-origin: 50% 40%;
  }
  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  [data-fit='contain'] img {
    object-fit: contain;
  }
  [data-fade='bottom'] {
    -webkit-mask-image: linear-gradient(to bottom, #000 62%, transparent);
    mask-image: linear-gradient(to bottom, #000 62%, transparent);
  }
  [data-fade='top'] {
    -webkit-mask-image: linear-gradient(to top, #000 62%, transparent);
    mask-image: linear-gradient(to top, #000 62%, transparent);
  }
  [data-fade='both'] {
    -webkit-mask-image: linear-gradient(to bottom, transparent, #000 22%, #000 72%, transparent);
    mask-image: linear-gradient(to bottom, transparent, #000 22%, #000 72%, transparent);
  }
  /* allineata alla colonna larga dei contenuti, anche sotto un'immagine a tutta larghezza */
  .credit {
    width: 100%;
    max-width: calc(var(--content-wide) + 2 * var(--gutter));
    margin: var(--space-2) auto 0;
    padding-inline: var(--gutter);
    font-size: var(--fs-micro);
    color: var(--c-muted);
  }
</style>
