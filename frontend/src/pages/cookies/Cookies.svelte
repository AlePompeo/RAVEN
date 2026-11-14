<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';
  import ConsentSettings from '../../shell/ConsentSettings.svelte';

  const localRows = [
    ['consent.v1', 'trust.storage.consent'],
    ['hb.mode / hb.lang', 'trust.storage.preferences'],
    ['hb.mission-planner.library.v1', 'trust.storage.library'],
    ['hb.planner-journey.history.v1', 'trust.storage.history'],
  ] as const;
  const sessionRows = [
    ['hb.scenario', 'trust.storage.scenario'],
    ['hb.planner-journey.v1 / hb.planner-journey.run.v1', 'trust.storage.journey'],
    ['hb.mission-planner / hb.mission-timeline.v1 / hb.mission-analyses.v1', 'trust.storage.legacy'],
  ] as const;
  const groups = [
    { rows: localRows, title: 'trust.storage.local' },
    { rows: sessionRows, title: 'trust.storage.session' },
  ] as const;
  const link = (path: string) => withBase(path, import.meta.env.BASE_URL);
</script>

<div class="doc tile">
  <div class="container">
    <h1>{t('title.cookies')}</h1>
    <p>{t('trust.cookies.intro')}</p>
    <h2>{t('trust.cookies.title')}</h2>
    <p>{t('trust.cookies.default')}</p>
    {#each groups as group}
      <h2>{t(group.title)}</h2>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label={t(group.title)}>
        <table>
          <caption>{t(group.title)}</caption>
          <thead><tr><th scope="col">{t('trust.storage.key')}</th><th scope="col">{t('trust.storage.purpose')}</th></tr></thead>
          <tbody>{#each group.rows as [key, purpose] (key)}<tr><th scope="row"><code>{key}</code></th><td>{t(purpose)}</td></tr>{/each}</tbody>
        </table>
      </div>
    {/each}
    <p>{t('trust.storage.lifetime')}</p>
    <h2>{t('trust.storage.backupTitle')}</h2>
    <p>{t('trust.storage.backup')}</p>
    <p><a href={link('/dashboard')}>{t('trust.history.link')}</a> · <a href={link('/mission-planner')}>{t('trust.planner.link')}</a></p>
    <h2>{t('trust.cookies.scriptsTitle')}</h2>
    <p>{t('trust.cookies.scripts')}</p>
    <p>{t('trust.cookies.scope')}</p>
    <ConsentSettings />
    <p><a href={link('/privacy')}>{t('title.privacy')}</a></p>
  </div>
</div>
