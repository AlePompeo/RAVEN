<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import type { MissionObjectives } from './objectives';
  import type { ReportPlanning } from './reportPlanning';
  import { OBJECTIVE_TYPES } from './reportMode';
  let { planning = $bindable(), objectives, editMission }: { planning: ReportPlanning; objectives: MissionObjectives; editMission: () => void } = $props();
  const percent = (v: number | null) => v === null ? t('planner.criterionNotSet') : `${v}%`;
</script>

<section class="essential" data-testid="dossier-essential">
  <label for="dossier-purpose">{t('dossier.objectiveType')}</label>
  <select id="dossier-purpose" bind:value={planning.objectiveType}>
    <option value="">{t('report.notProvided')}</option>
    {#each OBJECTIVE_TYPES as type}<option value={type}>{t(`report.field.${type}_objectives` as 'report.field.scientific_objectives')}</option>{/each}
  </select>
  <div class="thresholds" data-testid="dossier-thresholds">
    <h3>{t('learn.setInMission')}</h3>
    <dl><div><dt>{t('planner.minimumSun')}</dt><dd>{percent(objectives.minSunPercent)}</dd></div>
      <div><dt>{t('planner.minimumRf')}</dt><dd>{percent(objectives.minRfPercent)}</dd></div></dl>
    <button type="button" onclick={editMission}>{t('learn.editMission')}</button>
  </div>
</section>

<style>
  label { display: block; font-weight: 600; margin-block: 1rem .5rem; }
  select { box-sizing: border-box; width: 100%; min-height: 44px; padding: .7rem; color: inherit; background: #081426; border: 1px solid #7b9cb36e; border-radius: .65rem; }
  .thresholds { margin-top: 1.2rem; padding: .8rem 1rem; border: 1px dashed #7b9cb36e; border-radius: .65rem; }
  h3 { margin-block: .4rem; } dl { display: flex; flex-wrap: wrap; gap: .5rem 2rem; margin: .4rem 0; } dl div { display: flex; gap: .5rem; } dt { font-weight: 600; } dd { margin: 0; }
  button { min-height: 44px; padding: .6rem 1rem; }
</style>
