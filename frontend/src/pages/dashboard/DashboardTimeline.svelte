<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { earthVisibility, nextChange } from '../planner/journey';
  import type { RavenEvaluation } from '../../shell/ravenApi';

  let { active, scenario, index, playing, onindex, onplay }: {
    active: RavenEvaluation; scenario: number; index: number; playing: boolean;
    onindex: (index: number) => void; onplay: () => void;
  } = $props();
  const samples = $derived(active.steps!);
  const rows = $derived([
    { label: 'planner.sun' as MessageKey, values: samples.lit },
    { label: 'planner.earth' as MessageKey, values: earthVisibility(active) },
    { label: 'dash.timelineRadio' as MessageKey, values: samples.link_usable },
    { label: 'planner.abUseful' as MessageKey, values: samples.useful },
  ]);
  const stamp = (s: number) => new Date(s * 1000).toISOString().replace('.000Z', ' UTC').replace('T', ' ');
  function segments(values: readonly (boolean | null)[]) {
    const groups: { value: boolean | null; length: number }[] = [];
    for (const value of values) {
      const last = groups.at(-1);
      if (last && last.value === value) last.length++;
      else groups.push({ value, length: 1 });
    }
    return groups;
  }
</script>

<section class="compact-timeline" aria-labelledby="dashboard-timeline-title" data-testid="dashboard-timeline">
  <div class="head">
    <h3 id="dashboard-timeline-title">{t('planner.timelineTitle')}</h3>
    <button type="button" aria-pressed={playing} onclick={onplay}>{t(playing ? 'planner.replayPause' : 'planner.replayPlay')}</button>
  </div>
  <label for="dashboard-time">{t('planner.instant', { scenario: scenario === 0 ? 'A' : 'B' })}: <strong>{stamp(samples.time_unix[index]!)}</strong></label>
  <input id="dashboard-time" type="range" min="0" max={samples.time_unix.length - 1} step="1" value={index} oninput={(e) => onindex(Number(e.currentTarget.value))} />
  {#each rows as row}
    {@const value = row.values[index]}
    {@const next = nextChange(row.values, index)}
    <div class="row">
      <span>{t(row.label)}</span>
      <div class="track" aria-hidden="true">
        {#each segments(row.values) as segment}<span class:yes={segment.value === true} class:no={segment.value === false} class:unknown={segment.value === null} style:flex-grow={segment.length}></span>{/each}
        <i style:left={`${samples.time_unix.length < 2 ? 0 : index / (samples.time_unix.length - 1) * 100}%`}></i>
      </div>
      <small>{t(value == null ? 'journey.unknown' : value ? 'dash.timelineYes' : 'dash.timelineNo')} · {next.kind === 'unknown' ? t('journey.changeUnknown') : next.kind === 'end' ? t('journey.noChange') : t('journey.nextChange', { hours: formatNumber((next.index - index) * active.window.step_min / 60, { maximumFractionDigits: 1 }) })}</small>
    </div>
  {/each}
  <p class="note">{t('journey.timelineLegend')} {t('dash.timelineScope', { step: active.window.step_min })}</p>
</section>

<style>
  .compact-timeline { margin-top: .75rem; border: 1px solid #9bdfff40; border-radius: .6rem; padding: .8rem; background: #081827; min-width: 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: .5rem; flex-wrap: wrap; }
  h3 { margin: 0; font-size: .9rem; color: #c9efff; }
  button { min-height: 44px; } label { display: block; font-size: .85rem; margin-top: .5rem; }
  input { width: 100%; min-height: 44px; accent-color: #9bdfff; }
  .row { display: grid; grid-template-columns: minmax(5rem, 8rem) minmax(4rem, 1fr); gap: .2rem .5rem; align-items: center; margin-block: .5rem; font-size: .8rem; }
  .track { display: flex; position: relative; height: .6rem; overflow: hidden; border-radius: .2rem; }
  .track span { min-width: 0; } .yes { background: #6ee7a8; } .no { background: #645875; }
  .unknown { background: repeating-linear-gradient(135deg, #c8c8c8 0 2px, #30394a 2px 5px); }
  .track i { position: absolute; top: 0; bottom: 0; width: 2px; background: white; transform: translateX(-1px); }
  small { grid-column: 2; color: #b7cbdc; } .note { color: #b7cbdc; font-size: .8rem; }
</style>
