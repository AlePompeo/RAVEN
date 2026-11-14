<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import SeriesChart from './SeriesChart.svelte';
  import MissionStatistics from './MissionStatistics.svelte';
  import VisibilityFigures from './VisibilityFigures.svelte';
  import LunarDays from './LunarDays.svelte';
  import { utcMinute } from './reportFormat';
  import { earthVisibility, firstChange, fraction, type JourneyRun } from './journey';
  import type { MissionObjectives } from './objectives';
  let { run, objectives, report = false, includeSummary = true, includeCharts = true, includeWindows = true, scenario = $bindable(0), index = $bindable(0) }: {
    run: JourneyRun; objectives: MissionObjectives; report?: boolean; scenario?: number; index?: number;
    includeSummary?: boolean; includeCharts?: boolean; includeWindows?: boolean;
  } = $props();
  const active = $derived(run.evaluations[scenario] ?? run.evaluations[0]!);
  const samples = $derived(active.steps!);
  const percent = (v: number | null) => v === null ? t('journey.unknown') : `${formatNumber(v * 100, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  const number = (v: number | null | undefined, unit = '') => v == null || !Number.isFinite(v) ? t('journey.unknown') : `${formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;
  const stamp = (s: number) => report ? utcMinute(s * 1000) : new Date(s * 1000).toISOString().replace('.000Z', ' UTC').replace('T', ' ');
  const flatZero = (values: readonly (number | null)[]) => values.length > 0 && values.every((v) => v === 0);
  const rows = [
    { key: 'lit', label: 'planner.sun' }, { key: 'earth', label: 'planner.earth' }, { key: 'rf_closes', label: 'planner.rfLine' },
    { key: 'dsn_visible', label: 'planner.rfDsnLine' }, { key: 'useful', label: 'planner.abUseful' },
  ] as const satisfies readonly { key: 'lit' | 'earth' | 'rf_closes' | 'dsn_visible' | 'useful'; label: MessageKey }[];
  function threshold(value: number | null, required: number | null) {
    return t(required === null ? 'planner.criterionNotSet' : value === null ? 'planner.criterionUnknown' :
      value >= required / 100 ? 'planner.criterionMet' : 'planner.criterionNotMet');
  }
  function segments(values: readonly (boolean | null)[]) {
    const groups: { value: boolean | null; length: number }[] = [];
    for (const value of values) {
      const last = groups.at(-1);
      if (last && last.value === value) last.length++;
      else groups.push({ value, length: 1 });
    }
    return groups;
  }
  const states: Record<string, MessageKey> = {
    operational: 'journey.operational', comms_only: 'journey.commsOnly', survival: 'journey.survival',
    dark: 'journey.dark', unknown: 'journey.unknown',
  };
  const reasons: Record<string, MessageKey> = {
    energy: 'journey.energyLimit', link: 'journey.radioLimit', visibility: 'journey.visibilityLimit', multiple: 'journey.multipleLimits',
  };
  const stateText = (e: RavenEvaluation) => t(states[e.steps?.state[index] ?? 'unknown'] ?? 'journey.unknown');
</script>

{#snippet candidates()}
  <div class="comparison">
    {#each run.evaluations as e, i}
      {@const prefix = e.steps!.soc.findIndex((v) => v === null)}
      {@const unknownRf = e.steps!.rf_closes.filter((v) => v === null).length}
      <article class="candidate">
        <span class="eyebrow">{i === 0 ? 'A' : 'B'}</span><h3>{e.site.name}</h3>
        <p>{utcMinute(e.window.start_utc)}</p>
        <dl>
          <div><dt>{t('journey.confirmedUsefulTime')}</dt><dd>{number(e.metrics.useful_hours, 'h')}</dd></div>
          <div><dt>{t('planner.sun')}</dt><dd>{percent(fraction(e.steps!.lit))}</dd></div>
          <div><dt>{t('planner.earth')}</dt><dd>{percent(fraction(earthVisibility(e)))}</dd></div>
          <div><dt>{t('planner.abRf')}</dt><dd>{percent(fraction(e.steps!.rf_closes))}</dd></div>
          <div><dt>{t('planner.energyMinSoc')}</dt><dd>{percent(e.metrics.min_soc)}</dd></div>
          <div><dt>{t('planner.energyHarvested')}</dt><dd>{number(e.metrics.harvested_wh, 'Wh')}</dd></div>
          <div><dt>{t('journey.unknownHours')}</dt><dd>{number(e.metrics.unknown_hours, 'h')}</dd></div>
        </dl>
        {#if e.metrics.harvested_wh !== null && e.metrics.harvested_wh > 0 && e.steps!.soc.every((v) => v === 1)}
          <p class="note">{t('journey.batteryFull')}</p>
        {/if}
        {#if e.steps!.lit.length && e.steps!.lit.every((v) => v === false)}
          <p class="note" data-testid="mission-no-sun">{t('journey.noSunWindow')}</p>
          {#if e.steps!.gen_w.every((v) => v === 0)}
            <p class="note">{t('journey.batteryOnly')}</p>
          {/if}
        {/if}
        {#if prefix >= 0}
          <p class="note" data-testid="mission-energy-prefix">{t('journey.energyPrefix', {
            known: number(prefix * e.window.step_min / 60), total: number(e.window.n_steps * e.window.step_min / 60),
            end: stamp(e.steps!.time_unix[prefix]!),
          })}</p>
          {#if e.steps!.rf_reason[prefix] === 'outside_model'}
            <p class="note">{t('journey.energyUnknownRf')}</p>
          {/if}
        {/if}
        {#if unknownRf}
          <p class="note" data-testid="mission-rf-unknown">{t('journey.rfUnknownCoverage', {
            hours: number(unknownRf * e.window.step_min / 60), total: number(e.window.n_steps * e.window.step_min / 60),
          })}</p>
        {/if}
        {#if unknownRf > 0 && e.metrics.unknown_hours !== null && e.metrics.unknown_hours > 0}
          {@const total = e.window.n_steps * e.window.step_min / 60}
          <table class="measures" data-testid="mission-unknown-measures">
            <caption>{t('journey.measuresCaption')}</caption>
            <thead><tr><th>{t('journey.measure')}</th><th>{t('journey.knownHours')}</th><th>{t('journey.unknownHours')}</th></tr></thead>
            <tbody>
              <tr><th>{t('planner.abRf')}</th><td>{number(total - unknownRf * e.window.step_min / 60, 'h')}</td><td>{number(unknownRf * e.window.step_min / 60, 'h')}</td></tr>
              <tr><th>{t('journey.measureState')}</th><td>{number(total - e.metrics.unknown_hours, 'h')}</td><td>{number(e.metrics.unknown_hours, 'h')}</td></tr>
            </tbody>
          </table>
          <p class="note">{t('journey.measuresNote')}</p>
        {/if}
        <p>{t('planner.minimumSun')}: <strong>{threshold(fraction(e.steps!.lit), objectives.minSunPercent)}</strong></p>
        <p>{t('planner.minimumRf')}: <strong>{threshold(fraction(e.steps!.rf_closes), objectives.minRfPercent)}</strong></p>
      </article>
    {/each}
  </div>
{/snippet}
<div class="results">
  {#if report && includeSummary}{@render candidates()}
  {:else if !report}<div class="scenario-controls">{#each run.evaluations as e, i}
    <button type="button" aria-pressed={scenario === i} onclick={() => scenario = i}>{t('journey.inspect', { scenario: i === 0 ? 'A' : 'B' })} — {e.site.name}</button>
  {/each}</div>{/if}
  <p class="note">{t('journey.samplingNote', { step: active.window.step_min })}</p>
  {#if !report || includeCharts}<MissionStatistics evaluations={run.evaluations} />{/if}
  {#if !report}
    <VisibilityFigures evaluations={run.evaluations} tr={(k, p) => t(k as MessageKey, p)} fmt={(v, d = 1) => formatNumber(v, { minimumFractionDigits: d, maximumFractionDigits: d })} />
    <LunarDays evaluations={run.evaluations} tr={(k, p) => t(k as MessageKey, p)} fmt={(v, d = 1) => formatNumber(v, { minimumFractionDigits: d, maximumFractionDigits: d })} />
  {/if}
  {#if !report}
    <section aria-labelledby="journey-timeline">
      <h3 id="journey-timeline">{t('planner.timelineTitle')}</h3>
      <label for="journey-time">{t('planner.instant', { scenario: scenario === 0 ? 'A' : 'B' })} <strong>{stamp(samples.time_unix[index]!)}</strong></label>
      <input id="journey-time" type="range" min="0" max={samples.time_unix.length - 1} step="1" bind:value={index} />
      <p aria-live="polite">{stateText(active)} · {t(reasons[samples.limiting[index] ?? ''] ?? 'journey.noLimit')}</p>
      <div class="instant">
        <span>{t('planner.sun')}: {number(samples.sun_el_deg[index], '°')}</span>
        <span>{t('planner.earth')}: {number(samples.earth_el_deg[index], '°')}</span>
        <span>{t('planner.rfMargin')}: {number(samples.margin_db[index], 'dB')}</span>
        <span>{t('journey.chosenRate')}: {number(samples.chosen_rate_bps?.[index], 'bit/s')}</span>
        <span>{t('planner.socChart')}: {percent(samples.soc[index] ?? null)}</span>
      </div>
      {#each rows as row}
        {@const values = row.key === 'earth' ? earthVisibility(active) : samples[row.key]}
        {@const next = firstChange(values, index)}
        {@const nextLabel: MessageKey = row.key === 'lit' ? values[index] ? 'journey.nextSunset' : 'journey.nextSunrise' :
          row.key === 'earth' ? values[index] ? 'journey.nextEarthset' : 'journey.nextEarthrise' : 'journey.nextChange'}
        <div class="timeline">
          <span>{t(row.label)}</span>
          <div class="track" role="img" aria-label={`${t(row.label)}: ${percent(fraction(values))}`}>
            {#each segments(values) as s}<span class:yes={s.value === true} class:no={s.value === false} class:unknown={s.value === null} style:flex-grow={s.length}></span>{/each}
            <i style:left={`${samples.time_unix.length < 2 ? 0 : index / (samples.time_unix.length - 1) * 100}%`}></i>
          </div>
          <small>{next === null ? t('journey.noChange') : t(nextLabel, { hours: ((next - index) * active.window.step_min / 60).toFixed(1) })}</small>
        </div>
      {/each}
      <p class="note">{t('journey.timelineLegend')}</p>
      <p class="note">{t('journey.kEffect')}</p>
    </section>
  {/if}
  {#each report ? run.evaluations : [active] as e}
    {@const rfBlocked = e.steps!.rf_closes.length > 0 && e.steps!.rf_closes.every((v) => v === false)}
    {#if !report || includeCharts}<section class="graphs">
      <h3>{report ? e.site.name : t('journey.graphs')}</h3>
      {#each [
        { label: t('planner.sun'), unit: '°', values: e.steps!.sun_el_deg },
        { label: t('planner.earth'), unit: '°', values: e.steps!.earth_el_deg },
        ...(flatZero(e.steps!.gen_w) ? [] : [{ label: t('planner.powerChart'), unit: 'W', values: e.steps!.gen_w }]),
        { label: t('planner.socChart'), unit: '%', values: e.steps!.soc.map((v) => v === null ? null : v * 100),
          description: t('planner.socChartHelp'), timeOffsetSeconds: e.window.step_min * 60 },
        { label: t('planner.rfMargin'), unit: 'dB', values: e.steps!.margin_db,
          emptyLabel: rfBlocked ? t('journey.noFiniteRfMargin') : undefined },
        ...(e.steps!.chosen_rate_bps ? [{ label: t('journey.chosenRate'), unit: 'bit/s', values: e.steps!.chosen_rate_bps,
          emptyLabel: rfBlocked ? t('journey.noSupportedRate') : undefined }] : []),
      ] as chart}
        <SeriesChart {...chart} times={e.steps!.time_unix} cursorIndex={report ? undefined : index}
          onselect={report ? undefined : (i) => index = i} rangeLabel={t('planner.chartRange')} emptyLabel={chart.emptyLabel ?? t('planner.chartEmpty')} />
      {/each}
      {#if flatZero(e.steps!.gen_w)}<p class="note" data-testid="flat-power-note">{t(e.steps!.lit.length && e.steps!.lit.every((v) => v === false) ? 'journey.powerZeroDark' : 'journey.powerZero')}</p>{/if}
    </section>{/if}
    {#if !report || includeWindows}<section class="windows">
      <h3>{t('planner.windowComparison')} — {e.site.name}</h3>
      <p class="note">{t('journey.windowsNote')}</p>
      <div class="table-wrap"><table>
        <thead><tr><th>{t('planner.windowCondition')}</th><th>{t('planner.startUtc')}</th><th>{t('journey.endUtc')}</th></tr></thead>
        <tbody>
          {#each [{ key: 'lit', label: 'planner.sun' }, { key: 'link_usable', label: 'planner.rfDsnLine' }, { key: 'useful', label: 'planner.abUseful' }] as row}
            {#each e.windows?.[row.key as 'lit' | 'link_usable' | 'useful'] ?? [] as window}
              <tr><th>{t(row.label as MessageKey)}</th><td>{stamp(window.start_unix)}{window.open_start ? ' *' : ''}</td><td>{stamp(window.end_unix)}{window.open_end ? ' *' : ''}</td></tr>
            {:else}<tr><th>{t(row.label as MessageKey)}</th><td colspan="2">{t(e.metrics.unknown_steps > 0 ? 'journey.unknown' : 'journey.noWindows')}</td></tr>{/each}
          {/each}
        </tbody>
      </table></div>
    </section>{/if}
  {/each}
  {#if !report}{@render candidates()}{/if}
  <p class="model-stamp note">{active.model_version} · {active.registry_sha256}</p>
</div>

<style>
  .measures { width: 100%; border-collapse: collapse; font-size: .85rem; margin-block: .75rem; } .measures caption { text-align: start; font-weight: 600; padding-block: .25rem; }
  .measures th, .measures td { text-align: start; padding: .3rem .5rem; border-bottom: 1px solid #7499b64d; font-variant-numeric: tabular-nums; }
  .results { display: grid; gap: 1.4rem; }
  .scenario-controls { display: flex; flex-wrap: wrap; gap: .5rem; }
  .model-stamp { overflow-wrap: anywhere; }
  .comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
  .candidate { padding: 1.25rem; border: 1px solid #759bb84d; border-radius: 1rem; background: #10233b70; }
  .eyebrow { color: #a4e5ff; font: 600 .85rem Orbitron, sans-serif; } h3 { margin: .4rem 0 1rem; }
  .candidate p, .note { color: var(--c-muted); font-size: .85rem; }
  dl { display: grid; gap: .6rem; } dl div { display: flex; justify-content: space-between; gap: 1rem; }
  dd { margin: 0; font-variant-numeric: tabular-nums; } dt { color: var(--c-muted); }
  #journey-time { width: 100%; min-height: 44px; accent-color: #9bdfff; }
  .instant { display: flex; flex-wrap: wrap; gap: 1rem; padding-block: 1rem; }
  .timeline { display: grid; gap: .4rem; margin-block: 1rem; } small { color: var(--c-muted); }
  .track { display: flex; position: relative; height: 1rem; border: 1px solid #ffffff50; border-radius: .2rem; }
  .yes { background: #66d8bd; } .no { background: #72627e; }
  .unknown { background: repeating-linear-gradient(45deg, #99a3b8 0 3px, #293447 3px 6px); }
  .track i { position: absolute; top: -.25rem; bottom: -.25rem; width: 2px; background: white; }
  .table-wrap { overflow-x: auto; } table { width: 100%; font-size: .85rem; } th, td { padding: .6rem; text-align: start; }
  button { min-height: 44px; }
  @media (max-width: 650px) { .comparison { grid-template-columns: 1fr; } }
  @media print { .candidate, section { break-inside: avoid; } .comparison { grid-template-columns: 1fr 1fr; } }
</style>
