<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Executive trade-off decision: which of the two sites is the better choice. The ENGINE decides (lexicographic by the mission priority, a tolerance
     below which two values are a tie, an unknown value never decides, no single score); a model, if one is available, only writes the explanation and
     its text is kept only if it names the same winner and uses no number that was not supplied. Table layout (the PDF engine has no CSS grid). -->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { nf, rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';

  let { evaluations, priority = null, onready }: { evaluations: readonly RavenEvaluation[]; priority?: 'sun' | 'earth' | 'radio' | 'balanced' | null; onready?: (done: boolean) => void } = $props();

  interface Row { component: string; label: string; unit: string; a: number | null; b: number | null; better: 'A' | 'B' | 'tie' | 'unknown' }
  interface Answer { verdict: { winner: 'A' | 'B' | 'tie' | 'undetermined'; decided_by: string | null; priority: string; rows: Row[]; rule: string }; names: string[]; text: string; text_source: 'template' | 'model'; model: string | null; model_note: string | null }
  let answer = $state.raw<Answer | null>(null);
  let failed = $state(false);
  let loading = $state(false); // the request is in flight (a local model needs up to a minute): the PDF must wait for the written comparison
  let useModel = $state(true), external = $state(false);

  const margin = (e: RavenEvaluation): number | null => {
    const series = Object.values(e.rf_series ?? {})[0];
    const v = (series ?? []).filter((x): x is number => x !== null && Number.isFinite(x));
    return v.length ? Math.min(...v) : null;
  };
  const site = (e: RavenEvaluation) => ({
    name: e.site.name.slice(0, 60), useful_hours: e.metrics.useful_hours, unknown_hours: e.metrics.unknown_hours,
    margin_min_db: margin(e), min_soc: e.metrics.min_soc, sun_hours: e.metrics.sun_hours,
  });
  const body = $derived(evaluations.length === 2 ? { sites: evaluations.map(site), priority, use_model: useModel, allow_external: useModel && external } : null);

  $effect(() => {
    const b = body;
    if (!b) { answer = null; loading = false; return; }
    const ctl = new AbortController();
    failed = false; loading = true;
    void fetch('/api/raven/report/verdict', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b), signal: ctl.signal })
      .then(async (r) => { if (!r.ok) throw new Error(String(r.status)); return (await r.json()) as Answer; })
      .then((a) => { answer = a; loading = false; })
      .catch(() => { if (!ctl.signal.aborted) { failed = true; loading = false; } });
    return () => ctl.abort();
  });
  $effect(() => { onready?.(!loading); });
  onDestroy(() => { onready?.(true); }); // a part that goes away (section switched off, new run) must not leave the PDF waiting for it
  const val = (v: number | null, unit: string) => (v === null ? rt('unknown') : `${nf(v, { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : unit ? 1 : 2 })}${unit ? ` ${unit}` : ''}`);
  const winnerName = $derived(answer && (answer.verdict.winner === 'A' || answer.verdict.winner === 'B') ? answer.names[answer.verdict.winner === 'A' ? 0 : 1] : null);
</script>

{#if evaluations.length === 2}
  <div class="rp-verdict" data-testid="report-site-verdict">
    <p class="rp-how">{rt('ver.intro')}</p>
    {#if failed}<p role="status" class="rp-how">{rt('ver.failed')}</p>
    {:else if !answer}<p role="status" class="rp-how">{rt('ver.pending')}</p>
    {:else}
      <p class="rp-verdict-head" data-winner={answer.verdict.winner}><strong>{winnerName ? rt('ver.winner', { name: winnerName, w: answer.verdict.winner }) : rt(answer.verdict.winner === 'tie' ? 'ver.tie' : 'ver.undetermined')}</strong></p>
      <p class="rp-how" data-testid="verdict-text">{answer.text}</p>
      <p class="rp-how">{rt(answer.text_source === 'model' ? 'ver.byModel' : 'ver.byTemplate', { model: answer.model ?? '' })}</p>
      <table class="rp-verdict-table">
        <thead><tr><th scope="col">{rt('ver.col.component')}</th><th scope="col">A: {answer.names[0]}</th><th scope="col">B: {answer.names[1]}</th><th scope="col">{rt('ver.col.better')}</th></tr></thead>
        <tbody>
          {#each answer.verdict.rows as r}
            <tr class:decided={r.component === answer.verdict.decided_by}>
              <th scope="row">{r.label}</th><td>{val(r.a, r.unit)}</td><td>{val(r.b, r.unit)}</td>
              <td>{r.better === 'unknown' ? rt('unknown') : r.better === 'tie' ? rt('ver.tieCell') : r.better}{r.component === answer.verdict.decided_by ? ` (${rt('ver.decisive')})` : ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="rp-how">{rt('ver.rule', { priority: answer.verdict.priority })} {answer.verdict.rule}</p>
    {/if}
    <div class="rp-verdict-opts" data-html2pdf-ignore>
      <label><input type="checkbox" bind:checked={useModel} /> {rt('ver.useModel')}</label>
      {#if useModel}<label><input type="checkbox" bind:checked={external} /> {rt('ver.external')}</label>{/if}
    </div>
  </div>
{/if}

<style>
  .rp-verdict-table { width: 100%; border-collapse: collapse; margin-block: .5rem; }
  .rp-verdict-table th, .rp-verdict-table td { text-align: left; padding: .25rem .5rem; border-bottom: 1px solid #9bdfff33; font-variant-numeric: tabular-nums; }
  .decided { font-weight: 600; }
  .rp-verdict-opts { display: grid; gap: .25rem; margin-top: .5rem; font-size: .85rem; }
  @media print { .rp-verdict-opts { display: none; } }
</style>
