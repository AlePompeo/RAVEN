<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The essential questions, shared by Learn and Expert: purpose (a list), statement, success criteria, owner, plus the two
     thresholds already set in the Mission step (read-only here so that the dossier never invalidates the calculation). -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import type { MissionObjectives } from './objectives';
  import type { ReportPlanning } from './reportPlanning';
  import { OBJECTIVE_TYPES } from './reportMode';
  let { planning = $bindable(), objectives, editMission }: { planning: ReportPlanning; objectives: MissionObjectives; editMission: () => void } = $props();
  const percent = (v: number | null) => v === null ? t('planner.criterionNotSet') : `${v}%`;
</script>

<section class="essential" data-testid="dossier-essential" aria-labelledby="dossier-essential-title">
  <h3 id="dossier-essential-title">{t('learn.essentialTitle')}</h3>
  <p>{t('learn.essentialIntro')}</p>
  <label for="dossier-purpose">{t('dossier.objectiveType')}</label>
  <select id="dossier-purpose" aria-describedby="dossier-purpose-help" bind:value={planning.objectiveType}>
    <option value="">{t('report.notProvided')}</option>
    {#each OBJECTIVE_TYPES as type}<option value={type}>{t(`report.field.${type}_objectives` as 'report.field.scientific_objectives')}</option>{/each}
  </select>
  <p id="dossier-purpose-help" class="help">{t('learn.purposeHelp')}</p>
  {#each ['missionStatement', 'successCriteria', 'owner'] as const as field}
    <label for={`dossier-${field}`}>{t(`dossier.input.${field}`)}</label>
    <input id={`dossier-${field}`} type="text" maxlength="1000" bind:value={planning.text[field]} />
  {/each}
  <div class="thresholds" data-testid="dossier-thresholds">
    <h4>{t('learn.setInMission')}</h4>
    <dl><div><dt>{t('planner.minimumSun')}</dt><dd>{percent(objectives.minSunPercent)}</dd></div>
      <div><dt>{t('planner.minimumRf')}</dt><dd>{percent(objectives.minRfPercent)}</dd></div></dl>
    <button type="button" onclick={editMission}>{t('learn.editMission')}</button>
  </div>
</section>

<style>
  label { display: block; font-weight: 600; margin-block: 1rem .5rem; }
  input, select { box-sizing: border-box; width: 100%; min-height: 44px; padding: .7rem; color: inherit; background: #081426; border: 1px solid #7b9cb36e; border-radius: .65rem; }
  .help { margin: .4rem 0 0; font-size: .9rem; line-height: 1.5; }
  .thresholds { margin-top: 1.2rem; padding: .8rem 1rem; border: 1px dashed #7b9cb36e; border-radius: .65rem; }
  h3, h4 { margin-block: .4rem; } dl { display: flex; flex-wrap: wrap; gap: .5rem 2rem; margin: .4rem 0; } dl div { display: flex; gap: .5rem; } dt { font-weight: 600; } dd { margin: 0; }
  button { min-height: 44px; padding: .6rem 1rem; }
</style>
