<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { t, formatNumber, type MessageKey } from '../../i18n/i18n.svelte';
  import { raven, type EvaluateIn, type RavenEvaluation, type RavenSiteInfo } from '../../shell/ravenApi';
  import type { EphemerisRange } from './timeline';
  import { assess, recover, type Assessment, type RecoveryOption, type RecoveryResult } from './recovery';

  let { baseline, request, sites, range, onapply }: {
    baseline: RavenEvaluation;
    request: EvaluateIn;
    sites: readonly RavenSiteInfo[];
    range: EphemerisRange | null;
    onapply: (option: RecoveryOption) => void;
  } = $props();
  let delay = $state<number | undefined>(6);
  let busy = $state(false);
  let result = $state.raw<RecoveryResult | null>(null);
  let preview = $state.raw<RecoveryOption | null>(null);
  let error = $state<MessageKey | null>(null);
  let controller: AbortController | null = null;
  onDestroy(() => controller?.abort());

  const validDelay = $derived(typeof delay === 'number' && Number.isInteger(delay) && delay >= 1 && delay <= 720);
  const statusKey: Record<Assessment['status'], MessageKey> = {
    met: 'recovery.met', blocked: 'recovery.blocked', unknown: 'recovery.unknown',
  };
  const causeKey: Record<NonNullable<Assessment['firstProblem']>['cause'], MessageKey> = {
    sun: 'recovery.sunBlocked', earth: 'recovery.earthBlocked',
    both: 'recovery.bothBlocked', unknown: 'recovery.dataUnknown',
  };
  const stamp = (value: string | number) => new Date(typeof value === 'number' ? value * 1000 : value).toISOString().replace('T', ' ').replace('.000Z', ' UTC');
  const number = (value: number) => formatNumber(value, { maximumFractionDigits: 1 });
  const hours = (e: RavenEvaluation) => e.window.n_steps * e.window.step_min / 60;

  function reset() { result = null; preview = null; error = null; }
  async function search() {
    if (!validDelay || delay === undefined || busy) return;
    reset();
    const c = new AbortController();
    controller = c;
    busy = true;
    const outcome = await recover(raven, baseline, request, delay, sites, range, c.signal);
    if (c.signal.aborted) return;
    busy = false;
    if (outcome.ok) result = outcome.data;
    else error = outcome.kind === 'range' ? 'recovery.range' : outcome.detail === 'needs_download' ? 'journey.downloadDeclined' :
      outcome.detail === 'too_large' ? 'journey.terrainCap' :
      outcome.kind === 'network' ? 'planner.errorNetwork' : outcome.kind === 'invalid' ? 'planner.errorInvalid' :
      outcome.kind === 'unavailable' ? 'planner.errorUnavailable' : outcome.kind === 'response' ? 'planner.errorResponse' :
      outcome.kind === 'aborted' ? 'journey.cancelled' : 'planner.errorServer';
  }
  function cancel() {
    controller?.abort();
    busy = false;
    error = 'journey.cancelled';
  }
</script>

<section class="recovery" data-testid="mission-recovery">
  <h3>{t('recovery.title')}</h3>
  <p>{t('recovery.intro')}</p>
  <p class="note">{t('recovery.method', { minutes: request.step_min })}</p>
  <div class="controls">
    <label for="recovery-delay">{t('recovery.delay')}</label>
    <input id="recovery-delay" type="number" min="1" max="720" step="1" bind:value={delay} disabled={busy} oninput={reset} />
    <button type="button" disabled={busy || !validDelay} onclick={search}>{t('recovery.search')}</button>
    {#if busy}<button type="button" onclick={cancel}>{t('journey.cancel')}</button>{/if}
  </div>
  {#if !validDelay}<p role="alert">{t('recovery.invalidDelay')}</p>{/if}
  {#if busy}<p role="status">{t('recovery.busy')}</p>{/if}
  {#if error}<p role="alert" class="warning">{t(error)}</p>{/if}
  {#if result}
    <div class="comparison">
      {#each [{ label: 'recovery.original' as const, evaluation: baseline, assessment: assess(baseline) },
        { label: 'recovery.delayed' as const, evaluation: result.delayed, assessment: result.assessment }] as row}
        <article>
          <h4>{t(row.label)}</h4>
          <p>{row.evaluation.site.name} · {stamp(row.evaluation.window.start_utc)} · {number(hours(row.evaluation))} h</p>
          <p><strong>{t(statusKey[row.assessment.status])}</strong></p>
          {#if row.assessment.firstProblem}
            <p>{t('recovery.firstIssue', { time: stamp(row.assessment.firstProblem.time), cause: t(causeKey[row.assessment.firstProblem.cause]) })}</p>
          {/if}
          <p>{t('recovery.metrics', { useful: number(row.evaluation.metrics.useful_hours), unknown: number(row.evaluation.metrics.unknown_hours) })}</p>
        </article>
      {/each}
    </div>
    <p class="note">{t('recovery.scope', { hours: number(result.searchHours), checked: result.sitesChecked, total: result.sitesInScope })}</p>
    <div class="comparison">
      {#each [{ label: 'recovery.timeOption' as const, option: result.time }, { label: 'recovery.siteOption' as const, option: result.site }] as item}
        <article>
          <h4>{t(item.label)}</h4>
          {#if item.option}
            {@const option = item.option}
            <p>{option.evaluation.site.name} · {stamp(option.evaluation.window.start_utc)}</p>
            <p>{t('recovery.met')} · {number(hours(option.evaluation))} h</p>
            <p>{option.kind === 'time'
              ? t('recovery.timeTradeoff', { hours: number((Date.parse(option.request.start_utc) - Date.parse(result.delayed.window.start_utc)) / 3600000) })
              : t('recovery.siteTradeoff', { km: number(option.distanceKm) })}</p>
            <button type="button" aria-pressed={preview === option} onclick={() => preview = option}>{t('recovery.preview')}</button>
          {:else}
            <p>{t('recovery.notFound')}</p>
          {/if}
        </article>
      {/each}
    </div>
    {#if preview}
      <div class="preview" aria-live="polite">
        <h4>{t('recovery.previewTitle')}</h4>
        <p>{preview.evaluation.site.name} · {stamp(preview.evaluation.window.start_utc)} → {stamp(Date.parse(preview.evaluation.window.start_utc) / 1000 + hours(preview.evaluation) * 3600)}</p>
        <p>{t('recovery.metrics', { useful: number(preview.evaluation.metrics.useful_hours), unknown: number(preview.evaluation.metrics.unknown_hours) })}</p>
        <p class="note">{t('recovery.applyNote')}</p>
        <button type="button" onclick={() => onapply(preview!)}>{t('recovery.apply')}</button>
      </div>
    {/if}
  {/if}
</section>

<style>
  .recovery { margin-block: 1.5rem; border: 1px solid var(--c-hairline); padding: 1rem; border-radius: .6rem; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
  .controls input { width: 7rem; }
  .comparison { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: .8rem; margin-block: 1rem; }
  article, .preview { border: 1px solid var(--c-hairline); border-radius: .4rem; padding: .8rem; }
  article h4, .preview h4 { margin-top: 0; }
  .note { color: var(--c-muted); }
</style>
