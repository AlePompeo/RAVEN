<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { scopedI18n } from '../../i18n/reportScope';
  const { t, formatNumber } = scopedI18n();
  import { mergeIdenticalScenarios, type ReliabilityResult, type ReliabilityScenario, type ReliabilityComponentResult } from './reliability';
  import ComparisonBars from './ComparisonBars.svelte';
  let { result }: { result: ReliabilityResult } = $props();
  const curves = [
    { label: 'rel.survival', key: 'hardware_survival' },
    { label: 'rel.operational', key: 'conditional_operational' },
    { label: 'rel.retainedChart', key: 'retained_min' },
  ] as const;
  const percent = (v: number | null | undefined) => v == null ? null : v * 100;
  const number = (v: number | null | undefined, unit = '') => v == null ? t('rel.chart.unknown')
    : `${formatNumber(v, { maximumSignificantDigits: 4 })}${unit ? ' ' + unit : ''}`;
  const merged = $derived(mergeIdenticalScenarios(result.scenarios));
  const scenarios = $derived(merged.shown);
  const labels = $derived(scenarios.map((s) => `${s.id} · ${number(s.duration_hours, 'h')}`));
  const horizon = $derived(Math.max(...scenarios.map((s) => s.duration_hours)));
  const component = (s: ReliabilityScenario, id: string) => s.components.find((c) => c.id === id);
  const componentRows = (values: (id: string) => (number | null)[]) => result.assumptions.components.map((c) =>
    ({ label: t(`rel.component.${c.id}`), values: values(c.id) }));
  const componentValues = (id: string, key: 'failure_probability' | 'dose_krad') =>
    scenarios.map((s) => component(s, id)?.[key] ?? null);
  const sharedValue = (id: string, key: keyof Pick<ReliabilityComponentResult, 'thermal_margin_c' | 'mean_recovery_hours' | 'retained_at_landing'>) =>
    scenarios[0] ? component(scenarios[0], id)?.[key] ?? null : null;
  function paths(s: ReliabilityScenario, key: typeof curves[number]['key']) {
    const groups: { x: number; y: number }[][] = [];
    let group: { x: number; y: number }[] = [];
    for (const point of s.timeline) {
      const value = point[key];
      if (value === null) {
        if (group.length) groups.push(group);
        group = [];
      } else group.push({ x: point.hours / horizon * 600, y: 130 - value * 120 });
    }
    if (group.length) groups.push(group);
    return groups;
  }
</script>

