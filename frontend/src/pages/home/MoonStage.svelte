<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  La Luna del palco: Canvas 2D sempre (13 KB, nessuna GPU), tramite selectViewportFactory per avere lo stesso
  ripiego testuale del visualizzatore se manca anche il 2D. three.js non viene scaricato nella home.
  Ingresso orchestrato (una volta): il Sole passa da dietro la Luna al lato destro (falce -> gibbosa), poi la
  rotazione lenta. Con reduced motion: fase finale subito, nessuna rotazione.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { prefersReducedMotion } from '../../shell/a11y';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { selectViewportFactory, type ViewportMode } from '../../viewports/select';
  import type { SceneState } from '../../viewports/scene';

  let { onmode }: { onmode?: (m: ViewportMode) => void } = $props();

  const SWEEP_MS = 1800;
  const FROM = { az_deg: 30, el_deg: 6 };
  const TO = { az_deg: 106, el_deg: 30 }; // terminatore ben visibile: ombre lunghe sui crateri
  const BASE: SceneState = { yaw_deg: -20, pitch_deg: 8, autoRotate: false };

  let host: HTMLElement | undefined = $state();
  // la Luna del palco è decorativa: senza Canvas 2D si nasconde (niente avviso "WebGL" fuori contesto)
  let unavailable = $state(false);

  /**
   * Luna dominante che esce dal bordo: in orizzontale diametro ~1.5 volte l'altezza del palco, centro
   * in basso a destra; in verticale diametro ~1.8 volte la larghezza, centro in basso.
   */
  function placeMoon(w: number, h: number) {
    if (w >= h) return { cx: w * 0.68, cy: h * 1.02, r: Math.min(h * 0.76, w * 0.5) };
    return { cx: w * 0.55, cy: h * 0.94, r: w * 0.74 };
  }

  const ease = (t: number) => 1 - (1 - t) ** 3;
  const at = (t: number): SceneState => ({
    ...BASE,
    sun: { az_deg: FROM.az_deg + (TO.az_deg - FROM.az_deg) * t, el_deg: FROM.el_deg + (TO.el_deg - FROM.el_deg) * t },
  });

  onMount(() => {
    if (!host) return;
    let raf = 0;
    let alive = true;
    const mql = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    const handle: ViewportHandle = mountViewport(
      selectViewportFactory({
        onMode: (m) => {
          unavailable = m === 'none';
          onmode?.(m);
        },
        webglAvailable: () => false,
        canvas2d: async () =>
          (await import('../../viewports/canvas2dViewport')).canvas2dViewportFactoryWith({
            decor: 'hero',
            place: placeMoon,
            // Luna ferma dopo l'ingresso: un'immagine nitida a piena risoluzione vale più di una rotazione sfocata
            maxFps: 30,
            maxSample: 1280,
          })(),
      }),
      host,
    );

    const settle = () => handle.update(at(1));
    const onMotion = () => {
      cancelAnimationFrame(raf);
      settle();
    };
    mql?.addEventListener('change', onMotion);

    if (prefersReducedMotion()) {
      handle.update(at(1));
    } else {
      handle.update(at(0));
      void handle.ready.then(() => {
        if (!alive) return;
        const t0 = performance.now();
        const step = (now: number) => {
          if (!alive) return;
          const t = Math.min(1, (now - t0) / SWEEP_MS);
          if (t < 1) {
            handle.update(at(ease(t)));
            raf = requestAnimationFrame(step);
          } else settle();
        };
        raf = requestAnimationFrame(step);
      });
    }

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      mql?.removeEventListener('change', onMotion);
      handle.dispose();
    };
  });
</script>

<div class="moon" bind:this={host} data-testid="moon-stage" hidden={unavailable} aria-hidden="true"></div>

<style>
  .moon {
    position: absolute;
    inset: 0;
  }
  /* ingresso: la Luna sale dal nero (insieme al passaggio da falce a gibbosa disegnato nel canvas) */
  @media (prefers-reduced-motion: no-preference) {
    .moon {
      animation: moonrise 2200ms cubic-bezier(0.22, 1, 0.36, 1) both;
    }
  }
  @keyframes moonrise {
    from {
      opacity: 0;
      transform: translateY(12%);
    }
    to {
      opacity: 1;
      transform: none;
    }
  }
</style>
