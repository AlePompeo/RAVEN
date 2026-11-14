<!-- SPDX-License-Identifier: Apache-2.0 -->
<script lang="ts">
  import { withBase } from '../../shell/router';
  import { t } from '../../i18n/i18n.svelte';

  let { base = import.meta.env.BASE_URL }: { base?: string } = $props();
</script>

<div class="doc tile">
  <div class="container">
    <h1>{t('shell.notFoundTitle')}</h1>
    <p>{t('shell.notFoundText')} <a href={withBase('/', base)}>{t('shell.backHome')}</a>{t('shell.sentenceEnd')}</p>
  </div>
</div>
