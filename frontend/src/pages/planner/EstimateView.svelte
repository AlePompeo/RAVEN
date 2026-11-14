<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- One RAVEN estimate: status chip (colour + icon + word), method and inputs expandable, rows as a table.
     With `controls` it offers accept/dismiss (real buttons, keyboard accessible); in the report it has none. -->
<script lang="ts">
  import type { MessageKey } from '../../i18n/i18n.svelte';
  import { scopedI18n } from '../../i18n/reportScope';
  const { t } = scopedI18n();
  import { utcMinute } from './reportFormat';
  import type { EngineEstimate, EstimateStatus } from './estimates';
  import { cellText, columnsOf, estimateTitle, rangeText } from './estimates/render';
  let { estimate, controls = false, onstatus, compact = false }: {
    estimate: EngineEstimate; controls?: boolean; compact?: boolean; onstatus?: (id: string, status: EstimateStatus) => void;
  } = $props();
  const columns = $derived(columnsOf(estimate));
  const range = $derived(rangeText(estimate, t));
  /** Assumptions for the report: the declared inputs, never the internal field paths of the engine result. */
  const assumptions = $derived(estimate.inputs_used.filter((i) => !i.name.startsWith('evaluations[')).map((i) => `${i.name} = ${i.value === null ? t('report.notAssessed') : String(i.value)}${i.tag ? ` (${t('est.tag', { tag: i.tag })})` : ''}`));
</script>

<section class="estimate" data-testid={`estimate-${estimate.id}`} data-status={estimate.status} data-field={estimate.field}>
  <header>
    <h5>{estimateTitle(estimate, t)}</h5>
    {#if compact}<span class="est-chip est-tag" data-testid="estimate-status">{t('est.chipEstimate')}</span>{:else}
    <span class={`est-chip est-${estimate.status}`} data-testid="estimate-status"><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      {#if estimate.status === 'accepted'}<circle cx="6" cy="6" r="5" /><path d="M3.2 6.2 5.2 8.2 8.9 4.1" />
      {:else if estimate.status === 'dismissed'}<circle cx="6" cy="6" r="5" /><path d="M3.9 3.9 8.1 8.1M8.1 3.9 3.9 8.1" />
      {:else}<circle cx="6" cy="6" r="5" stroke-dasharray="2 2" /><path d="M4.5 4.7A1.6 1.6 0 1 1 6.6 6.2C6.1 6.5 6 6.8 6 7.3M6 9V9.1" />{/if}
    </svg>{t(`est.status.${estimate.status}` as MessageKey)}</span>{/if}
    <span class="est-chip est-tag">{t('est.tag', { tag: estimate.tag })}</span>
  </header>
  {#if range}<p class="est-range"><strong>{t('est.range')}:</strong> {range}</p>{/if}
  <div class="table-wrap"><table>
    <caption class="sr-only">{estimateTitle(estimate, t)}</caption>
    <thead><tr><th scope="col">ID</th>{#each columns as c}<th scope="col">{t(`est.col.${c}` as MessageKey)}</th>{/each}</tr></thead>
    <tbody>{#each estimate.items as item}<tr><th scope="row">{item.id}</th>{#each columns as c}<td>{cellText(item.cells[c], t)}</td>{/each}</tr>{/each}</tbody>
  </table></div>
  {#if compact}
    <p class="est-meta"><strong>{t('est.methodId')}</strong> {estimate.method_id}. <strong>{t('est.source')}</strong> {estimate.source}. <strong>{t('est.assumptions')}</strong> {assumptions.join('; ')}. <strong>{t('est.limits')}</strong> {estimate.validity_limits.map((l) => t(l as MessageKey)).join(' ')}</p>
  {:else}
  <details>
    <summary>{t('est.method')}</summary>
    <dl>
      <div><dt>{t('est.methodId')}</dt><dd>{estimate.method_id}</dd></div>
      <div><dt>{t('est.source')}</dt><dd>{estimate.source}</dd></div>
      <div><dt>{t('est.producedAt')}</dt><dd>{utcMinute(estimate.produced_at)}</dd></div>
      <div><dt>{t('est.inputs')}</dt><dd><ul>{#each estimate.inputs_used as input}<li><code>{input.name}</code> = {input.value === null ? t('report.notAssessed') : String(input.value)}{input.tag ? ` (${t('est.tag', { tag: input.tag })})` : ''}</li>{/each}</ul></dd></div>
      <div><dt>{t('est.limits')}</dt><dd><ul>{#each estimate.validity_limits as limit}<li>{t(limit as MessageKey)}</li>{/each}</ul></dd></div>
    </dl>
  </details>
  {/if}
  {#if controls && onstatus}
    <div class="est-actions">
      {#if estimate.status !== 'accepted'}<button type="button" class="primary" data-testid="estimate-accept" onclick={() => onstatus(estimate.id, 'accepted')}>{t('est.accept')}</button>{/if}
      {#if estimate.status !== 'dismissed'}<button type="button" data-testid="estimate-dismiss" onclick={() => onstatus(estimate.id, 'dismissed')}>{t('est.dismiss')}</button>{/if}
      {#if estimate.status !== 'proposed'}<button type="button" onclick={() => onstatus(estimate.id, 'proposed')}>{t('est.reopen')}</button>{/if}
    </div>
  {/if}
</section>

<style>
  .estimate { border: 1px solid var(--border, #8a8f98); border-left-width: 4px; border-radius: 6px; padding: .6rem .8rem; margin: .8rem 0; background: var(--surface, transparent); }
  header { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
  h5 { margin: 0; font-size: 1rem; flex: 1 1 14rem; }
  .est-chip { display: inline-flex; gap: .3rem; align-items: center; padding: .05rem .5rem; border: 1px solid currentColor; border-radius: 999px; font-size: .8rem; font-weight: 700; white-space: nowrap; }
  .est-proposed { color: #7a4b00; background: #fff3d6; border-style: dashed; }
  .est-accepted { color: #0b5d2a; background: #dff3e5; }
  .est-dismissed { color: #5a5f69; background: #eceef1; }
  .est-tag { color: #1f4e8c; background: #e3edfa; }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: .85rem; }
  th, td { border: 1px solid #9aa0a8; padding: .25rem .4rem; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .est-meta { font-size: .8rem; line-height: 1.35; margin: .4rem 0 0; overflow-wrap: anywhere; }
  .est-actions { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .5rem; }
  dl div { margin: .2rem 0; } dt { font-weight: 700; } dd { margin: 0; }
</style>
