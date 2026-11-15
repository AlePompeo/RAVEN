<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Overlay chooser and legend shared by the dashboard and the sites page. Every overlay has a scale, a legend, a source and a tag;
     a cell with no data is hatched ("unknown"), never coloured as a value; nothing is interpolated between sites. -->
<script lang="ts">
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import type { RavenOverlay } from '../ravenApi';
  import { sequentialGradient, CATEGORICAL } from '../../pages/dashboard/overlayColors';
  import type { OverlayController, Layer } from './overlayController.svelte';

  let { ctl, usefulMax = null, name = 'overlay-layer' }: { ctl: OverlayController; usefulMax?: number | null; name?: string } = $props();
  const GROUPS: { label: MessageKey; layers: { id: Layer; label: MessageKey }[] }[] = [
    { label: 'dash.groupTerrain', layers: [
      { id: 'elevation', label: 'dash.layer.elevation' }, { id: 'slope', label: 'dash.layer.slope' }, { id: 'coverage', label: 'dash.layer.coverage' },
    ] },
    { label: 'dash.groupLight', layers: [
      { id: 'sun', label: 'dash.layer.sun' }, { id: 'sun_gap', label: 'dash.layer.sunGap' },
    ] },
    { label: 'dash.groupComms', layers: [
      { id: 'earth', label: 'dash.layer.earth' }, { id: 'earth_gap', label: 'dash.layer.earthGap' },
    ] },
    { label: 'dash.groupCombined', layers: [
      { id: 'suitability', label: 'finder.layer' }, { id: 'both', label: 'dash.layer.both' },
      { id: 'composite', label: 'dash.layer.composite' }, { id: 'useful', label: 'dash.layer.useful' },
    ] },
  ];
  const shown = $derived(GROUPS.map((g) => ({ ...g, layers: g.layers.filter((l) => (l.id !== 'useful' || usefulMax !== null) && (l.id !== 'suitability' || ctl.suitability !== null)) })).filter((g) => g.layers.length));
  const legendLabel = (o: RavenOverlay) => (o.unit === 'class' ? '' : `${new Intl.NumberFormat().format(Math.round(o.min * 10) / 10)} – ${new Intl.NumberFormat().format(Math.round(o.max * 10) / 10)} ${o.unit}`);
</script>

<fieldset class="overlays">
  <legend>{t('dash.overlay')}</legend>
  <div class="choices" role="radiogroup" aria-label={t('dash.overlay')}>
    <label class="choice"><input type="radio" {name} value="none" checked={ctl.layer === 'none'} onchange={() => { ctl.layer = 'none'; }} />{t('dash.layer.none')}</label>
    {#each shown as group}
      <div class="group" role="group" aria-label={t(group.label)}>
        <strong>{t(group.label)}</strong>
        {#each group.layers as l}
          <label class="choice"><input type="radio" {name} value={l.id} checked={ctl.layer === l.id} onchange={() => { ctl.layer = l.id; }} />{t(l.label)}</label>
        {/each}
      </div>
    {/each}
  </div>
  {#if ctl.layer !== 'none'}
    <label class="opacity" for={`${name}-opacity`}>{t('dash.opacity')}</label>
    <input id={`${name}-opacity`} type="range" min="0.2" max="1" step="0.05" bind:value={ctl.opacity} disabled={ctl.layer === 'useful'} />
  {/if}
  {#if ctl.layer !== 'none' && ctl.layer !== 'useful'}<p class="note" data-testid="overlay-scope">{t(ctl.scope === 'global' ? 'dash.scope.global' : 'dash.scope.polar')}</p>{/if}
  {#if ctl.busy}<p role="status" class="note">{t('dash.loading')}</p>{/if}
  {#if ctl.failed}<p role="alert">{t('dash.overlayFailed')}</p>{/if}
  <div class="legend" data-testid="overlay-legend">
    {#if ctl.layer === 'useful' && usefulMax !== null}
      <div class="bar" style:background={sequentialGradient()} aria-hidden="true"></div>
      <span>0 – {Math.round(usefulMax)} h</span>
      <p class="note">{t('dash.useful.note')}</p>
    {:else if ctl.layer === 'composite' && ctl.parts.sun && ctl.parts.earth && ctl.parts.slope}
      <ul class="classes">
        <li><span class="sw" style:background="rgb(255,0,0)"></span>{t('dash.comp.r')}</li>
        <li><span class="sw" style:background="rgb(0,255,0)"></span>{t('dash.comp.g')}</li>
        <li><span class="sw" style:background="rgb(0,0,255)"></span>{t('dash.comp.b')}</li>
      </ul>
      <p class="note"><span class="hatch" aria-hidden="true"></span>{t('dash.nodata')}</p>
      <p class="note">{ctl.parts.sun.source} · {t('dash.tag', { tag: ctl.parts.sun.tag })}. {ctl.parts.sun.note}</p>
    {:else if ctl.data && (ctl.single || ctl.layer === 'suitability')}
      {#if ctl.data.kind === 'categorical'}
        <ul class="classes">{#each ctl.data.classes ?? [] as c}<li><span class="sw" style:background={`rgb(${CATEGORICAL[(c.value - 1) % CATEGORICAL.length]!.join(',')})`}></span>{c.label}</li>{/each}</ul>
      {:else}
        <div class="bar" style:background={sequentialGradient()} aria-hidden="true"></div>
        <span>{legendLabel(ctl.data)}</span>
      {/if}
      <p class="note"><span class="hatch" aria-hidden="true"></span>{t('dash.nodata')}</p>
      <p class="note">{ctl.data.source} · {t('dash.tag', { tag: ctl.data.tag })}. {ctl.data.note}</p>
    {:else if ctl.layer === 'none'}<p class="note">{t('dash.noOverlay')}</p>{/if}
  </div>
</fieldset>

<style>
  .overlays { border: 1px solid #9bdfff33; border-radius: .6rem; padding: .6rem .9rem; min-width: 0; }
  legend { padding-inline: .4rem; color: #a4dfff; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; }
  .choices { display: grid; gap: .25rem; }
  .group { display: flex; flex-wrap: wrap; gap: 0 1rem; border-top: 1px solid #9bdfff33; padding-top: .35rem; }
  .group strong { flex-basis: 100%; color: #c9efff; font-size: .8rem; }
  .choice { display: inline-flex; align-items: center; gap: .4rem; min-height: 44px; }
  .opacity { display: block; margin-top: .4rem; font-size: .85rem; } input[type='range'] { width: min(20rem, 100%); min-height: 44px; }
  .legend { margin-top: .5rem; font-size: .85rem; } .legend .bar { height: .7rem; border-radius: .2rem; margin-bottom: .25rem; }
  .classes { list-style: none; margin: 0; padding: 0; } .classes li { display: flex; align-items: center; gap: .5rem; }
  .sw { display: inline-block; width: 1rem; height: .7rem; border-radius: .15rem; }
  .hatch { display: inline-block; width: 1rem; height: .7rem; margin-right: .4rem; vertical-align: middle; background: repeating-linear-gradient(135deg, #c8c8c8 0 2px, transparent 2px 5px); }
  .note { color: var(--c-muted); font-size: .8rem; }
</style>
