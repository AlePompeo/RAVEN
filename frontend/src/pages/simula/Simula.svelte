<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Simula: scena didattica o sito reale nella stessa vista, e simulazione dell'onda.
-->
<script lang="ts">
  import Hub from '../../shell/Hub.svelte';
  import type { HubTab } from '../../shell/hub';

  /** Stringhe della pagina (chiavi stabili, i18n in arrivo). */
  const STR = {
    title: 'Simula',
    tabs: 'Viste della simulazione',
    scena: 'Scena',
    scenaTitle: 'Simulatore',
    onda: 'L’onda',
    ondaTitle: 'Onda 3D',
    failed: 'Impossibile caricare la scheda. Controlla la connessione e ricarica la pagina.',
  } as const;

  const tabs: HubTab[] = [
    { id: 'scena', label: STR.scena, title: STR.scenaTitle, load: () => import('./UnifiedScene.svelte') },
    { id: 'onda', label: STR.onda, title: STR.ondaTitle, load: () => import('../wave/Wave.svelte') },
  ];
</script>

<Hub title={STR.title} label={STR.tabs} {tabs} loading={STR.failed} />
