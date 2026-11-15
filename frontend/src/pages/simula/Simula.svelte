<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Simula: scena didattica o sito reale nella stessa vista, e simulazione dell'onda.
-->
<script lang="ts">
  import Hub from '../../shell/Hub.svelte';
  import type { HubTab } from '../../shell/hub';
  import { t } from '../../i18n/i18n.svelte';

  const STR = $derived({
    title: t('simula.page.title'),
    tabs: t('simula.page.tabs'),
    scena: t('simula.page.scene'),
    scenaTitle: t('simula.page.sceneTitle'),
    onda: t('simula.page.wave'),
    ondaTitle: t('simula.page.waveTitle'),
    failed: t('simula.page.failed'),
  });

  const tabs: HubTab[] = $derived([
    { id: 'scena', label: STR.scena, title: STR.scenaTitle, load: () => import('./UnifiedScene.svelte') },
    { id: 'onda', label: STR.onda, title: STR.ondaTitle, load: () => import('../wave/Wave.svelte') },
  ]);
</script>

<Hub title={STR.title} label={STR.tabs} {tabs} loading={STR.failed} />
