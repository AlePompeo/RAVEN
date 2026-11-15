<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Lunar landing sites navigator: the centre of the mission-control dashboard. Three views of the same sites (south-polar map,
     3D Moon, rover scene) and remote-sensing style overlays on the map. Overlays are rasters with a scale, a legend, a source and
     a tag; a cell with no data is hatched ("unknown"), never coloured as a value; nothing is interpolated between sites. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { customSites, toApi } from '../../shell/customSites';
  import { scenarioStore } from '../../shell/scenario';
  import SitePolarMap from '../planner/SitePolarMap.svelte';
  import type { JourneyRun } from '../planner/journey';
  import OverlayPanel from '../../shell/overlay/OverlayPanel.svelte';
  import { OverlayController } from '../../shell/overlay/overlayController.svelte';
  import { sequentialColor } from './overlayColors';
  import { countdownAt, type Countdown } from '../planner/visibilityStats';
  import DashboardTimeline from './DashboardTimeline.svelte';

  let { sites, run, scenario = 0, index = 0, playing = false, onsite, onscenario, onindex, onplay }: {
    sites: readonly { id: string; name: string; lat: number; lon: number }[];
    run: JourneyRun | null; scenario?: number; index?: number; playing?: boolean;
    onsite?: (id: string) => void; onscenario?: (index: number) => void; onindex: (index: number) => void; onplay: () => void;
  } = $props();

  type View = 'polar' | 'globe' | 'rover';
  let view = $state<View>('polar');
  let selectedId = $state('');
  const ctl = new OverlayController();
  const store = scenarioStore();
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
  const selectedSite = $derived(sites.find((s) => s.id === selectedId) ?? null);
  const selectedEvaluation = $derived(active?.site.id === selectedId ? active : null);
  const pickedState = $derived(selectedEvaluation?.steps ? selectedEvaluation.steps.useful[index] ?? null : undefined);
  const countdown = $derived(selectedEvaluation ? countdownAt(selectedEvaluation, index) : null);
  const measurement = (v: number | null | undefined, unit: string, scale = 1) =>
    v == null || !Number.isFinite(v) ? t('journey.unknown') : `${formatNumber(v * scale, { maximumFractionDigits: 1 })} ${unit}`;
  const countText = (c: Countdown | undefined, body: 'sun' | 'earth') =>
    !c || c.visible === null ? t('journey.unknown') : c.status === 'unknown' ? t('journey.changeUnknown') : c.hours === null ? t('journey.noChange')
      : t(body === 'sun' ? (c.visible ? 'journey.nextSunset' : 'journey.nextSunrise') : (c.visible ? 'journey.nextEarthset' : 'journey.nextEarthrise'), { hours: formatNumber(c.hours, { maximumFractionDigits: 1 }) });
  $effect(() => { selectedId = active?.site.id ?? ''; });

  function selectSite(id: string) {
    if (!sites.some((site) => site.id === id)) return;
    selectedId = id;
    if (active?.site.id !== id) {
      const match = evals.findIndex((e) => e.site.id === id);
      if (match >= 0) onscenario?.(match);
    }
    if (view === 'globe') store.set({ site: id });
  }
  function changeView(next: View) {
    view = next;
    if (next === 'globe' && !selectedId) {
      const site = store.get().site;
      if (site) selectSite(site);
    }
  }
  onMount(() => store.subscribe((state) => {
    if (view === 'globe' && state.site && state.site !== selectedId) selectSite(state.site);
  }));

  $effect(() => {
    if (view !== 'globe') return;
    const ms = active?.steps ? active.steps.time_unix[Math.min(index, active.steps.time_unix.length - 1)]! * 1000 : NaN;
    if (selectedId || Number.isFinite(ms)) store.set({
      ...(selectedId ? { site: selectedId } : {}),
      ...(Number.isFinite(ms) ? { t: new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z') } : {}),
    });
  });
  const roverMs = $derived(active?.steps ? active.steps.time_unix[Math.min(index, active.steps.time_unix.length - 1)]! * 1000 : NaN);
  const roverCustom = $derived(active ? customSites.get().find((c) => c.id === active.site.id) : undefined);
  const radio = $derived(run?.config.radio);
</script>

<section class="navigator" aria-labelledby="nav-title" data-testid="dashboard-navigator">
  <h2 id="nav-title">{t('dash.navigator')}</h2>
  <div class="work">
    <aside class="controls" aria-label={t('dash.controls')}>
      <h3>{t('dash.view')}</h3>
      <div class="switch" role="group" aria-label={t('dash.view')}>
        {#each [['polar', 'dash.view.polar'], ['globe', 'dash.view.globe'], ['rover', 'dash.view.rover']] as [id, label]}
          <button type="button" aria-pressed={view === id} disabled={id === 'rover' && !run} onclick={() => changeView(id as View)}>{t(label as MessageKey)}</button>
        {/each}
      </div>
      {#if view !== 'rover'}<OverlayPanel {ctl} usefulMax={run ? maxUseful : null} />{/if}
    </aside>
    <div class="scene-column">
    <div class="stage">
      {#if view === 'polar'}
        <div class="polar"><SitePolarMap {sites} {assigned} {pickedState} picked={selectedSite ? { lat: selectedSite.lat, lon: selectedSite.lon } : null}
          limit={-75} overlay={ctl.canvas} {markerColors} help={t('dash.mapInspect')}
          onmarker={selectSite} onpick={() => {}} />
          {#if pickedState !== undefined}<p class="note" data-testid="dashboard-map-state">{t('dash.mapSample')}: {t(pickedState === null ? 'journey.unknown' : pickedState ? 'dash.timelineYes' : 'dash.timelineNo')}</p>{/if}
        </div>
      {:else if view === 'globe'}
        {#await import('../viewer/Viewer.svelte') then m}
          <m.default embedded tall controlledTime={!!active?.steps} overlay={ctl.raster} />
        {:catch}<p role="alert">{t('custom.globeFailed')}</p>{/await}
      {:else if active && radio && radio.gain !== null && radio.rate !== null && radio.mast !== null && Number.isFinite(roverMs)}
        {#await import('../lander/Lander.svelte') then m}
          <m.default embedded compact plannerSite={active.site.id} plannerMs={roverMs} plannerCustomSite={roverCustom ? toApi(roverCustom) : undefined}
            plannerRadio={{ station: radio.station, gain: radio.gain, rate: radio.rate, mast: radio.mast }} />
        {:catch}<p role="alert">{t('journey.visualFailed')}</p>{/await}
        <p class="note">{t('dash.roverScenario', { site: active.site.name })}</p>
      {:else}<p class="note">{t('dash.noRun')}</p>{/if}
    </div>
    {#if active?.steps?.time_unix.length}
      <DashboardTimeline {active} {scenario} {index} {playing} {onindex} {onplay} />
    {:else}<p class="note">{t('dash.timelineEmpty')}</p>{/if}
    </div>
    <aside class="site-detail" aria-labelledby="dashboard-site-title" data-testid="dashboard-site-detail">
      <h3 id="dashboard-site-title">{t('dash.selectedSite')}</h3>
      <label for="dashboard-site">{t('dash.selectSite')}</label>
      <select id="dashboard-site" value={selectedId} onchange={(e) => selectSite(e.currentTarget.value)}>
        <option value="" disabled>{t('dash.chooseSite')}</option>
        {#each sites as site (site.id)}<option value={site.id}>{site.name}</option>{/each}
      </select>
      {#if selectedSite}
        <h4>{selectedSite.name}</h4>
        <dl>
          <div><dt>{t('dash.latitude')}</dt><dd>{formatNumber(selectedSite.lat, { maximumFractionDigits: 4 })}°</dd></div>
          <div><dt>{t('dash.longitude')}</dt><dd>{formatNumber(selectedSite.lon, { maximumFractionDigits: 4 })}°</dd></div>
        </dl>
        {#if selectedEvaluation?.steps}
          <h4>{t('dash.instantData')}</h4>
          <p class="note">{new Date(selectedEvaluation.steps.time_unix[index]! * 1000).toISOString().replace('.000Z', ' UTC').replace('T', ' ')}</p>
          <dl data-testid="dashboard-instant">
            <div><dt>{t('dash.sunElevation')}</dt><dd>{measurement(selectedEvaluation.steps.sun_el_deg[index], '°')}</dd></div>
            <div><dt>{t('dash.earthElevation')}</dt><dd>{measurement(selectedEvaluation.steps.earth_el_deg[index], '°')}</dd></div>
            <div><dt>{t('dash.rfMargin')}</dt><dd>{measurement(selectedEvaluation.steps.margin_db[index], 'dB')}</dd></div>
            <div><dt>{t('planner.socChart')}</dt><dd>{measurement(selectedEvaluation.steps.soc[index], '%', 100)}</dd></div>
          </dl>
          <p class="note">{t('dash.batteryEndStep')}</p>
          <p class="note">{countText(countdown?.sun, 'sun')}</p>
          <p class="note">{countText(countdown?.earth, 'earth')}</p>
        {:else}
          <p class="note">{t('dash.instantUnavailable')}</p>
        {/if}
        {#if view === 'polar' && selectedSite.lat > -75}<p class="note">{t('dash.outsidePolar')}</p>{/if}
        <button type="button" onclick={() => onsite?.(selectedSite.id)}>{t('demo.openPlanner')}</button>
      {:else}
        <p class="note">{t('dash.selectSiteHint')}</p>
      {/if}
    </aside>
  </div>
</section>

<style>
  .navigator { display: grid; gap: .75rem; min-width: 0; }
  h2 { margin: 0; font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #a4dfff; }
  h3 { margin: 0 0 .6rem; font-size: .9rem; color: #c9efff; }
  .switch { display: grid; gap: .35rem; margin-bottom: 1rem; } .switch button { min-height: 44px; padding: .4rem .8rem; text-align: left; }
  .switch button[aria-pressed='true'] { background: #9bdfff22; border-color: #9bdfff; color: #c9efff; }
  .work { display: grid; gap: .75rem; grid-template-columns: minmax(13rem, 16rem) minmax(0, 1fr) minmax(13rem, 16rem); align-items: start; }
  .scene-column { min-width: 0; }
  .stage { min-width: 0; min-height: max(30rem, 74svh); background: #05101c; border: 1px solid #9bdfff40; border-radius: .6rem; padding: .5rem; overflow: hidden; --polar-max: min(100%, 78svh); }
  .polar { display: grid; place-items: center; min-height: max(29rem, 72svh); }
  .controls, .site-detail { min-width: 0; border: 1px solid #9bdfff33; border-radius: .6rem; padding: .75rem; background: #081827; }
  .controls { max-height: max(30rem, 74svh); overflow: auto; }
  .site-detail label { display: block; margin-bottom: .35rem; font-size: .85rem; }
  .site-detail select { width: 100%; min-height: 44px; }
  .site-detail h4 { margin: 1rem 0 .6rem; overflow-wrap: anywhere; }
  dl { margin: 0 0 1rem; } dl div { display: flex; justify-content: space-between; gap: .5rem; padding-block: .35rem; border-bottom: 1px solid #9bdfff33; }
  dt, .note { color: #a7c2d7; font-size: .85rem; } dd { margin: 0; font-variant-numeric: tabular-nums; }
  .site-detail button { min-height: 44px; }
  @media (max-width: 1100px) {
    .work { grid-template-columns: minmax(0, 1fr); }
    .controls { max-height: none; overflow: visible; }
    .switch { display: flex; flex-wrap: wrap; }
  }
</style>
