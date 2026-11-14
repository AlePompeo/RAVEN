<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';
  import { withScenario, type Scenario } from '../../shell/scenario';
  import Button from '../../components/ui/Button.svelte';

  const BASE = import.meta.env.BASE_URL;
  const customSite = {
    id: 'c-demo-ridge',
    name: 'Demo Ridge',
    lat_deg: -88.2,
    lon_deg_east: 42.6,
    panel_height_m: 2,
    antenna_height_m: 2,
  };
  const base: Omit<Scenario, 'site'> = {
    t: '2027-04-07T00:00:00Z',
    station: 'dsn34',
    gain: null,
    bitrate: 100000,
    k: null,
    mast: null,
    customSites: [customSite],
  };
  const scenario = (site: string): Scenario => ({ ...base, site });
  const href = (path: string, site: string) => withBase(withScenario(path, scenario(site)), BASE);
</script>

<div class="workspace tile tile--alt">
  <div class="container container--wide demo">
    <header class="intro">
      <p class="eyebrow">{t('demo.eyebrow')}</p>
      <h1>{t('demo.title')}</h1>
      <p class="lead">{t('demo.intro')}</p>
    </header>

    <ol class="steps">
      <li class="panel">
        <span class="step-number">01</span>
        <h2>{t('demo.malapertTitle')}</h2>
        <p>{t('demo.malapertText')}</p>
        <Button href={href('/mission-planner', 'malapert-massif')} size="lg">{t('demo.openPlanner')}</Button>
      </li>
      <li class="panel">
        <span class="step-number">02</span>
        <h2>{t('demo.haworthTitle')}</h2>
        <p>{t('demo.haworthText')}</p>
        <Button href={href('/mission-planner', 'haworth')} size="lg">{t('demo.openPlanner')}</Button>
      </li>
      <li class="panel">
        <span class="step-number">03</span>
        <h2>{t('demo.customTitle')}</h2>
        <p>{t('demo.customText')}</p>
        <Button href={href('/mission-planner', customSite.id)} size="lg">{t('demo.openPlanner')}</Button>
      </li>
    </ol>

    <section class="next panel" aria-labelledby="demo-compare-title">
      <h2 id="demo-compare-title">{t('demo.compareTitle')}</h2>
      <p>{t('demo.compareText')}</p>
      <Button href={href('/siti', 'malapert-massif')} variant="ghost">{t('demo.openCompare')}</Button>
    </section>
  </div>
</div>

<style>
  .demo { padding-block: var(--space-7); }
  .intro { max-width: 46rem; margin-bottom: var(--space-6); }
  .eyebrow, .step-number { color: var(--c-accent); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  h1 { margin-bottom: var(--space-2); }
  .lead { color: var(--c-muted); font-size: var(--fs-large); }
  .steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); padding: 0; list-style: none; }
  .panel { padding: var(--space-5); }
  .steps h2 { margin: var(--space-2) 0; }
  .steps p { min-height: 5rem; color: var(--c-muted); }
  .next { margin-top: var(--space-5); }
  @media (max-width: 800px) { .steps { grid-template-columns: 1fr; } .steps p { min-height: 0; } }
</style>
