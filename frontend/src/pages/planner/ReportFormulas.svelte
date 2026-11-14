<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Part 3, "How it was computed". For every indicator of the cards and charts: (1) the formula with named variables, written as
     the engine computes it; (2) a legend of the variables (meaning, unit, origin, V/D/I tag for parameters), each explained once;
     (3) last and small, the values of THIS run for A and B. Names, formulas and legends come from reportFormulas.ts only. -->
<script lang="ts">
  import { rt } from './reportText';
  import type { RavenEvaluation, RavenParameter, RavenValidation } from '../../shell/ravenApi';
  import { FORMULAS, VARS, pieces, stageStatus, varMeaning, varName, variableValue, type FormulaDef, type VarId } from './reportFormulas';
  import { usedParameter } from './ravenAdapter';
  import StatusChip from './StatusChip.svelte';
  let { evaluations, validation = null, registry = [], appendix = false, learn = false }: {
    evaluations: readonly RavenEvaluation[]; validation?: RavenValidation | null; registry?: readonly RavenParameter[]; appendix?: boolean; learn?: boolean;
  } = $props();

  /** Learn: only the formulas with a compact version (the main ones), each with the lines and variables of that version. */
  const blocks = $derived(FORMULAS.filter((f) => (f.appendix === 'reliability') === appendix && (!learn || f.learn)).map((f) => (
    learn && f.learn ? { ...f, lines: f.learn.lines.map((i) => f.lines[i]!), vars: f.learn.vars } : f)));
  /** A variable is explained where it is first used. */
  const firstUse = $derived.by(() => {
    const seen = new Set<VarId>();
    return blocks.map((f) => f.vars.filter((v) => (seen.has(v) ? false : (seen.add(v), true))));
  });
  function origin(id: VarId): string {
    const def = VARS[id];
    if (def.origin === 'engine') return rt('origin.engine', { stage: def.stage.toUpperCase() });
    if (def.origin === 'formula') return rt('origin.formula');
    if (def.origin === 'constant') return rt('origin.constant');
    const f = def.field;
    const row = f && (f.src === 'rf' || f.src === 'energy' || f.src === 'scenario') ? usedParameter(registry, f.src, f.key) : null;
    return row ? rt('origin.param', { tag: row.tag }) : rt('origin.paramUntagged');
  }
</script>

{#each blocks as f, i (f.id)}
  <section class="rp-formula-block" class:rp-learn={learn} data-formula={f.id}>
    <h5>{rt(`f.${f.id}`)} <span class="rp-tag">{rt('tag.label')} {f.tag}</span> <StatusChip kind={stageStatus(validation, f.stages)} /></h5>
    <p class="rp-flines">{#each f.lines as line}<span class="rp-fline">{#each pieces(line) as p}{#if p.kind === 'var'}<var>{p.text}</var>{:else}{p.text}{/if}{/each}</span>{/each}</p>
    {#if firstUse[i]!.length}
      <table class="rp-vars" data-testid="formula-legend">
        <thead><tr><th scope="col">{rt('vars.name')}</th><th scope="col">{rt('vars.meaning')}</th><th scope="col">{rt('vars.unit')}</th><th scope="col">{rt('vars.origin')}</th>
          {#if !appendix}{#each evaluations as _e, k}<th scope="col" class="rp-run">{rt('values.title')} {k === 0 ? 'A' : 'B'}</th>{/each}{/if}</tr></thead>
        <tbody>
          {#each firstUse[i]! as v}<tr><th scope="row"><var>{varName(v)}</var></th><td>{varMeaning(v)}</td><td>{VARS[v].unit || '—'}</td><td>{origin(v)}</td>
            {#if !appendix}{#each evaluations as e}<td class="rp-run">{variableValue(v, e) ?? '—'}</td>{/each}{/if}</tr>{/each}
        </tbody>
      </table>
    {/if}
  </section>
{/each}
