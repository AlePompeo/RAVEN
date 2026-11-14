<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { scopedI18n } from '../../i18n/reportScope';
  const { t } = scopedI18n();
  import { COST_ITEMS, CARBON_PHASES, type ReportPlanning, type BudgetEstimate, type CarbonEstimate } from './reportPlanning';
  import ComparisonBars from './ComparisonBars.svelte';
  let { planning, budget = null, carbon = null, economics = true, sustainability = true }: {
    planning: ReportPlanning; budget?: BudgetEstimate | null; carbon?: CarbonEstimate | null;
    economics?: boolean; sustainability?: boolean;
  } = $props();
</script>

{#if economics && budget && budget.known_cost_items > 0}
  <div data-testid="cost-statistics">
    <ComparisonBars label={t('stats.costTitle')} description={t('stats.costScope')} unit={budget.currency ?? ''}
      series={[t('stats.declared')]}
      rows={[
        ...COST_ITEMS.map((id) => ({ label: t(`report.field.${id}`), values: [planning.costs[id]] })),
        { label: t('stats.contingencyAmount'), values: [budget.contingency_amount] },
      ]} />
  </div>
{/if}
{#if sustainability && carbon && carbon.mission.known_phases > 0}
  <div data-testid="carbon-statistics">
    <ComparisonBars label={t('stats.carbonTitle')} description={t('stats.carbonScope')} unit="kg CO₂e"
      series={[t('stats.declared')]}
      rows={CARBON_PHASES.map((phase) => ({ label: t('carbon.phaseInput', { phase }), values: [carbon.mission.phase_emissions_kg_co2e[phase]] }))} />
  </div>
{/if}
