<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { scenarioStore, type Scenario } from '../../shell/scenario';
  import { clearPageContext, setPageContext } from '../../shell/pageContext.svelte';
  import Viewer from '../viewer/Viewer.svelte';
  import Compare from '../compare/RavenCompare.svelte';
  import OverlayPanel from '../../shell/overlay/OverlayPanel.svelte';
  import SiteFinder from '../../shell/finder/SiteFinder.svelte';
  import { OverlayController } from '../../shell/overlay/overlayController.svelte';

  const store = scenarioStore();
  const ctl = new OverlayController();
  ctl.scope = 'global'; // the 3D Moon: the whole surface, not only the south-polar disc
  $effect(() => ctl.fetchEffect());
  $effect(() => ctl.buildEffect());
  let scenario = $state<Scenario>(store.get());
  let body = $state<string | null>(null);
  let viewer: { revealSite: (siteId: string) => void; pauseTime: () => void } | undefined = $state();

  onMount(() => store.subscribe((s) => (scenario = s)));
  onDestroy(clearPageContext);
  $effect(() => {
    setPageContext({
      params: {
        ...(body ? { body } : {}),
        ...(scenario.site ? { site: scenario.site } : {}),
        ...(scenario.t ? { istante_utc: scenario.t } : {}),
        stazione: scenario.station,
        ...(scenario.bitrate !== null ? { bitrate_bps: scenario.bitrate } : {}),
      },
    });
  });
</script>

<div class="combined" data-testid="siti-combined">
  <div class="globe">
    <Viewer embedded bind:this={viewer} overlay={body === 'moon' || body === null ? ctl.raster : null} onBodyChange={(value) => (body = value)}>
      {#snippet below()}
        {#if body === 'moon' || body === null}<div class="overlay"><OverlayPanel {ctl} name="siti-layer" /></div>{/if}
      {/snippet}
    </Viewer>
  </div>
  <div class="finder"><SiteFinder onresult={(o) => { ctl.suitability = o; ctl.layer = o ? 'suitability' : 'none'; }} /></div>
  <div class="ranking"><Compare embedded onRevealSite={(id) => viewer?.revealSite(id)} onEditStart={() => viewer?.pauseTime()} /></div>
</div>

<style>
  .combined {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }
  .overlay {
    padding: 0.5rem 1rem;
  }
  .finder {
    padding: 0.5rem 1rem;
  }
  .globe,
  .ranking,
  .finder {
    min-width: 0;
  }
</style>
