<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- "What could go wrong": at most five risks merged across A and B, ordered by severity, built from the engine results of this run
     (estimates/risks.ts). Learn: three bullets. Expert: one compact table. No probabilities, no field paths, no per-stage rows. -->
<script lang="ts">
  import { rt } from './reportText';
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { topRisks } from './estimates/risks';
  let { evaluations, expert = false }: { evaluations: readonly RavenEvaluation[]; expert?: boolean } = $props();
  const risks = $derived(topRisks(evaluations));
</script>

<div class="rp-risks" data-testid="report-risks">
  <h4 class="rp-means">{rt('risk.title')}</h4>
  {#if risks.length === 0}
    <p>{rt('risk.none')}</p>
  {:else if expert}
    <table class="rp-risktable">
      <thead><tr><th scope="col">{rt('risk.col.severity')}</th><th scope="col">{rt('risk.col.risk')}</th><th scope="col">{rt('risk.col.cons')}</th><th scope="col">{rt('risk.col.act')}</th></tr></thead>
      <tbody>{#each risks as r}<tr data-severity={r.severity}><th scope="row">{rt(`risk.sev.${r.severity}`)}</th><td>{r.what}</td><td>{r.consequence}</td><td>{r.action}</td></tr>{/each}</tbody>
    </table>
  {:else}
    <ul class="rp-bullets">{#each risks.slice(0, 3) as r}<li>{r.what} {r.consequence}<br /><strong>{rt('risk.next')}</strong> {r.action}</li>{/each}</ul>
  {/if}
</div>
