<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { scopedI18n } from '../../i18n/reportScope';
  const { t, formatNumber } = scopedI18n();
  import { componentFields, COMPONENT_FIELDS, profileFields, PROFILE_FIELDS, type ReliabilityResult } from './reliability';
  import ReliabilityCharts from './ReliabilityCharts.svelte';
  import { mergeIdenticalScenarios } from './reliability';
  let { result, showInputs = false, charts = true }: { result: ReliabilityResult; showInputs?: boolean; charts?: boolean } = $props();
  const merged = $derived(mergeIdenticalScenarios(result.scenarios));
  const number = (v: number | null, unit = '') => v === null ? t('report.notAssessed') :
    `${formatNumber(v, { maximumSignificantDigits: 4 })}${unit ? ' ' + unit : ''}`;
  const percent = (v: number | null) => number(v === null ? null : v * 100, '%');
</script>

<section class="reliability-results" data-testid="reliability-results">
  <h3>{t('rel.title')}</h3>
  <p class="scope">{t('rel.scope')}</p>
  <p>{t('rel.conditions')}</p>
  <p class="registry">{result.model} · {t('rel.basis')}: {result.assumptions.basis}</p>
  <p>{t('rel.formula')}</p>
  {#if merged.identical}<p class="scope" data-testid="reliability-identical">{t('rel.identical')}</p>{/if}
  {#if charts}<ReliabilityCharts {result} />{/if}
  {#each merged.shown as scenario}
    <section class="reliability-scenario" data-testid={`reliability-${scenario.id.slice(0, 1)}`}>
      <h4>{t('rel.scenario', { scenario: scenario.id, hours: number(scenario.duration_hours, 'h') })}</h4>
      {#if !scenario.complete_probability_inputs}<p class="status">{t('rel.incomplete')}</p>{/if}
      <ol class="chain">
        {#each scenario.stages as stage}<li><strong>{t(`rel.stage.${stage.phase}`)}</strong> {percent(stage.survival_probability)}</li>{/each}
        <li><strong>{t('rel.stage.operations')}</strong> {percent(scenario.conditional_operational_probability)}</li>
      </ol>
      <dl class="pending">
        <div><dt>{t('rel.survival')}</dt><dd>{percent(scenario.hardware_survival_probability)}</dd></div>
        <div><dt>{t('rel.operational')}</dt><dd>{percent(scenario.conditional_operational_probability)}</dd></div>
        <div><dt>{t('rel.available')}</dt><dd>{number(scenario.expected_available_hours, 'h')}</dd></div>
        <div><dt>{t('rel.unavailable')}</dt><dd>{number(scenario.expected_unavailable_hours, 'h')}</dd></div>
        <div><dt>{t('rel.useful')}</dt><dd>{number(scenario.expected_useful_hours, 'h')}</dd></div>
        <div><dt>{t('rel.usefulBounds')}</dt><dd>{number(scenario.expected_useful_lower_hours, 'h')} / {number(scenario.expected_useful_upper_hours, 'h')}</dd></div>
      </dl>
      <p class="note">{t('rel.durationScope')}</p>
      <div class="table-wrap">
        <table>
          <caption>{t('rel.faultTable')}</caption>
          <thead><tr><th>{t('rel.component')}</th><th>{t('rel.failure')}</th><th>{t('rel.malfunction')}</th><th>{t('rel.restart')}</th><th>{t('rel.recovery')}</th><th>{t('rel.restartCount')}</th></tr></thead>
          <tbody>{#each scenario.components as c}<tr><th>{t(`rel.component.${c.id}`)}</th><td>{percent(c.failure_probability)}</td><td>{percent(c.malfunction_probability)}</td><td>{percent(c.restart_probability)}</td><td>{number(c.mean_recovery_hours, 'h')}</td><td>{number(c.expected_restart_count_full_exposure)}</td></tr>{/each}</tbody>
        </table>
      </div>
      <div class="table-wrap">
        <table>
          <caption>{t('rel.environmentTable')}</caption>
          <thead><tr><th>{t('rel.component')}</th><th>{t('rel.retainedLanding')}</th><th>{t('rel.retainedEnd')}</th><th>{t('rel.thermalMargin')}</th><th>{t('rel.dose')}</th><th>{t('rel.radiationMargin')}</th></tr></thead>
          <tbody>{#each scenario.components as c}<tr><th>{t(`rel.component.${c.id}`)}</th><td>{percent(c.retained_at_landing)}</td><td>{percent(c.retained_at_end)}</td><td>{number(c.thermal_margin_c, '°C')}</td><td>{number(c.dose_krad, 'krad(Si)')}</td><td>{number(c.radiation_margin_krad, 'krad(Si)')}</td></tr>{/each}</tbody>
        </table>
      </div>
      {#each scenario.components as c}
        <p class:status={c.environment_status !== 'within_declared_envelope'}>{t(`rel.component.${c.id}`)}: {t(`rel.environment.${c.environment_status}`)}
          {#if c.performance_cutoff_hours !== null} · <strong>{t('rel.cutoff', { hours: number(c.performance_cutoff_hours, 'h') })}</strong>{/if}
          {#if c.missing.length} · {t('rel.missing')}: {c.missing.map((field) => t(`rel.field.${field}`)).join('; ')}{/if}
        </p>
      {/each}
    </section>
  {/each}
  {#if showInputs}
    <h4>{t('rel.inputRecord')}</h4>
    <dl class="pending">{#each profileFields as key}<div><dt>{t(`rel.field.${key}`)}</dt><dd>{number(result.assumptions[key], PROFILE_FIELDS[key][2])}</dd></div>{/each}</dl>
    <p>{t('rel.applyPower')}: {t(result.assumptions.apply_thermal_load ? 'rel.yes' : 'rel.no')}</p>
    <div class="table-wrap"><table>
      <caption>{t('rel.componentAssumptions')}</caption>
      <thead><tr><th>{t('journey.parameter')}</th>{#each result.assumptions.components as c}<th>{t(`rel.component.${c.id}`)}</th>{/each}</tr></thead>
      <tbody>
        <tr><th>{t('rel.protection')}</th>{#each result.assumptions.components as c}<td>{t(`rel.protection.${c.protection}`)}</td>{/each}</tr>
        {#each componentFields as field}<tr><th>{t(`rel.field.${field}`)} ({COMPONENT_FIELDS[field][2]})</th>{#each result.assumptions.components as c}<td>{number(c[field])}</td>{/each}</tr>{/each}
      </tbody>
    </table></div>
    <p>{t('rel.thermalHelp')}</p><p>{t('rel.radiationHelp')}</p>
  {/if}
</section>

<style>
  .reliability-results { margin-block: 1.5rem; min-width: 0; } p { line-height: 1.55; overflow-wrap: anywhere; }
  .scope, .status { border-inline-start: 3px solid #d6ba7c; padding-inline-start: .75rem; }
  .chain { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; padding-inline-start: 1.5rem; } .chain strong { display: block; }
  .pending { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; } dt { font-weight: 600; } dd { margin: .25rem 0; font-variant-numeric: tabular-nums; }
  .table-wrap { overflow-x: auto; } table { width: 100%; border-collapse: collapse; font-size: .85rem; }
  caption { text-align: start; font-weight: 600; padding-block: 1rem .5rem; } th, td { text-align: start; padding: .5rem; border-bottom: 1px solid #7499b64d; vertical-align: top; }
  .note, .registry { color: var(--c-muted); font-size: .85rem; }
  @media (max-width: 650px) { .pending { grid-template-columns: 1fr; } .chain { grid-template-columns: 1fr 1fr; } }
  @media print { .table-wrap { overflow: visible; } .chain { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
</style>
