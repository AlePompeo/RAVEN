<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Key figures of Sun and Earth per scenario (planner Results step and report): elevation, hours, longest continuous runs and, when
     asked, the countdown to sunset / Earthset at the start of the window. `tr` and `fmt` come from the caller (site catalog in the
     planner, English-only text in the report). -->
<script lang="ts">
  import type { RavenEvaluation } from '../../shell/ravenApi';
  import { countdownAt, siteStats, type Countdown } from './visibilityStats';
  let { evaluations, tr, fmt, countdown = false }: {
    evaluations: readonly RavenEvaluation[]; tr: (key: string, params?: Record<string, string | number>) => string;
    fmt: (v: number, digits?: number) => string; countdown?: boolean;
  } = $props();
  const names = $derived(evaluations.map((e, i) => `${i === 0 ? 'A' : 'B'}: ${e.site.name}`));
  const stats = $derived(evaluations.map(siteStats));
  const counts = $derived(evaluations.map((e) => (countdown ? countdownAt(e, 0) : null)));
  const val = (v: number | null, unit: string, d = 1) => (v === null ? tr('vis.unknown') : `${fmt(v, d)} ${unit}`);
  const rows = $derived([
    ['vis.sunMax', (s: NonNullable<typeof stats[number]>) => val(s.sunMaxElDeg, '°')],
    ['vis.sunMean', (s: NonNullable<typeof stats[number]>) => val(s.sunMeanElDeg, '°')],
    ['vis.litH', (s: NonNullable<typeof stats[number]>) => val(s.litH, 'h')],
    ['vis.longestLit', (s: NonNullable<typeof stats[number]>) => val(s.longestLitH, 'h')],
    ['vis.longestDark', (s: NonNullable<typeof stats[number]>) => val(s.longestDarkH, 'h')],
    ['vis.earthH', (s: NonNullable<typeof stats[number]>) => val(s.earthH, 'h')],
    ['vis.longestEarth', (s: NonNullable<typeof stats[number]>) => val(s.longestEarthH, 'h')],
    ['vis.longestNoEarth', (s: NonNullable<typeof stats[number]>) => val(s.longestNoEarthH, 'h')],
    ['phase.dsnVisible', (s: NonNullable<typeof stats[number]>) => val(s.dsnVisibleH, 'h')],
  ] as const);
  const when = (c: Countdown | undefined, body: 'sun' | 'earth') => {
    if (!c || c.visible === null) return tr('vis.unknown');
    if (c.hours === null) return tr('vis.noChange');
    return tr(`vis.${body}${c.visible ? 'Sets' : 'Rises'}`, { h: fmt(c.hours, 1) });
  };
</script>

{#if stats.some((s) => s)}
  <section class="vis" data-testid="visibility-figures">
    <h4 class="rp-means">{tr('vis.title')}</h4>
    <table class="rp-risktable">
      <thead><tr><th scope="col">{tr('vis.site')}</th>{#each names as n}<th scope="col">{n}</th>{/each}</tr></thead>
      <tbody>
        {#each rows as [key, f]}
          <tr><th scope="row">{tr(key)}</th>{#each stats as s}<td>{s ? f(s) : tr('vis.unknown')}</td>{/each}</tr>
        {/each}
        {#if stats.some((s) => s && s.unknownH > 0)}
          <tr><th scope="row">{tr('vis.unknownH')}</th>{#each stats as s}<td>{s ? fmt(s.unknownH, 1) + ' h' : tr('vis.unknown')}</td>{/each}</tr>
        {/if}
        {#if stats.some((s) => s && s.dsnUnknownH > 0)}
          <tr><th scope="row">{tr('phase.dsnUnknown')}</th>{#each stats as s}<td>{s ? fmt(s.dsnUnknownH, 1) + ' h' : tr('vis.unknown')}</td>{/each}</tr>
        {/if}
        {#if countdown}
          <tr><th scope="row">{tr('vis.start')}: {tr('vis.sun')}</th>{#each counts as c}<td>{when(c?.sun, 'sun')}</td>{/each}</tr>
          <tr><th scope="row">{tr('vis.start')}: {tr('vis.earth')}</th>{#each counts as c}<td>{when(c?.earth, 'earth')}</td>{/each}</tr>
        {/if}
      </tbody>
    </table>
    <p class="note">{tr('vis.note')}</p>
  </section>
{/if}

<style>
  .vis { margin-block: 1.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #7b9cb34d; vertical-align: top; }
  .note { color: var(--c-muted); font-size: .85rem; }
</style>
