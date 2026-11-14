<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import SubNav from '../components/ui/SubNav.svelte';
  import { lang, t } from '../i18n/i18n.svelte';
  import { BASE } from '../registry';
  import { withBase } from './router';
  import { scenarioStore, withScenario, type Scenario } from './scenario';

  const store = scenarioStore();
  let scenario = $state<Scenario>(store.reload());
  $effect(() => store.subscribe((s) => (scenario = s)));
  const copyLang = $derived(lang.current);
  const items = $derived([
    { path: '/simula?tab=scena', group: t('journey.terrainGroup'), name: t('journey.scene'), text: t('journey.sceneText') },
    { path: '/simula?tab=onda', group: t('journey.propagationGroup'), name: t('journey.wave'), text: t('journey.waveText') },
    { path: '/analizza', group: t('journey.analysisGroup'), name: t('journey.linkBudgetTool'), text: t('journey.analysisGroupText') },
    { path: '/siti', group: t('journey.siteGroup'), name: t('journey.sitesAnalysisTool'), text: t('journey.sitesText') },
  ]);
  function href(path: string) {
    return withBase(withScenario(path, scenario), BASE);
  }
</script>

<svelte:window onpopstate={() => store.reload()} />
<SubNav title="Explore" mode={false} />
<div class="workspace tile tile--alt">
  <div class="container container--wide">
    <p class="lead" lang={copyLang}>{t('journey.exploreIntro')}</p>
    <ul class="cards">
      {#each items as item (item.path)}
        <li class="panel card">
          {#if 'group' in item && item.group}<h2 lang={copyLang}>{item.group}</h2><h3><a href={href(item.path)} lang={item.path.startsWith('/simula?') ? copyLang : undefined}>{item.name}</a></h3>
          {:else}<h2><a href={href(item.path)} lang={item.path.startsWith('/simula?') || item.path.includes('#') ? copyLang : undefined}>{item.name}</a></h2>{/if}
          <p lang={copyLang}>{item.text}</p>
        </li>
      {/each}
    </ul>
  </div>
</div>

<style>
  .workspace { padding-block: var(--space-5) var(--space-7, 4rem); }
  .lead { max-inline-size: var(--measure); margin-block: 0 var(--space-4); }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
    gap: var(--space-4);
    list-style: none;
    margin: 0;
    padding: 0;
    counter-reset: chapter;
  }
  .card {
    position: relative;
    overflow: hidden;
    counter-increment: chapter;
    transition: border-color var(--dur-ui) var(--ease-out), transform var(--dur-ui) var(--ease-out);
  }
  .card::before {
    content: '0' counter(chapter);
    display: block;
    margin-bottom: var(--space-4);
    color: #b0d7ff;
    font: 500 0.75rem 'Orbitron', var(--font-sans);
    letter-spacing: 0.12em;
  }
  .card:hover, .card:focus-within {
    border-color: #82bfff;
    transform: translateY(-3px);
  }
  .card h2 { margin: 0 0 var(--space-2); font-size: var(--fs-h3); }
  .card h3 { margin: 0; font-size: 1rem; }
  .card p { margin: 0; color: var(--c-muted); }
  .card a { display: inline-block; padding-block: 0.4rem; }
</style>