<section class="reliability-charts" data-testid="reliability-charts">
  <h4>{t('rel.chart.title')}</h4>
  <p>{t('rel.chart.comparisonScope')}</p>
  <div class="graphs">
    {#each curves as curve}
      <figure class="chart reliability-timeline" aria-label={t(curve.label)}>
        <figcaption>{t(curve.label)} (%)</figcaption>
        <p>{t('rel.chart.elapsed')}</p>
        <ul class="legend" aria-label={t('rel.chart.legend')}>
          {#each scenarios as s, i}
            <li><span class="line-key" class:second={i === 1} aria-hidden="true"></span>{labels[i]}:
              {number(percent(s.timeline.at(-1)?.[curve.key]), '%')}</li>
          {/each}
        </ul>
        <div class="time-plot">
          <div class="y-axis" aria-hidden="true"><span>100</span><span>50</span><span>0</span></div>
          <svg viewBox="-4 0 608 140" role="img" aria-label={t(curve.label)} preserveAspectRatio="none">
            {#each [10, 70, 130] as y}<line class="grid-line" x1="0" x2="600" y1={y} y2={y} />{/each}
            {#each scenarios as s, i}
              <g class:second={i === 1} data-scenario={s.id}>
                {#each paths(s, curve.key) as group}
                  {#if group.length === 1}<circle cx={group[0]!.x} cy={group[0]!.y} r="3" />
                  {:else}<polyline points={group.map((p) => `${p.x},${p.y}`).join(' ')} />{/if}
                {/each}
              </g>
            {/each}
          </svg>
        </div>
        <div class="axis"><span>0 h</span><span>{number(horizon, 'h')}</span></div>
      </figure>
    {/each}
    <ComparisonBars label={t('rel.chart.chain')} unit="%" description={t('rel.chart.chainScope')} series={labels} fixedMax={100}
      rows={[
        ...(['launch', 'cruise', 'landing'] as const).map((phase) => ({
          label: t(`rel.stage.${phase}`),
          values: scenarios.map((s) => percent(s.stages.find((p) => p.phase === phase)?.survival_probability)),
        })),
        { label: t('rel.survival'), values: scenarios.map((s) => percent(s.hardware_survival_probability)) },
        { label: t('rel.stage.operations'), values: scenarios.map((s) => percent(s.conditional_operational_probability)) },
      ]} />
    <ComparisonBars label={t('rel.chart.faults')} unit="%" description={t('rel.chart.faultScope')} series={labels}
      rows={componentRows((id) => componentValues(id, 'failure_probability').map(percent))} />
    <ComparisonBars label={t('rel.chart.recovery')} unit="h" description={t('rel.chart.sharedScope')} series={[t('rel.chart.shared')]}
      rows={componentRows((id) => [sharedValue(id, 'mean_recovery_hours')])} />
    <ComparisonBars label={t('rel.chart.retention')} unit="%" description={t('rel.chart.retentionScope')} fixedMax={100}
      series={[...labels, t('rel.retainedLanding')]}
      rows={componentRows((id) => [...scenarios.map((s) => percent(component(s, id)?.retained_at_end)),
        percent(sharedValue(id, 'retained_at_landing'))])} />
    <ComparisonBars label={t('rel.chart.thermal')} unit="°C" description={t('rel.chart.thermalScope')} series={[t('rel.chart.shared')]}
      rows={componentRows((id) => [sharedValue(id, 'thermal_margin_c')])} />
    <ComparisonBars label={t('rel.chart.radiation')} unit="krad(Si)" description={t('rel.chart.radiationScope')}
      series={[...labels, t('rel.field.tid_limit_krad')]}
      rows={componentRows((id) => [...componentValues(id, 'dose_krad'),
        result.assumptions.components.find((c) => c.id === id)?.tid_limit_krad ?? null])} />
    <ComparisonBars label={t('rel.chart.hours')} unit="h" description={t('rel.chart.hoursScope')} series={labels}
      rows={[
        { label: t('rel.available'), values: scenarios.map((s) => s.expected_available_hours) },
        { label: t('rel.unavailable'), values: scenarios.map((s) => s.expected_unavailable_hours) },
        { label: t('rel.chart.usefulLower'), values: scenarios.map((s) => s.expected_useful_lower_hours) },
        { label: t('rel.chart.usefulUpper'), values: scenarios.map((s) => s.expected_useful_upper_hours) },
      ]} />
  </div>
  <p class="note">{t('rel.chartScope')}</p>
</section>

<style>
  .graphs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem 1.5rem; }
  .chart { margin: 1rem 0; min-width: 0; } figcaption { font-weight: 600; }
  p, .legend { font-size: .85rem; color: var(--c-muted); }
  .legend { display: flex; flex-wrap: wrap; list-style: none; gap: .3rem .8rem; padding: 0; }
  .legend li { display: flex; align-items: center; gap: .3rem; }
  .line-key { width: 1rem; border-top: 2px solid var(--c-action); flex-shrink: 0; }
  .line-key.second { border-top: 2px dashed var(--c-power); }
  .time-plot { display: grid; grid-template-columns: 2.5rem minmax(0, 1fr); gap: .4rem; }
  .y-axis { display: flex; flex-direction: column; justify-content: space-between; text-align: end; font-size: .75rem; }
  svg { width: 100%; height: 7rem; border: 1px solid var(--c-hairline); display: block; }
  .grid-line { stroke: var(--c-hairline); stroke-dasharray: 3 4; }
  polyline { fill: none; stroke: var(--c-action); stroke-width: 2; vector-effect: non-scaling-stroke; }
  circle { fill: var(--c-action); }
  .second polyline { stroke: var(--c-power); stroke-dasharray: 7 4; } .second circle { fill: var(--c-power); }
  .axis { display: flex; justify-content: space-between; margin-left: 2.9rem; color: var(--c-muted); font-size: .75rem; }
  @media (max-width: 650px) { .graphs { grid-template-columns: 1fr; } }
</style>
