<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Appendix B: the parameters the engine actually used, one table; rows where A and B differ are marked. English only. -->
<script lang="ts">
  import { rt } from './reportText';
  import type { RavenEvaluation, RavenParameter } from '../../shell/ravenApi';
  import { usedParameter } from './ravenAdapter';
  let { evaluations, registry = [] }: { evaluations: readonly RavenEvaluation[]; registry?: readonly RavenParameter[] } = $props();
  const GROUPS = ['rf', 'energy', 'scenario'] as const;
  const rows = $derived(GROUPS.flatMap((group) => {
    const sets = evaluations.map((e) => (e.parameters_used?.[group] ?? {}) as Record<string, unknown>);
    const keys = [...new Set(sets.flatMap((s) => Object.keys(s)))];
    return keys.map((key) => {
      const values = sets.map((s) => (key in s ? String(s[key]) : null));
      const row = usedParameter(registry, group, key);
      return { group, key, values, differs: new Set(values).size > 1, tag: row?.tag ?? null, source: row?.source ?? null, unit: row?.unit ?? '' };
    });
  }));
</script>

<table class="rp-params" data-testid="report-parameters">
  <thead><tr><th scope="col">{rt('params.parameter')}</th>{#each evaluations as _e, i}<th scope="col">{i === 0 ? 'A' : 'B'}</th>{/each}<th scope="col">{rt('params.source')}</th></tr></thead>
  <tbody>
    {#each rows as r (r.group + r.key)}
      <tr class:differs={r.differs}>
        <th scope="row">{r.group}.{r.key}{r.unit ? ` (${r.unit})` : ''}{r.differs ? ` ≠` : ''}</th>
        {#each r.values as v}<td>{v ?? '—'}</td>{/each}
        <td>{r.tag ? `${r.tag} · ${r.source}` : rt('params.untagged')}</td>
      </tr>
    {/each}
  </tbody>
</table>
