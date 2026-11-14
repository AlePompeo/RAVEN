<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { t } from '../../i18n/i18n.svelte';
  import { withBase } from '../../shell/router';
  const sections = ['scope', 'evidence', 'commercial', 'data', 'licence'] as const;
  const link = (path: string) => withBase(path, import.meta.env.BASE_URL);
</script>

<div class="doc tile">
  <div class="container">
    <h1>{t('title.terms')}</h1>
    <p class="lead">{t('trust.terms.intro')}</p>
    {#each sections as section (section)}
      <h2>{t(`trust.terms.${section}.title`)}</h2>
      <p>{t(`trust.terms.${section}.body`)}</p>
    {/each}
    <p><a href={link('/model')}>{t('title.model')}</a> · <a href={link('/licenses')}>{t('title.licenses')}</a></p>
    <p><a href={link('/privacy')}>{t('title.privacy')}</a> · <a href={link('/contacts')}>{t('trust.support.link')}</a></p>
  </div>
</div>
