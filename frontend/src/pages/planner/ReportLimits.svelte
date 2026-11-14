<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 4: ONE box with the limits that apply to this run, the validation status by engine stage, the single disclaimer. -->
<script lang="ts">
  import { rt } from './reportText';
  import type { RavenEvaluation, RavenValidation } from '../../shell/ravenApi';
  import { stageStatus, variableValue } from './reportFormulas';
  import StatusChip from './StatusChip.svelte';
  import { NO_SOURCE_CHECKLIST } from './estimates/missionClass';
  let { evaluations, validation = null, extraLoadW = null }: { evaluations: readonly RavenEvaluation[]; validation?: RavenValidation | null; extraLoadW?: number | null } = $props();
  const STAGES = ['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'];
  const limits = $derived([...new Set(evaluations.flatMap((e) => e.declared_limits))]);
  const terrain = $derived(evaluations.filter((e) => e.inputs_state.terrain_mask !== 'ok'));
  const first = $derived(evaluations[0]);
  /** The load assumptions behind the battery result, so a changed useful-hours figure can be traced to its cause. */
  const loads = $derived(first ? { active: variableValue('active_load', first), survival: variableValue('survival_load', first), comms: variableValue('comms_load', first), duty: variableValue('comms_duty', first), capacity: variableValue('battery_capacity', first), reserve: variableValue('reserve_threshold', first) } : null);
  const loadsKnown = $derived(!!loads && Object.values(loads).every((v) => v !== null));
</script>

<section class="rp-limits" data-testid="mission-liability">
  <div class="rp-limit-box" data-testid="report-essential-limits">
    <ul>
      {#each limits as limit}<li>{limit}</li>{/each}
      {#if loads && loadsKnown}<li data-testid="report-load-assumptions">{rt('limits.loads', loads as Record<string, string>)}</li>{/if}
      {#if extraLoadW !== null}<li data-testid="report-thermal-load">{rt('limits.thermal', { w: String(extraLoadW) })}</li>{/if}
      {#each terrain as e}<li>{rt('limits.terrain', { site: e.site.name, state: e.inputs_state.terrain_mask })}</li>{/each}
    </ul>
  </div>
  <table class="rp-stages">
    <thead><tr><th scope="col">{rt('limits.stage')}</th><th scope="col">{rt('limits.status')}</th></tr></thead>
    <tbody>{#each STAGES as s}<tr><th scope="row">{rt(`stage.${s}`)}</th><td><StatusChip kind={stageStatus(validation, [s])} /></td></tr>{/each}</tbody>
  </table>
  <div class="rp-limit-box" data-testid="report-checklist"><strong>{rt('check.title', { n: NO_SOURCE_CHECKLIST.length })}</strong> {rt('check.intro')}
    <ul>{#each NO_SOURCE_CHECKLIST as item}<li>{item}</li>{/each}</ul></div>
  <p class="rp-disclaimer">{rt('disclaimer')}</p>
</section>
