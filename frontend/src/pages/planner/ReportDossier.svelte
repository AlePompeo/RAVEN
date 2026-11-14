<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Dossier step. Learn: the essential questions, one-click report, every other field hidden (not deleted).
     Expert: every field, in closed "Optional" groups with a counter. Same numbers in both modes. -->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import { defaultMassDefaults } from './estimates';
  import type { ReportPlanning, BudgetEstimate, CarbonEstimate } from './reportPlanning';
  import ReportModeSwitch from './ReportModeSwitch.svelte';
  import ReportOptionalSections from './ReportOptionalSections.svelte';
  import DossierEssential from './DossierEssential.svelte';
  import MissionClassSlider from './MissionClassSlider.svelte';
  import type { MissionObjectives } from './objectives';
  import type { ReportMode } from './reportSections';
  import { SCENARIO_SLOT, type DossierProgress } from './reportMode';
  let { planning = $bindable(), budget, carbon = null, busy, error, siBusy, siError, generate, clearSi,
    allowExternal = $bindable(false), cloudAvailable = false, mode, setMode, objectives, editMission, progress, canOpenReport, openReport,
    scenarioSlot }: {
    planning: ReportPlanning; budget: BudgetEstimate | null; carbon?: CarbonEstimate | null; busy: boolean; error: string | null;
    siBusy: boolean; siError: string | null; generate: () => void; clearSi: () => void;
    allowExternal?: boolean; cloudAvailable?: boolean;
    mode: ReportMode; setMode: (mode: ReportMode) => void; objectives: MissionObjectives; editMission: () => void;
    progress: DossierProgress; canOpenReport: boolean; openReport: () => void;
    /** Extension slot for the scenario slider (a later job). Nothing is rendered until a snippet is passed. */
    scenarioSlot?: Snippet;
  } = $props();
</script>

<div class="dossier" data-testid="report-dossier" data-mode={mode}>
  <ReportModeSwitch {mode} onchange={setMode} />
  {#if mode === 'expert'}<p>{t('dossier.intro')}</p>{/if}
  <p role="status" data-testid="dossier-progress"><strong>{t('prog.title')}.</strong> {t('prog.text', { ...progress })}</p>
  {#if busy}<p role="status">{t('dossier.calculating')}</p>{/if}
  {#if error}<p role="alert">{error}</p>{/if}

  <DossierEssential bind:planning {objectives} {editMission} />

  <MissionClassSlider bind:value={planning.missionClass} />

  <fieldset class="estimates" data-testid="raven-estimates">
    <legend>{t('est.legend')}</legend>
    <label class="check"><input id="estimates-on" type="checkbox" checked={!planning.estimatesOff}
      onchange={(e) => { planning.estimatesOff = e.currentTarget.checked ? undefined : true; }} />{t('est.on')}</label>
    <p>{t('est.scope')}</p>
    {#if mode === 'expert' && !planning.estimatesOff}
      <label class="check"><input id="mass-apply" type="checkbox" checked={planning.massDefaults?.applied ?? true}
        onchange={(e) => { planning.massDefaults = { ...(planning.massDefaults ?? defaultMassDefaults()), applied: e.currentTarget.checked }; }} />{t('est.massApply')}</label>
    {/if}
  </fieldset>

  {#if mode === 'learn'}
    <section class="generate" data-testid="learn-generate" aria-labelledby="learn-generate-title">
      <h3 id="learn-generate-title">{t('learn.generateTitle')}</h3>
      <p>{t('learn.generateHint')}</p>
      <button class="primary" type="button" data-testid="generate-now" disabled={!canOpenReport} onclick={openReport}>{t('learn.generateNow')}</button>
    </section>
  {:else}
    <section>
      <h3>{t('dossier.siTitle')}</h3>
      <p>{t('dossier.siScope')}</p>
      <label class="cloud-consent"><input type="checkbox" data-testid="report-cloud-consent" disabled={!cloudAvailable || siBusy} bind:checked={allowExternal} />{t('si.reportOnline')}</label>
      <p>{t(cloudAvailable ? 'si.reportOnlineScope' : 'si.notConfigured')}</p>
      <button type="button" disabled={siBusy || busy || !!error} onclick={generate}>{t(siBusy ? 'dossier.siGenerating' : 'dossier.siGenerate')}</button>
      {#if planning.si}<button type="button" onclick={clearSi}>{t('dossier.siClear')}</button>{/if}
      {#if siError}<p role="alert">{siError}</p>{/if}
      {#if planning.si}<p role="status">{t('dossier.siSaved', { model: planning.si.result.model })}</p>{/if}
    </section>
  {/if}
  {#if planning.sections}<ReportOptionalSections bind:selection={planning.sections} />{/if}
  <!-- {SCENARIO_SLOT}: extension point for the scenario slider (illustrative mission-class scenarios), a later job. -->
  {#if scenarioSlot}<div data-slot={SCENARIO_SLOT}>{@render scenarioSlot()}</div>{/if}
</div>

<style>
  label { display: block; font-weight: 600; margin-block: 1rem .5rem; }
  .cloud-consent { display: flex; align-items: center; gap: .75rem; } .cloud-consent input { width: 1.2rem; min-height: 1.2rem; }
  input { box-sizing: border-box; width: 100%; min-height: 44px; padding: .7rem; color: inherit; background: #081426; border: 1px solid #7b9cb36e; border-radius: .65rem; }
  fieldset { margin-block: 2rem; border: 1px solid #7b9cb36e; border-radius: .65rem; padding: 1rem; }
  .check { display: flex; align-items: center; gap: .75rem; } .check input { width: 1.2rem; min-height: 1.2rem; }
  .generate { margin-block: 1.5rem; padding: 1rem; border: 1px solid #9bdfff80; border-radius: .65rem; }
  button { min-height: 44px; margin: .5rem .5rem .5rem 0; padding: .7rem; }
  p { line-height: 1.6; } [role='alert'] { border-inline-start: 3px solid #d6ba7c; padding-inline-start: 1rem; }
</style>
