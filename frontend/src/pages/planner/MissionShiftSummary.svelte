<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import type { MissionShiftBaseline, MissionShiftDays } from './journey';

  type Label = 'analysisTitle' | 'selected' | 'site' | 'baselineStart' | 'evaluatedStart' | 'usefulBaseline' | 'usefulSelected' |
    'usefulChange' | 'socBaseline' | 'socSelected' | 'baselineMissing' | 'unknown';
  let { evaluations, baseline = [], shiftDays, tr, fmt }: {
    evaluations: readonly RavenEvaluation[];
    baseline?: readonly MissionShiftBaseline[];
    shiftDays: MissionShiftDays;
    tr: (key: Label, params?: Record<string, string | number>) => string;
    fmt: (value: number, digits?: number) => string;
  } = $props();

  const rows = $derived(evaluations.map((evaluation) => {
    const baselineStart = evaluation.base_start_utc ?? evaluation.window.start_utc;
    const stored = baseline.find((item) => item.site_id === evaluation.site.id && item.start_utc === baselineStart);
    const comparison = stored ?? (shiftDays === 0 ? {
      site_id: evaluation.site.id,
      site_name: evaluation.site.name,
      start_utc: evaluation.base_start_utc ?? evaluation.window.start_utc,
      useful_hours: evaluation.metrics.useful_hours,
      unknown_hours: evaluation.metrics.unknown_hours,
      harvested_wh: evaluation.metrics.harvested_wh,
      min_soc: evaluation.metrics.min_soc,
    } : null);
    return { evaluation, comparison };
  }));
  const stamp = (value: string) => value.replace('T', ' ').replace(/:\d{2}Z$/, ' UTC');
  const quantity = (value: number | null | undefined, unit: string, digits = 1) =>
    value === null || value === undefined || !Number.isFinite(value) ? tr('unknown') : `${fmt(value, digits)} ${unit}`;
  const change = (current: number | null, base: number | null | undefined, unit: string, scale = 1) =>
    current === null || base === null || base === undefined ? tr('unknown')
      : `${current - base >= 0 ? '+' : ''}${fmt((current - base) * scale, 1)} ${unit}`;
</script>

{#if evaluations.length}
  <section class="mission-shift-summary" data-testid="mission-time-shift-summary">
    <h3>{tr('analysisTitle')}</h3>
    <p>{tr('selected', { days: shiftDays })}</p>
    {#if shiftDays > 0 && !baseline.length}<p class="note">{tr('baselineMissing')}</p>{/if}
    <div class="table-wrap">
      <table class="rp-risktable">
        <thead><tr>
          <th scope="col">{tr('site')}</th><th scope="col">{tr('baselineStart')} → {tr('evaluatedStart')}</th>
          <th scope="col">{tr('usefulBaseline')}</th><th scope="col">{tr('usefulSelected')}</th>
          <th scope="col">{tr('usefulChange')}</th><th scope="col">{tr('socBaseline')}</th><th scope="col">{tr('socSelected')}</th>
        </tr></thead>
        <tbody>{#each rows as { evaluation, comparison }, i (i)}
          <tr>
            <th scope="row">{evaluation.site.name}</th>
            <td>{stamp(comparison?.start_utc ?? evaluation.base_start_utc ?? evaluation.window.start_utc)} → {stamp(evaluation.window.start_utc)}</td>
            <td>{quantity(comparison?.useful_hours, 'h')}</td>
            <td>{quantity(evaluation.metrics.useful_hours, 'h')}</td>
            <td>{change(evaluation.metrics.useful_hours, comparison?.useful_hours, 'h')}</td>
            <td>{quantity(comparison?.min_soc === null || comparison?.min_soc === undefined ? null : comparison.min_soc * 100, '%')}</td>
            <td>{quantity(evaluation.metrics.min_soc === null ? null : evaluation.metrics.min_soc * 100, '%')}</td>
          </tr>
        {/each}</tbody>
      </table>
    </div>
  </section>
{/if}

<style>
  .mission-shift-summary { margin-block: 1.5rem; }
  .mission-shift-summary p, .note { color: var(--c-muted); font-size: .9rem; }
  .table-wrap { overflow-x: auto; }
  table { min-width: 46rem; font-variant-numeric: tabular-nums; }
</style>
