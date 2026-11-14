<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { tEn as t, type MessageKey } from '../../i18n/i18n.svelte';
  import type { ReportField } from './report';
  import type { missionLifecycleReport } from './report';
  import { rt } from './reportText';
  import StatusChip from './StatusChip.svelte';

  type PhaseView = ReturnType<typeof missionLifecycleReport>['phases'][number];
  let { phase, fields, includeProposal = false }: {
    phase: PhaseView; fields: readonly ReportField[]; includeProposal?: boolean;
  } = $props();

  const rows = $derived(phase.deliverables.filter((item) => fields.includes(item.id) && item.status !== 'draft_proposal'));
  const chipKind = (status: string): 'provided' | 'estimated' | 'plausible' | 'known' | 'unknown' => status === 'user_input' ? 'provided'
    : status === 'engine_estimate' ? 'estimated'
      : status === 'engine_result' ? 'plausible' : status === 'core_arithmetic' ? 'known' : 'unknown';
</script>

{#if rows.length}
  <table class="rp-phase-fields" data-testid={`report-phase-${phase.id}`}>
    <thead><tr><th scope="col">{rt('phase.deliverable')}</th><th scope="col">{rt('phase.status')}</th><th scope="col">{rt('phase.detail')}</th></tr></thead>
    <tbody>{#each rows as item (item.id)}
      <tr><th scope="row">{t(`report.field.${item.id}` as MessageKey)}</th><td><StatusChip kind={chipKind(item.status)} /></td><td class="narrative">{item.value}</td></tr>
    {/each}</tbody>
  </table>
{/if}
{#if includeProposal && phase.si_proposal}
  <aside class="si-proposal" data-testid={`phase-${phase.id}-si-proposal`}>
    <strong>{rt('app.siTitle')}</strong>
    <span class="registry">{phase.id === 'D' ? rt('phase.aiRisk') : ''}</span>
    <p>{phase.si_proposal}</p>
  </aside>
{/if}
