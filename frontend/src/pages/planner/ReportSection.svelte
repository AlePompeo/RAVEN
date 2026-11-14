<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Lateral section of each scenario (terrain profile, ridge, line of sight, Fresnel zone, antenna), the same 2D drawing as the
     Communications step, taken at the first useful sample of the window (else the window start). The canvas is swapped for a
     PNG when the PDF is made (data-pdf-image). A scene that cannot be computed leaves a plain sentence, never a blank figure. -->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { mountViewport, type ViewportHandle } from '../../viewports/port';
  import { detectQuality } from '../../viewports/quality';
  import { sectionViewportFactory } from '../lander/landerViewport';
  import { fetchScene, FALLBACK_SUN, type LanderScene, type SceneParams } from '../lander/model';
  import { buildTerrain, presetCamera, type LanderViewState } from '../lander/view';
  import { customSites, toApi } from '../../shell/customSites';
  let { evaluations, radio }: { evaluations: readonly RavenEvaluation[]; radio: { station: 'dsn34' | 'dsn18'; rate: number | null; gain: number | null; mast: number | null } } = $props();

  interface Item { tag: string; name: string; when: string; state: 'loading' | 'ok' | 'failed' }
  const items = $state<Item[]>([]);
  const hosts: (HTMLElement | null)[] = $state([]);

  const instant = (e: RavenEvaluation): number => {
    const s = e.steps;
    const t = s?.time_unix ?? [];
    const k = s ? s.useful.findIndex((u) => u === true) : -1;
    return (t[k >= 0 ? k : 0] ?? Date.parse(e.window.start_utc) / 1000) * 1000;
  };

  onMount(() => {
    const handles: ViewportHandle[] = [];
    const observers: MutationObserver[] = [];
    const ctl = new AbortController();
    let alive = true;
    evaluations.slice(0, 2).forEach((e, i) => {
      const ms = instant(e);
      items[i] = { tag: i === 0 ? 'A' : 'B', name: e.site.name, when: new Date(ms).toISOString().replace('.000Z', ' UTC').replace('T', ' '), state: 'loading' };
      const custom = customSites.get().find((c) => c.id === e.site.id);
      const p: SceneParams = { site: e.site.id, ms, station: radio.station, gain: radio.gain ?? 15, rate: radio.rate ?? 1e5, mast: radio.mast ?? 2,
        ...(custom ? { customSite: toApi(custom) } : {}) };
      void fetchScene(p, ctl.signal).then((scene: LanderScene) => {
        if (!alive) return;
        const host = hosts[i];
        if (!host) { items[i]!.state = 'failed'; return; }
        const vs: LanderViewState = { scene, sceneGen: 1, terrain: null, terrainGen: 1, cam: presetCamera('side', scene, 1), vExag: 1, tubeScale: 20,
          errorDeg: 0, showOverlays: true, sun: FALLBACK_SUN, tier: detectQuality().tier, language: 'en' };
        vs.terrain = buildTerrain(scene, 1, FALLBACK_SUN);
        const h = mountViewport(sectionViewportFactory, host, () => { if (alive) items[i]!.state = 'failed'; });
        handles.push(h);
        h.update(vs);
        items[i]!.state = 'ok';
        // the viewport adds its canvas after an async import: tag it when it appears (the PDF export swaps it for a PNG)
        const tag = () => host.querySelector('canvas')?.setAttribute('data-pdf-image', 'dark');
        tag();
        const mo = new MutationObserver(tag);
        mo.observe(host, { childList: true });
        observers.push(mo);
      }).catch(() => { if (alive) untrack(() => { items[i]!.state = 'failed'; }); });
    });
    return () => { alive = false; ctl.abort(); handles.forEach((h) => h.dispose()); observers.forEach((o) => o.disconnect()); };
  });
</script>

{#if evaluations.length}
  <figure class="rp-section" data-testid="report-section-2d">
    <figcaption>{rt('sec.q')}</figcaption>
    <p class="rp-how">{rt('sec.d')}</p>
    {#each evaluations.slice(0, 2) as e, i}
      <div class="one">
        <strong>{i === 0 ? 'A' : 'B'}: {e.site.name} ({items[i]?.when ?? ''})</strong>
        <div class="host" bind:this={hosts[i]} hidden={items[i]?.state === 'failed'}></div>
        {#if items[i]?.state === 'failed'}<p class="rp-how">{rt('sec.failed')}</p>{/if}
      </div>
    {/each}
  </figure>
{/if}

<style>
  .rp-section { margin: 1rem 0; } figcaption { font-weight: 600; }
  .one { margin-block: .6rem; break-inside: avoid; }
  .host { position: relative; width: 100%; height: 14rem; background: #05070b; border-radius: .5rem; overflow: hidden; }
  .host :global(canvas) { width: 100%; height: 100%; }
</style>
