<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The report document. Built around ONE purpose: compare two sites. Parts 1-4 are the Learn report (verdict, charts, how it was
     computed, limits); Expert adds appendices that exist only when there is something to say. English only, whatever the site language. -->
<script lang="ts">
  import { tEn as t, formatNumberEn as formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { enterReportEnglish } from '../../i18n/reportScope';
  import { rt, nf } from './reportText';
  import type { JourneyDraft } from './journey';
  import { missionLifecycleReport, REPORT_PHASES, type ReportField, type ReportIdentity } from './report';
  import ravenMark from '../../assets/media/raven-mark.webp?no-inline';
  import type { RavenEconomics, RavenEvaluation, RavenParameter, RavenValidation } from '../../shell/ravenApi';
  import type { BudgetEstimate, CarbonEstimate } from './reportPlanning';
  import type { SimulatedCertificate } from './reportPresentation';
  import { newReportSections } from './reportSections';
  import type { TocEntry } from './reportToc';
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
  import ReportLink from './ReportLink.svelte';
  import ReportMoonSites from './ReportMoonSites.svelte';
  import ReportOverlays from './ReportOverlays.svelte';
  import ReportSky from './ReportSky.svelte';
  import ReportSection from './ReportSection.svelte';
  import VisibilityFigures from './VisibilityFigures.svelte';
  import LunarDays from './LunarDays.svelte';
  import ReportFormulas from './ReportFormulas.svelte';
  import ReportLimits from './ReportLimits.svelte';
  import ReportParameters from './ReportParameters.svelte';
  import ReportToc from './ReportToc.svelte';
  import StatusChip from './StatusChip.svelte';

  let { draft, identity, evaluations, budget = null, carbon = null, reliability = null, certificate = null, certificateError = false,
    validation = null, registry = [], economics = null, expert, created, toc = [], onverdict, onoverlays }: {
    onverdict?: (done: boolean) => void; onoverlays?: (done: boolean) => void;
    draft: JourneyDraft; identity: ReportIdentity; evaluations: readonly RavenEvaluation[]; budget?: BudgetEstimate | null;
    carbon?: CarbonEstimate | null; certificate?: SimulatedCertificate | null; certificateError?: boolean; reliability?: ReliabilityResult | null;
    validation?: RavenValidation | null; registry?: readonly RavenParameter[]; economics?: RavenEconomics | null; expert: boolean; created: string; toc?: TocEntry[];
  } = $props();
  enterReportEnglish();

  const document = $derived(missionLifecycleReport(draft, rt('disclaimer'), identity, evaluations, budget, carbon, certificate, reliability));
  const selection = $derived(draft.planning?.sections ?? newReportSections());
  const accepted = $derived(evaluations.length ? acceptedEstimates(draft.planning?.estimates) : []);
  const phases = $derived(REPORT_PHASES.filter((p) => selection[`phase${p.id}`]));
  const fieldLabel = (id: ReportField) => t(`report.field.${id}` as MessageKey);
  const reliabilityOn = $derived(selection.reliability && !!draft.planning?.reliability?.enabled);
  const costsProvided = $derived(!!budget && (budget.known_cost_items > 0 || budget.funding_gap !== null));
  const carbonProvided = $derived(!!carbon && carbon.mission.known_phases > 0);
  // estimates the report shows (cost, development time, vehicle, launch CO2, statistics, mass and power); the others stay in the Dossier and the JSON
  const SHOWN = ['est.cost', 'est.devtime', 'est.vehicle', 'est.launch_co2', 'est.stats', 'est.mass.A', 'est.mass.B'];
  // scenario B often has the same configuration as A: the same masses are then shown once ("A = B")
  const rangeKey = (e: { range: unknown } | undefined) => JSON.stringify(e?.range ?? null);
  const massSame = $derived(rangeKey(accepted.find((e) => e.id === 'est.mass.A')) === rangeKey(accepted.find((e) => e.id === 'est.mass.B')) && accepted.some((e) => e.id === 'est.mass.B'));
  const shownEstimates = $derived(accepted.filter((e) => SHOWN.includes(e.id) && !(massSame && e.id === 'est.mass.B')));
  const showD = $derived(selection.economics || selection.sustainability || (selection.deliverables && shownEstimates.length > 0));
  const thermalLoad = $derived(draft.planning?.reliability?.enabled && draft.planning.reliability.apply_thermal_load ? draft.planning.reliability.thermal_load_w ?? null : null);
  const labels = ['A', 'B', 'C', 'D', 'E'];
  // appendix letters follow the sections that are really present
  const present = $derived([reliabilityOn, selection.provenance, phases.length > 0, showD, selection.seal || selection.paper]);
  const letter = (index: number) => labels[present.slice(0, index).filter(Boolean).length];
  const grams = (kg: number | null | undefined) => kg == null ? t('report.notAssessed') : formatNumber(kg * 1000, { maximumFractionDigits: 1 });
</script>

<div class="lifecycle-report" data-testid="mission-lifecycle-report" lang="en">
  <ReportSummary {evaluations} missionName={draft.name || t('planner.libraryUnnamed')} start={draft.input.start} days={draft.input.days} {created} {expert} decision={draft.decision} {budget} {carbon} estimates={draft.planning?.estimates} missionClass={draft.planning?.missionClass} />
  {#if expert}<ReportToc entries={toc} />{/if}

  <section class="rp-part" data-part="2"><h3>{rt('part2')}</h3><ReportMoonSites {evaluations} /><ReportOverlays {evaluations} onready={onoverlays} /><ReportCharts {evaluations} /><ReportSky {evaluations} /><ReportLink {evaluations} {expert} /><VisibilityFigures {evaluations} tr={rt} fmt={(v: number, d = 1) => nf(v, { minimumFractionDigits: d, maximumFractionDigits: d })} countdown /><LunarDays {evaluations} tr={rt} fmt={(v: number, d = 1) => nf(v, { minimumFractionDigits: d, maximumFractionDigits: d })} />{#if expert}<ReportSection {evaluations} radio={draft.radio} />{/if}</section>
  <section class="rp-part" data-part="sustainability"><h3>{rt('part.sust')}</h3><ReportSustainability {evaluations} {economics} {expert} /><ReportEstimates {expert} /></section>
  <section class="rp-part" data-part="3"><h3>{rt('part3')}</h3><p class="rp-how">{rt('part3.how')}</p>{#if !expert}<p class="rp-how">{rt('part3.learn')}</p>{/if}<ReportFormulas {evaluations} {validation} {registry} learn={!expert} /></section>
  <section class="rp-part" data-part="4"><h3>{rt('part4')}</h3><ReportLimits {evaluations} {validation} extraLoadW={thermalLoad} /></section>

  <section class="rp-part" data-part="verdict"><h3>{rt('part.verdict')}</h3><ReportVerdict {evaluations} priority={draft.objectives?.priority ?? null} onready={onverdict} /></section>

  {#if expert}
    {#if reliabilityOn}
      <section class="rp-appendix" data-appendix="reliability">
        <h3>{rt('appendix', { letter: letter(0) ?? 'A' })} — {rt('app.reliability')}</h3>
        {#if reliability}<div data-toc-skip><ReliabilityResults result={reliability} showInputs charts /></div>
          <ReportFormulas {evaluations} {validation} {registry} appendix />
        {:else}<p class="rp-note">{rt('app.reliabilityIncomplete')}</p>{/if}
      </section>
    {/if}
    {#if selection.provenance}
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
          {@const done = content.deliverables.filter((i) => i.status !== 'draft_proposal')}
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
    {#if selection.seal || selection.paper}
      <section class="rp-appendix appendix" data-appendix="stamp" data-testid="report-appendix">
        <h3>{rt('appendix', { letter: letter(4) ?? 'E' })} — {rt('app.stamp')}</h3>
        {#if selection.seal}
          <div class="seal" aria-label={t('report.sealLabel')} data-testid="mission-signature"><img src={ravenMark} alt="" width="88" height="44" /><strong>RAVEN</strong></div>
          <div data-testid="simulated-blockchain-certificate">
            {#if certificate}<p class="registry">SHA-256 {certificate.payload_sha256}</p><p class="registry">{t('certificate.transaction')}: {certificate.simulated_transaction_id}</p>
            {:else}<p role={certificateError ? 'alert' : 'status'}>{t(certificateError ? 'certificate.error' : 'certificate.pending')}</p>{/if}
          </div>
        {/if}
        {#if selection.paper && carbon?.document.compact_pages && carbon.document.reference_pages}
          <p data-testid="document-carbon">{t('carbon.pageEstimate', { compact: carbon.document.compact_pages, reference: carbon.document.reference_pages })}
            {t('carbon.digitalReminder', { grams: grams(carbon.document.not_printing_avoided_kg_co2e) })}</p>
        {/if}
      </section>
    {/if}
  {/if}
</div>
