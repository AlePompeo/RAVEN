<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The report document follows the requested ECSS-style waterfall order. User declarations, engine results, estimates and unknowns stay
     distinct; the phase-gate structure is an outline, not an ECSS compliance claim. English only, whatever the site language. -->
<script lang="ts">
  import { tEn as t, formatNumberEn as formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { enterReportEnglish } from '../../i18n/reportScope';
  import { rt, nf } from './reportText';
  import type { JourneyDraft, MissionShiftBaseline, MissionShiftDays } from './journey';
  import { missionLifecycleReport, REPORT_PHASES, type ReportField, type ReportIdentity } from './report';
  import type { RavenEconomics, RavenEvaluation, RavenParameter, RavenValidation } from '../../shell/ravenApi';
  import type { BudgetEstimate, CarbonEstimate } from './reportPlanning';
  import { newReportSections } from './reportSections';
  import type { ReliabilityResult } from './reliability';
  import ReliabilityResults from './ReliabilityResults.svelte';
  import PlanningStatistics from './PlanningStatistics.svelte';
  import EstimateView from './EstimateView.svelte';
  import { acceptedEstimates } from './estimates';
  import ReportSummary from './ReportSummary.svelte';
  import ReportCharts from './ReportCharts.svelte';
  import ReportSustainability from './ReportSustainability.svelte';
  import ReportEstimates from './ReportEstimates.svelte';
  import ReportVerdict from './ReportVerdict.svelte';
  import ReportRisks from './ReportRisks.svelte';
  import ReportTotals from './ReportTotals.svelte';
  import ReportLink from './ReportLink.svelte';
  import ReportMoonSites from './ReportMoonSites.svelte';
  import ReportOverlays from './ReportOverlays.svelte';
  import ReportSky from './ReportSky.svelte';
  import ReportSection from './ReportSection.svelte';
  import ReportPhaseFields from './ReportPhaseFields.svelte';
  import VisibilityFigures from './VisibilityFigures.svelte';
  import LunarDays from './LunarDays.svelte';
  import ReportFormulas from './ReportFormulas.svelte';
  import ReportLimits from './ReportLimits.svelte';
  import ReportParameters from './ReportParameters.svelte';
  import ReportFinalSections from './ReportFinalSections.svelte';
  import type { SimulatedCertificate } from './reportPresentation';
  import StatusChip from './StatusChip.svelte';
  import MissionShiftSummary from './MissionShiftSummary.svelte';

  let { draft, identity, evaluations, budget = null, carbon = null, reliability = null, certificate = null, certificateError = false,
    validation = null, registry = [], economics = null, missionShiftBaseline = [], missionShiftDays = 0, expert, created, onverdict, onoverlays }: {
    onverdict?: (done: boolean) => void; onoverlays?: (done: boolean) => void;
    draft: JourneyDraft; identity: ReportIdentity; evaluations: readonly RavenEvaluation[]; budget?: BudgetEstimate | null;
    missionShiftBaseline?: readonly MissionShiftBaseline[]; missionShiftDays?: MissionShiftDays;
    carbon?: CarbonEstimate | null; reliability?: ReliabilityResult | null; certificate?: SimulatedCertificate | null; certificateError?: boolean;
    validation?: RavenValidation | null; registry?: readonly RavenParameter[]; economics?: RavenEconomics | null; expert: boolean; created: string;
  } = $props();
  enterReportEnglish();

  const document = $derived(missionLifecycleReport(draft, rt('disclaimer'), identity, evaluations, budget, carbon, certificate, reliability, missionShiftBaseline));
  const selection = $derived(draft.planning?.sections ?? newReportSections());
  const accepted = $derived(evaluations.length ? acceptedEstimates(draft.planning?.estimates) : []);
  const phases = $derived(REPORT_PHASES.filter((p) => selection[`phase${p.id}`]));
  const fieldLabel = (id: ReportField) => t(`report.field.${id}` as MessageKey);
  const reliabilityEnabled = $derived(!!draft.planning?.reliability?.enabled);
  const reliabilityOn = $derived(selection.reliability && reliabilityEnabled);
  const costsProvided = $derived(!!budget && (budget.known_cost_items > 0 || budget.funding_gap !== null));
  const carbonProvided = $derived(!!carbon && carbon.mission.known_phases > 0);
  // estimates the report shows (cost, development time, vehicle, launch CO2, statistics, mass and power); the others stay in the Dossier and the JSON
  const SHOWN = ['est.cost', 'est.devtime', 'est.vehicle', 'est.launch_co2', 'est.stats', 'est.mass.A', 'est.mass.B'];
  // scenario B often has the same configuration as A: the same masses are then shown once ("A = B")
  const rangeKey = (e: { range: unknown } | undefined) => JSON.stringify(e?.range ?? null);
  const massSame = $derived(rangeKey(accepted.find((e) => e.id === 'est.mass.A')) === rangeKey(accepted.find((e) => e.id === 'est.mass.B')) && accepted.some((e) => e.id === 'est.mass.B'));
  const shownEstimates = $derived(accepted.filter((e) => SHOWN.includes(e.id) && !(massSame && e.id === 'est.mass.B')));
  const estimatesFor = (ids: readonly string[]) => shownEstimates.filter((e) => ids.includes(e.id));
  const showD = $derived(selection.economics || selection.sustainability || (selection.deliverables && shownEstimates.length > 0));
  const thermalLoad = $derived(draft.planning?.reliability?.enabled && draft.planning.reliability.apply_thermal_load ? draft.planning.reliability.thermal_load_w ?? null : null);
  const labels = ['A', 'B', 'C', 'D', 'E'];
  const phase = (id: string) => document.phases.find((p) => p.id === id)!;
  const letter = (index: number) => labels[index]!;
</script>

<div class="lifecycle-report" data-testid="mission-lifecycle-report" lang="en">
  <section class="rp-part rp-executive" data-part="executive" data-testid="report-executive-summary">
    <ReportSummary {evaluations} missionName={draft.name || t('planner.libraryUnnamed')} start={draft.input.start} days={draft.input.days} {created} {expert} decision={draft.decision}
      {budget} {carbon} estimates={draft.planning?.estimates} missionClass={draft.planning?.missionClass} showRisks={false} showTotals={false} />
    <h4>{rt('part.verdict')}</h4>
    <ReportVerdict {evaluations} priority={draft.objectives?.priority ?? null} onready={onverdict} />
    <ReportMoonSites {evaluations} />
  </section>

  <section class="rp-part rp-ecss-phase rp-ecss-phase--0" data-part="0" data-testid="report-phase-0">
    <h3>{rt('phase.title.0')}</h3>
    <h4>{rt('phase.goal')}</h4>
    <ReportPhaseFields phase={phase('0')} fields={['scientific_objectives', 'technology_objectives', 'other_objectives', 'success_criteria', 'stakeholders']} />
    <ReportOverlays {evaluations} onready={onoverlays} />
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--A" data-part="A" data-testid="report-phase-A">
    <h3>{rt('phase.title.A')}</h3>
    <ReportPhaseFields phase={phase('A')} fields={['high_level_requirements', 'technical_feasibility', 'economic_feasibility', 'schedule']} />
    <ReportCharts {evaluations} ids={['cum', 'sun', 'earth']} />
    <ReportRisks {evaluations} expert />
    <ReportSustainability {evaluations} {economics} {expert} showCarbon={false} showEnergy={false} showLaunch={false} />
    <ReportTotals {budget} {carbon} estimates={draft.planning?.estimates} missionClass={draft.planning?.missionClass} {expert} show={['cost']} />
    {#each estimatesFor(['est.cost', 'est.devtime']) as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--B" data-part="B" data-testid="report-phase-B">
    <h3>{rt('phase.title.B')}</h3>
    <ReportPhaseFields phase={phase('B')} fields={['system_architecture', 'space_and_ground_segments', 'interfaces', 'mass_and_power_budgets', 'verification_plan']} />
    <ReportCharts {evaluations} ids={['battery']} />
    <h4>{rt('phase.massBudget')}</h4>
    {#each estimatesFor(['est.mass.A', 'est.mass.B']) as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
    {#if !estimatesFor(['est.mass.A', 'est.mass.B']).length}<p class="rp-note">{rt('phase.massUnknown')}</p>{/if}
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--C" data-part="C" data-testid="report-phase-C">
    <h3>{rt('phase.title.C')}</h3>
    <ReportPhaseFields phase={phase('C')} fields={['detailed_design', 'hardware_selection', 'design_verification', 'ait_plan']} />
    <ReportSky {evaluations} />
    <ReportEstimates {expert} showLanding={false} />
    <ReportCharts {evaluations} ids={['rf']} />
    <ReportLink {evaluations} expert />
    <ReportSection {evaluations} radio={draft.radio} />
    {#if selection.methodology}
      <h4>{rt('part3')}</h4><p class="rp-how">{rt('part3.how')}</p>
      <ReportFormulas {evaluations} {validation} {registry} />
    {/if}
    <h4>{rt('part4')}</h4><ReportLimits {evaluations} {validation} extraLoadW={thermalLoad} />
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--D" data-part="D" data-testid="report-phase-D">
    <h3>{rt('phase.title.D')}</h3>
    <ReportPhaseFields phase={phase('D')} fields={['development_and_production', 'integration', 'qualification_tests', 'acceptance_tests', 'nonconformances']} includeProposal />
    {#if reliabilityOn && reliability}
      <ReliabilityResults result={reliability} showInputs charts report />
      <ReportFormulas {evaluations} {validation} {registry} appendix />
    {/if}
    <ReportEstimates {expert} showFresnel={false} showIntro={false} showTitle={false} />
    {#each estimatesFor(['est.stats']) as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--E" data-part="E" data-testid="report-phase-E">
    <h3>{rt('phase.title.E')}</h3>
    <MissionShiftSummary {evaluations} baseline={missionShiftBaseline} shiftDays={missionShiftDays}
      tr={(key, params) => rt(`shift.${key}`, params)} fmt={(v, d = 1) => nf(v, { minimumFractionDigits: d, maximumFractionDigits: d })} />
    <ReportSustainability {evaluations} {economics} {expert} showCosts={false} showCarbon={false} showEnergy={false} showIntro={false} />
    {#each estimatesFor(['est.vehicle']) as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
    <VisibilityFigures {evaluations} tr={rt} fmt={(v: number, d = 1) => nf(v, { minimumFractionDigits: d, maximumFractionDigits: d })} countdown />
    <p class="rp-how">{rt('phase.dsnScope')}</p>
    <LunarDays {evaluations} tr={rt} fmt={(v: number, d = 1) => nf(v, { minimumFractionDigits: d, maximumFractionDigits: d })} />
    <p class="rp-how">{rt('phase.lunarDaysScope')}</p>
  </section>
  <section class="rp-part rp-ecss-phase rp-ecss-phase--F" data-part="F" data-testid="report-phase-F">
    <h3>{rt('phase.title.F')}</h3>
    <ReportSustainability {evaluations} {economics} {expert} showCosts={false} showIntro={false} />
    <ReportTotals {budget} {carbon} estimates={draft.planning?.estimates} missionClass={draft.planning?.missionClass} expert={false} show={['co2']} />
    {#each estimatesFor(['est.launch_co2']) as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
  </section>

  {#if expert}
    {#if selection.configuration && selection.provenance}
      <section class="rp-appendix" data-appendix="parameters">
        <h3>{rt('appendix', { letter: letter(1) ?? 'B' })} — {rt('app.parameters')}</h3>
        <ReportParameters {evaluations} {registry} />
      </section>
    {/if}
    {#if phases.length}
      <section class="rp-appendix" data-appendix="dossier" data-testid="report-dossier-appendix">
        <h3>{rt('appendix', { letter: letter(2) ?? 'C' })} — {rt('app.dossier')}</h3>
        {#each phases as phase}
          {@const content = document.phases.find((p) => p.id === phase.id)!}
          {@const done = content.deliverables.filter((i) => i.status !== 'draft_proposal' && i.id !== 'drawings_and_software_baselines')}
          <section class="phase" data-phase={phase.id}>
            <h4>{t(phase.title as MessageKey)}</h4>
            {#if done.length}
              <table class="rp-dossier">
                <tbody>
                  {#each done as item}
                    <tr><th scope="row">{fieldLabel(item.id)}</th>
                      <td><StatusChip kind={item.status === 'user_input' ? 'provided' : item.status === 'engine_estimate' ? 'estimated' : 'known'} /></td>
                      <td class="narrative">{item.value}</td></tr>
                  {/each}
                </tbody>
              </table>
            {/if}
            {#if selection.assistance && content.si_proposal}
              <aside class="si-proposal" data-testid="mission-assistance"><strong>{rt('app.siTitle')}</strong>
                <span class="registry">{document.assistance.mission_specific_si_model}; {t(document.assistance.mission_specific_si_prompt_or_record?.local === false ? 'si.cloudSource' : 'si.localSource')}</span>
                <p>{content.si_proposal}</p></aside>
            {/if}
          </section>
        {/each}
      </section>
    {/if}
    {#if showD}
      <section class="rp-appendix" data-appendix="costs-esg">
        <h3>{rt('appendix', { letter: letter(3) ?? 'D' })} — {rt('app.costs')}</h3>
        <p class="rp-how">{rt('app.costsScope')}</p>
        {#if selection.economics && costsProvided && budget}
          <p data-testid="report-budget-summary">{t('dossier.costSummary', {
            count: budget.known_cost_items,
            subtotal: budget.known_subtotal === null ? t('report.notAssessed') : `${formatNumber(budget.known_subtotal)} ${budget.currency ?? ''}`,
            total: budget.total_lifecycle_cost === null ? t('report.notAssessed') : `${formatNumber(budget.total_lifecycle_cost)} ${budget.currency ?? ''}`,
            gap: budget.funding_gap === null ? t('report.notAssessed') : `${formatNumber(budget.funding_gap)} ${budget.currency ?? ''}`,
          })}</p>
          {#if draft.planning}<PlanningStatistics planning={draft.planning} {budget} sustainability={false} />{/if}
        {/if}
        {#if selection.sustainability && carbonProvided && carbon}
          <p data-testid="mission-carbon">{t('carbon.missionSummary', {
            count: carbon.mission.known_phases, subtotal: carbon.mission.known_subtotal_kg_co2e ?? t('report.notAssessed'),
            total: carbon.mission.total_kg_co2e ?? t('report.notAssessed'),
          })}</p>
          {#if carbon.mission.boundary}<p>{t('carbon.boundary')}: {carbon.mission.boundary}</p>{/if}
          {#if carbon.mission.basis}<p>{t('carbon.basis')}: {carbon.mission.basis}</p>{/if}
          {#if draft.planning}<PlanningStatistics planning={draft.planning} {carbon} economics={false} />{/if}
        {/if}
        {#if selection.deliverables}
          {#each shownEstimates as estimate (estimate.id)}<EstimateView {estimate} compact />{/each}
          {#if massSame}<p class="rp-how">{rt('app.massSame')}</p>{/if}
        {/if}
      </section>
    {/if}
  {/if}
  <ReportFinalSections {carbon} {certificate} {certificateError} />
</div>
