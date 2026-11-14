<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Lunar landing sites navigator: the centre of the mission-control dashboard. Three views of the same sites (south-polar map,
     3D Moon, rover scene) and remote-sensing style overlays on the map. Overlays are rasters with a scale, a legend, a source and
     a tag; a cell with no data is hatched ("unknown"), never coloured as a value; nothing is interpolated between sites. -->
<script lang="ts">
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import { customSites, toApi } from '../../shell/customSites';
  import { scenarioStore } from '../../shell/scenario';
  import SitePolarMap from '../planner/SitePolarMap.svelte';
  import type { JourneyRun } from '../planner/journey';
  import OverlayPanel from '../../shell/overlay/OverlayPanel.svelte';
  import { OverlayController } from '../../shell/overlay/overlayController.svelte';
  import { sequentialColor } from './overlayColors';

  let { sites, run, scenario = 0, index = 0, onsite }: {
    sites: readonly { id: string; name: string; lat: number; lon: number }[];
    run: JourneyRun | null; scenario?: number; index?: number; onsite?: (id: string) => void;
  } = $props();

  type View = 'polar' | 'globe' | 'rover';
  let view = $state<View>('polar');
  const ctl = new OverlayController();
  $effect(() => { ctl.scope = view === 'globe' ? 'global' : 'polar'; });
  $effect(() => ctl.fetchEffect());
  $effect(() => ctl.buildEffect());

  const evals = $derived(run?.evaluations ?? []);
  const assigned = $derived({ ...(evals[0] ? { A: evals[0].site.id } : {}), ...(evals[1] ? { B: evals[1].site.id } : {}) });
  const maxUseful = $derived(Math.max(1, ...evals.map((e) => e.metrics.useful_hours)));
  const markerColors = $derived.by<Record<string, string>>(() => {
    if (ctl.layer !== 'useful') return {};
    return Object.fromEntries(evals.map((e) => [e.site.id, `rgb(${sequentialColor(e.metrics.useful_hours / maxUseful).join(',')})`]));
  });
  const active = $derived(evals[scenario] ?? evals[0] ?? null);
  // the 3D Moon is the one of the Sites page: it follows the scenario of the session (site and instant)
  $effect(() => {
    if (view !== 'globe' || !active) return;
    const ms = active.steps ? active.steps.time_unix[Math.min(index, active.steps.time_unix.length - 1)]! * 1000 : NaN;
    scenarioStore().set({ site: active.site.id, ...(Number.isFinite(ms) ? { t: new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z') } : {}) });
  });
  const roverMs = $derived(active?.steps ? active.steps.time_unix[Math.min(index, active.steps.time_unix.length - 1)]! * 1000 : NaN);
  const roverCustom = $derived(active ? customSites.get().find((c) => c.id === active.site.id) : undefined);
  const radio = $derived(run?.config.radio);
</script>

<section class="navigator" aria-labelledby="nav-title" data-testid="dashboard-navigator">
  <div class="bar">
    <h2 id="nav-title">{t('dash.navigator')}</h2>
    <div class="switch" role="group" aria-label={t('dash.view')}>
      {#each [['polar', 'dash.view.polar'], ['globe', 'dash.view.globe'], ['rover', 'dash.view.rover']] as [id, label]}
        <button type="button" aria-pressed={view === id} disabled={id === 'rover' && !run} onclick={() => { view = id as View; }}>{t(label as MessageKey)}</button>
      {/each}
    </div>
  </div>

  <div class="work" class:with-side={view !== 'rover'}>
    <div class="stage">
      {#if view === 'polar'}
        <div class="polar"><SitePolarMap {sites} {assigned} limit={-75} overlay={ctl.canvas} {markerColors}
          onmarker={(id) => onsite?.(id)} onpick={() => {}} /></div>
      {:else if view === 'globe'}
        {#await import('../viewer/Viewer.svelte') then m}
          <m.default embedded tall overlay={ctl.raster} />
        {:catch}<p role="alert">{t('custom.globeFailed')}</p>{/await}
      {:else if active && radio && radio.gain !== null && radio.rate !== null && radio.mast !== null && Number.isFinite(roverMs)}
        {#await import('../lander/Lander.svelte') then m}
          <m.default embedded compact plannerSite={active.site.id} plannerMs={roverMs} plannerCustomSite={roverCustom ? toApi(roverCustom) : undefined}
            plannerRadio={{ station: radio.station, gain: radio.gain, rate: radio.rate, mast: radio.mast }} />
        {:catch}<p role="alert">{t('journey.visualFailed')}</p>{/await}
      {:else}<p class="note">{t('dash.noRun')}</p>{/if}
    </div>
    {#if view !== 'rover'}
      <aside class="side"><OverlayPanel {ctl} usefulMax={run ? maxUseful : null} /></aside>
    {/if}
  </div>
</section>

<style>
  .navigator { display: grid; gap: .75rem; min-width: 0; }
  .bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; }
  h2 { margin: 0; font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #a4dfff; }
  .switch { display: flex; gap: .25rem; } .switch button { min-height: 44px; padding: .4rem 1rem; }
  .switch button[aria-pressed='true'] { background: #9bdfff22; border-color: #9bdfff; color: #c9efff; }
  .work { display: grid; gap: .75rem; grid-template-columns: minmax(0, 1fr); align-items: start; }
  .work.with-side { grid-template-columns: minmax(0, 1fr) minmax(16rem, 22rem); }
  .stage { min-height: max(30rem, 74svh); display: block; background: #05101c; border: 1px solid #9bdfff40; border-radius: .6rem; padding: .5rem; overflow: hidden; --polar-max: min(100%, 78svh); }
  .polar { display: grid; place-items: center; min-height: max(29rem, 72svh); }
  .side { min-width: 0; max-height: max(30rem, 74svh); overflow: auto; }
  .note { color: var(--c-muted); font-size: .8rem; }
  @media (max-width: 1000px) { .work.with-side { grid-template-columns: minmax(0, 1fr); } .side { max-height: none; } }
</style>
