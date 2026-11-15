<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Vista unificata e schede precedenti, accessibili anche tramite le vecchie rotte. -->
<script lang="ts">
  import Hub from '../../shell/Hub.svelte';
  import type { HubTab } from '../../shell/hub';
  import { t } from '../../i18n/i18n.svelte';

  const STR = $derived({
    title: t('sites.pageTitle'),
    tabs: t('sites.pageTabs'),
    failed: t('sites.pageFailed'),
  });

  const tabs: HubTab[] = $derived([
    { id: 'insieme', label: t('sites.combined'), title: t('sites.combined'), header: true, learn: t('sites.combinedHelp'), load: () => import('./SitiCombined.svelte') },
  ]);
</script>

<Hub title={STR.title} label={STR.tabs} {tabs} loading={STR.failed} />
