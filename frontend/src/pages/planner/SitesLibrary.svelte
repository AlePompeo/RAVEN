<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t, type MessageKey } from '../../i18n/i18n.svelte';
  import type { RavenSiteInfo } from '../../shell/ravenApi';
  let { sites }: { sites: readonly RavenSiteInfo[] } = $props();
  const descriptions: Record<string, MessageKey> = {
    apollo11: 'sitesLibrary.apollo11', apollo17: 'sitesLibrary.apollo17',
    'malapert-massif': 'sitesLibrary.massif', 'mons-mouton': 'sitesLibrary.massif',
    haworth: 'sitesLibrary.crater', 'nobile-rim': 'sitesLibrary.crater',
    'de-gerlache': 'sitesLibrary.crater', shackleton: 'sitesLibrary.shackleton',
  };
</script>

<details class="sites-library" data-testid="planner-sites-library">
  <summary>{t('sitesLibrary.title')}</summary>
  <p>{t('sitesLibrary.intro')}</p>
  <p class="note">{t('sitesLibrary.coordinates')}</p>
  <div class="library-grid">
    {#each sites as site (site.id)}
      <article>
        <h3>{site.name}</h3>
        <p>{t(descriptions[site.id] ?? 'sitesLibrary.generic')}</p>
        <p>{site.lat_deg.toFixed(4)}°, {site.lon_deg_east.toFixed(4)}° E</p>
        <p>{t(site.coordinate_basis === 'feature_centre' ? 'sitesLibrary.featureCentre' : 'sitesLibrary.point')}</p>
        {#if site.source_url}<a href={site.source_url} target="_blank" rel="noopener noreferrer">{t('sitesLibrary.source')}</a>{/if}
      </article>
    {/each}
  </div>
</details>

<style>
  .sites-library { margin-block: 1.5rem; border: 1px solid var(--c-hairline); border-radius: 1rem; padding: 1rem; }
  summary { cursor: pointer; font-weight: 600; min-height: var(--target); padding-block: .6rem; }
  p { max-inline-size: 75ch; line-height: 1.65; color: var(--c-muted); }
  .note { border-inline-start: 3px solid var(--c-uplink); padding-inline-start: 1rem; }
  .library-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1rem; }
  article { min-width: 0; border: 1px solid var(--c-hairline); border-radius: .75rem; padding: 1rem; overflow-wrap: anywhere; }
  h3 { font-size: var(--fs-h3); }
  a { display: inline-flex; align-items: center; min-height: var(--target); }
</style>
