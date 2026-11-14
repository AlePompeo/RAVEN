<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';

  const rows = ['requests', 'saved', 'chat', 'external'] as const;
  const link = (path: string) => withBase(path, import.meta.env.BASE_URL);
</script>

<div class="doc tile">
  <div class="container">
    <h1>{t('title.privacy')}</h1>
    <p class="lead">{t('trust.privacy.intro')}</p>
    <aside aria-label={t('trust.readiness.title')}>
      <h2>{t('trust.readiness.title')}</h2>
      <p>{t('trust.readiness.privacy')}</p>
    </aside>
    <h2>{t('trust.privacy.flows')}</h2>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div class="table-scroll" tabindex="0" role="region" aria-label={t('trust.privacy.flows')}>
      <table>
        <caption>{t('trust.privacy.flows')}</caption>
        <thead><tr><th scope="col">{t('trust.activity')}</th><th scope="col">{t('trust.data')}</th></tr></thead>
        <tbody>
          {#each rows as row (row)}
            <tr><th scope="row">{t(`trust.privacy.${row}.title`)}</th><td>{t(`trust.privacy.${row}.body`)}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
    <h2>{t('trust.privacy.logsTitle')}</h2>
    <p>{t('trust.privacy.logs')}</p>
    <h2>{t('trust.privacy.controlTitle')}</h2>
    <p>{t('trust.privacy.control')}</p>
    <p><a href={link('/cookies')}>{t('trust.storage.link')}</a> · <a href={link('/dashboard')}>{t('trust.history.link')}</a></p>
    <h2>{t('trust.privacy.rightsTitle')}</h2>
    <p>{t('trust.privacy.rights')}</p>
    <p><a href={link('/contacts')}>{t('trust.support.link')}</a> · <a href={link('/terms')}>{t('title.terms')}</a></p>
  </div>
</div>
